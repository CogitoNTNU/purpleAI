"""Prepare chart data without inferring attack outcomes or cross-agent causality."""

import pandas as pd

DECISIONS = ["allowed", "blocked", "error"]


def event_frame(events):
    frame = pd.DataFrame(events)
    for column in [
        "timestamp",
        "actor",
        "action",
        "status",
        "run_id",
        "task_id",
        "tool_call_id",
        "tool",
        "target",
        "path",
        "request_id",
        "event_id",
    ]:
        if column not in frame:
            frame[column] = ""
        else:
            frame[column] = frame[column].fillna("")
    frame["time"] = pd.to_datetime(
        frame["timestamp"], utc=True, errors="coerce", format="mixed"
    )
    return frame


def decisions(frame):
    return frame[
        (frame.actor == "defender")
        & (frame.action == "request_decision")
        & frame.status.isin(DECISIONS)
        & frame.time.notna()
    ].copy()


def traffic(frame, start, end, frequency):
    """One decision per request; never count the forwarded result a second time."""
    rows = decisions(frame)
    rows = rows[(rows.time >= start) & (rows.time <= end)]
    if not rows.empty:
        rows = rows.copy()
        rows["bucket"] = rows.time.dt.floor(frequency)
        counts = rows.groupby(["bucket", "status"]).size()
    else:
        counts = pd.Series(dtype=int)
    buckets = pd.date_range(
        start.floor(frequency), end.floor(frequency), freq=frequency
    )
    index = pd.MultiIndex.from_product([buckets, DECISIONS], names=["bucket", "status"])
    return counts.reindex(index, fill_value=0).rename("requests").reset_index()


def endpoint_counts(frame):
    rows = decisions(frame)
    rows["path"] = rows.path.replace("", "(unrecorded path)")
    return rows.groupby(["path", "status"]).size().rename("requests").reset_index()


def executions(frame, start, end):
    """Pair exact tool IDs within a process, including starts before the window."""
    rows = frame[
        (frame.actor == "attacker")
        & frame.action.isin(["tool_call", "tool_result"])
        & frame.time.notna()
    ].sort_values("time")
    paired = {}
    for position, (_, row) in enumerate(rows.iterrows()):
        # Missing IDs cannot be safely paired with another event.
        key = (
            f"{row.run_id}:{row.tool_call_id}"
            if row.tool_call_id
            else f"unpaired:{position}"
        )
        item = paired.setdefault(
            key,
            {
                "execution": key,
                "start": None,
                "end": None,
                "tool": row.tool or "Unknown tool",
                "run_id": row.run_id,
                "task_id": row.task_id,
                "target": row.target,
                "status": "No result logged",
                "duration_ms": None,
                "exit_code": None,
                "error_type": "",
            },
        )
        if row.action == "tool_call":
            item["start"] = row.time
        else:
            item.update(
                end=row.time,
                status=row.status or "Unknown result",
                duration_ms=row.get("duration_ms"),
                exit_code=row.get("exit_code"),
                error_type=row.get("error_type", ""),
            )
            if item["start"] is None:
                duration = pd.to_numeric(row.get("duration_ms"), errors="coerce")
                item["start"] = (
                    row.time - pd.Timedelta(milliseconds=float(duration))
                    if pd.notna(duration) and duration >= 0
                    else row.time
                )
                item["status"] += " (start not logged)"
    result = []
    for item in paired.values():
        finish = item["end"] if item["end"] is not None else end
        if item["start"] is None or item["start"] > end or finish < start:
            continue
        item["plot_start"] = max(item["start"], start)
        item["plot_end"] = max(item["plot_start"], min(finish, end))
        item["lane"] = f"{item['tool']} · {item['execution'][-8:]}"
        result.append(item)
    return pd.DataFrame(result)
