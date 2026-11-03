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
`.streamlit/config.toml`. Live updates poll every ten seconds while enabled. Turn off **Live updates**
to pause polling; **Refresh now** checks immediately. Time/view controls stay
outside the timed fragment so background polls do not redraw them.

## Review a run

- **Time range and engagement** filter the summary and execution timeline.
  Live windows follow the current clock. The history window ends at the
  latest recorded event. Select **All engagements** to include older and
  untagged events.
- **Summary** counts tool executions with activity in the selected window
  and blocked requests by recorded source (RedAI, k6, or unlabelled).
  Classifier errors are counted separately from detections.
- **Tool executions** shows the latest 12 executions in a UTC timeline.
  Click a mark or choose an execution from the dropdown. The inspector shows
  matching BlueAI decisions by `tool_call_id` and any VulnShop objective
  events linked by `request_id`, even when those events fall outside the
  selected window. Completion describes the tool process. A target event
  records a specific observation such as VulnShop serving the admin page.
- **Event search** shows recent events in the selection. Enter an exact
  request, tool call, or event ID to search across the entire archive.

The dashboard keeps older executions without correlation IDs available in
the timeline. Starts without a result appear as points.

## Local preview

To read an alternative directory without changing Vector, set
`PURPLEAI_EVENTS_DIR` to a folder containing `events-*.jsonl` archives:

```bash
PURPLEAI_EVENTS_DIR=/path/to/archives bash src/gamehost/dashboard/run_dashboard.sh
```

This reads only that directory; example files are never mixed into live data.
The tracked sample fixture illustrates the envelope and older action names;
traffic charts use the current `request_decision` vocabulary.

## Refresh performance

The running dashboard shares a `LiveData` resource per archive directory.
`EventArchive` tracks each file's identity, size, modification time, consumed
byte offset and a small checkpoint. Unchanged files are not opened; appended
records are read from the previous offset. The normalized dataframe is reused
when no new events arrive, and only new records are normalized on append.

Partial final lines wait for a newline. Replacements, truncation, in-place
rewrites and archive removal rebuild the snapshot and its deduplication state.
A lock serializes shared-resource updates; published dataframes are not mutated
in place. The original `load_events` helper remains available for one-shot reads.

Existing chart content remains opaque during a poll. The displayed "Checked"
time shows when the last update completed; pausing polling is explicit. Polling
still redraws the selected chart view, but does not reread historical JSONL or
render the unselected investigation view each time.

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
