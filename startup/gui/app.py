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
import os
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

try:  # ensure the Siege view is bundled by PyInstaller
    import arena  # noqa: F401
except Exception:  # noqa: BLE001
    arena = None

# --------------------------------------------------------------------------- #
# CONFIG — edit to match your setup                                           #
# --------------------------------------------------------------------------- #
GAMEHOST = "gamehost"          # ssh alias of the jump host (reached from this PC)
REPO = "~/purpleAI"            # repo path on redai and blueai
BLUEAI_IP = "192.168.0.120"    # LAN IP of blueai (where the vulnerable app listens)

# Isolated instances you can run in parallel to compare configs (e.g. main vs
# recon-agent). Each gets its own attacker server port, vulnerable-app port,
# tmux session, and git worktree on redai, so they never collide. `branch` is
# editable at runtime from the header; defaults set up the common A/B compare.
INSTANCES = [
    {"id": "a", "label": "A", "server_port": 2024, "app_port": 8080, "branch": "main"},
    {"id": "b", "label": "B", "server_port": 2025, "app_port": 8081, "branch": "recon-agent"},
    {"id": "c", "label": "C", "server_port": 2026, "app_port": 8082, "branch": "main"},
    {"id": "d", "label": "D", "server_port": 2027, "app_port": 8083, "branch": "main"},
]


def inst_session(inst):   return f"attacker-{inst['id']}"
def inst_worktree(inst):  return f"$HOME/purpleAI-{inst['id']}"
def inst_target(inst):    return f"http://{BLUEAI_IP}:{inst['app_port']}/"
def inst_project(inst):   return f"purpleai-{inst['id']}"


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


def with_pull(cmd: str) -> str:
    """Bring the main checkout to the latest origin/main before running `cmd`
    (defender/vulnapp build from it). A hard reset is robust even when the box
    left the checkout on a detached HEAD (worktrees do that). Uses `;` so a
    network hiccup is reported but doesn't block the start."""
    return (f"cd {REPO} && git fetch origin --quiet 2>/dev/null; "
            f"git checkout -f main 2>/dev/null; "
            f"git reset --hard --quiet origin/main 2>/dev/null; {cmd}")


# ---- per-instance docker (vulnerable app / defender on blueai) ------------ #
# The vulnerable-app/defender code is identical across branches, so instances
# build from the one main checkout but run isolated containers: a per-instance
# compose project, host port, container names, and logs dir. The compose files
# read these env vars (defaulting to the single-run values when unset).
def _dc_env(inst: dict) -> str:
    return (f"COMPOSE_PROJECT_NAME={inst_project(inst)} APP_PORT={inst['app_port']} "
            f"APP_CONTAINER=vulnerable-app-{inst['id']} "
            f"DEF_CONTAINER=defender-{inst['id']} APP_LOGS=./logs-{inst['id']}")


def _dc_inst(inst: dict, compose: str, action: str) -> str:
    """A docker-compose action for one instance (its own project/port/names)."""
    return (f"cd {REPO}/src/defender && {_DOCKER_PICK} && export {_dc_env(inst)} && "
            f"$DC compose -f {compose} {action}")


def docker_start_inst(inst: dict, target: str, other: str) -> str:
    """Start `target` for one instance, bringing its sibling compose down first
    so the two files don't fight over this instance's port / container names."""
    return (f"cd {REPO}/src/defender && {_DOCKER_PICK} && export {_dc_env(inst)} && "
            f"$DC compose -f {other} down --remove-orphans; "
            f"$DC compose -f {target} up -d --build --remove-orphans")


# The attacker has a multi-step launch (tmux + venv). Rather than require these
# scripts to already be on redai, the GUI ships them over ssh via `bash -s` on
# stdin, so the box only needs the repo itself — not these helper files.
# Template: one ISOLATED attacker instance. Placeholders (__SESSION__ etc.) are
# filled per-instance by _fill(). Each instance runs from its OWN git worktree
# (so different branches run in parallel), on its OWN server port, against its
# OWN vulnerable-app port via TARGET_URL — nothing is shared between instances.
ATTACKER_START_TMPL = r"""
set -euo pipefail
MAIN="${PURPLE_REPO:-$HOME/purpleAI}"
SESSION="__SESSION__"
SRVPORT="__SRVPORT__"
BRANCH="__BRANCH__"
WT="__WT__"
export TARGET_URL="__TARGET__"
export SUBAGENT_SERVER_URL="http://localhost:$SRVPORT"
LOGDIR="$WT/startup/logs"
LOG="$LOGDIR/attacker.log"

# --- set up / refresh this instance's worktree on the chosen branch --------
( cd "$MAIN" && git fetch origin --quiet ) || echo "[attacker] git fetch skipped/failed."
if [ -e "$WT/.git" ]; then
  git -C "$WT" fetch origin --quiet || true
  git -C "$WT" checkout --detach --quiet "origin/$BRANCH" 2>/dev/null \
    || git -C "$WT" checkout --detach --quiet "$BRANCH" || true
  git -C "$WT" reset --hard --quiet "origin/$BRANCH" 2>/dev/null || true
else
  git -C "$MAIN" worktree add --detach "$WT" "origin/$BRANCH" 2>/dev/null \
    || git -C "$MAIN" worktree add --detach "$WT" "$BRANCH" \
    || { echo "ERROR: could not create worktree $WT on $BRANCH" >&2; exit 1; }
fi
ATT="$WT/src/attacker"
[ -d "$ATT" ] || ATT="$WT/src/Attacker"
[ -d "$ATT" ] || { echo "ERROR: $ATT not found in worktree." >&2; exit 1; }
mkdir -p "$LOGDIR"

if ! command -v tmux >/dev/null 2>&1; then
  echo "[attacker] installing tmux..."
  sudo -n apt-get update -y && sudo -n apt-get install -y tmux \
    || { echo "ERROR: tmux missing and cannot sudo-install it."; exit 1; }
fi

# Restart THIS instance clean (scoped to its own session + server port).
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[attacker] restarting instance $SESSION..."
  tmux kill-session -t "$SESSION" 2>/dev/null || true
fi
tmux kill-session -t attacker 2>/dev/null || true   # legacy pre-instance session
# Free THIS instance's port from ANY stale server, including a legacy run
# started without --port (which the per-port pkill below would miss) — that
# squatter is exactly what makes a new server fail to bind and the Boss talk to
# a stale server.
command -v fuser >/dev/null 2>&1 && fuser -k "${SRVPORT}/tcp" 2>/dev/null || true
for pid in $(ss -ltnp 2>/dev/null | grep "127.0.0.1:$SRVPORT " | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u); do
  kill "$pid" 2>/dev/null || true
done
pkill -f "langgraph dev --port $SRVPORT" 2>/dev/null || true
sleep 1

# Fresh state each run (rotate events, wipe this worktree's server threads).
mkdir -p "$ATT/logs"
[ -s "$ATT/logs/events.jsonl" ] && mv -f "$ATT/logs/events.jsonl" "$ATT/logs/events.prev.jsonl" 2>/dev/null || true
rm -rf "$ATT/.langgraph_api" 2>/dev/null || true
echo "[attacker] cleared previous run state."

# Carry the gitignored .env + reuse a venv with langgraph from the main checkout.
if [ ! -f "$ATT/.env" ]; then
  for alt in "$MAIN/src/Attacker/.env" "$MAIN/src/attacker/.env"; do
    [ -f "$alt" ] && cp "$alt" "$ATT/.env" && echo "[attacker] copied .env from $alt" && break
  done
fi
VENV=""
for alt in "$ATT/.venv" "$MAIN/src/attacker/.venv" "$MAIN/src/Attacker/.venv"; do
  if [ -x "$alt/bin/langgraph" ]; then VENV="$alt"; break; fi
done
if [ -z "$VENV" ]; then
  echo "[attacker] no venv with langgraph; bootstrapping with uv..."
  if command -v uv >/dev/null 2>&1; then
    ( cd "$ATT" && uv venv && uv pip install --python .venv/bin/python -r requirements.txt )
    VENV="$ATT/.venv"
  else
    echo "ERROR: no usable .venv and uv not on PATH." >&2; exit 1
  fi
fi
echo "[attacker] venv=$VENV  target=$TARGET_URL  server=:$SRVPORT  branch=$BRANCH"

: > "$LOG"
START_DELAY="${PURPLE_ATTACKER_DELAY:-10}"
tmux new-session -d -s "$SESSION" -c "$ATT"
tmux pipe-pane -o -t "$SESSION" "cat >> '$LOG'"
# Export this instance's target + server URL, then load the .env (LLM_API_KEY).
tmux send-keys -t "$SESSION" "export TARGET_URL='$TARGET_URL' SUBAGENT_SERVER_URL='$SUBAGENT_SERVER_URL'" C-m
tmux send-keys -t "$SESSION" "set -a; [ -f .env ] && . ./.env; [ -z \"\${LLM_API_KEY:-}\" ] && [ -f '$MAIN/src/Attacker/.env' ] && . '$MAIN/src/Attacker/.env'; set +a" C-m
# 1) Subagent server (langgraph dev) on this instance's port, backgrounded.
#    --no-browser/--no-reload/--n-jobs-per-worker: see history; needed headless.
tmux send-keys -t "$SESSION" "BROWSER=true $VENV/bin/langgraph dev --port $SRVPORT --no-browser --no-reload --n-jobs-per-worker 10 > '$LOGDIR/langgraph.log' 2>&1 &" C-m
# 2) Boot delay, then wait until the server answers before launching the Boss.
tmux send-keys -t "$SESSION" "echo 'server starting on :$SRVPORT'; echo 'Boss starts in ${START_DELAY}s...'; sleep ${START_DELAY}" C-m
tmux send-keys -t "$SESSION" "n=0; until curl -s http://localhost:$SRVPORT/ok >/dev/null 2>&1 || curl -s http://localhost:$SRVPORT/ >/dev/null 2>&1; do n=\$((n+1)); [ \$n -ge 30 ] && break; sleep 2; done" C-m
tmux send-keys -t "$SESSION" "if curl -s http://localhost:$SRVPORT/ok >/dev/null 2>&1 || curl -s http://localhost:$SRVPORT/ >/dev/null 2>&1; then echo 'server up; starting Boss'; else echo 'WARNING: server not responding on :$SRVPORT'; fi; $VENV/bin/python redagent.py" C-m
echo "[attacker:$SESSION] started on $BRANCH (server :$SRVPORT, target $TARGET_URL)."
"""

ATTACKER_STOP_TMPL = r"""
set -uo pipefail
SESSION="__SESSION__"
SRVPORT="__SRVPORT__"
# Kill only THIS instance: its tmux session (which holds the Boss) and whatever
# server is bound to this instance's port. Other instances are untouched.
tmux kill-session -t "$SESSION" 2>/dev/null && echo "killed tmux '$SESSION'" || echo "no tmux session '$SESSION'"
command -v fuser >/dev/null 2>&1 && fuser -k "${SRVPORT}/tcp" 2>/dev/null || true
for pid in $(ss -ltnp 2>/dev/null | grep "127.0.0.1:$SRVPORT " | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u); do
  kill "$pid" 2>/dev/null || true
done
pkill -f "langgraph dev --port $SRVPORT" 2>/dev/null && echo "stopped langgraph server :$SRVPORT" || true
echo "[attacker:$SESSION] stop done."
"""

# Dump each subagent thread's message trail (its reasoning) from the langgraph
# server as JSON lines. Shipped to redai via bash -s and run on each poll; the
# GUI dedupes by (tid, index) and maps tid -> subagent via subagent_status.
REASONING_TMPL = r"""
python3 - <<'PY'
import json, urllib.request
BASE = "http://localhost:__SRVPORT__"
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
        # "human" = the task the Boss handed this subagent when it launched the
        # thread (its marching orders); "ai"/"tool" = the subagent's own work.
        if typ not in ("ai", "tool", "human"):
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


def _fill(tmpl: str, inst: dict) -> str:
    """Substitute an instance's parameters into a shell/script template."""
    return (tmpl
            .replace("__SESSION__", inst_session(inst))
            .replace("__SRVPORT__", str(inst["server_port"]))
            .replace("__APPPORT__", str(inst["app_port"]))
            .replace("__BRANCH__", inst["branch"])
            .replace("__WT__", inst_worktree(inst))
            .replace("__TARGET__", inst_target(inst))
            .replace("__ID__", inst["id"]))


# ---- per-instance script builders (attacker on redai) --------------------- #
def att_start(inst):  return _fill(ATTACKER_START_TMPL, inst)
def att_stop(inst):   return _fill(ATTACKER_STOP_TMPL, inst)
def att_reason(inst): return _fill(REASONING_TMPL, inst)

def att_logs(inst):
    wt = inst_worktree(inst)
    return (f"mkdir -p {wt}/startup/logs && touch {wt}/startup/logs/attacker.log "
            f"&& tail -n 300 -F {wt}/startup/logs/attacker.log")

def att_events(inst):
    # A fresh worktree is always a checkout of a branch where the dir is the
    # lowercase src/attacker, so pin it (no capital-A fallback) to avoid a
    # path-resolution race when the tail starts before the worktree exists.
    a = f"{inst_worktree(inst)}/src/attacker"
    return (f"mkdir -p {a}/logs && touch {a}/logs/events.jsonl "
            f"&& tail -n 200 -F {a}/logs/events.jsonl")

def att_serverlog(inst):
    wt = inst_worktree(inst)
    return (f"mkdir -p {wt}/startup/logs && touch {wt}/startup/logs/langgraph.log "
            f"&& tail -n 200 -F {wt}/startup/logs/langgraph.log")

def att_health(inst):
    p = inst["server_port"]
    return (
        'c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 4 '
        f"http://localhost:{p}/ok 2>/dev/null); "
        'if [ -z "$c" ] || [ "$c" = "000" ]; then '
        'c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 4 '
        f"http://localhost:{p}/ 2>/dev/null); fi; "
        'echo "SERVER $c"'
    )

def att_status(inst):
    return (f"tmux has-session -t {inst_session(inst)} 2>/dev/null "
            "&& echo RUNNING || echo STOPPED")


# Each component's instance-varying scripts are produced by its `build(inst)`;
# the static fields (panes, subagent lights, colours) are the same for every
# instance. ComponentTab merges build(inst) into its cfg and re-tails on switch.
def _attacker_build(inst):
    return {
        "start": {"script": att_start(inst),
                  "desc": f"inst {inst['label']}: worktree {inst['branch']} + start server/Boss"},
        "stop":  {"script": att_stop(inst),
                  "desc": f"stop attacker instance {inst['label']}"},
        "logs": att_logs(inst),
        "events": att_events(inst),
        "server_logs": att_serverlog(inst),
        "reasoning_script": att_reason(inst),
        "health": att_health(inst),
        "status": att_status(inst),
    }


def _defender_build(inst):
    return {
        "start":  with_pull(docker_start_inst(inst, "docker-compose.full.yml", "docker-compose.app.yml")),
        "stop":   _dc_inst(inst, "docker-compose.full.yml", "down"),
        "logs":   _dc_inst(inst, "docker-compose.full.yml", "logs -f --tail=300"),
        "status": _dc_inst(inst, "docker-compose.full.yml", "ps"),
    }


def _vulnapp_build(inst):
    return {
        "start":  with_pull(docker_start_inst(inst, "docker-compose.app.yml", "docker-compose.full.yml")),
        "stop":   _dc_inst(inst, "docker-compose.app.yml", "down"),
        "logs":   _dc_inst(inst, "docker-compose.app.yml", "logs -f --tail=300"),
        "status": _dc_inst(inst, "docker-compose.app.yml", "ps"),
    }


COMPONENTS = [
    {
        "key": "attacker",
        "label": "Attacker  (redai)",
        "host": "redai",
        "color": "#C0392B",
        "filterable": True,   # adds the "Reasoning only" checkbox (on by default)
        "show_flags": True,   # adds the "Flags captured" overview
        # Live panes side by side: Boss, Recon, SQL, Cross-site, SSTI.
        "panes": [
            {"key": "boss", "title": "Boss"},
            {"key": "recon", "title": "Recon  (recon_agent)"},
            {"key": "sql", "title": "SQL  (sql_injection_agent)"},
            {"key": "xss", "title": "Cross-site  (xss_agent)"},
            {"key": "ssti", "title": "SSTI  (ssti_agent)"},
        ],
        # Subagents to show activity lights for; `tool` maps a tool event to its
        # subagent (sqlmap -> SQLi, xsser -> XSS, curl -> SSTI's ssti_scanner);
        # `pane` routes its output.
        "subagents": [
            {"name": "recon_agent", "label": "Recon", "tool": "recon",
             "tools": ["whatweb"], "pane": "recon"},
            {"name": "sql_injection_agent", "label": "SQLi", "tool": "sqlmap", "pane": "sql"},
            {"name": "xss_agent", "label": "XSS", "tool": "xsser", "pane": "xss"},
            {"name": "ssti_agent", "label": "SSTI", "tool": "curl", "pane": "ssti"},
        ],
        "build": _attacker_build,
    },
    {
        "key": "defender",
        "label": "Defender + VulnApp  (blueai)",
        "host": "blueai",
        "color": "#2471A3",
        "counts_blue": True,  # blocked requests in its log = blue team score
        "build": _defender_build,
    },
    {
        "key": "vulnapp",
        "label": "Vulnerable app only  (blueai)",
        "host": "blueai",
        "color": "#7D3C98",
        "build": _vulnapp_build,
    },
]

# Hide the console windows spawned by ssh.exe on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

# FLAG{...} values are the objective; harvest them from the attacker's stream.
FLAG_RE = re.compile(r"FLAG\{[^}\n]{0,200}\}")

# Subagent graph name -> Siege arena commander key (includes xxe, which has no
# text pane but does get a commander on the battlefield).
AGENT_ARENA = {
    "recon_agent": "recon",
    "sql_injection_agent": "sql", "xss_agent": "xss",
    "ssti_agent": "ssti", "xxe_agent": "xxe",
}

# The flags planted in the vulnerable app (see
# src/defender/vulnerable-app/VULNERABILITIES.md). Each is a light that starts
# blue (defended) and turns red when the attacker captures it THROUGH ITS OWN
# vulnerability class (`owner` pane) — so a flag merely leaked via another bug
# (e.g. SSTI reading app.py, which inlines the SQL/XSS flag strings) does not
# count. `owner=None` = no current agent targets it, so it stays blue.
KNOWN_FLAGS = [
    ("FLAG{sql_login_bypass_success}", "SQL login bypass", "sql"),
    ("FLAG{sql_union_injection_found}", "SQL UNION", "sql"),
    ("FLAG{reflected_xss}", "Reflected XSS", "xss"),
    ("FLAG{stored_xss_dom}", "Stored XSS", "xss"),
    ("FLAG{server_side_template_injection}", "SSTI", "ssti"),
    ("FLAG{broken_access_control_admin_panel}", "Admin access", None),
    ("FLAG{path_traversal_outside_reports_dir}", "Path traversal", None),
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
    "hover": "#1f2630",    # chrome: hover fill (tabs, ghost buttons)
    "track": "#0b0e13",    # chrome: scoreboard proportion-bar track
}


def apply_style(root: tk.Misc) -> None:
    """A dark, flat, modern ttk theme built on 'clam'.

    Only the outer chrome is restyled: the header, the scoreboard, the Notebook
    tab switcher, and dedicated header buttons. The in-tab styles (Card.*,
    TLabelframe, the base TButton/Accent.TButton used *inside* the tabs, the
    checkbutton) are kept exactly as before so the tab bodies are unchanged.
    """
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    p = PAL

    # ---- base (unchanged) ------------------------------------------------ #
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

    # base buttons used *inside* the tab bodies — kept as before
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

    # ---- chrome: header -------------------------------------------------- #
    style.configure("Header.TFrame", background=p["bg"])
    style.configure("HeaderTitle.TLabel", background=p["bg"], foreground=p["text"],
                    font=("Segoe UI Semibold", 17))
    style.configure("HeaderSub.TLabel", background=p["bg"], foreground=p["muted"],
                    font=("Segoe UI", 10))

    # header buttons (distinct from the in-tab ones so tab bodies stay as-is)
    style.configure("Primary.TButton", background=p["accent"], foreground="#0d1117",
                    bordercolor=p["accent"], borderwidth=0, focusthickness=0,
                    padding=(16, 9), relief="flat", font=("Segoe UI Semibold", 10))
    style.map("Primary.TButton",
              background=[("active", "#b183f9"), ("pressed", "#9a6cf0")],
              foreground=[("disabled", p["muted"])])
    style.configure("Ghost.TButton", background=p["panel"], foreground=p["text"],
                    bordercolor=p["border"], borderwidth=1, focusthickness=0,
                    padding=(16, 9), relief="flat", font=("Segoe UI", 10))
    style.map("Ghost.TButton",
              background=[("active", p["hover"]), ("pressed", p["hover"])],
              bordercolor=[("active", p["muted"])])

    # ---- chrome: scoreboard ---------------------------------------------- #
    style.configure("Scorecard.TFrame", background=p["panel"])
    style.configure("ScoreTeam.TLabel", background=p["panel"],
                    font=("Segoe UI Semibold", 11))
    style.configure("ScoreSub.TLabel", background=p["panel"], foreground=p["muted"],
                    font=("Segoe UI", 9))
    style.configure("Leader.TLabel", background=p["panel"], foreground=p["text"],
                    font=("Segoe UI Semibold", 11))

    # ---- chrome: Notebook tab switcher (flat, segmented pills) ------------ #
    style.configure("TNotebook", background=p["bg"], borderwidth=0,
                    tabmargins=(0, 6, 0, 0))
    style.configure("TNotebook.Tab", background=p["bg"], foreground=p["muted"],
                    padding=(18, 10), borderwidth=0, font=("Segoe UI", 10))
    style.map("TNotebook.Tab",
              background=[("selected", p["accent"]), ("active", p["hover"])],
              foreground=[("selected", "#0d1117"), ("active", p["text"])],
              # keep the selected tab the same size as the rest (no clam jitter)
              expand=[("selected", (0, 0, 0, 0))])


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
    def __init__(self, master: tk.Misc, cfg: dict, app=None, instance: dict | None = None):
        super().__init__(master, padding=8)
        # cfg carries static metadata; build(instance) fills the instance-varying
        # scripts (ports/branch/worktree/target). Merge them so the rest of the
        # tab reads self.cfg["start"/"logs"/…] exactly as before.
        self.cfg = dict(cfg)
        self.instance = instance or INSTANCES[0]
        if callable(self.cfg.get("build")):
            self.cfg.update(self.cfg["build"](self.instance))
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
        self._reason_err_shown = False        # throttle "server unreachable"
        self._seen_msgs: set = set()          # (tid, i) already shown
        self.tid_label: dict = {}             # thread id -> subagent label
        self.tid_arena: dict = {}             # thread id -> arena commander key
        self.action_proc: Proc | None = None  # one-shot start/stop/status
        self.lights: dict = {}  # subagent name AND tool -> light entry
        # "Reasoning only" filter (attacker): show iteration headers + the
        # Boss's [node] reasoning + flags; hide tool-call/result chatter.
        self.reasoning_only = tk.BooleanVar(value=bool(cfg.get("filterable")))
        self._show_block = False  # filter state: are we inside a shown block?
        self.flags: set[str] = set()  # unique FLAG{...} seen on this box
        self.captured: set[str] = set()  # flags scored (attributed to their agent)
        self._leaked_seen: set[str] = set()  # leaked-not-scored, for dedup
        self.flag_lights: dict = {}  # flag string -> {canvas, oval, label, owner}
        self.sub_tasks: dict = {}  # subagent name -> {task_id: status}
        self.panes: dict = {}  # pane key -> ScrolledText (multi-pane mode)
        # Route a subagent name / tool / label to its pane key.
        self.pane_for: dict = {}
        for sa in cfg.get("subagents", []):
            if sa.get("pane"):
                for k in (sa["name"], sa["tool"], sa["label"], *sa.get("tools", [])):
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
                for extra in sa.get("tools", []):  # e.g. recon also runs whatweb
                    self.lights[extra] = entry

        # Flags overview (attacker): one light per planted flag. Blue =
        # defended/uncaptured, red = the attacker has captured it.
        if cfg.get("show_flags"):
            self.flags_frame = ttk.LabelFrame(
                self, text=f" 🚩 FLAGS  (0 / {len(KNOWN_FLAGS)} captured) ")
            self.flags_frame.pack(fill="x", pady=(0, 8))
            grid = ttk.Frame(self.flags_frame, style="Card.TFrame")
            grid.pack(fill="x", padx=8, pady=8)
            cols = 4
            for idx, (flag, label, owner) in enumerate(KNOWN_FLAGS):
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
                self.flag_lights[flag] = {"canvas": cv, "oval": oval,
                                          "label": lbl, "owner": owner}

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

    def _arena(self):
        return getattr(self.app, "arena", None) if self.app else None

    def _update_flag_title(self):
        known = len(self.flag_lights)
        self.flags_frame.configure(
            text=f" 🚩 FLAGS  ({len(self.captured)} / {known} captured) ")

    def clear_flags(self):
        if not self.cfg.get("show_flags"):
            return
        self.flags.clear()
        self.captured.clear()
        self._leaked_seen.clear()
        for e in self.flag_lights.values():
            e["canvas"].itemconfig(e["oval"], fill=PAL["blue"])
            e["label"].configure(fg=PAL["muted"])
        self._update_flag_title()
        if self.app:
            self.app.set_red(0)
        ar = self._arena()
        if ar:
            ar.reset()

    def _add_flag(self, flag: str, source_pane=None) -> str:
        """Score a flag only if captured through its owning vulnerability class.
        Returns 'new' (just scored), 'dup' (already scored), or 'reject'
        (unknown flag, or leaked via a different agent)."""
        entry = self.flag_lights.get(flag) if flag else None
        if entry is None or entry["owner"] != source_pane:
            return "reject"
        if flag in self.captured:
            return "dup"
        self.captured.add(flag)
        self.flags.add(flag)
        entry["canvas"].itemconfig(entry["oval"], fill=PAL["red"])  # blue -> red
        entry["label"].configure(fg=PAL["red"])
        self._update_flag_title()
        if self.app:
            self.app.set_red(len(self.captured))
        return "new"

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
        ar = self._arena()
        if ar:
            ar.block()

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
        self.tid_arena.clear()
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
            akey = AGENT_ARENA.get(sub)
            if tid is not None:
                tasks[tid] = status
                self.tid_label[tid] = self._label_for(sub)
                if akey:
                    self.tid_arena[tid] = akey
            running = sum(1 for s in tasks.values() if s in ("running", "busy"))
            queued = sum(1 for s in tasks.values() if s == "pending")
            total = len(tasks)
            # Server has 1 worker: green while one truly runs, amber if only
            # queued work is waiting, grey when nothing is outstanding.
            color = PAL["green"] if running else (PAL["amber"] if queued else PAL["idle"])
            self._set_light(sub, running > 0,
                            f"{running} running / {queued} queued / {total} launched",
                            color=color)
            ar = self._arena()
            if ar and akey:
                ar.set_state(akey, "running" if running else
                             ("queued" if queued else "idle"))
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
            pane = self.pane_for.get(tool, "boss")
            result = self._add_flag(flag, pane)
            ar = self._arena()
            if result == "new":
                self.append(f"  🚩 {flag}\n", pane=pane)
                if ar:
                    ar.capture(flag)
            elif result == "reject" and flag and flag not in self._leaked_seen:
                # Seen here but not this agent's vuln (e.g. leaked via source
                # disclosure): show it, but don't score it.
                self._leaked_seen.add(flag)
                self.append(f"  📄 leaked (not scored): {flag}\n", pane=pane)
                if ar and pane:
                    ar.leak(pane)

    def _handle_health(self, line: str):
        """Parse a 'SERVER <code>' health line and colour the Server light."""
        entry = self.lights.get("server")
        if not entry or "SERVER" not in line:
            return
        code = line.split("SERVER", 1)[1].strip() or "000"
        up = code not in ("", "000")
        entry["canvas"].itemconfig(entry["oval"], fill=PAL["green"] if up else PAL["red"])
        port = self.instance["server_port"]
        entry["status"].set(f"connected ({code})" if up else f"down (:{port})")

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
            if not self._reason_err_shown:  # show once, not every poll
                self.append(f"  [reason] subagent server not reachable on "
                            f":{self.instance['server_port']} "
                            "(is it up? check the Server light / 📄 Server log)\n")
                self._reason_err_shown = True
            return
        if not line.startswith("{"):
            return
        try:
            m = json.loads(line)
        except (ValueError, TypeError):
            return
        self._reason_err_shown = False  # a good poll; re-arm the error notice
        tid, i = m.get("tid"), m.get("i")
        key = (tid, i)
        if key in self._seen_msgs:
            return
        self._seen_msgs.add(key)
        label = self.tid_label.get(tid)
        if not label:
            return  # a thread not launched in this session; skip
        pane = self.pane_for.get(label, "boss")
        akey = self.tid_arena.get(tid)
        typ, text, tools = m.get("type"), m.get("text") or "", m.get("tools") or []
        if typ == "human":
            # The Boss's delegation to this subagent: show it in the Boss's
            # voice in the War Room, addressed to the subagent it launched.
            if text:
                self.append(f"  👑 → {label}: {text}\n", pane="boss")
                ar = self._arena()
                if ar:
                    ar.say("boss", f"→ {label}: {text}")
        elif typ == "ai":
            if text:
                self.append(f"  🧠 {text}\n", pane=pane)
                ar = self._arena()
                if ar and akey:
                    ar.say(akey, text)
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

    def set_instance(self, instance: dict):
        """Point this tab at another isolated instance: stop its current
        viewers, rebuild its per-instance scripts, reset the view, and re-tail
        the newly-selected instance's live logs."""
        self.stop_logs()
        if self.action_proc and self.action_proc.is_running():
            self.action_proc.kill()
        self.instance = instance
        if callable(self.cfg.get("build")):
            self.cfg.update(self.cfg["build"](instance))
        self.clear_log()
        if self.cfg.get("show_flags"):
            self.clear_flags()
            ar = self._arena()
            if ar:
                ar.reset()
            if self.app:
                self.app.set_red(0)
        if self.cfg.get("counts_blue") and self.app:
            self._blue = 0
            self._blue_seen.clear()
            self.app.set_blue(0)
        self.status_var.set("idle")
        self.set_dot(PAL["muted"])
        # Re-attach viewers so the selected instance's live logs stream in.
        self.start_logs()

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
                        if self.cfg.get("counts_blue"):
                            self._count_blue(payload)  # defender: blocked = blue
                        s = payload.strip()
                        if s.startswith("{") and '"action"' in s:
                            continue  # raw event JSON; shown via the events feed
                        if not self.reasoning_only.get() or self._keep_line(payload):
                            self.append(payload)
                            ar = self._arena()
                            if ar and self.cfg.get("panes"):
                                s2 = payload.strip()
                                if s2.startswith("[") or s2.startswith("====="):
                                    ar.say("boss", s2)
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

        # Window / taskbar icon (Cogito brain) while the app is running. The
        # .ico is bundled via --add-data; _MEIPASS is set inside the frozen exe.
        try:
            _base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
            self.iconbitmap(os.path.join(_base, "assets", "cogito.ico"))
        except Exception:  # noqa: BLE001  (icon is cosmetic)
            pass

        self.red_score = 0
        self.blue_score = 0
        self.arena = None
        self.current_instance = INSTANCES[0]

        # -- header: logo, title, host + global actions -------------------- #
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 14, 18, 14))
        header.pack(fill="x")
        if LOGO_PNG_B64:
            try:
                img = tk.PhotoImage(data=LOGO_PNG_B64)
                factor = max(1, img.height() // 34)
                self._logo_img = img.subsample(factor, factor)
                # transparent PNG composites over the header bg — no white box
                tk.Label(header, image=self._logo_img, bg=PAL["bg"],
                         bd=0).pack(side="left", padx=(0, 12))
            except Exception:  # noqa: BLE001  (logo is cosmetic)
                pass
        ttk.Label(header, text="PurpleAI Control",
                  style="HeaderTitle.TLabel").pack(side="left")

        # Instance + branch selectors: pick which isolated run you're viewing /
        # starting, and which branch that instance pulls. Instances are fully
        # isolated (own server port, vulnerable-app port, tmux session, worktree)
        # so you can run several at once and compare.
        sel = ttk.Frame(header, style="Header.TFrame")
        sel.pack(side="left", padx=(24, 0))
        ttk.Label(sel, text="Instance", style="HeaderSub.TLabel").pack(side="left", padx=(0, 6))
        self.inst_var = tk.StringVar(value=INSTANCES[0]["label"])
        inst_cb = ttk.Combobox(sel, textvariable=self.inst_var, state="readonly",
                               width=3, values=[i["label"] for i in INSTANCES])
        inst_cb.pack(side="left")
        inst_cb.bind("<<ComboboxSelected>>", self._on_instance_change)
        ttk.Label(sel, text="Branch", style="HeaderSub.TLabel").pack(side="left", padx=(14, 6))
        self.branch_var = tk.StringVar(value=INSTANCES[0]["branch"])
        branch_cb = ttk.Combobox(sel, textvariable=self.branch_var, width=16,
                                 values=["main", "recon-agent"])
        branch_cb.pack(side="left")
        branch_cb.bind("<<ComboboxSelected>>", self._on_branch_change)
        branch_cb.bind("<Return>", self._on_branch_change)
        branch_cb.bind("<FocusOut>", self._on_branch_change)

        # right cluster: Stop (secondary) · Start (primary) · host (muted)
        ttk.Button(header, text="■  Stop all", command=self.stop_all,
                   style="Ghost.TButton").pack(side="right", padx=(8, 0))
        ttk.Button(header, text="▶  Start all", command=self.start_all,
                   style="Primary.TButton").pack(side="right", padx=(8, 0))
        ttk.Label(header, text=f"via {GAMEHOST}",
                  style="HeaderSub.TLabel").pack(side="right", padx=(0, 16))

        # hairline divider between the header and the scoreboard
        tk.Frame(self, height=1, bg=PAL["border"]).pack(fill="x")

        self._build_scoreboard()

        # -- tabs ----------------------------------------------------------- #
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.tabs: list[ComponentTab] = []
        for cfg in COMPONENTS:
            tab = ComponentTab(nb, cfg, app=self, instance=self.current_instance)
            nb.add(tab, text=cfg["label"])
            self.tabs.append(tab)

        try:
            from arena import ArenaTab
            self.arena = ArenaTab(nb, PAL, KNOWN_FLAGS)
            nb.add(self.arena, text="⚔ Siege")
        except Exception:  # noqa: BLE001  (arena is an extra view)
            self.arena = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- Red vs Blue scoreboard -------------------------------------------- #
    def _build_scoreboard(self):
        wrap = ttk.Frame(self, style="Header.TFrame", padding=(12, 12, 12, 0))
        wrap.pack(fill="x")

        # crisp hairline-bordered flat card (ttk frames can't round corners)
        card = tk.Frame(wrap, bg=PAL["panel"], highlightthickness=1,
                        highlightbackground=PAL["border"],
                        highlightcolor=PAL["border"])
        card.pack(fill="x")
        inner = ttk.Frame(card, style="Scorecard.TFrame", padding=(22, 16))
        inner.pack(fill="both", expand=True)
        inner.columnconfigure(0, weight=0, minsize=150)
        inner.columnconfigure(1, weight=1)
        inner.columnconfigure(2, weight=0, minsize=150)

        self.red_var = tk.StringVar(value="0")
        self.blue_var = tk.StringVar(value="0")
        self.leader_var = tk.StringVar(value="TIED  0 – 0")

        # RED (left, left-aligned stat block)
        left = ttk.Frame(inner, style="Scorecard.TFrame")
        left.grid(row=0, column=0, sticky="nw")
        rl = ttk.Frame(left, style="Scorecard.TFrame")
        rl.pack(anchor="w")
        tk.Label(rl, text="●", bg=PAL["panel"], fg=PAL["red"],
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))
        tk.Label(rl, text="RED", bg=PAL["panel"], fg=PAL["red"],
                 font=("Segoe UI Semibold", 11)).pack(side="left")
        self._red_num = tk.Label(left, textvariable=self.red_var, bg=PAL["panel"],
                                 fg=PAL["red"], font=("Segoe UI", 34, "bold"))
        self._red_num.pack(anchor="w", pady=(2, 0))
        tk.Label(left, text="flags captured", bg=PAL["panel"], fg=PAL["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w")

        # BLUE (right, right-aligned stat block)
        right = ttk.Frame(inner, style="Scorecard.TFrame")
        right.grid(row=0, column=2, sticky="ne")
        bl = ttk.Frame(right, style="Scorecard.TFrame")
        bl.pack(anchor="e")
        tk.Label(bl, text="BLUE", bg=PAL["panel"], fg=PAL["blue"],
                 font=("Segoe UI Semibold", 11)).pack(side="left")
        tk.Label(bl, text="●", bg=PAL["panel"], fg=PAL["blue"],
                 font=("Segoe UI", 10)).pack(side="left", padx=(6, 0))
        self._blue_num = tk.Label(right, textvariable=self.blue_var, bg=PAL["panel"],
                                  fg=PAL["blue"], font=("Segoe UI", 34, "bold"))
        self._blue_num.pack(anchor="e", pady=(2, 0))
        tk.Label(right, text="attacks blocked", bg=PAL["panel"], fg=PAL["muted"],
                 font=("Segoe UI", 9)).pack(anchor="e")

        # CENTER (leader text + proportion bar + end captions)
        mid = ttk.Frame(inner, style="Scorecard.TFrame")
        mid.grid(row=0, column=1, sticky="nsew", padx=18)
        tk.Label(mid, textvariable=self.leader_var, bg=PAL["panel"], fg=PAL["text"],
                 font=("Segoe UI Semibold", 11)).pack(pady=(6, 0))
        self.score_canvas = tk.Canvas(mid, height=16, highlightthickness=0,
                                      bg=PAL["panel"], bd=0)
        self.score_canvas.pack(fill="x", pady=(10, 2))
        self.score_canvas.bind("<Configure>", lambda e: self._draw_score_bar())
        cap = ttk.Frame(mid, style="Scorecard.TFrame")
        cap.pack(fill="x")
        tk.Label(cap, text="attacker", bg=PAL["panel"], fg=PAL["muted"],
                 font=("Segoe UI", 8)).pack(side="left")
        tk.Label(cap, text="defender", bg=PAL["panel"], fg=PAL["muted"],
                 font=("Segoe UI", 8)).pack(side="right")

    def set_red(self, n: int):
        self.red_score = n
        if self.arena:
            self.arena.set_scores(self.red_score, self.blue_score)
        self._refresh_score()

    def set_blue(self, n: int):
        self.blue_score = n
        if self.arena:
            self.arena.set_scores(self.red_score, self.blue_score)
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
        if w <= 2:
            return
        rad = h // 2  # capsule radius

        def capsule(x0, x1, fill):
            """A rounded-end (capsule) bar segment from x0..x1, full height."""
            if x1 - x0 < 1:
                return
            rr = min(rad, (x1 - x0) / 2)
            c.create_oval(x0, 0, x0 + 2 * rr, h, fill=fill, outline="")
            c.create_oval(x1 - 2 * rr, 0, x1, h, fill=fill, outline="")
            c.create_rectangle(x0 + rr, 0, x1 - rr, h, fill=fill, outline="")

        # inset track
        capsule(0, w, PAL["track"])

        r, b = self.red_score, self.blue_score
        tot = r + b
        if tot == 0:
            return  # neutral track only until the first point lands
        split = int(round(w * r / tot))
        gap = 2  # tiny divider where the two colours meet
        if split > 0:
            capsule(0, max(split - gap, 1), PAL["red"])
        if split < w:
            capsule(min(split + gap, w - 1), w, PAL["blue"])

    def _tab(self, key: str) -> ComponentTab:
        return next(t for t in self.tabs if t.cfg["key"] == key)

    # -- instance / branch selection --------------------------------------- #
    def _instance_by_label(self, label: str) -> dict:
        return next((i for i in INSTANCES if i["label"] == label), INSTANCES[0])

    def _on_instance_change(self, _evt=None):
        """Switch the whole view (all tabs + arena) to the chosen instance."""
        inst = self._instance_by_label(self.inst_var.get())
        self.current_instance = inst
        self.branch_var.set(inst["branch"])
        self.title(f"PurpleAI Control — instance {inst['label']}")
        for t in self.tabs:
            t.set_instance(inst)

    def _on_branch_change(self, _evt=None):
        """Set the current instance's branch; takes effect on its next Start."""
        branch = self.branch_var.get().strip()
        if not branch or branch == self.current_instance.get("branch"):
            return
        self.current_instance["branch"] = branch
        # Rebuild each tab's scripts so the next Start pulls the new branch.
        for t in self.tabs:
            if callable(t.cfg.get("build")):
                t.cfg.update(t.cfg["build"](t.instance))

    def start_all(self):
        # Current instance's attacker + defender (defender includes the vuln app).
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
