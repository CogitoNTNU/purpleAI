"""Snapshot reuse must retain ordering, timestamps and exact source references."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/gamehost/dashboard"))
from live_data import LiveData


def test_normalization_is_incremental_and_old_snapshots_are_immutable(tmp_path):
    path = tmp_path / "events-test.jsonl"
    path.write_text(
        json.dumps({"event_id": "one", "timestamp": "2026-10-27T12:00:00Z"}) + "\n"
    )
    source = LiveData(tmp_path)
    first = source.refresh()
    assert source.refresh() is first
    with path.open("a") as stream:
        stream.write(
            json.dumps(
                {
                    "event_id": "two",
                    "timestamp": "2026-10-27T11:00:00Z",
                    "duration_ms": 10,
                }
            )
            + "\n"
        )
    second = source.refresh()
    assert first.event_id.tolist() == ["one"]
    assert second.event_id.tolist() == ["two", "one"]
    assert second.time.notna().all()
    assert second.index.tolist() == [0, 1]
    path.write_text('{"event_id":"replacement"}\n')
    assert source.refresh().event_id.tolist() == ["replacement"]
