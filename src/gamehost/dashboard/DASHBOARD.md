# Gamehost dashboard

The Streamlit dashboard reads the JSONL archives produced by gamehost
Vector at `/var/log/purpleai/collected/events-*.jsonl`. `event_store.py`
loads the archives, sorts events by timestamp, and removes duplicates
with the same `event_id`. Invalid JSON and partial lines are skipped;
completed lines are picked up on the next refresh.

## Run

Use the same account as the gamehost Vector service so the dashboard can
read its archives. From the repository root:

```bash
uv sync --locked
bash src/gamehost/dashboard/run_dashboard.sh
```

Open `http://GAMEHOST_IP:8501` in a browser. The script starts Streamlit
with network access on its default port 8501. The theme is defined in
`.streamlit/config.toml`. Refresh runs every five seconds while the browser
session is active, including while the archive is empty.

## Activity views

- **Attack & defense timeline:** paired attacker tool executions alongside defender
  decision counts on a shared UTC time axis. Click an execution bar or start
  point to open its inspector. The latest 60 executions are plotted; all
  executions intersecting the selected window remain in the selector.
- **Defender traffic:** allowed, blocked, and classifier-error decisions per
  interval, including zero-count intervals. Forwarded response events do not
  count as additional requests. Boundary intervals can be partial; zero means
  no recorded decisions, not confirmed service availability.
- **Endpoint activity:** the 15 busiest recorded routes, broken down by decision.
  Click a cell for the latest 100 events for that route in the current window.
  Click empty chart space to clear the selection.
- **Execution inspector:** tool, target, task/process IDs, duration, exit status,
  and related attacker events joined by exact task/tool IDs. Related events may
  extend beyond the selected window; the latest 100 are displayed.
- **Event investigation:** the latest 500 events in the selected window, with
  an actor filter. Streamlit tables provide CSV download and search.

The time selector covers the latest hour, latest 24 hours, or all dated logs.
Windows end at the latest event in the archive, so historical sessions can be
reviewed. Last-event timestamps/ages for each agent are shown separately and
are not liveness probes. Invalid/missing timestamps are excluded from charts
with a warning. Time buckets grow with the selected period to bound chart size.

Tool calls are paired by `run_id` and `tool_call_id`, including executions that
started before the selected window. Missing IDs remain separate observations;
result-only observations use recorded duration where available. "No result
logged" does not prove that a tool is still running. Boss delegation and
subagent status events are available in the inspector but do not count as
actual tool executions.

Shared timing does not establish an attack/request relationship. A completed
tool, successful subagent task, allowed request, or defender block is not a
verified attack outcome. Classifier errors block requests but are distinct
from detections. Engagement IDs, cross-agent request correlation, labelled
traffic, and independently verified objective events remain future work.

## Local preview

To read an alternative directory without changing Vector, set
`PURPLEAI_EVENTS_DIR` to a folder containing `events-*.jsonl` archives:

```bash
PURPLEAI_EVENTS_DIR=/path/to/archives bash src/gamehost/dashboard/run_dashboard.sh
```

This reads only that directory; example files are never mixed into live data.
The tracked sample fixture illustrates the envelope and older action names;
traffic charts use the current `request_decision` vocabulary.

## Diagnostics

```bash
sudo systemctl status vector --no-pager
sudo journalctl -u vector -n 40 --no-pager
ls -l /var/log/purpleai/collected/
```

If the dashboard is empty, check the Vector services and source file
paths. The account running the dashboard needs read access to the archive
files and search access to their parent directories. The tracked
`dashboard/data/sample_events.jsonl` is an example; the live dashboard
reads Vector's archives. The legacy local `dashboard/data/events.jsonl`
is ignored by Git.

See [Vector setup](../../../deploy/vector/README.md) for the pipeline and
[event format](../../../docs/event-format.md) for the event envelope.
