# PurpleAI Control

A desktop workspace for running the PurpleAI lab over SSH. The GUI upgrade
introduces sidebar navigation, a violet and charcoal theme, compact scorecards,
agent status cards, and resizable live feeds. It uses Python's built-in Tk toolkit
with a custom theme; no extra GUI dependencies are needed.

## Run

Double-click `dist/PurpleAIControl-GUIUpgrade.exe` for the upgraded build.
The original `dist/PurpleAIControl.exe` can remain alongside it.

From source:

```powershell
uv run --no-project --python 3.12 startup/gui/app.py
```

For a local design preview with SSH and configuration writes disabled:

```powershell
uv run --no-project --python 3.12 startup/gui/preview.py
```

## Workspace

Use the sidebar to switch between:

- **Attack workspace**: Boss orchestration alongside a resizable 2-by-2 grid
  of Recon, SQL, Cross-site, and SSTI feeds. Server and agent cards show live
  activity; objective indicators show which flags have been captured.
- **Defense workspace**: controls and logs for the defender plus vulnerable app.
- **Application**: controls and logs for the vulnerable app on its own.
- **Siege arena**: the existing animated battlefield and War Room, driven by the
  same live events, reasoning, captures, and defender blocks.

The top controls select instance A-D, its branch, and its model. Each instance
has a separate worktree, server port, application port, and tmux session.
Branch and model changes take effect on the next start. Switching instances
reattaches the live viewers and restores that instance's arena transcript.

**Start all** starts the current instance's attacker and defender/app stack.
**Stop all** stops the current instance's components. **Launch instances** opens
the batch launcher with per-instance branches, an optional vulnerable app,
and a configurable delay between launches.

Each component provides Start, Stop, Logs, Status, and Clear. The attacker also
provides Server log, a toggle for the reasoning stream, the Reasoning only
filter, and End engagement. End engagement interrupts the Boss so it writes its
final summary, leaving the server and logs available for review.

Sidebar tools provide engagement notes, the Strategist brief, and the shared
API key pool. Saving keys updates the live pool on redai. **Reset all instances**
requires confirmation and stops all A-D instances, removes their server state,
and clears their logs.

## Scoring and live data

Blue begins defending all seven objectives. A flag counts for Red only when
captured through its owning vulnerability class; a flag leaked through another
class appears in the logs without scoring. Blue's displayed score is the
number of objectives still defended. Blocked requests animate the arena.

The attacker reads its console log, `events.jsonl`, the LangGraph server log,
and thread state for subagent output. Logs start reasoning and health polling
automatically. Server health is checked every eight seconds and reasoning is
polled every six seconds while enabled.

Starting the attacker preserves checkpoints and server threads for resume.
Use Reset all instances when you want to clear the engagement state.

## Build

```powershell
cd startup\gui
.\build.ps1 -Name PurpleAIControl-GUIUpgrade
```

Builds a separate windowed, single-file executable, including arena assets.
The default command `.\build.ps1` produces `dist/PurpleAIControl.exe`.
`-Clean` removes existing build outputs first. Build outputs are git-ignored.
The build uses uv and an ephemeral PyInstaller installation.

## Lab configuration

Edit the configuration constants in `app.py`:

- `GAMEHOST`: SSH jump host alias (default `gamehost`).
- `REPO`: repository path on the lab machines (default `~/purpleAI`).
- `BLUEAI_IP`: address hosting the target applications.
- `INSTANCES`: A-D ports and default branches/models.

Commands travel from this PC to gamehost, then to redai or blueai, in background
processes. SSH aliases and key authentication must already work without password
prompts. Remote requirements are the repository, tmux on redai, and Docker on
blueai. Docker uses the login user's access or passwordless `sudo -n docker`.

API keys and model choices stay in `~/.purpleai_instance_keys.json`; engagement
notes stay in `~/.purpleai_notes.md`. Neither file is committed to the repository.

## Verification

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
uv run --no-project --python 3.12 --with pytest python -m pytest tests/test_gui_workspace.py tests/test_war_room_routing.py -k 'not complete_boss' -q
```

The GUI checks exercise navigation, all five output panes, live agent activity,
flag attribution and score updates, minimum window sizing, and the notes dialog.
They do not connect to the lab or load the operator's saved configuration.
