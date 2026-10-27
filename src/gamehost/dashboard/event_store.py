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


class EventArchive:
    """Tail archives across polls, rebuilding safely on retention or replacement.

    Callers sharing an instance between threads must serialize refresh calls.
    Only newline-terminated records are consumed; partial writes are retried.
    """

    def __init__(self, directory):
        self.directory = Path(directory)
        self.files = {}
        self.events = []
        self.seen = set()
        self.revision = 0
        self.appended = []
        self.rebuilt = False
        self.bytes_read = 0

    def refresh(self):
        """Return the cached events; read suffixes only when a file changes."""
        self.bytes_read = 0
        self.appended = []
        self.rebuilt = False
        paths = sorted(self.directory.glob("events-*.jsonl"))
        reset = bool(set(self.files) - set(paths))
        self.files = {
            path: state for path, state in self.files.items() if path in paths
        }
        candidates = []
        for path in paths:
            try:
                stat = path.stat()
                identity = (stat.st_dev, stat.st_ino)
                signature = (stat.st_size, stat.st_mtime_ns)
                state = self.files.get(path)
                if (
                    state
                    and state["identity"] == identity
                    and state["signature"] == signature
                ):
                    continue
                with path.open("rb") as stream:
                    replace = (
                        state is None
                        or state["identity"] != identity
                        or stat.st_size < state["signature"][0]
                        or stat.st_size == state["signature"][0]
                    )
                    if not replace and state["offset"]:
                        # Detect an in-place rewrite even when the file has grown.
                        stream.seek(state["offset"] - len(state["checkpoint"]))
                        checkpoint = stream.read(len(state["checkpoint"]))
                        self.bytes_read += len(checkpoint)
                        replace = checkpoint != state["checkpoint"]
                    if replace:
                        reset = True
                        state = {
                            "identity": identity,
                            "offset": 0,
                            "checkpoint": b"",
                            "events": [],
                        }
                    stream.seek(state["offset"])
                    chunk = stream.read(max(0, stat.st_size - state["offset"]))
                    self.bytes_read += len(chunk)
                    for line in chunk.splitlines(keepends=True):
                        if not line.endswith(b"\n"):
                            break
                        state["offset"] += len(line)
                        try:
                            event = json.loads(line)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
                        if isinstance(event, dict):
                            state["events"].append(event)
                            candidates.append(event)
                    length = min(64, state["offset"])
                    stream.seek(state["offset"] - length)
                    state["checkpoint"] = stream.read(length)
                    self.bytes_read += length
                    state["signature"] = signature
                    self.files[path] = state
            except FileNotFoundError:
                # A rotated file will be discovered/reconciled on the next poll.
                if path in self.files:
                    del self.files[path]
                    reset = True
        if reset:
            self.events, self.seen = [], set()
            candidates = [
                event
                for path in sorted(self.files)
                for event in self.files[path]["events"]
            ]
        for event in candidates:
            event_id = event.get("event_id")
            if isinstance(event_id, str):
                if event_id in self.seen:
                    continue
                self.seen.add(event_id)
            self.appended.append(event)
        if reset or self.appended:
            self.events = sorted(
                self.events + self.appended,
                key=lambda event: str(event.get("timestamp", "")),
            )
            self.revision += 1
        self.rebuilt = reset
        return self.events
