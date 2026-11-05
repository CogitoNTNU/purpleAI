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
    def __init__(self, master: tk.Misc, cfg: dict):
        super().__init__(master, padding=8)
        self.cfg = cfg
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
        self.sub_tasks: dict = {}  # subagent name -> {task_id: status}
        self.panes: dict = {}  # pane key -> ScrolledText (multi-pane mode)
        # Route a subagent name / tool / label to its pane key.
        self.pane_for: dict = {}
        for sa in cfg.get("subagents", []):
            if sa.get("pane"):
                for k in (sa["name"], sa["tool"], sa["label"]):
                    self.pane_for[k] = sa["pane"]

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))

        dot = tk.Canvas(bar, width=14, height=14, highlightthickness=0)
        dot.pack(side="left", padx=(0, 6))
        self._dot = dot.create_oval(2, 2, 12, 12, fill="#888", outline="")
        self._dot_canvas = dot

        self.status_var = tk.StringVar(value="idle")
        ttk.Label(bar, textvariable=self.status_var, width=16).pack(side="left")

        ttk.Button(bar, text="▶ Start", command=self.on_start).pack(side="left", padx=2)
        ttk.Button(bar, text="■ Stop", command=self.on_stop).pack(side="left", padx=2)
        ttk.Button(bar, text="📜 View logs", command=self.start_logs).pack(side="left", padx=2)
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
            sframe = ttk.LabelFrame(self, text="Subagents")
            sframe.pack(fill="x", pady=(0, 6))
            inner = ttk.Frame(sframe)
            inner.pack(fill="x", padx=6, pady=4)
            if cfg.get("health"):
                cell = ttk.Frame(inner)
                cell.pack(side="left", padx=(0, 20))
                c = tk.Canvas(cell, width=14, height=14, highlightthickness=0)
                c.pack(side="left", padx=(0, 6))
                oval = c.create_oval(2, 2, 12, 12, fill="#555", outline="")
                ttk.Label(cell, text="Server", width=6).pack(side="left")
                sv = tk.StringVar(value="?")
                ttk.Label(cell, textvariable=sv, width=14).pack(side="left")
                self.lights["server"] = {"canvas": c, "oval": oval,
                                         "status": sv, "label": "Server"}
            for sa in cfg["subagents"]:
                cell = ttk.Frame(inner)
                cell.pack(side="left", padx=(0, 20))
                c = tk.Canvas(cell, width=14, height=14, highlightthickness=0)
                c.pack(side="left", padx=(0, 6))
                oval = c.create_oval(2, 2, 12, 12, fill="#555", outline="")
                ttk.Label(cell, text=sa["label"], width=5).pack(side="left")
                sv = tk.StringVar(value="idle")
                ttk.Label(cell, textvariable=sv, width=12).pack(side="left")
                entry = {"canvas": c, "oval": oval, "status": sv, "label": sa["label"]}
                self.lights[sa["name"]] = entry
                self.lights[sa["tool"]] = entry  # same light, keyed by tool too

        # Flags overview (attacker): a running list of captured FLAG{...}.
        self.flags_list = None
        if cfg.get("show_flags"):
            self.flags_frame = ttk.LabelFrame(self, text="🚩 Flags captured (0)")
            self.flags_frame.pack(fill="x", pady=(0, 6))
            row = ttk.Frame(self.flags_frame)
            row.pack(fill="x", padx=4, pady=4)
            self.flags_list = tk.Listbox(row, height=4, bg="#141414", fg="#f1c40f",
                                         font=("Consolas", 10), activestyle="none",
                                         selectbackground="#333")
            self.flags_list.pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Clear", width=6,
                       command=self.clear_flags).pack(side="left", padx=(6, 0))

        if cfg.get("panes"):
            # Three live panes side by side (resizable).
            pw = ttk.PanedWindow(self, orient="horizontal")
            pw.pack(fill="both", expand=True)
            for p in cfg["panes"]:
                frame = ttk.LabelFrame(pw, text=p["title"])
                txt = ScrolledText(frame, height=18, width=30, bg="#0e0f12",
                                   fg="#d6d6d6", insertbackground="#d6d6d6",
                                   font=("Consolas", 10), wrap="word",
                                   state="disabled")
                txt.pack(fill="both", expand=True)
                pw.add(frame, weight=1)
                self.panes[p["key"]] = txt
            # Default target for undirected output is the first pane (Boss).
            self.log = self.panes[cfg["panes"][0]["key"]]
        else:
            self.log = ScrolledText(self, height=18, bg="#0e0f12", fg="#d6d6d6",
                                    insertbackground="#d6d6d6",
                                    font=("Consolas", 10), wrap="none",
                                    state="disabled")
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

    def clear_flags(self):
        if self.flags_list is None:
            return
        self.flags.clear()
        self.flags_list.delete(0, "end")
        self.flags_frame.configure(text="🚩 Flags captured (0)")

    def _add_flag(self, flag: str):
        if self.flags_list is None or not flag or flag in self.flags:
            return
        self.flags.add(flag)
        self.flags_list.insert("end", flag)
        self.flags_list.see("end")
        self.flags_frame.configure(text=f"🚩 Flags captured ({len(self.flags)})")

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
        fill = color or ("#2ECC71" if on else "#555")
        entry["canvas"].itemconfig(entry["oval"], fill=fill)
        if status is not None:
            entry["status"].set(status)

    def _reset_lights(self):
        self.sub_tasks.clear()
        self.tid_label.clear()
        self._seen_msgs.clear()
        for entry in self.lights.values():
            entry["canvas"].itemconfig(entry["oval"], fill="#555")
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
            color = "#2ECC71" if running else ("#E1B400" if queued else "#555")
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
        entry["canvas"].itemconfig(entry["oval"], fill="#2ECC71" if up else "#E74C3C")
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
        self.set_dot("#E1B400")
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
    #   "===== iteration N ====="   -> boundary (hide; resets block state)
    #   "  [node] reasoning..."      -> reasoning (show; may wrap to more lines)
    #   "  -> tool(args)" / "  <- tool: result"  -> tool chatter (hide)
    #   "  … 3 subagent(s) running"  -> structural noise (hide)
    #   "  🚩 CAPTURED FLAG: ..."    -> always show
    _RE_ITER = re.compile(r"^\s*=+\s*iteration\b", re.IGNORECASE)
    _RE_REASON = re.compile(r"^\s*\[")          # "  [node] ..."
    _RE_TOOL = re.compile(r"^\s*[→←>←<]")       # tool call "→"/">" or result "←"/"<"
    _RE_NOISE = re.compile(r"^\s*[…]")          # structural status lines

    def _keep_line(self, line: str) -> bool:
        """Show only Boss reasoning and flags; hide everything else."""
        if "🚩" in line or "CAPTURED FLAG" in line or "FLAG{" in line:
            return True
        if self._RE_ITER.match(line):
            self._show_block = False   # reset at iteration boundary
            return False               # hide the header itself
        if self._RE_NOISE.match(line):
            self._show_block = False
            return False
        if self._RE_TOOL.match(line):
            self._show_block = False
            return False
        if self._RE_REASON.match(line):
            self._show_block = True
            return True
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
                self.set_dot("#2ECC71")
                self.start_logs()  # auto-attach the live log stream
            else:
                self.status_var.set("start failed")
                self.set_dot("#E74C3C")
        elif which == "stop":
            self.status_var.set("stopped")
            self.set_dot("#888888")
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
        self.geometry("1200x680")
        self.minsize(760, 480)

        header = ttk.Frame(self, padding=(10, 8))
        header.pack(fill="x")
        ttk.Label(header, text="PurpleAI Control", font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Button(header, text="Start all", command=self.start_all).pack(side="right", padx=3)
        ttk.Button(header, text="Stop all", command=self.stop_all).pack(side="right", padx=3)
        ttk.Label(header, text=f"via {GAMEHOST}", foreground="#888").pack(side="right", padx=10)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tabs: list[ComponentTab] = []
        for cfg in COMPONENTS:
            tab = ComponentTab(nb, cfg)
            nb.add(tab, text=cfg["label"])
            self.tabs.append(tab)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
