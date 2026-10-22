"""Dashboard ingestion follows Vector's daily archive layout."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dashboard_event_store", ROOT / "src/gamehost/dashboard/event_store.py"
)
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


def test_daily_archives_are_sorted_and_retries_are_deduplicated(tmp_path):
    early = {
        "event_id": "one",
        "timestamp": "2026-10-19T12:00:00+00:00",
        "actor": "attacker",
    }
    late = {
        "event_id": "two",
        "timestamp": "2026-10-20T12:00:00+00:00",
        "actor": "defender",
    }
    (tmp_path / "events-2026-10-19.jsonl").write_text(json.dumps(early) + "\n")
    (tmp_path / "events-2026-10-20.jsonl").write_text(
        json.dumps(late) + "\n" + json.dumps(early) + '\ninvalid\n[]\nnull\n{"partial":'
    )
    (tmp_path / "sample_events.jsonl").write_text(
        json.dumps({"event_id": "sample"}) + "\n"
    )
    assert store.load_events(tmp_path) == [early, late]


def test_refresh_picks_up_first_event_and_completed_partial_line(tmp_path):
    directory = tmp_path / "collected"
    assert store.load_events(directory) == []
    directory.mkdir()
    path = directory / "events-2026-10-20.jsonl"
    path.write_text('{"event_id": "one", "action":')
    assert store.load_events(directory) == []
    with path.open("a") as stream:
        stream.write(' "task_start"}\n')
    assert store.load_events(directory) == [{"event_id": "one", "action": "task_start"}]


def test_default_path_matches_vector_archives(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "EVENTS_DIR", tmp_path)
    (tmp_path / "events-2026-10-20.jsonl").write_text('{"event_id":"one"}\n')
    assert store.load_events() == [{"event_id": "one"}]
