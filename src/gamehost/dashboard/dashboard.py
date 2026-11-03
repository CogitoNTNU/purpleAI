"""Review recorded PurpleAI executions and their linked request outcomes."""

import os

import pandas as pd
import streamlit as st
from activity import decisions, executions
from charts import execution_chart
from event_store import EVENTS_DIR
from live_data import LiveData

st.set_page_config(page_title="PurpleAI", layout="wide")
st.title("PurpleAI")

controls = st.columns([3, 1, 1], vertical_alignment="bottom")
with controls[0]:
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
with controls[1]:
    automatic = st.toggle("Live updates", value=True)
with controls[2]:
    st.button("Refresh now")


@st.cache_resource(show_spinner=False, max_entries=4)
def live_data(directory):
    return LiveData(directory)


def render_summary(scope, runs):
    requests = decisions(scope)
    blocked = requests[requests.status == "blocked"]
    columns = st.columns(5)
    columns[0].metric("Tool executions", len(runs))
    columns[1].metric(
        "RedAI requests blocked", int(blocked.traffic_source.eq("redai").sum())
    )
    columns[2].metric("k6 requests blocked", int(blocked.traffic_source.eq("k6").sum()))
    columns[3].metric(
        "Unlabelled requests blocked",
        int((~blocked.traffic_source.isin(["redai", "k6"])).sum()),
    )
    columns[4].metric("Classifier errors", int(requests.status.eq("error").sum()))


def render_execution(runs, frame, start, end):
    st.subheader("Tool executions")
    if runs.empty:
        st.caption("No tool executions recorded in this selection.")
        return
    runs = runs.sort_values("plot_start")
    displayed = runs.tail(12)
    chart = execution_chart(displayed, start, end).properties(
        height=max(100, len(displayed) * 32)
    )
    event = st.altair_chart(
        chart, width="stretch", key="execution_timeline", on_select="rerun"
    )
    picks = event.selection.get("execution_pick", [])
    picked = picks[0].get("execution") if picks else None
    labels = runs.set_index("execution").label.to_dict()
    if picked != st.session_state.get("last_chart_pick"):
        if picked in labels:
            st.session_state["inspected_execution"] = picked
        st.session_state["last_chart_pick"] = picked
    if st.session_state.get("inspected_execution") not in labels:
        st.session_state["inspected_execution"] = runs.execution.iloc[-1]
    if len(displayed) < len(runs):
        st.caption(
            f"Latest {len(displayed)} of {len(runs)} executions shown in the timeline."
        )
    choice = st.selectbox(
        "Inspect execution",
        runs.execution.iloc[::-1].tolist(),
        format_func=labels.get,
        key="inspected_execution",
    )
    item = runs.loc[runs.execution.eq(choice)].iloc[0]
    duration = (
        f" · {item.duration_ms / 1000:,.1f}s" if pd.notna(item.duration_ms) else ""
    )
    st.write(f"**{item.result}**{duration} · {item.target or 'Target unavailable'}")

    requests = decisions(frame)
    requests = requests[
        requests.tool_call_id.eq(item.tool_call_id) & requests.tool_call_id.ne("")
    ]
    if requests.empty:
        st.caption("No BlueAI decisions linked to this execution.")
        return

    st.write(f"**BlueAI decisions · {len(requests):,}**")
    st.dataframe(
        requests.reindex(
            columns=[
                "timestamp",
                "method",
                "path",
                "status",
                "classifier",
                "request_id",
            ]
        )
        .tail(100)
        .iloc[::-1],
        hide_index=True,
    )
    if len(requests) > 100:
        st.caption("Showing the latest 100 decisions.")

    request_ids = requests.loc[requests.request_id.ne(""), "request_id"]
    objectives = frame[
        frame.action.eq("objective_served") & frame.request_id.isin(request_ids)
    ]
    if not objectives.empty:
        st.write("**Recorded target events**")
        st.dataframe(
            objectives.reindex(columns=["timestamp", "objective", "request_id"]).tail(
                100
            ),
            hide_index=True,
        )


def render_search(frame, scope):
    with st.expander("Event search"):
        query = st.text_input(
            "Request ID, tool call ID, or event ID",
            help="An exact ID searches across the entire archive.",
        ).strip()
        records = scope
        if query:
            ids = ["request_id", "tool_call_id", "event_id"]
            records = frame[frame[ids].eq(query).any(axis=1)]
        st.caption(
            f"Showing the latest {min(len(records), 500):,} of {len(records):,} events."
        )
        st.dataframe(records.drop(columns="time").tail(500).iloc[::-1], hide_index=True)


@st.fragment(run_every=10 if automatic else None)
def render_dashboard():
    directory = os.environ.get("PURPLEAI_EVENTS_DIR", str(EVENTS_DIR))
    frame = live_data(directory).refresh()
    if frame.empty:
        st.info(f"Waiting for Vector events in {directory}.")
        return

    dated = frame[frame.time.notna()]
    if dated.empty:
        st.warning("The archive contains no events with valid timestamps.")
        render_search(frame, frame)
        return

    invalid = len(frame) - len(dated)
    if invalid:
        st.warning(
            f"{invalid:,} events with invalid timestamps are excluded from the timeline."
        )

    now = pd.Timestamp.now(tz="UTC")
    end = now if period.startswith("Live") else dated.time.max()
    spans = {
        "Live · last 15 minutes": pd.Timedelta(minutes=15),
        "Live · last hour": pd.Timedelta(hours=1),
        "Latest hour of logs": pd.Timedelta(hours=1),
        "Latest 24 hours of logs": pd.Timedelta(hours=24),
    }
    start = end - spans[period] if period in spans else dated.time.min()
    if start == end:
        start -= pd.Timedelta(seconds=1)

    window = dated[dated.time.between(start, end)]
    tags = sorted(dated.loc[dated.engagement_id.ne(""), "engagement_id"].unique())
    engagement = st.selectbox(
        "Engagement",
        [None, *tags],
        format_func=lambda value: value or "All engagements",
    )
    scope = window
    execution_events = dated
    if engagement is not None:
        scope = scope[scope.engagement_id.eq(engagement)]
        execution_events = dated[dated.engagement_id.eq(engagement)]
    runs = executions(execution_events, start, end)

    st.caption(
        f"{start:%d %b %H:%M}–{end:%d %b %H:%M} UTC · Checked {now:%H:%M:%S} UTC"
    )
    if not automatic:
        st.caption("Live updates paused.")
    if scope.empty:
        st.caption("No events in this selection.")
    render_summary(scope, runs)
    render_execution(runs, dated, start, end)
    render_search(frame, scope)


render_dashboard()
