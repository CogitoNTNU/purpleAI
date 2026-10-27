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
    result = counts.reindex(index, fill_value=0).rename("requests").reset_index()
    result["bucket_end"] = result.bucket + pd.tseries.frequencies.to_offset(frequency)
    return result


def endpoint_counts(frame):
    rows = decisions(frame)
    rows["path"] = rows.path.replace("", "(unrecorded path)")
    counts = rows.groupby(["path", "status"]).size()
    index = pd.MultiIndex.from_product(
        [rows.path.unique(), DECISIONS], names=["path", "status"]
    )
    result = counts.reindex(index, fill_value=0).rename("requests").reset_index()
    return result


def executions(frame, start, end):
    """Pair exact tool IDs within a process, including starts before the window."""
    rows = frame[
        (frame.actor == "attacker")
        & frame.action.isin(["tool_call", "tool_result"])
        & frame.time.notna()
    ].sort_values("time")
    paired = {}
    for position, (source_index, row) in enumerate(rows.iterrows()):
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
                "tool_call_id": row.tool_call_id,
                "event_indices": [],
                "status": "No result logged",
                "duration_ms": None,
                "exit_code": None,
                "error_type": "",
            },
        )
        item["event_indices"].append(source_index)
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
    for number, item in enumerate(paired.values(), 1):
        finish = item["end"] if item["end"] is not None else end
        if (
            item["start"] is None
            or item["start"] > end
            or finish < start
            or (item["end"] is None and item["start"] < start)
        ):
            continue
        item["plot_start"] = max(item["start"], start)
        # Missing end events are observations, not evidence of continuous execution.
        item["plot_end"] = (
            max(item["plot_start"], min(finish, end))
            if item["end"] is not None
            else item["plot_start"]
        )
        item["result"] = execution_result(item["status"])
        item["label"] = (
            f"{item['tool']} #{number} · {item['start']:%H:%M:%S} · {item['result']}"
        )
        item["lane"] = f"{item['tool']} · {item['execution'][-8:]}"
        result.append(item)
    return pd.DataFrame(result)


def execution_result(status):
    """Human labels describe execution, never exploitation."""
    return {
        "completed": "Completed",
        "error": "Error",
        "timeout": "Timed out",
        "cancelled": "Cancelled",
        "No result logged": "No end event",
    }.get(status, "Start missing" if "start not logged" in status else "Unknown")


def age_label(timestamp, now):
    if pd.isna(timestamp):
        return "No dated events"
    seconds = max(0, int((now - timestamp).total_seconds()))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def event_summary(row):
    action, status = row.action, row.status
    if action == "tool_call":
        return f"{row.tool or 'Tool'} started"
    if action == "tool_result":
        return f"{row.tool or 'Tool'} · {execution_result(status).lower()}"
    if action == "request_decision":
        label = {
            "allowed": "Allowed",
            "blocked": "Blocked",
            "error": "Classifier error",
        }.get(status, status)
        return f"{label} · {row.get('method', '')} {row.path}".strip()
    return f"{action.replace('_', ' ').capitalize()} · {status}"
