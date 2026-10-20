# PurpleAI Dashboard Guide

## What is this?

A simple real-time dashboard that shows what your attacker and defender agents are doing.

## Where to run it?

**Run this on the GAMEHOST PC** (the machine that collects logs at `192.168.0.110`)

## Setup (One-time)

1. Make sure you have Streamlit installed:
   ```bash
   pip install streamlit pandas
   ```

## How to run

1. Navigate to the dashboard directory:
   ```bash
   cd src/gamehost/dashboard
   ```

2. Start the dashboard:
   ```bash
   ./run_dashboard.sh
   ```

   Or manually:
   ```bash
   streamlit run dashboard.py --server.address 0.0.0.0
   ```

3. The dashboard will open in your browser at:
   - Local: `http://localhost:8501`
   - Network: `http://192.168.0.110:8501` (accessible from other machines)

## What you'll see

- **Total Events**: How many things have happened
- **Agent Runs**: How many times agents have run
- **Events by Source**: Which agents (nmap-agent, etc.) are active
- **Events by Actor**: Attacker vs. Defender activity
- **Actions**: What actions are being taken (task_start, tool_call, etc.)
- **Status**: Success/failure rates
- **Recent Events**: Live feed of the latest 20 events

## Troubleshooting

**"No events found yet"**
- Make sure `log_collector.py` is running
- Check that `data/events.jsonl` exists
- Verify agents are configured to send events to the collector

**Dashboard won't start**
- Install streamlit: `pip install streamlit pandas`
- Make sure you're in the `src/gamehost/dashboard` directory

**Can't access from other machines**
- Streamlit might be binding to localhost only
- Run with: `streamlit run dashboard.py --server.address 0.0.0.0`

## Next Steps

Once this works, you can:
- Add custom metrics
- Create charts for specific attack types
- Add gameification (animated agents, house visualization, etc.)
- Filter events by time period
- Export reports
