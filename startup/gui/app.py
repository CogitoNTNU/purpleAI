"""PurpleAI Control — a clickable GUI to start/stop the attacker, defender and
vulnerable app on the remote lab boxes, with live logs shown in-window.

Connection path (no terminal needed):
    this PC --ssh--> gamehost --ssh--> redai (attacker) / blueai (defender)

The ssh host aliases (gamehost/redai/blueai) and the repo path live in CONFIG
below — edit them if yours differ. Requires key-based ssh (no password prompts),
since this GUI runs ssh non-interactively.
"""
from __future__ import annotations

import json
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

try:  # the Cogito logo, base64-embedded so it bundles into the exe
    from logo_data import LOGO_PNG_B64
except Exception:  # noqa: BLE001  (logo is cosmetic)
    LOGO_PNG_B64 = None

# --------------------------------------------------------------------------- #
# CONFIG — edit to match your setup                                           #
# --------------------------------------------------------------------------- #
GAMEHOST = "gamehost"          # ssh alias of the jump host (reached from this PC)
REPO = "~/purpleAI"            # repo path on redai and blueai


# Picks how to call docker: plain `docker` if the socket is reachable,
# passwordless `sudo -n docker` if that's allowed, otherwise a clear one-time-fix
# message. `sudo -n` never prompts — it fails fast instead of hanging.
# Only double quotes here; single quotes would clash with the `ssh host '...'`
# wrapper.
_DOCKER_PICK = (
    "if docker info >/dev/null 2>&1; then DC=docker; "
    'elif sudo -n docker info >/dev/null 2>&1; then DC="sudo -n docker"; '
    'else echo "ERROR: this user cannot access Docker on this box."; '
    'echo "One-time fix:  sudo usermod -aG docker $(whoami)  then log out and back in."; '
    "exit 13; fi"
)


def _dc(compose: str, action: str) -> str:
    """A single docker-compose action (stop/logs/status) on one compose file."""
    return f"cd {REPO}/src/defender && {_DOCKER_PICK} && $DC compose -f {compose} {action}"


def docker_start(target: str, other: str) -> str:
    """Start `target`, first bringing `other` down so the two compose files
    don't fight over port 8080 / the `vulnerable-app` container name."""
    return (
        f"cd {REPO}/src/defender && {_DOCKER_PICK} && "
        f"$DC compose -f {other} down --remove-orphans; "
        f"$DC compose -f {target} up -d --build --remove-orphans"
    )


def with_pull(cmd: str) -> str:
    """Pull the latest main on the remote before running `cmd`. Uses `;` so a
    pull hiccup (no network, non-fast-forward) is reported but doesn't block
    the start."""
    return f"cd {REPO} && git pull --ff-only origin main; {cmd}"


# The attacker has a multi-step launch (tmux + venv). Rather than require these
# scripts to already be on redai, the GUI ships them over ssh via `bash -s` on
# stdin, so the box only needs the repo itself — not these helper files.
ATTACKER_START_SH = r"""
set -euo pipefail
REPO="${PURPLE_REPO:-$HOME/purpleAI}"
ATT="$REPO/src/Attacker"
SESSION="attacker"
LOGDIR="$REPO/startup/logs"
LOG="$LOGDIR/attacker.log"
mkdir -p "$LOGDIR"

# Pull latest main first (non-fatal if it can't fast-forward).
( cd "$REPO" && git pull --ff-only origin main ) || echo "[attacker] git pull skipped/failed."

if ! command -v tmux >/dev/null 2>&1; then
  echo "[attacker] installing tmux..."
  sudo -n apt-get update -y && sudo -n apt-get install -y tmux \
    || { echo "ERROR: tmux missing and cannot sudo-install it. Run: sudo apt-get install -y tmux"; exit 1; }
fi

# Always restart clean: end any existing attacker before starting a new one.
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[attacker] ending existing attacker session before restart..."
  tmux kill-session -t "$SESSION" 2>/dev/null || true
fi
pkill -f 'langgraph dev' 2>/dev/null || true
pkill -f 'redagent.py'   2>/dev/null || true
sleep 1

[ -d "$ATT" ] || { echo "ERROR: $ATT not found." >&2; exit 1; }

# Fresh state each run so earlier runs' tasks don't carry over into the UI or
# keep draining the single worker:
#  - rotate events.jsonl (the GUI tails it; it otherwise accumulates across runs)
#  - wipe .langgraph_api (the dev server persists subagent threads/runs to disk)
mkdir -p "$ATT/logs"
[ -s "$ATT/logs/events.jsonl" ] && mv -f "$ATT/logs/events.jsonl" "$ATT/logs/events.prev.jsonl" 2>/dev/null || true
rm -rf "$ATT/.langgraph_api" 2>/dev/null || true
echo "[attacker] cleared previous run state (events rotated, server threads wiped)."

if [ ! -x "$ATT/.venv/bin/langgraph" ]; then
  echo "[attacker] .venv not set up; bootstrapping with uv..."
  if command -v uv >/dev/null 2>&1; then
    ( cd "$ATT" && uv venv && uv pip install --python .venv/bin/python -r requirements.txt )
  else
    echo "ERROR: no .venv and uv missing; see $ATT/README.md" >&2; exit 1
  fi
fi

: > "$LOG"
START_DELAY="${PURPLE_ATTACKER_DELAY:-10}"
tmux new-session -d -s "$SESSION" -c "$ATT"
tmux pipe-pane -o -t "$SESSION" "cat >> '$LOG'"
# 1) Start the subagent server (langgraph dev) in the background, own log.
#    --no-browser: on a headless box, opening LangGraph Studio launches a
#      text-mode browser that grabs the tmux pane's tty and suspends the server.
#    --no-reload: the attacker writes its event log and scan reports INSIDE the
#      watched project tree; with auto-reload on, every write reloads the dev
#      server and interrupts the one worker, so subagent runs stick at "pending"
#      forever and the Boss never advances past iteration 0.
#    --n-jobs-per-worker: run subagent scans concurrently (SQLi/XSS/SSTI at
#      once) rather than serialised.
tmux send-keys -t "$SESSION" "BROWSER=true .venv/bin/langgraph dev --no-browser --no-reload --n-jobs-per-worker 10 > '$LOGDIR/langgraph.log' 2>&1 &" C-m
# 2) Give it time to boot (and you a chance to open the Server log) before Boss.
tmux send-keys -t "$SESSION" "echo 'subagent server starting on :2024 (log: $LOGDIR/langgraph.log)'; echo 'open the Server log to watch it; Boss starts in ${START_DELAY}s...'; sleep ${START_DELAY}" C-m
# 3) Then wait (bounded, ~60s) until it actually answers before starting Boss.
tmux send-keys -t "$SESSION" "n=0; until curl -s http://localhost:2024/ok >/dev/null 2>&1 || curl -s http://localhost:2024/ >/dev/null 2>&1; do n=\$((n+1)); [ \$n -ge 30 ] && break; sleep 2; done" C-m
tmux send-keys -t "$SESSION" "if curl -s http://localhost:2024/ok >/dev/null 2>&1 || curl -s http://localhost:2024/ >/dev/null 2>&1; then echo 'server up; starting Boss'; else echo 'WARNING: server not responding on :2024 - check the Server log'; fi; .venv/bin/python redagent.py" C-m
echo "[attacker] started (detached). Server booting; Boss starts after ${START_DELAY}s. Logs -> $LOG"
"""

ATTACKER_STOP_SH = r"""
set -uo pipefail
SESSION="attacker"
tmux kill-session -t "$SESSION" 2>/dev/null && echo "killed tmux '$SESSION'" || echo "no tmux session '$SESSION'"
pkill -f 'langgraph dev' 2>/dev/null && echo "stopped langgraph server" || true
pkill -f 'redagent.py'   2>/dev/null && echo "stopped Boss" || true
echo "[attacker] stop done."
"""

# Dump each subagent thread's message trail (its reasoning) from the langgraph
# server as JSON lines. Shipped to redai via bash -s and run on each poll; the
# GUI dedupes by (tid, index) and maps tid -> subagent via subagent_status.
REASONING_SCRIPT = r"""
python3 - <<'PY'
import json, urllib.request
BASE = "http://localhost:2024"
def jget(u):
    return json.load(urllib.request.urlopen(u, timeout=6))
def jpost(u, d):
    req = urllib.request.Request(u, data=json.dumps(d).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=6))
try:
    ths = jpost(BASE + "/threads/search", {"limit": 40})
except Exception as e:
    print("REASON_ERR " + str(e)); raise SystemExit
for t in ths:
    tid = t.get("thread_id")
    if not tid:
        continue
    try:
        st = jget(BASE + "/threads/%s/state" % tid)
    except Exception:
        continue
    msgs = (st.get("values") or {}).get("messages") or []
    for i, m in enumerate(msgs):
        if not isinstance(m, dict):
            continue
        typ = m.get("type")
        if typ not in ("ai", "tool"):
            continue
        c = m.get("content")
        if isinstance(c, list):
            c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
        c = " ".join(str(c or "").split())
        tools = [tc.get("name") for tc in (m.get("tool_calls") or [])
                 if isinstance(tc, dict)]
        if not c and not tools:
            continue
        print(json.dumps({"tid": tid, "i": i, "type": typ,
                          "text": c[:500], "tools": tools}))
PY
"""


COMPONENTS = [
    {
        "key": "attacker",
        "label": "Attacker  (redai)",
        "host": "redai",
        "color": "#C0392B",
        "filterable": True,   # adds the "Reasoning only" checkbox (on by default)
        "show_flags": True,   # adds the "Flags captured" overview
        # Live panes side by side: Boss, SQL, Cross-site, SSTI.
        "panes": [
            {"key": "boss", "title": "Boss"},
            {"key": "sql", "title": "SQL  (sql_injection_agent)"},
            {"key": "xss", "title": "Cross-site  (xss_agent)"},
            {"key": "ssti", "title": "SSTI  (ssti_agent)"},
        ],
        # Subagents to show activity lights for; `tool` maps a tool event to its
        # subagent (sqlmap -> SQLi, xsser -> XSS, curl -> SSTI's ssti_scanner);
        # `pane` routes its output.
        "subagents": [
            {"name": "sql_injection_agent", "label": "SQLi", "tool": "sqlmap", "pane": "sql"},
            {"name": "xss_agent", "label": "XSS", "tool": "xsser", "pane": "xss"},
            {"name": "ssti_agent", "label": "SSTI", "tool": "curl", "pane": "ssti"},
        ],
        # Structured event log (both Boss and subagent server append here).
        "events": f"mkdir -p {REPO}/src/Attacker/logs "
                  f"&& touch {REPO}/src/Attacker/logs/events.jsonl "
                  f"&& tail -n 200 -F {REPO}/src/Attacker/logs/events.jsonl",
        # The subagent server's own stdout/stderr (why it did/didn't start).
        "server_logs": f"mkdir -p {REPO}/startup/logs "
                       f"&& touch {REPO}/startup/logs/langgraph.log "
                       f"&& tail -n 200 -F {REPO}/startup/logs/langgraph.log",
        # Subagent reasoning: pull each subagent thread's message trail from the
        # server (shipped via bash -s, so no quoting worries).
        "reasoning_script": REASONING_SCRIPT,
        # One-shot health probe of the subagent server (langgraph dev :2024),
        # polled on a timer. Prints "SERVER <http_code>" (000 = unreachable).
        "health": (
            'c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 4 '
            "http://localhost:2024/ok 2>/dev/null); "
            'if [ -z "$c" ] || [ "$c" = "000" ]; then '
            'c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 4 '
            "http://localhost:2024/ 2>/dev/null); fi; "
            'echo "SERVER $c"'
        ),
        "start": {"script": ATTACKER_START_SH, "desc": "pull main + start Boss/server in tmux"},
        "stop":  {"script": ATTACKER_STOP_SH, "desc": "stop attacker (kill tmux + procs)"},
        "logs":  f"mkdir -p {REPO}/startup/logs && touch {REPO}/startup/logs/attacker.log "
                 f"&& tail -n 300 -F {REPO}/startup/logs/attacker.log",
        "status": "tmux has-session -t attacker 2>/dev/null "
                  "&& echo RUNNING || echo STOPPED",
    },
    {
        "key": "defender",
        "label": "Defender + VulnApp  (blueai)",
        "host": "blueai",
        "color": "#2471A3",
        "counts_blue": True,  # blocked requests in its log = blue team score
        "start":  with_pull(docker_start("docker-compose.full.yml", "docker-compose.app.yml")),
        "stop":   _dc("docker-compose.full.yml", "down"),
        "logs":   _dc("docker-compose.full.yml", "logs -f --tail=300"),
        "status": _dc("docker-compose.full.yml", "ps"),
    },
    {
        "key": "vulnapp",
        "label": "Vulnerable app only  (blueai)",
        "host": "blueai",
        "color": "#7D3C98",
        "start":  with_pull(docker_start("docker-compose.app.yml", "docker-compose.full.yml")),
        "stop":   _dc("docker-compose.app.yml", "down"),
        "logs":   _dc("docker-compose.app.yml", "logs -f --tail=300"),
        "status": _dc("docker-compose.app.yml", "ps"),
    },
]

# Hide the console windows spawned by ssh.exe on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

# FLAG{...} values are the objective; harvest them from the attacker's stream.
FLAG_RE = re.compile(r"FLAG\{[^}\n]{0,200}\}")

# The flags planted in the vulnerable app (see
# src/defender/vulnerable-app/VULNERABILITIES.md). Each is a light that starts
# blue (defended) and turns red when the attacker captures it.
KNOWN_FLAGS = [
    ("FLAG{sql_login_bypass_success}", "SQL login bypass"),
    ("FLAG{sql_union_injection_found}", "SQL UNION"),
    ("FLAG{reflected_xss}", "Reflected XSS"),
    ("FLAG{stored_xss_dom}", "Stored XSS"),
    ("FLAG{server_side_template_injection}", "SSTI"),
    ("FLAG{broken_access_control_admin_panel}", "Admin access"),
    ("FLAG{path_traversal_outside_reports_dir}", "Path traversal"),
]

# --------------------------------------------------------------------------- #
# Theme                                                                       #
# --------------------------------------------------------------------------- #
PAL = {
    "bg": "#0d1117",       # app background
    "panel": "#161b22",    # cards
    "log": "#0b0e13",      # log/console background
    "border": "#30363d",
    "text": "#e6edf3",
    "muted": "#8b949e",
    "red": "#f85149",      # attacker / red team
    "blue": "#58a6ff",     # defender / blue team
    "green": "#3fb950",
    "amber": "#d29922",
    "accent": "#a371f7",   # purple
    "idle": "#30363d",
}


def apply_style(root: tk.Misc) -> None:
    """A dark, modern-ish ttk theme built on 'clam'."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    p = PAL
    style.configure(".", background=p["bg"], foreground=p["text"],
                    fieldbackground=p["panel"], bordercolor=p["border"],
                    focuscolor=p["accent"], font=("Segoe UI", 10))
    style.configure("TFrame", background=p["bg"])
    style.configure("Card.TFrame", background=p["panel"])
    style.configure("TLabel", background=p["bg"], foreground=p["text"])
    style.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"])
    style.configure("CardMuted.TLabel", background=p["panel"], foreground=p["muted"])
    style.configure("Card.TLabel", background=p["panel"], foreground=p["text"])
    style.configure("Title.TLabel", background=p["bg"], foreground=p["text"],
                    font=("Segoe UI Semibold", 16))
    style.configure("Score.TLabel", background=p["bg"], font=("Segoe UI", 9))
    style.configure("TLabelframe", background=p["panel"], bordercolor=p["border"],
                    relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=p["panel"],
                    foreground=p["muted"], font=("Segoe UI Semibold", 9))
    style.configure("TNotebook", background=p["bg"], borderwidth=0, tabmargins=(4, 4, 4, 0))
    style.configure("TNotebook.Tab", background=p["panel"], foreground=p["muted"],
                    padding=(14, 7), borderwidth=0, font=("Segoe UI", 10))
    style.map("TNotebook.Tab",
              background=[("selected", p["bg"])],
              foreground=[("selected", p["text"])])
    style.configure("TButton", background=p["panel"], foreground=p["text"],
                    bordercolor=p["border"], borderwidth=1, focusthickness=0,
                    padding=(9, 5), relief="flat")
    style.map("TButton",
              background=[("active", "#21262d"), ("pressed", "#21262d")],
              bordercolor=[("active", p["accent"])])
    style.configure("Accent.TButton", background=p["accent"], foreground="#0d1117",
                    bordercolor=p["accent"])
    style.map("Accent.TButton", background=[("active", "#b586f9")])
    style.configure("TCheckbutton", background=p["bg"], foreground=p["muted"])
    style.map("TCheckbutton", foreground=[("selected", p["text"])])


def ssh_inline_argv(host: str, remote_cmd: str) -> list[str]:
    """argv for: ssh GAMEHOST "ssh HOST 'remote_cmd'". remote_cmd must not use
    single quotes (they'd clash with the wrapper); use double quotes instead."""
    return ["ssh", GAMEHOST, f"ssh {host} '{remote_cmd}'"]


def ssh_script_argv(host: str) -> list[str]:
    """argv for: ssh GAMEHOST "ssh HOST bash -s"  — the script is fed on stdin,
    so it can use any quoting and need not exist on the remote."""
    return ["ssh", GAMEHOST, f"ssh {host} bash -s"]


class Proc:
    """Runs one argv, streaming combined stdout/stderr line-by-line to a queue."""

    def __init__(self, argv: list[str], out_q: "queue.Queue[tuple]",
                 stdin_data: str | None = None, role: str = "action"):
        self.argv = argv
        self.q = out_q
        self.stdin_data = stdin_data
        self.role = role  # "action" (start/stop/status) or "logs" (live stream)
        self.popen: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self.popen = subprocess.Popen(
                self.argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=(subprocess.PIPE if self.stdin_data is not None
                       else subprocess.DEVNULL),
                text=True,
                bufsize=1,
                creationflags=_NO_WINDOW,
            )
        except Exception as exc:  # noqa: BLE001
            self.q.put(("line", self.role, f"!! failed to launch ssh: {exc}\n"))
            self.q.put(("exit", self.role, -1))
            return
        if self.stdin_data is not None and self.popen.stdin is not None:
            try:
                # Normalize to LF — bash on the Linux remote fails on CRLF with
                # "$'\r': command not found". In text mode Windows would re-add
                # CRLF on write, so disable newline translation first.
                data = self.stdin_data.replace("\r\n", "\n").replace("\r", "\n")
                try:
                    self.popen.stdin.reconfigure(newline="")
                except Exception:  # noqa: BLE001
                    pass
                self.popen.stdin.write(data)
                self.popen.stdin.close()
            except Exception as exc:  # noqa: BLE001
                self.q.put(("line", self.role, f"!! stdin write failed: {exc}\n"))
        assert self.popen.stdout is not None
        for line in self.popen.stdout:
            self.q.put(("line", self.role, line))
        code = self.popen.wait()
        self.q.put(("exit", self.role, code))

    def is_running(self) -> bool:
        return self.popen is not None and self.popen.poll() is None

    def kill(self):
        if self.is_running():
            try:
                self.popen.terminate()
            except Exception:  # noqa: BLE001
                pass


class ComponentTab(ttk.Frame):
    def __init__(self, master: tk.Misc, cfg: dict, app=None):
        super().__init__(master, padding=8)
        self.cfg = cfg
        self.app = app  # for the Red-vs-Blue scoreboard
        self._blue = 0  # defender: requests blocked (blue score)
        self._blue_seen: set = set()
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.log_proc: Proc | None = None   # the long-lived `logs -f` stream
        self.events_proc: Proc | None = None  # the events.jsonl stream (attacker)
        self.serverlog_proc: Proc | None = None  # langgraph server log stream
        self.health_proc: Proc | None = None  # one-shot server health probe
        self._health_after = None             # pending health-poll timer id
        self.reason_proc: Proc | None = None  # subagent-reasoning poll
        self._reason_after = None             # pending reasoning-poll timer id
        self._reason_on = False               # reasoning stream toggled on?
        self._seen_msgs: set = set()          # (tid, i) already shown
        self.tid_label: dict = {}             # thread id -> subagent label
        self.action_proc: Proc | None = None  # one-shot start/stop/status
        self.lights: dict = {}  # subagent name AND tool -> light entry
        # "Reasoning only" filter (attacker): show iteration headers + the
        # Boss's [node] reasoning + flags; hide tool-call/result chatter.
        self.reasoning_only = tk.BooleanVar(value=bool(cfg.get("filterable")))
        self._show_block = False  # filter state: are we inside a shown block?
        self.flags: set[str] = set()  # unique FLAG{...} seen on this box
        self.flag_lights: dict = {}  # flag string -> {canvas, oval, label}
        self.sub_tasks: dict = {}  # subagent name -> {task_id: status}
        self.panes: dict = {}  # pane key -> ScrolledText (multi-pane mode)
        # Route a subagent name / tool / label to its pane key.
        self.pane_for: dict = {}
        for sa in cfg.get("subagents", []):
            if sa.get("pane"):
                for k in (sa["name"], sa["tool"], sa["label"]):
                    self.pane_for[k] = sa["pane"]

        def _text(parent, **kw):
            t = ScrolledText(parent, bg=PAL["log"], fg=PAL["text"],
                             insertbackground=PAL["text"], font=("Consolas", 10),
                             state="disabled", relief="flat", borderwidth=0,
                             highlightthickness=1, highlightbackground=PAL["border"],
                             selectbackground="#264f78", padx=8, pady=6, **kw)
            return t

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))

        dot = tk.Canvas(bar, width=14, height=14, highlightthickness=0, bg=PAL["bg"])
        dot.pack(side="left", padx=(0, 6))
        self._dot = dot.create_oval(2, 2, 12, 12, fill=PAL["muted"], outline="")
        self._dot_canvas = dot

        self.status_var = tk.StringVar(value="idle")
        ttk.Label(bar, textvariable=self.status_var, width=15,
                  style="Muted.TLabel").pack(side="left", padx=(0, 6))

        ttk.Button(bar, text="▶ Start", command=self.on_start,
                   style="Accent.TButton").pack(side="left", padx=2)
        ttk.Button(bar, text="■ Stop", command=self.on_stop).pack(side="left", padx=2)
        ttk.Button(bar, text="📜 Logs", command=self.start_logs).pack(side="left", padx=2)
        if cfg.get("server_logs"):
            ttk.Button(bar, text="📄 Server log",
                       command=self.toggle_server_log).pack(side="left", padx=2)
        if cfg.get("reasoning_script"):
            ttk.Button(bar, text="🧠 Reasoning",
                       command=self.toggle_reasoning).pack(side="left", padx=2)
        ttk.Button(bar, text="⟳ Status", command=self.on_status).pack(side="left", padx=2)
        ttk.Button(bar, text="Clear", command=self.clear_log).pack(side="left", padx=2)
        if cfg.get("filterable"):
            ttk.Checkbutton(bar, text="Reasoning only",
                            variable=self.reasoning_only).pack(side="left", padx=(10, 2))

        # Subagent activity lights (attacker): green while that subagent / its
        # tool is running, grey when idle.
        if cfg.get("subagents"):
            sframe = ttk.LabelFrame(self, text=" SUBAGENTS ")
            sframe.pack(fill="x", pady=(0, 8))
            inner = ttk.Frame(sframe, style="Card.TFrame")
            inner.pack(fill="x", padx=8, pady=8)

            def _light_cell(label, status_init, label_w, status_w):
                cell = ttk.Frame(inner, style="Card.TFrame")
                cell.pack(side="left", padx=(0, 22))
                c = tk.Canvas(cell, width=14, height=14, highlightthickness=0,
                              bg=PAL["panel"])
                c.pack(side="left", padx=(0, 7))
                oval = c.create_oval(2, 2, 12, 12, fill=PAL["idle"], outline="")
                ttk.Label(cell, text=label, width=label_w,
                          style="Card.TLabel").pack(side="left")
                sv = tk.StringVar(value=status_init)
                ttk.Label(cell, textvariable=sv, width=status_w,
                          style="CardMuted.TLabel").pack(side="left")
                return {"canvas": c, "oval": oval, "status": sv, "label": label}

            if cfg.get("health"):
                self.lights["server"] = _light_cell("Server", "?", 6, 14)
            for sa in cfg["subagents"]:
                entry = _light_cell(sa["label"], "idle", 5, 24)
                self.lights[sa["name"]] = entry
                self.lights[sa["tool"]] = entry  # same light, keyed by tool too

        # Flags overview (attacker): one light per planted flag. Blue =
        # defended/uncaptured, red = the attacker has captured it.
        if cfg.get("show_flags"):
            self.flags_frame = ttk.LabelFrame(
                self, text=f" 🚩 FLAGS  (0 / {len(KNOWN_FLAGS)} captured) ")
            self.flags_frame.pack(fill="x", pady=(0, 8))
            grid = ttk.Frame(self.flags_frame, style="Card.TFrame")
            grid.pack(fill="x", padx=8, pady=8)
            cols = 4
            for idx, (flag, label) in enumerate(KNOWN_FLAGS):
                cell = ttk.Frame(grid, style="Card.TFrame")
                cell.grid(row=idx // cols, column=idx % cols, sticky="w",
                          padx=(0, 20), pady=3)
                cv = tk.Canvas(cell, width=14, height=14, highlightthickness=0,
                               bg=PAL["panel"])
                cv.pack(side="left", padx=(0, 7))
                oval = cv.create_oval(2, 2, 12, 12, fill=PAL["blue"], outline="")
                lbl = tk.Label(cell, text=label, bg=PAL["panel"], fg=PAL["muted"],
                               font=("Segoe UI", 9))
                lbl.pack(side="left")
                self.flag_lights[flag] = {"canvas": cv, "oval": oval, "label": lbl}

        if cfg.get("panes"):
            # Live panes side by side (resizable).
            pw = ttk.PanedWindow(self, orient="horizontal")
            pw.pack(fill="both", expand=True)
            for p in cfg["panes"]:
                frame = ttk.LabelFrame(pw, text=f" {p['title']} ")
                txt = _text(frame, height=18, width=28, wrap="word")
                txt.pack(fill="both", expand=True, padx=2, pady=2)
                pw.add(frame, weight=1)
                self.panes[p["key"]] = txt
            # Default target for undirected output is the first pane (Boss).
            self.log = self.panes[cfg["panes"][0]["key"]]
        else:
            self.log = _text(self, height=18, wrap="none")
            self.log.pack(fill="both", expand=True)

        self.after(100, self._drain)

    # -- UI helpers --------------------------------------------------------- #
    def set_dot(self, color: str):
        self._dot_canvas.itemconfig(self._dot, fill=color)

    def append(self, text: str, pane: str = "boss"):
        w = self.panes.get(pane) if self.panes else None
        w = w or self.log
        w.configure(state="normal")
        w.insert("end", text)
        w.see("end")
        w.configure(state="disabled")

    def clear_log(self):
        widgets = list(self.panes.values()) or [self.log]
        for w in widgets:
            w.configure(state="normal")
            w.delete("1.0", "end")
            w.configure(state="disabled")

    def _update_flag_title(self):
        known = len(self.flag_lights)
        cap = sum(1 for f in self.flag_lights if f in self.flags)
        self.flags_frame.configure(text=f" 🚩 FLAGS  ({cap} / {known} captured) ")

    def clear_flags(self):
        if not self.cfg.get("show_flags"):
            return
        self.flags.clear()
        for e in self.flag_lights.values():
            e["canvas"].itemconfig(e["oval"], fill=PAL["blue"])
            e["label"].configure(fg=PAL["muted"])
        self._update_flag_title()
        if self.app:
            self.app.set_red(0)

    def _add_flag(self, flag: str):
        if not self.cfg.get("show_flags") or not flag or flag in self.flags:
            return
        self.flags.add(flag)
        entry = self.flag_lights.get(flag)
        if entry:  # a known planted flag: blue -> red
            entry["canvas"].itemconfig(entry["oval"], fill=PAL["red"])
            entry["label"].configure(fg=PAL["red"])
        self._update_flag_title()
        if self.app:
            self.app.set_red(len(self.flags))

    def _count_blue(self, line: str):
        """Defender: count blocked requests (blue score) from its log stream."""
        if '"request_decision"' not in line or '"blocked"' not in line:
            return
        m = re.search(r'"event_id":\s*"([^"]+)"', line)
        eid = m.group(1) if m else line
        if eid in self._blue_seen:
            return
        self._blue_seen.add(eid)
        self._blue += 1
        if self.app:
            self.app.set_blue(self._blue)

    def _harvest_flags(self, text: str):
        """Pull any new FLAG{...} out of a streamed line into the overview."""
        for flag in FLAG_RE.findall(text):
            self._add_flag(flag)

    # -- subagent lights + event feed -------------------------------------- #
    def _set_light(self, key: str, on: bool, status: str | None = None,
                   color: str | None = None):
        entry = self.lights.get(key)
        if not entry:
            return
        fill = color or (PAL["green"] if on else PAL["idle"])
        entry["canvas"].itemconfig(entry["oval"], fill=fill)
        if status is not None:
            entry["status"].set(status)

    def _reset_lights(self):
        self.sub_tasks.clear()
        self.tid_label.clear()
        self._seen_msgs.clear()
        for entry in self.lights.values():
            entry["canvas"].itemconfig(entry["oval"], fill=PAL["idle"])
            entry["status"].set("idle")

    def _label_for(self, key: str) -> str:
        entry = self.lights.get(key)
        return entry["label"] if entry else (key or "sub")

    def _handle_event(self, ev: dict):
        """Turn one events.jsonl record into a light update + a readable line."""
        action = ev.get("action")
        tool = ev.get("tool")
        sub = ev.get("subagent")
        if action == "subagent_status" and sub:
            tid = ev.get("task_id")
            status = ev.get("status") or ""
            tasks = self.sub_tasks.setdefault(sub, {})
            is_new = tid is not None and tid not in tasks
            if tid is not None:
                tasks[tid] = status
                self.tid_label[tid] = self._label_for(sub)
            running = sum(1 for s in tasks.values() if s in ("running", "busy"))
            queued = sum(1 for s in tasks.values() if s == "pending")
            total = len(tasks)
            # Server has 1 worker: green while one truly runs, amber if only
            # queued work is waiting, grey when nothing is outstanding.
            color = PAL["green"] if running else (PAL["amber"] if queued else PAL["idle"])
            self._set_light(sub, running > 0,
                            f"{running} running / {queued} queued / {total} launched",
                            color=color)
            if is_new:
                self.append(f"  ➕ launched scan (#{total}, task {str(tid)[:8]})\n",
                            pane=self.pane_for.get(sub, "boss"))
        elif action == "tool_call" and tool:
            opts = " ".join(ev.get("scan_options") or [])
            self._set_light(tool, True)  # blip on; subagent_status owns the text
            self.append(f"  ▶ {tool} {opts}".rstrip() + "\n",
                        pane=self.pane_for.get(tool, "boss"))
        elif action == "tool_result" and tool:
            st = ev.get("status") or "done"
            dur = ev.get("duration_ms")
            mark = "✓" if st == "completed" else "✗"
            tail = f" ({dur} ms)" if dur is not None else ""
            self.append(f"  {mark} {tool} {st}{tail}\n",
                        pane=self.pane_for.get(tool, "boss"))
        elif action == "flag_captured":
            flag = ev.get("flag")
            self._add_flag(flag)
            self.append(f"  🚩 {flag}\n", pane=self.pane_for.get(tool, "boss"))

    def _handle_health(self, line: str):
        """Parse a 'SERVER <code>' health line and colour the Server light."""
        entry = self.lights.get("server")
        if not entry or "SERVER" not in line:
            return
        code = line.split("SERVER", 1)[1].strip() or "000"
        up = code not in ("", "000")
        entry["canvas"].itemconfig(entry["oval"], fill=PAL["green"] if up else PAL["red"])
        entry["status"].set(f"connected ({code})" if up else "down (:2024)")

    def _poll_health(self):
        """Fire a one-shot health probe, then reschedule while streaming."""
        if not self.cfg.get("health"):
            return
        if not (self.health_proc and self.health_proc.is_running()):
            self.health_proc = Proc(ssh_inline_argv(self.cfg["host"], self.cfg["health"]),
                                    self.q, role="health")
            self.health_proc.start()
        self._health_after = self.after(8000, self._poll_health)

    def toggle_reasoning(self):
        """Start/stop polling the server for subagent reasoning."""
        if self._reason_on:
            self._reason_on = False
            if self._reason_after is not None:
                self.after_cancel(self._reason_after)
                self._reason_after = None
            if self.reason_proc:
                self.reason_proc.kill()
                self.reason_proc = None
            self.append("--- subagent reasoning stream stopped ---\n")
        else:
            self._reason_on = True
            self.append("\n--- subagent reasoning (polling server threads) ---\n")
            self._poll_reasoning()

    def _poll_reasoning(self):
        if not self._reason_on:
            return
        if not (self.reason_proc and self.reason_proc.is_running()):
            self.reason_proc = Proc(ssh_script_argv(self.cfg["host"]), self.q,
                                    stdin_data=self.cfg["reasoning_script"],
                                    role="reasoning")
            self.reason_proc.start()
        self._reason_after = self.after(6000, self._poll_reasoning)

    def _handle_reasoning(self, line: str):
        line = line.strip()
        if line.startswith("REASON_ERR"):
            self.append("  [reason] " + line + "\n")
            return
        if not line.startswith("{"):
            return
        try:
            m = json.loads(line)
        except (ValueError, TypeError):
            return
        tid, i = m.get("tid"), m.get("i")
        key = (tid, i)
        if key in self._seen_msgs:
            return
        self._seen_msgs.add(key)
        label = self.tid_label.get(tid)
        if not label:
            return  # a thread not launched in this session; skip
        pane = self.pane_for.get(label, "boss")
        typ, text, tools = m.get("type"), m.get("text") or "", m.get("tools") or []
        if typ == "ai":
            if text:
                self.append(f"  🧠 {text}\n", pane=pane)
            if tools:
                self.append(f"  🧠 → {', '.join(tools)}\n", pane=pane)
        elif typ == "tool" and text:
            self.append(f"  ← {text[:200]}\n", pane=pane)

    def _on_event_line(self, line: str):
        """Parse one events.jsonl line (JSON) and dispatch it; ignore the rest."""
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            ev = json.loads(line)
        except (ValueError, TypeError):
            return
        if isinstance(ev, dict) and ev.get("action"):
            self._handle_event(ev)

    # -- actions ------------------------------------------------------------ #
    def _run_action(self, which: str):
        if self.action_proc and self.action_proc.is_running():
            self.append("… an action is already running; wait for it to finish.\n")
            return
        self.status_var.set(f"{which}…")
        self.set_dot(PAL["amber"])
        spec = self.cfg[which]
        host = self.cfg["host"]
        if isinstance(spec, dict) and "script" in spec:
            self.append(f"\n$ [{which}] ({spec.get('desc', 'run script')}) on {host}\n")
            proc = Proc(ssh_script_argv(host), self.q, stdin_data=spec["script"])
        else:
            self.append(f"\n$ [{which}] {spec}\n")
            proc = Proc(ssh_inline_argv(host, spec), self.q)
        proc._which = which  # type: ignore[attr-defined]
        self.action_proc = proc
        proc.start()

    def on_start(self):
        self.clear_flags()  # fresh run: reset the flags panel so re-finds show
        if self.cfg.get("counts_blue") and self.app:
            self._blue = 0
            self._blue_seen.clear()
            self.app.set_blue(0)
        self._run_action("start")

    def on_stop(self):
        self.stop_logs()
        self._run_action("stop")

    def on_status(self):
        self._run_action("status")

    def start_logs(self):
        self.stop_logs()
        self._show_block = False  # reset the reasoning filter for a fresh stream
        self._reset_lights()
        self.append(f"\n--- streaming logs ({self.cfg['host']}) ---\n")
        self.log_proc = Proc(ssh_inline_argv(self.cfg["host"], self.cfg["logs"]),
                             self.q, role="logs")
        self.log_proc.start()
        if self.cfg.get("events"):
            self.events_proc = Proc(ssh_inline_argv(self.cfg["host"], self.cfg["events"]),
                                    self.q, role="events")
            self.events_proc.start()
        if self.cfg.get("health"):
            if "server" in self.lights:
                self.lights["server"]["status"].set("checking…")
            self._poll_health()
        # Auto-start subagent reasoning so Boss/SQL/XSS panes are all live.
        if self.cfg.get("reasoning_script") and not self._reason_on:
            self._reason_on = True
            self._poll_reasoning()

    def toggle_server_log(self):
        """Start/stop streaming the subagent server's own log into the panel."""
        if self.serverlog_proc and self.serverlog_proc.is_running():
            self.serverlog_proc.kill()
            self.serverlog_proc = None
            self.append("--- server log stream stopped ---\n")
            return
        self.append("\n--- streaming SERVER log (langgraph dev) ---\n")
        self.serverlog_proc = Proc(ssh_inline_argv(self.cfg["host"], self.cfg["server_logs"]),
                                   self.q, role="serverlog")
        self.serverlog_proc.start()

    def stop_logs(self):
        if self.log_proc:
            self.log_proc.kill()
            self.log_proc = None
        if self.events_proc:
            self.events_proc.kill()
            self.events_proc = None
        if self.serverlog_proc:
            self.serverlog_proc.kill()
            self.serverlog_proc = None
        if self._health_after is not None:
            self.after_cancel(self._health_after)
            self._health_after = None
        if self.health_proc:
            self.health_proc.kill()
            self.health_proc = None
        self._reason_on = False
        if self._reason_after is not None:
            self.after_cancel(self._reason_after)
            self._reason_after = None
        if self.reason_proc:
            self.reason_proc.kill()
            self.reason_proc = None

    # -- reasoning-only filter --------------------------------------------- #
    # Boss output per turn:
    #   "===== iteration N ====="   -> boundary (show)
    #   "  [node] reasoning..."      -> reasoning (show; may wrap to more lines)
    #   "  -> tool(args)" / "  <- tool: result"  -> tool chatter (hide)
    #   "  🚩 CAPTURED FLAG: ..."    -> always show
    _RE_ITER = re.compile(r"^\s*=+\s*iteration\b", re.IGNORECASE)
    _RE_REASON = re.compile(r"^\s*\[")          # "  [node] ..."
    _RE_TOOL = re.compile(r"^\s*[→←>←<]")       # tool call "→"/">" or result "←"/"<"

    def _keep_line(self, line: str) -> bool:
        """Stateful filter: True to show this line, False to drop it."""
        if "🚩" in line or "CAPTURED FLAG" in line or "FLAG{" in line:
            return True
        if self._RE_ITER.match(line) or self._RE_REASON.match(line):
            self._show_block = True
            return True
        if self._RE_TOOL.match(line):
            self._show_block = False
            return False
        # Continuation / blank line: follow the current block's visibility.
        return self._show_block

    # -- queue pump --------------------------------------------------------- #
    def _drain(self):
        try:
            while True:
                kind, role, payload = self.q.get_nowait()
                if kind == "line":
                    if role == "health":
                        self._handle_health(payload)
                    elif role == "reasoning":
                        self._handle_reasoning(payload)
                    elif role == "serverlog":
                        self.append("[srv] " + payload)
                    elif role == "events":
                        self._on_event_line(payload)
                    elif role == "logs":
                        self._harvest_flags(payload)  # scan all log lines
                        if self.cfg.get("counts_blue"):
                            self._count_blue(payload)  # defender: blocked = blue
                        s = payload.strip()
                        if s.startswith("{") and '"action"' in s:
                            continue  # raw event JSON; shown via the events feed
                        if not self.reasoning_only.get() or self._keep_line(payload):
                            self.append(payload)
                    else:
                        self.append(payload)
                elif kind == "exit" and role == "action":
                    self._on_action_exit(payload)
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _on_action_exit(self, code):
        # Only react to the one-shot action process finishing.
        which = getattr(self.action_proc, "_which", None) if self.action_proc else None
        if which is None:
            return
        if self.action_proc and self.action_proc.is_running():
            return
        self.append(f"[{which} exited: {code}]\n")
        if which == "start":
            if code == 0:
                self.status_var.set("started")
                self.set_dot(PAL["green"])
                self.start_logs()  # auto-attach the live log stream
            else:
                self.status_var.set("start failed")
                self.set_dot(PAL["red"])
        elif which == "stop":
            self.status_var.set("stopped")
            self.set_dot(PAL["muted"])
        elif which == "status":
            self.status_var.set("status shown")
        self.action_proc = None

    def shutdown(self):
        self.stop_logs()
        if self.action_proc:
            self.action_proc.kill()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PurpleAI Control")
        self.geometry("1240x720")
        self.minsize(820, 520)
        self.configure(bg=PAL["bg"])
        apply_style(self)

        self.red_score = 0
        self.blue_score = 0

        # -- header: title + actions --------------------------------------- #
        header = ttk.Frame(self, padding=(14, 12, 14, 4))
        header.pack(fill="x")
        if LOGO_PNG_B64:
            try:
                img = tk.PhotoImage(data=LOGO_PNG_B64)
                factor = max(1, img.height() // 38)
                self._logo_img = img.subsample(factor, factor)
                tk.Label(header, image=self._logo_img, bg="#ffffff",
                         bd=0, padx=4, pady=2).pack(side="left", padx=(0, 10))
            except Exception:  # noqa: BLE001  (logo is cosmetic)
                pass
        ttk.Label(header, text="PurpleAI Control",
                  style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="■ Stop all", command=self.stop_all).pack(side="right", padx=3)
        ttk.Button(header, text="▶ Start all", command=self.start_all,
                   style="Accent.TButton").pack(side="right", padx=3)
        ttk.Label(header, text=f"via {GAMEHOST}",
                  style="Muted.TLabel").pack(side="right", padx=12)

        self._build_scoreboard()

        # -- tabs ----------------------------------------------------------- #
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.tabs: list[ComponentTab] = []
        for cfg in COMPONENTS:
            tab = ComponentTab(nb, cfg, app=self)
            nb.add(tab, text=cfg["label"])
            self.tabs.append(tab)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- Red vs Blue scoreboard -------------------------------------------- #
    def _build_scoreboard(self):
        card = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        card.pack(fill="x", padx=12, pady=(4, 0))

        self.red_var = tk.StringVar(value="0")
        self.blue_var = tk.StringVar(value="0")
        self.leader_var = tk.StringVar(value="RED 0  –  0 BLUE")

        # RED side
        left = ttk.Frame(card, style="Card.TFrame")
        left.pack(side="left")
        tk.Label(left, text="🔴 RED", bg=PAL["panel"], fg=PAL["red"],
                 font=("Segoe UI Semibold", 11)).pack(anchor="w")
        tk.Label(left, text="flags captured", bg=PAL["panel"], fg=PAL["muted"],
                 font=("Segoe UI", 8)).pack(anchor="w")
        self._red_num = tk.Label(card, textvariable=self.red_var, bg=PAL["panel"],
                                 fg=PAL["red"], font=("Segoe UI", 30, "bold"))
        self._red_num.pack(side="left", padx=(10, 20))

        # BLUE side (right-anchored)
        right = ttk.Frame(card, style="Card.TFrame")
        right.pack(side="right")
        tk.Label(right, text="BLUE 🔵", bg=PAL["panel"], fg=PAL["blue"],
                 font=("Segoe UI Semibold", 11)).pack(anchor="e")
        tk.Label(right, text="attacks blocked", bg=PAL["panel"], fg=PAL["muted"],
                 font=("Segoe UI", 8)).pack(anchor="e")
        self._blue_num = tk.Label(card, textvariable=self.blue_var, bg=PAL["panel"],
                                  fg=PAL["blue"], font=("Segoe UI", 30, "bold"))
        self._blue_num.pack(side="right", padx=(20, 10))

        # centre: proportion bar + leader text
        mid = ttk.Frame(card, style="Card.TFrame")
        mid.pack(fill="x", padx=8)
        tk.Label(mid, textvariable=self.leader_var, bg=PAL["panel"],
                 fg=PAL["muted"], font=("Segoe UI Semibold", 10)).pack()
        self.score_canvas = tk.Canvas(mid, height=14, highlightthickness=0,
                                      bg=PAL["log"])
        self.score_canvas.pack(fill="x", pady=(6, 0))
        self.score_canvas.bind("<Configure>", lambda e: self._draw_score_bar())

    def set_red(self, n: int):
        self.red_score = n
        self._refresh_score()

    def set_blue(self, n: int):
        self.blue_score = n
        self._refresh_score()

    def _refresh_score(self):
        self.red_var.set(str(self.red_score))
        self.blue_var.set(str(self.blue_score))
        r, b = self.red_score, self.blue_score
        if r > b:
            self.leader_var.set(f"🔴 RED leads  {r} – {b}")
        elif b > r:
            self.leader_var.set(f"🔵 BLUE leads  {r} – {b}")
        else:
            self.leader_var.set(f"TIED  {r} – {b}")
        self._draw_score_bar()

    def _draw_score_bar(self):
        c = self.score_canvas
        c.delete("all")
        w = c.winfo_width() or 1
        h = int(c["height"])
        r, b = self.red_score, self.blue_score
        tot = r + b
        rw = w // 2 if tot == 0 else int(round(w * r / tot))
        c.create_rectangle(0, 0, rw, h, fill=PAL["red"], width=0)
        c.create_rectangle(rw, 0, w, h, fill=PAL["blue"], width=0)

    def _tab(self, key: str) -> ComponentTab:
        return next(t for t in self.tabs if t.cfg["key"] == key)

    def start_all(self):
        # Attacker + defender (defender already includes the vuln app).
        self._tab("attacker").on_start()
        self._tab("defender").on_start()

    def stop_all(self):
        for t in self.tabs:
            t.on_stop()

    def _on_close(self):
        for t in self.tabs:
            t.shutdown()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
