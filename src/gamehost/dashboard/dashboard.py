"""Display agent events from gamehost Vector's daily JSONL archives."""

import pandas as pd
import streamlit as st
from event_store import EVENTS_DIR, load_events

st.set_page_config(
    page_title="PurpleAI Dashboard", layout="wide", page_icon=":material/monitoring:"
)
st.title(":material/monitoring: PurpleAI Dashboard", text_alignment="center")
st.markdown(
    "Monitoring attacker and defender events from Vector. Refreshes every 5 seconds.",
    text_alignment="center",
)


@st.fragment(run_every=5)
def render_events():
    # Load the data
    df = pd.DataFrame(load_events())

    # Display message if no data
    if df.empty:
        st.warning(f"No events found yet. Waiting for Vector archives in {EVENTS_DIR}")
        st.info("Check the Vector services on gamehost, RedAI, and BlueAI.")
        return

    # Lifecycle/subagent events and tool completion do not prove attack success.
    actions = df.get("action", pd.Series(index=df.index, dtype=str))
    actors = df.get("actor", pd.Series(index=df.index, dtype=str))
    statuses = df.get("status", pd.Series(index=df.index, dtype=str))
    tool_calls = ((actors == "attacker") & (actions == "tool_call")).sum()
    tool_errors = (
        (actors == "attacker")
        & (actions == "tool_result")
        & statuses.isin(["error", "timeout"])
    ).sum()
    blocked_requests = (
        (actors == "defender")
        & (actions == "request_decision")
        & (statuses == "blocked")
    ).sum()

    # Overview Statistics
    st.header("Overview")

    col1, col2, col3, col4 = st.columns(4, border=True)

    with col1:
        st.metric("Attacker Tool Calls", int(tool_calls))

    with col2:
        st.metric("Tool Errors / Timeouts", int(tool_errors))

    with col3:
        st.metric("Defender Requests Blocked", int(blocked_requests))

    with col4:
        total_events = len(df)
        st.metric("Total Events", total_events)

    # Recent Events Feed
    st.header("All events")

    # Show the most recent 20 events
    recent_events = df.tail(20).iloc[::-1]  # Reverse to show newest first

    # Select columns to display
    display_columns = [
        "timestamp",
        "source",
        "actor",
        "action",
        "status",
        "tool",
        "target",
    ]
    available_columns = [col for col in display_columns if col in recent_events.columns]

    st.dataframe(recent_events[available_columns], width="stretch", hide_index=True)


render_events()
st.caption("Dashboard refreshes every 5 seconds", text_alignment="center")
