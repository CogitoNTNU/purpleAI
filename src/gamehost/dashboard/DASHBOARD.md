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

The page shows attacker tool calls, tool errors/timeouts, defender blocked
requests, total events, and the most recent 20 events across the archives.
Boss lifecycle/delegation events do not count as tool calls. A completed
tool or successful subagent task is not a verified attack outcome.

## Diagnostics

```bash
sudo systemctl status vector --no-pager
sudo journalctl -u vector -n 40 --no-pager
ls -l /var/log/purpleai/collected/
```

If the dashboard is empty, check the Vector services and source file
paths. The account running the dashboard needs read access to the archive
files and search access to their parent directories. Sample files under
`dashboard/data/` are examples; the live dashboard reads Vector's archives.

See [Vector setup](../../../deploy/vector/README.md) for the pipeline and
[event format](../../../docs/event-format.md) for the event envelope.
