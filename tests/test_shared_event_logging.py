"""The shared sender preserves local events when delivery fails."""

import json
import logging
from unittest.mock import patch

from purpleai.event_logging import EventSender


def test_failed_delivery_sends_once_per_event_and_warns_once(capsys, caplog):
    sender = EventSender(
        "defender",
        "defender",
        url="http://collector:8765/events",
        token="private-token",
    )
    with patch(
        "purpleai.event_logging.urlopen", side_effect=OSError("private-token")
    ) as opened:
        sender.emit("request_decision", status="model_error", model_http_status=None)
        sender.emit("request_decision", status="forwarded", http_status=200)
    local = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(local) == opened.call_count == 2
    assert local[0]["model_http_status"] is None
    assert local[0]["run_id"] == local[1]["run_id"]
    assert local[0]["event_id"] != local[1]["event_id"]
    for call, event in zip(opened.call_args_list, local):
        assert call.kwargs["timeout"] == 0.5
        assert json.loads(call.args[0].data) == event
        assert call.args[0].get_header("Authorization") == "Bearer private-token"
    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1 and "defender" in warnings[0].message
    assert "private-token" not in caplog.text


def test_local_events_do_not_send_without_collector(capsys):
    sender = EventSender("nmap-agent", "attacker")
    with patch("purpleai.event_logging.urlopen") as opened:
        sender.emit("task_start", status="started")
    assert json.loads(capsys.readouterr().out)["status"] == "started"
    opened.assert_not_called()
