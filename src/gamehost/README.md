# Gamehost - Event Collection & Dashboard

This folder contains the PurpleAI event collection and monitoring system.

## What's inside

- **dashboard/** - Log collector service and web dashboard
  - `log_collector.py` - Receives events from agents via HTTP
  - `dashboard.py` - Streamlit web dashboard for monitoring
  - `data/` - Stores all events in `events.jsonl`

## Quick Start

### 1. Start the Log Collector

The log collector receives PurpleAI events and stores them. From the repository root:

```bash
cd src/gamehost/dashboard
cp .env.example .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Paste the generated token into `GAMEHOST_LOG_TOKEN` in `.env`, then start the collector:

```bash
python3 log_collector.py
```

The collector listens on TCP port `8765` by default on `192.168.0.110`.

### 2. Start the Dashboard

In another terminal:

```bash
cd src/gamehost/dashboard
./run_dashboard.sh
```

Open `http://192.168.0.110:8501` in your browser.

## Agent Configuration

On machines running agents (nmap-agent, attacker, defender), set these values in their `.env`:

```env
LOG_COLLECTOR_URL=http://192.168.0.110:8765/events
LOG_COLLECTOR_TOKEN=the-same-shared-token
```

## Monitor Events

Watch events in real-time:

```bash
tail -f src/gamehost/dashboard/data/events.jsonl
```

## Event Schema

Every event has:
- `schema_version: 1`
- `event_id` - Unique ID for this event
- `run_id` - Shared by one agent run
- `timestamp` - UTC timestamp
- `source` - Which agent sent it (e.g., "nmap-agent")
- `actor` - Role (e.g., "attacker", "defender")
- `action` - What happened (e.g., "task_start", "tool_call")
- Optional: `tool`, `target`, `status`

## Security Note

The shared token is sent over HTTP. Keep this on a controlled lab network.
For untrusted networks, use HTTPS.
