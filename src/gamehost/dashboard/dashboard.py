"""Display agent events from gamehost Vector's daily JSONL archives."""

import streamlit as st
import pandas as pd

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

    # Calculate attack and defender metrics
    attack_events = (
        df[df["actor"] == "attacker"].copy()
        if "actor" in df.columns
        else pd.DataFrame()
    )

    if not attack_events.empty and "status" in attack_events.columns:
        total_attacks = len(attack_events)
        successful_attacks = len(attack_events[attack_events["status"] == "success"])
        blocked_attacks = len(attack_events[attack_events["status"] == "blocked"])

        attack_success_rate = (
            (successful_attacks / total_attacks * 100) if total_attacks > 0 else 0
        )
        defender_block_rate = (
            (blocked_attacks / total_attacks * 100) if total_attacks > 0 else 0
        )
    else:
        total_attacks = 0
        successful_attacks = 0
        blocked_attacks = 0
        attack_success_rate = 0
        defender_block_rate = 0

    # Overview Statistics
    st.header("Overview")

    col1, col2, col3, col4 = st.columns(4, border=True)

    with col1:
        st.metric(
            "Attacker Success Rate",
            f"{attack_success_rate:.1f}%",
            delta=f"{successful_attacks} successful",
            delta_color="inverse",  # Red arrow = bad for security
        )

    with col2:
        st.metric(
            "Defender Block Rate",
            f"{defender_block_rate:.1f}%",
            delta=f"{blocked_attacks} blocked",
            delta_color="normal",  # Green arrow = good
        )

    with col3:
        st.metric("Total Attack Attempts", total_attacks)

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
