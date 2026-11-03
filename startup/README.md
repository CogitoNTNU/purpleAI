# PurpleAI Control — desktop launcher

A clickable Windows app to start/stop the three components on the lab boxes,
with live logs shown **inside the window** — no terminal needed.

```
this PC ──ssh──► gamehost ──ssh──► redai   (Attacker: Boss + subagent server)
                          └──ssh──► blueai  (Defender + Vulnerable app, Docker)
```

## Run it

Double-click **`startup/gui/dist/PurpleAIControl.exe`**.

Every **Start** first runs `git pull --ff-only origin main` on the target box,
then starts the component:

| Tab | Start does | Stop does |
|---|---|---|
| **Attacker (redai)** | Boss + subagent server in a detached tmux session | kills the tmux session + stray procs |
| **Defender + VulnApp (blueai)** | brings the app-only stack down, then `docker-compose.full.yml up -d --build` | `… down` |
| **Vulnerable app only (blueai)** | brings the full stack down, then `docker-compose.app.yml up -d --build` | `… down` |

Each tab has **▶ Start**, **■ Stop**, **📜 View logs**, **⟳ Status**, **Clear**.
After Start, logs stream into the panel automatically. The header has
**Start all** (attacker + defender) and **Stop all**.

The **Attacker** tab has a **Reasoning only** checkbox (on by default): it shows
the `===== iteration N =====` boundaries, the Boss's reasoning, and any
`FLAG{…}`, and hides the raw tool-call/result chatter. Untick for the full
console. (Filtering is display-only; the full log is kept in `attacker.log` on
redai.)

The attacker's launch script is **shipped over SSH from the app** (fed to
`bash -s` on stdin), so redai doesn't need any helper files — just the repo.

## Requirements

- The `ssh` aliases `gamehost`, `redai`, `blueai` work the way you use them by
  hand (gamehost from this PC; redai/blueai from gamehost), using **key auth**
  (the app runs ssh non-interactively — no password prompts).
- Repo at `~/purpleAI` on redai and blueai. `tmux` is auto-installed on redai if
  missing; Docker must already be on blueai.

If any of those differ, edit the `CONFIG` block at the top of
[`startup/gui/app.py`](gui/app.py) and rebuild.

## Rebuild the exe

After editing `app.py`:

```powershell
cd startup\gui
.\build.ps1            # or .\build.ps1 -Clean
```

Produces `startup/gui/dist/PurpleAIControl.exe` (windowed, single file, no
console). Uses `uv` + PyInstaller; nothing is added to the project's deps.

## Notes

- **Defender** and **Vulnerable app only** share port `8080` and the
  `vulnerable-app` container name, so only one can run. Starting either now
  brings the other down first, so just click the one you want.
- **Docker permissions on blueai:** the app uses plain `docker` if the login
  user can reach the socket, falls back to passwordless `sudo -n docker`, and
  otherwise prints a one-time fix: `sudo usermod -aG docker $(whoami)` then log
  out/in.
- The attacker's target is set in `src/Attacker/config.py`. Point it at whatever
  the defender/vuln app is reachable as from redai.
- First attacker run needs the Python env in `src/Attacker/.venv`; the launch
  script bootstraps it with `uv` if missing (see `src/Attacker/README.md`).

## Files

| Path | Runs on | Purpose |
|---|---|---|
| `gui/app.py` | Windows | the GUI (Tkinter); edit `CONFIG` + the embedded attacker script here |
| `gui/build.ps1` | Windows | build the `.exe` |
| `gui/dist/PurpleAIControl.exe` | Windows | the app (git-ignored; build locally) |
