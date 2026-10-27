"""Operational counters must not treat lifecycle events as successful attacks."""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_counts_calls_errors_and_defender_blocks(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "src/gamehost/dashboard"))
    import event_store

    monkeypatch.setattr(event_store, "EVENTS_DIR", tmp_path)
    records = [
        {"actor": "attacker", "action": "task_start", "status": "started"},
        {"actor": "attacker", "action": "tool_call", "status": "started"},
        {"actor": "attacker", "action": "tool_result", "status": "completed"},
        {"actor": "attacker", "action": "tool_call", "status": "started"},
        {"actor": "attacker", "action": "tool_result", "status": "timeout"},
        {"actor": "attacker", "action": "subagent_status", "status": "success"},
        {"actor": "defender", "action": "request_decision", "status": "blocked"},
        {"actor": "defender", "action": "request_decision", "status": "allowed"},
    ]
    (tmp_path / "events-2026-10-27.jsonl").write_text(
        "".join(
            json.dumps({**record, "timestamp": "2026-10-27T12:00:00Z"}) + "\n"
            for record in records
        )
    )
    app = AppTest.from_file(str(ROOT / "src/gamehost/dashboard/dashboard.py")).run(
        timeout=20
    )
    assert not app.exception
    assert {metric.label: metric.value for metric in app.metric} == {
        "Tool executions started": "2",
        "Requests inspected": "2",
        "Classifier errors": "0",
    }


def test_dashboard_empty_then_new_events_and_filters(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "src/gamehost/dashboard"))
    monkeypatch.setenv("PURPLEAI_EVENTS_DIR", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "src/gamehost/dashboard/dashboard.py")).run()
    assert not app.exception
    assert "Waiting for Vector" in app.info[0].value
    records = [
        {
            "timestamp": "2026-10-26T10:00:00Z",
            "actor": "defender",
            "action": "request_decision",
            "status": "blocked",
            "path": "/old",
        },
        {
            "timestamp": "2026-10-27T12:00:00Z",
            "actor": "defender",
            "action": "request_decision",
            "status": "error",
            "path": "/new",
        },
        {
            "timestamp": "not-a-date",
            "actor": "defender",
            "action": "request_decision",
            "status": "blocked",
        },
    ]
    (tmp_path / "events-test.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in records)
    )
    app.run()
    assert not app.exception
    assert {metric.label: metric.value for metric in app.metric}[
        "Requests inspected"
    ] == "1"
    assert "invalid timestamps" in app.warning[0].value
    app.selectbox[0].select("All logs").run()
    assert not app.exception
    assert {metric.label: metric.value for metric in app.metric}[
        "Requests inspected"
    ] == "2"
    app.selectbox[1].select("attacker").run()
    assert not app.exception
    assert app.dataframe[-1].value.empty
