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
        {
            "actor": "attacker",
            "action": "tool_call",
            "status": "started",
            "tool_call_id": "one",
        },
        {
            "actor": "attacker",
            "action": "tool_result",
            "status": "completed",
            "tool_call_id": "one",
        },
        {
            "actor": "attacker",
            "action": "tool_call",
            "status": "started",
            "tool_call_id": "two",
        },
        {
            "actor": "attacker",
            "action": "tool_result",
            "status": "timeout",
            "tool_call_id": "two",
        },
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
    app.selectbox[0].select("Latest hour of logs").run()
    assert not app.exception
    summary = [item.value for item in app.markdown]
    assert "**RedAI.** 2 tool executions. No decisions recorded." in summary
    assert "**Unlabelled traffic.** 2 inspected · 1 blocked · 0 classifier errors." in summary
    assert any("0 target objective events and 0 attacker flag reports" in line for line in summary)



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
            "request_id": "old-request",
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
    assert app.selectbox[0].value == "Live · last 15 minutes"
    app.selectbox[0].select("Latest hour of logs").run()
    assert not app.exception
    assert any(
        "**Unlabelled traffic.** 1 inspected · 0 blocked · 1 classifier errors." == item.value
        for item in app.markdown
    )
    assert "invalid timestamps" in app.warning[0].value
    assert app.dataframe[-1].value["path"].tolist() == ["/new"]
    app.text_input[0].set_value("old-request").run()
    assert not app.exception
    assert app.dataframe[-1].value["path"].tolist() == ["/old"]


def test_refresh_controls_keep_updates_optional(tmp_path, monkeypatch):
    monkeypatch.setenv("PURPLEAI_EVENTS_DIR", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "src/gamehost/dashboard/dashboard.py")).run()
    app.toggle[0].set_value(False).run()
    assert not app.exception
    (tmp_path / "events-new.jsonl").write_text(
        '{"event_id":"one","actor":"defender","action":"request_decision","status":"allowed","timestamp":"2026-10-27T12:00:00Z"}\n'
    )
    app.button[0].click().run()
    app.selectbox[0].select("Latest hour of logs").run()
    assert not app.exception
    assert app.dataframe[-1].value["event_id"].tolist() == ["one"]
    assert any("Live updates paused" in caption.value for caption in app.caption)
