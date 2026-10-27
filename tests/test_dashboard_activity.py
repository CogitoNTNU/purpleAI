"""Charts preserve request grain and exact execution correlation."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/gamehost/dashboard"))
from activity import endpoint_counts, event_frame, executions, traffic
from charts import defense_timeline, execution_chart, heatmap_chart, traffic_chart

START = pd.Timestamp("2026-10-27T12:00:00Z")
END = START + pd.Timedelta(minutes=2)


def test_request_results_do_not_inflate_decisions_and_gaps_are_zero():
    frame = event_frame(
        [
            {
                "timestamp": str(START),
                "actor": "defender",
                "action": "request_decision",
                "status": "allowed",
                "path": "/login",
            },
            {
                "timestamp": str(START),
                "actor": "defender",
                "action": "request_result",
                "status": "returned",
                "path": "/login",
            },
            {
                "timestamp": str(END),
                "actor": "defender",
                "action": "request_decision",
                "status": "error",
                "path": "/login",
            },
            {
                "timestamp": "bad",
                "actor": "defender",
                "action": "request_decision",
                "status": "blocked",
            },
        ]
    )
    counts = traffic(frame, START, END, "1min")
    assert counts.requests.sum() == 2
    assert len(counts) == 9
    assert counts[counts.bucket == START + pd.Timedelta(minutes=1)].requests.sum() == 0
    assert endpoint_counts(frame).requests.sum() == 2
    traffic_chart(counts).to_dict()
    defense_timeline(counts, START, END).to_dict()
    heatmap_chart(endpoint_counts(frame)).to_dict()


def test_pairing_uses_process_and_tool_ids_and_keeps_window_overlap():
    records = [
        {
            "timestamp": str(START - pd.Timedelta(seconds=10)),
            "actor": "attacker",
            "run_id": "one",
            "action": "tool_call",
            "tool_call_id": "same",
            "tool": "sqlmap",
        },
        {
            "timestamp": str(START + pd.Timedelta(seconds=10)),
            "actor": "attacker",
            "run_id": "one",
            "action": "tool_result",
            "tool_call_id": "same",
            "status": "completed",
            "duration_ms": 20000,
        },
        {
            "timestamp": str(START),
            "actor": "attacker",
            "run_id": "two",
            "action": "tool_call",
            "tool_call_id": "same",
            "tool": "sqlmap",
        },
        {
            "timestamp": str(START),
            "actor": "attacker",
            "action": "tool_call",
            "tool": "other",
        },
        {
            "timestamp": str(END),
            "actor": "attacker",
            "action": "tool_result",
            "tool": "other",
            "status": "error",
        },
    ]
    result = executions(event_frame(records), START, END)
    assert len(result) == 4  # ID-less events are not paired by guesswork.
    paired = result[result.execution == "one:same"].iloc[0]
    assert paired.plot_start == START
    assert paired.duration_ms == 20000
    assert result[result.execution == "two:same"].iloc[0].status == "No result logged"
    execution_chart(result, START, END).to_dict()


def test_empty_and_invalid_events_are_safe():
    assert event_frame([]).empty
    frame = event_frame(
        [{"timestamp": "invalid", "actor": "attacker", "action": "tool_call"}]
    )
    assert executions(frame, START, END).empty
    assert traffic(frame, START, END, "1min").requests.sum() == 0
