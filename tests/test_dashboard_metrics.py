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
        "".join(json.dumps(record) + "\n" for record in records)
    )
    app = AppTest.from_file(str(ROOT / "src/gamehost/dashboard/dashboard.py")).run(
        timeout=20
    )
    assert not app.exception
    assert {metric.label: metric.value for metric in app.metric} == {
        "Attacker Tool Calls": "2",
        "Tool Errors / Timeouts": "1",
        "Defender Requests Blocked": "1",
        "Total Events": "8",
    }
