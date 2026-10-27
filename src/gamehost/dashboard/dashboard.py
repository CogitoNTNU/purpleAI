"""Explore attacker activity and defender decisions from Vector archives."""

import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from activity import decisions, endpoint_counts, event_frame, executions, traffic
from charts import defense_timeline, execution_chart, heatmap_chart, traffic_chart
from event_store import EVENTS_DIR, load_events

st.set_page_config(
    page_title="PurpleAI · Activity", layout="wide", page_icon=":material/monitoring:"
)
st.title("PurpleAI")
st.caption("Agent activity & defense monitoring")


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
    health = st.columns(2)
    for column, actor in zip(health, ["attacker", "defender"]):
        latest = frame.loc[(frame.actor == actor) & frame.time.notna(), "time"].max()
        with column:
            if pd.isna(latest):
                st.caption(f"{actor.title()} · No dated events received")
            else:
                age = max(0, int((now - latest).total_seconds()))
                st.caption(
                    f"{actor.title()} · Last event {age:,}s ago · {latest:%Y-%m-%d %H:%M:%S} UTC"
                )

    invalid = int(frame.time.isna().sum())
    if invalid:
        st.warning(
            f"{invalid} events have missing or invalid timestamps and are excluded from time-based views."
        )
    dated = frame[frame.time.notna()]
    if dated.empty:
        st.dataframe(frame.drop(columns="time"), hide_index=True)
        return

    period = st.selectbox(
        "Time range", ["Latest hour of logs", "Latest 24 hours of logs", "All logs"]
    )
    end = dated.time.max()
    start = (
        dated.time.min()
        if period == "All logs"
        else end - pd.Timedelta(hours=1 if period == "Latest hour of logs" else 24)
    )
    if start == end:
        start -= pd.Timedelta(seconds=1)
    scope = dated[(dated.time >= start) & (dated.time <= end)]
    st.caption(
        f"{start:%Y-%m-%d %H:%M:%S} — {end:%Y-%m-%d %H:%M:%S} UTC · Window ends at the latest logged event"
    )
    frequency = (
        "1min"
        if (end - start) <= pd.Timedelta(hours=2)
        else "15min"
        if (end - start) <= pd.Timedelta(days=2)
        else "1h"
    )
    # Bound aggregation even for long-running archives.
    if (end - start) / pd.Timedelta(frequency) > 1500:
        frequency = "1D"
    trend = traffic(scope, start, end, frequency)
    requests = decisions(scope)
    calls = scope[(scope.actor == "attacker") & (scope.action == "tool_call")]
    columns = st.columns(3)
    columns[0].metric("Tool executions started", len(calls))
    columns[1].metric("Requests inspected", len(requests))
    columns[2].metric("Classifier errors", int((requests.status == "error").sum()))

    overview, investigation = st.tabs(["Activity", "Event investigation"])
    with overview:
        st.subheader("Attack & defense timeline")
        st.caption(
            "Shared timing is context, not proof that a defender request belongs to an attack. Tool completion does not prove exploitation."
        )
        runs = executions(frame, start, end)
        if runs.empty:
            st.info("No logged tool executions in this window.")
            picked = None
        else:
            displayed = runs.sort_values("plot_start").tail(60)
            if len(runs) > 60:
                st.caption(
                    f"Showing the latest 60 of {len(runs)} executions; all remain available in the inspector."
                )
            event = st.altair_chart(
                alt.layer(
                    execution_chart(displayed, start, end),
                    defense_timeline(trend, start, end),
                )
                .properties(height=max(260, min(750, len(displayed) * 27 + 120)))
                .resolve_scale(color="independent"),
                width="stretch",
                key="execution_timeline",
                on_select="rerun",
            )
            selected = event.selection.get("execution_pick", [])
            picked = selected[0].get("execution") if selected else None
        if runs.empty:
            st.altair_chart(defense_timeline(trend, start, end), width="stretch")

        left, right = st.columns([3, 2], gap="large")
        with left:
            st.subheader("Defender traffic")
            st.caption(
                f"Decision counts per {frequency}. Classifier errors block requests but are shown separately from detections."
            )
            st.altair_chart(traffic_chart(trend), width="stretch")
        with right:
            st.subheader("Endpoint activity")
            endpoints = endpoint_counts(scope)
            if endpoints.empty:
                st.info("No defender decisions in this window.")
            else:
                top = endpoints.groupby("path").requests.sum().nlargest(15).index
                chart_data = endpoints[endpoints.path.isin(top)]
                st.caption(
                    f"Top {len(top)} of {endpoints.path.nunique()} routes by request count. Click a cell to inspect that route."
                )
                route_event = st.altair_chart(
                    heatmap_chart(chart_data),
                    width="stretch",
                    key="endpoint_heatmap",
                    on_select="rerun",
                )
                selected_routes = route_event.selection.get("endpoint", [])
                if selected_routes:
                    route = selected_routes[0]["path"]
                    st.write(f"Route: {route}")
                    route_rows = scope[
                        (scope.actor == "defender")
                        & (scope.path.replace("", "(unrecorded path)") == route)
                    ]
                    st.dataframe(
                        route_rows[
                            ["timestamp", "action", "status", "request_id"]
                        ].tail(100),
                        hide_index=True,
                    )

        st.subheader("Execution inspector")
        if not runs.empty:
            options = runs.execution.tolist()
            if picked in options and picked != st.session_state.get("last_chart_pick"):
                st.session_state["inspected_execution"] = picked
                st.session_state["last_chart_pick"] = picked
            if st.session_state.get("inspected_execution") not in options:
                st.session_state["inspected_execution"] = options[-1]
            labels = (
                runs.set_index("execution")
                .apply(
                    lambda row: (
                        f"{row['start']:%H:%M:%S} · {row['tool']} · {row['status']} · {row.name[-8:]}"
                    ),
                    axis=1,
                )
                .to_dict()
            )
            choice = st.selectbox(
                "Select an execution or click its start point above",
                options,
                format_func=labels.get,
                key="inspected_execution",
            )
            item = runs[runs.execution == choice].iloc[0]
            details = {
                key: item[key]
                for key in [
                    "tool",
                    "status",
                    "target",
                    "run_id",
                    "task_id",
                    "duration_ms",
                    "exit_code",
                    "error_type",
                ]
            }
            st.json(
                {
                    key: None if pd.isna(value) else value
                    for key, value in details.items()
                },
                expanded=True,
            )
            # Only exact IDs establish relationships; never attach defender events by time.
            related = frame[(frame.actor == "attacker") & (frame.run_id == item.run_id)]
            if item.task_id:
                related = frame[
                    (frame.actor == "attacker")
                    & (
                        (frame.task_id == item.task_id)
                        | (
                            (frame.run_id == item.run_id)
                            & (frame.tool_call_id == choice.split(":", 1)[-1])
                        )
                    )
                ]
            else:
                related = related[related.tool_call_id == choice.split(":", 1)[-1]]
            st.caption(
                "Related attacker events use exact task/tool IDs and may extend beyond the selected time window. No result logged does not confirm the tool is still running."
            )
            st.dataframe(related.drop(columns="time").tail(100), hide_index=True)
        else:
            st.caption("Tool details will appear when execution events arrive.")

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
st.caption("Vector archives · Refreshes every 5 seconds · All chart times are UTC")
