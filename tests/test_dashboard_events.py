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


def test_incremental_polls_read_only_new_bytes_and_skip_unchanged_files(tmp_path):
    path = tmp_path / "events-today.jsonl"
    path.write_text(
        "".join(json.dumps({"event_id": str(i)}) + "\n" for i in range(1000))
    )
    reader = store.EventArchive(tmp_path)
    assert len(reader.refresh()) == 1000
    cold_bytes = reader.bytes_read
    revision = reader.revision
    assert len(reader.refresh()) == 1000
    assert reader.bytes_read == 0
    assert reader.revision == revision
    with path.open("a") as stream:
        stream.write('{"event_id":"new"}\n')
    assert len(reader.refresh()) == 1001
    assert reader.appended == [{"event_id": "new"}]
    assert not reader.rebuilt
    assert reader.bytes_read < cold_bytes / 10


def test_incremental_partial_writes_duplicates_rotation_and_retention(tmp_path):
    path = tmp_path / "events-today.jsonl"
    path.write_text('{"event_id":"one"}\n{"event_id":')
    reader = store.EventArchive(tmp_path)
    assert reader.refresh() == [{"event_id": "one"}]
    with path.open("a") as stream:
        stream.write('"two"}\n{"event_id":"one"}\n')
    assert reader.refresh() == [{"event_id": "one"}, {"event_id": "two"}]
    assert reader.appended == [{"event_id": "two"}]
    path.rename(tmp_path / "events-old.jsonl")
    path.write_text('{"event_id":"three"}\n')
    assert {row["event_id"] for row in reader.refresh()} == {"one", "two", "three"}
    assert reader.rebuilt
    (tmp_path / "events-old.jsonl").unlink()
    assert reader.refresh() == [{"event_id": "three"}]
    path.write_text('{"event_id":"other"}\n')  # Same-size in-place replacement.
    assert reader.refresh() == [{"event_id": "other"}]
    path.write_text('{"event_id":"rewritten-longer"}\n')
    assert reader.refresh() == [{"event_id": "rewritten-longer"}]
    path.write_text("")
    assert reader.refresh() == []


def test_incremental_reader_retries_non_ascii_partial_and_invalid_lines(tmp_path):
    path = tmp_path / "events-test.jsonl"
    data = '{"event_id":"one","path":"/bær"}\n'.encode()
    path.write_bytes(b"invalid\n[]\n" + data[:-3])
    reader = store.EventArchive(tmp_path)
    assert reader.refresh() == []
    with path.open("ab") as stream:
        stream.write(data[-3:])
    assert reader.refresh() == [{"event_id": "one", "path": "/bær"}]
