"""Follow live agent activity and investigate historical Vector events."""

import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from activity import (
    age_label,
    decisions,
    endpoint_counts,
    event_frame,
    event_summary,
    executions,
    traffic,
)
from charts import defense_timeline, execution_chart, heatmap_chart, traffic_chart
from event_store import EVENTS_DIR, load_events

st.set_page_config(
    page_title="PurpleAI · Activity", layout="wide", page_icon=":material/monitoring:"
)
st.markdown(
    """<style>
[data-testid="stMainBlockContainer"] {padding-top: 2rem; padding-bottom: 3rem;}
</style>""",
    unsafe_allow_html=True,
)
st.title("PurpleAI")
st.caption("Live attacker activity and defender decisions")


def render_inspector(runs, frame, picked):
    if runs.empty:
        st.info("No tool executions recorded in this window.")
        return
    options = runs.execution.tolist()
    if picked != st.session_state.get("last_chart_pick"):
        if picked in options:
            st.session_state["inspected_execution"] = picked
        st.session_state["last_chart_pick"] = picked
    if st.session_state.get("inspected_execution") not in options:
        st.session_state["inspected_execution"] = options[-1]
    labels = runs.set_index("execution").label.to_dict()
    choice = st.selectbox(
        "Execution details", options, format_func=labels.get, key="inspected_execution"
    )
    item = runs[runs.execution == choice].iloc[0]
    duration = (
        f"{item.duration_ms / 1000:,.1f}s"
        if pd.notna(item.duration_ms)
        else "Not recorded"
    )
    columns = st.columns(3)
    columns[0].write(f"**Result:** {item.result}")
    columns[1].write(f"**Duration:** {duration}")
    columns[2].write(f"**Target:** {item.target or 'Not recorded'}")
    if item.result == "No end event":
        st.caption(
            "Only the start was logged. This does not establish that the tool is still running."
        )
    related = frame.loc[item.event_indices]
    if item.task_id:
        related = frame[
            (frame.actor == "attacker")
            & ((frame.task_id == item.task_id) | frame.index.isin(item.event_indices))
        ]
    with st.expander("Task IDs and related events"):
        st.json(
            {
                "run_id": item.run_id,
                "task_id": item.task_id,
                "tool_call_id": item.tool_call_id,
                "exit_code": None if pd.isna(item.exit_code) else item.exit_code,
                "error_type": None if pd.isna(item.error_type) else item.error_type,
            }
        )
        st.caption(
            "Joined by exact task/tool IDs. Related events can extend beyond this time window; latest 100 shown."
        )
        st.dataframe(related.drop(columns="time").tail(100), hide_index=True)


@st.fragment(run_every=5)
def render_events():
    directory = Path(os.environ.get("PURPLEAI_EVENTS_DIR", str(EVENTS_DIR)))
    frame = event_frame(load_events(directory))
    if frame.empty:
        st.info(
            f"Waiting for Vector events in {directory}. Refreshing every 5 seconds."
        )
        return
    now = pd.Timestamp.now(tz="UTC")
    dated = frame[frame.time.notna()]
    invalid = int(frame.time.isna().sum())
    if invalid:
        st.warning(
            f"{invalid} events have missing or invalid timestamps and are excluded from time-based views."
        )
    if dated.empty:
        st.dataframe(frame.drop(columns="time").tail(500), hide_index=True)
        return

    period = st.selectbox(
        "Time range",
        [
            "Live · last 15 minutes",
            "Live · last hour",
            "Latest hour of logs",
            "Latest 24 hours of logs",
            "All logs",
        ],
    )
    live = period.startswith("Live")
    end = now if live else dated.time.max()
    span = (
        pd.Timedelta(minutes=15)
        if period == "Live · last 15 minutes"
        else pd.Timedelta(hours=24 if period == "Latest 24 hours of logs" else 1)
    )
    start = dated.time.min() if period == "All logs" else end - span
    if start == end:
        start -= pd.Timedelta(seconds=1)
    scope = dated[(dated.time >= start) & (dated.time <= end)]
    anchor = (
        "Live window · follows the clock"
        if live
        else "History · ends at the latest logged event"
    )
    st.caption(f"{start:%d %b %H:%M}–{end:%H:%M} UTC · {anchor} · Refreshes every 5s")

    # Latest action is global and explicitly dated, even when reviewing history.
    for column, actor in zip(st.columns(2, gap="large"), ["attacker", "defender"]):
        rows = dated[
            (dated.actor == actor)
            & dated.action.isin(
                [
                    "tool_call",
                    "tool_result",
                    "request_decision",
                    "task_start",
                    "task_end",
                    "subagent_status",
                ]
            )
        ]
        with column:
            st.write(f"**{actor.title()} · latest logged action**")
            if rows.empty:
                st.caption("No actions recorded")
            else:
                row = rows.sort_values("time").iloc[-1]
                st.write(event_summary(row))
                st.caption(
                    f"{age_label(row.time, now)} · {row.time:%d %b %H:%M:%S} UTC"
                )

    frequency = (
        "30s"
        if end - start <= pd.Timedelta(minutes=20)
        else "1min"
        if end - start <= pd.Timedelta(hours=2)
        else "15min"
        if end - start <= pd.Timedelta(days=2)
        else "1h"
    )
    if (end - start) / pd.Timedelta(frequency) > 1500:
        days = max(1, int((end - start) / pd.Timedelta(days=1500)) + 1)
        frequency = f"{days}D"
    trend = traffic(scope, start, end, frequency)
    requests = decisions(scope)
    calls = scope[(scope.actor == "attacker") & (scope.action == "tool_call")]
    columns = st.columns(4)
    columns[0].metric("Tool executions started", len(calls))
    columns[1].metric("Requests inspected", len(requests))
    columns[2].metric("Requests blocked", int((requests.status == "blocked").sum()))
    columns[3].metric("Classifier errors", int((requests.status == "error").sum()))
    if scope.empty:
        st.info(
            "No dated events in this window. The latest actions above show when logging last recorded activity; select a history range to review older events."
        )

    overview, investigation = st.tabs(["Activity", "Event investigation"])
    with overview:
        st.subheader("Recent attack & defense activity")
        st.caption(
            "Red: tool execution · Blue: allowed · Pink: blocked · Amber: errors/timeouts · Purple diamond: start without an end event. Shared timing does not link a request to an attack."
        )
        runs = executions(frame, start, end)
        picked = None
        if runs.empty:
            st.altair_chart(
                defense_timeline(trend, start, end).properties(height=120),
                width="stretch",
            )
            st.caption("No tool executions with observed activity in this window.")
        else:
            displayed = runs.sort_values("plot_start").tail(12)
            lanes = [
                "Defender · Allowed",
                "Defender · Blocked",
                "Defender · Classifier error",
            ] + displayed.sort_values("plot_start", ascending=False).label.tolist()
            timeline = (
                alt.layer(
                    execution_chart(displayed, start, end, lanes),
                    defense_timeline(trend, start, end, lanes),
                )
                .properties(height=max(220, len(displayed) * 30 + 110))
                .resolve_scale(color="independent")
            )
            event = st.altair_chart(
                timeline, width="stretch", key="execution_timeline", on_select="rerun"
            )
            selected = event.selection.get("execution_pick", [])
            picked = selected[0].get("execution") if selected else None
            st.caption(
                f"Latest {len(displayed)} of {len(runs)} executions with activity in this window. Click a bar or point for details below. Completion describes tool execution, not attack success."
            )

        st.subheader("Defender traffic over time")
        mode = st.radio(
            "Traffic display", ["Request counts", "Decision share"], horizontal=True
        )
        st.altair_chart(
            traffic_chart(trend, share=mode == "Decision share"), width="stretch"
        )
        st.caption(
            f"Recorded decisions per {frequency}; boundary intervals can be partial. Classifier errors also block requests. Zero counts mean no logged decisions, not proven availability."
        )

        st.subheader("Which endpoints are receiving traffic?")
        endpoints = endpoint_counts(scope)
        if endpoints.empty:
            st.info("No defender decisions in this window.")
        else:
            top = endpoints.groupby("path").requests.sum().nlargest(10).index
            chart_data = endpoints[endpoints.path.isin(top)]
            st.caption(
                f"Top {len(top)} of {endpoints.path.nunique()} routes · Counts are shown in every cell · Click a route to inspect its events"
            )
            route_event = st.altair_chart(
                heatmap_chart(chart_data),
                width="stretch",
                key="endpoint_heatmap",
                on_select="rerun",
            )
            selected_routes = route_event.selection.get("endpoint", [])
            if selected_routes and selected_routes[0].get("path") in top:
                route = selected_routes[0]["path"]
                with st.expander(
                    f"Events for {route} · double-click the chart to clear",
                    expanded=True,
                ):
                    rows = scope[
                        (scope.actor == "defender")
                        & (scope.path.replace("", "(unrecorded path)") == route)
                    ]
                    st.dataframe(
                        rows[["timestamp", "action", "status", "request_id"]]
                        .tail(100)
                        .iloc[::-1],
                        hide_index=True,
                    )

        st.subheader("Inspect an attacker execution")
        render_inspector(runs, frame, picked)
        with st.expander("Older starts without an end event"):
            # Excluded from the timeline: no evidence they continued into this window.
            older = executions(frame, dated.time.min(), end)
            if not older.empty:
                older = older[(older.result == "No end event") & (older.start < start)]
            if older.empty:
                st.caption("None recorded before this window.")
            else:
                st.caption(
                    "These starts have no matching result. They are not shown as ongoing scans."
                )
                st.dataframe(
                    older[["start", "tool", "target", "run_id"]].tail(50),
                    hide_index=True,
                )

    with investigation:
        actor = st.selectbox("Actor", ["All", "attacker", "defender"])
        records = scope if actor == "All" else scope[scope.actor == actor]
        st.caption(f"Latest 500 of {len(records):,} events in this time window")
        st.dataframe(
            records.drop(columns="time").tail(500).iloc[::-1],
            width="stretch",
            hide_index=True,
        )


render_events()
