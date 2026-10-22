"""Read the daily JSONL archives written by gamehost Vector."""

import json
from pathlib import Path

EVENTS_DIR = Path("/var/log/purpleai/collected")


def load_events(directory=None):
    """Load archives, tolerate partial lines, and collapse delivery retries."""
    directory = Path(directory) if directory is not None else EVENTS_DIR
    events, seen = [], set()
    for path in sorted(directory.glob("events-*.jsonl")):
        try:
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    event_id = event.get("event_id")
                    if isinstance(event_id, str):
                        if event_id in seen:
                            continue
                        seen.add(event_id)
                    events.append(event)
        except FileNotFoundError:
            # A retention task can remove an archive during a refresh.
            continue
    return sorted(events, key=lambda event: str(event.get("timestamp", "")))
