# PurpleAI Control (GUI)

A small Tkinter desktop app that starts/stops the three PurpleAI components on
the lab machines over SSH and shows their live output — no terminal needed.

```
this PC ──ssh──► gamehost ──ssh──► redai   (Attacker: Boss + subagent server)
                          └──ssh──► blueai  (Defender + Vulnerable app, Docker)
```

Every command is run as `ssh gamehost "ssh <redai|blueai> …"` in a background
thread with the console window hidden, and output is streamed into the window.

## Run

Double-click **`dist/PurpleAIControl.exe`**. No install, no console.

## Build

```powershell
cd startup\gui
.\build.ps1            # or .\build.ps1 -Clean
```

Produces `dist/PurpleAIControl.exe` (windowed, single file). Uses `uv` +
PyInstaller ephemerally — nothing is added to the project's dependencies. The
exe is git-ignored; rebuild after editing `app.py`.

## Tabs

| Tab | Start | Stop |
|---|---|---|
| **Attacker (redai)** | pull main → start Boss + subagent server in tmux | kill the tmux session + stray procs |
| **Defender + VulnApp (blueai)** | pull main → `docker compose -f docker-compose.full.yml up -d --build` (brings the app-only stack down first) | `… down` |
| **Vulnerable app only (blueai)** | pull main → `docker compose -f docker-compose.app.yml up -d --build` (brings the full stack down first) | `… down` |

Each tab has **▶ Start · ■ Stop · 📜 View logs · ⟳ Status · Clear**. Start pulls
`main` on the box first, then launches; logs auto-stream afterwards. The header
has **Start all** / **Stop all**.

## Attacker tab specifics

Extra controls: **📄 Server log**, **🧠 Reasoning**, **Reasoning only** (checkbox).

### Server + subagent lights
A row of status lights:

- **Server** — polls `http://localhost:2024/ok` on redai every 8 s.
  🟢 `connected (200)` / 🔴 `down (:2024)`.
- **SQLi / XSS / SSTI** — one per subagent, showing
  `R running / Q queued / M launched`:
  🟢 green = a run is executing, 🟡 amber = only queued work waiting,
  ⚪ grey = idle. `M` is the count of unique task IDs launched this run — a quick
  way to spot the Boss over-delegating.

### Four live panes
The log area is split into **Boss · SQL · Cross-site · SSTI** (resizable
dividers). Output is routed by subagent:

- **Boss** — the Boss's own reasoning stream.
- **SQL / Cross-site / SSTI** — each subagent's reasoning (`🧠`), tool runs
  (`▶ sqlmap/xsser/curl …`), results (`✓/✗`), launches (`➕`) and flags (`🚩`).

Subagent reasoning is pulled from the langgraph server's thread state and
starts automatically with the log stream. The 🧠 Reasoning button toggles it.
(The subagents' full formatted trace also lives in LangSmith.)

### Reasoning only
On by default: the **Boss** pane shows just iteration headers and the Boss's
reasoning, hiding raw tool-call/result chatter. Untick for the full console.

### 🚩 Flags captured
A deduplicated list of every `FLAG{…}` seen across all streams, with a count.

## How a Start works (attacker)

1. The attacker launch script is **shipped over SSH on stdin** (`bash -s`), so
   redai needs only the repo — not any helper file. It is normalised to LF so
   bash doesn't choke on CRLF.
2. It restarts clean: kills any existing `attacker` tmux session, **rotates
   `events.jsonl`** and **wipes the server's `.langgraph_api`** so earlier runs'
   tasks don't carry over.
3. Starts the subagent server with `langgraph dev --no-browser --no-reload
   --n-jobs-per-worker 10`:
   - `--no-browser`: headless redai would otherwise open a text-mode browser
     that grabs the tty and suspends the server.
   - `--no-reload`: the attacker writes logs inside the watched tree; auto-reload
     would restart the server on every write and freeze runs at `pending`.
   - `--n-jobs-per-worker 10`: run SQLi/XSS/SSTI concurrently.
4. Waits for `:2024` to answer (after a short delay — your chance to open the
   Server log), then starts the Boss (`redagent.py`).

## Streams it reads (attacker)

| Source on redai | Shown as |
|---|---|
| `startup/logs/attacker.log` | Boss pane (reasoning) |
| `src/Attacker/logs/events.jsonl` | lights + activity lines + flags |
| langgraph server thread state (`:2024`) | subagent reasoning panes |
| `startup/logs/langgraph.log` | 📄 Server log |

## Configuration

Edit the `CONFIG` block at the top of [`app.py`](app.py) and rebuild:

- `GAMEHOST` — ssh alias of the jump host (default `gamehost`).
- `REPO` — repo path on redai/blueai (default `~/purpleAI`).
- `COMPONENTS` — per-tab host, commands, subagents, panes.
- `PURPLE_ATTACKER_DELAY` (env var on redai) — seconds before the Boss starts
  (default 10).

## Requirements

- The `ssh` aliases `gamehost`, `redai`, `blueai` work as you use them by hand
  (gamehost from this PC; redai/blueai from gamehost), with **key auth** — the
  app runs ssh non-interactively (no password prompts).
- Repo at `~/purpleAI` on redai and blueai; `tmux` on redai (auto-installed if
  missing and passwordless sudo is available); Docker on blueai.
- **Docker on blueai**: the app uses plain `docker` if the login user can reach
  the socket, else passwordless `sudo -n docker`, else it prints a one-time fix
  (`sudo usermod -aG docker $(whoami)` then re-login).
