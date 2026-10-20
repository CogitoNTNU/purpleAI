# Blue Team Event Logging Setup

This guide explains how to send logs from your blue team PC to the gamehost so they appear on the dashboard.

## Overview

The blue team PC will send events to the gamehost using the same event logging system that the attacker agents use. This allows the dashboard to show both attacker and defender activity in real-time.

```
Blue Team PC                 Gamehost PC (192.168.0.110)
    |                               |
    | HTTP POST /events             |
    |------------------------------>| log_collector.py
    |                               |    |
    |                               |    v
    |                               | events.jsonl
    |                               |    |
    |                               |    v
    |                               | dashboard.py
```

## Prerequisites

- Python 3.9 or newer on the blue team PC
- Network connectivity between blue team PC and gamehost (192.168.0.110:8765)
- The gamehost authentication token (from `src/gamehost/dashboard/.env`)

## Setup Steps

### 1. Get the Gamehost Token

On the **gamehost PC**, find your log collector token:

```bash
cat src/gamehost/dashboard/.env
```

Look for the `GAMEHOST_LOG_TOKEN` value. You'll need this on the blue team PC.

### 2. Copy Files to Blue Team PC

Copy these two files to your blue team PC:

- `src/gamehost/event_sender.py` - The logging library
- `src/gamehost/blueteam_example.py` - Example usage

You can copy them anywhere, for example:

```bash
# On blue team PC
mkdir ~/purpleai-logging
cd ~/purpleai-logging

# Copy files here (via USB, scp, etc.)
```

### 3. Configure the Token

Edit `blueteam_example.py` and replace the placeholder token:

```python
sender = EventSender(
    collector_url="http://192.168.0.110:8765/events",
    token="replace-with-your-gamehost-token",  # <-- Put your actual token here
    source="blue-team-pc",
)
```

### 4. Test the Connection

Run the example script:

```bash
python3 blueteam_example.py
```

You should see:
- "Connected to gamehost successfully!"
- Several example events printed
- "Example events sent to gamehost!"

Then check the dashboard at http://192.168.0.110:8501 to see the events appear.

## Using in Your Own Scripts

### Basic Usage

```python
from event_sender import EventSender

# Initialize once
sender = EventSender(
    collector_url="http://192.168.0.110:8765/events",
    token="your-gamehost-token",
    source="blue-team-pc",
)

# Log defensive actions
sender.log_event(
    actor="defender",
    action="block_attack",
    tool="iptables",
    target="192.168.50.10:8080",
    status="blocked",
)
```

### Event Fields

Every event requires:
- `actor`: Who acted (use `"defender"` for blue team)
- `action`: What happened (e.g., `"tool_call"`, `"detection"`, `"block_attack"`)

Optional fields:
- `tool`: Tool used (e.g., `"iptables"`, `"fail2ban"`, `"ids"`)
- `target`: Target of the action (e.g., `"192.168.50.10:8080"`)
- `status`: Outcome (e.g., `"success"`, `"blocked"`, `"failure"`)

### Common Actions

Here are some useful action types for defensive logging:

| Action | Description | Example |
|--------|-------------|---------|
| `task_start` | Begin monitoring/defense | `sender.log_event("defender", "task_start", status="started")` |
| `task_end` | End monitoring/defense | `sender.log_event("defender", "task_end", status="success")` |
| `tool_call` | Use a defensive tool | `sender.log_event("defender", "tool_call", tool="iptables", target="192.168.50.10")` |
| `detection` | Detect suspicious activity | `sender.log_event("defender", "detection", tool="ids", status="suspicious")` |
| `block_attack` | Block an attack | `sender.log_event("defender", "block_attack", tool="fail2ban", status="blocked")` |
| `scan` | Scan for threats | `sender.log_event("defender", "scan", tool="nmap", target="192.168.50.0/24")` |
| `patch` | Apply security patch | `sender.log_event("defender", "patch", tool="apt", target="nginx", status="success")` |
| `service_restart` | Restart a service | `sender.log_event("defender", "service_restart", tool="systemctl", target="nginx")` |

## Integration Examples

### Example 1: Shell Script Integration

You can call the event sender from bash scripts:

```bash
#!/bin/bash
# defensive_action.sh

python3 - <<'EOF'
from event_sender import EventSender

sender = EventSender(
    collector_url="http://192.168.0.110:8765/events",
    token="your-token-here",
    source="blue-team-script",
)

sender.log_event(
    actor="defender",
    action="block_attack",
    tool="iptables",
    target="192.168.50.10",
    status="blocked",
)
EOF

# Your defensive actions here
iptables -A INPUT -s 192.168.50.10 -j DROP
```

### Example 2: Log File Monitoring

Monitor a log file and send events when patterns are detected:

```python
#!/usr/bin/env python3
import time
from event_sender import EventSender

sender = EventSender(
    collector_url="http://192.168.0.110:8765/events",
    token="your-token-here",
    source="blue-team-monitor",
)

# Follow log file like 'tail -f'
log_file = "/var/log/auth.log"

with open(log_file, "r") as f:
    # Seek to end
    f.seek(0, 2)

    while True:
        line = f.readline()
        if not line:
            time.sleep(0.1)
            continue

        # Detect failed SSH attempts
        if "Failed password" in line:
            sender.log_event(
                actor="defender",
                action="detection",
                tool="sshd",
                status="failed_auth",
            )
```

### Example 3: Cron Job

Add to crontab to run defensive checks periodically:

```bash
# Run security scan every 5 minutes
*/5 * * * * cd /home/blueteam/purpleai-logging && python3 security_check.py
```

```python
# security_check.py
from event_sender import EventSender

sender = EventSender(
    collector_url="http://192.168.0.110:8765/events",
    token="your-token-here",
    source="blue-team-cron",
)

sender.log_event(actor="defender", action="scan", tool="security-check", status="started")

# Your security checks here...

sender.log_event(actor="defender", action="scan", tool="security-check", status="complete")
```

## Troubleshooting

### "Cannot reach gamehost" Error

1. Check network connectivity:
   ```bash
   ping 192.168.0.110
   ```

2. Verify log collector is running on gamehost:
   ```bash
   # On gamehost PC
   curl http://localhost:8765/health
   # Should return: ok
   ```

3. Check if port 8765 is open on gamehost firewall

### Events Not Appearing on Dashboard

1. Check the gamehost token matches:
   ```bash
   # On gamehost PC
   cat src/gamehost/dashboard/.env | grep GAMEHOST_LOG_TOKEN
   ```

2. Check events are being written to file:
   ```bash
   # On gamehost PC
   tail -f src/gamehost/dashboard/data/events.jsonl
   ```

3. Make sure the dashboard is running:
   ```bash
   # On gamehost PC
   cd src/gamehost/dashboard
   ./run_dashboard.sh
   ```

### "401 Unauthorized" Error

Your token is incorrect. Double-check you copied the `GAMEHOST_LOG_TOKEN` exactly from the gamehost's `.env` file.

### "Connection Timeout" Error

The blue team PC cannot reach the gamehost on port 8765. Check:
- Network connectivity
- Firewall rules
- Log collector is running

## Advanced: Running as a Service

To run continuous monitoring as a systemd service:

1. Create `/etc/systemd/system/blueteam-monitor.service`:

```ini
[Unit]
Description=Blue Team Event Monitor
After=network.target

[Service]
Type=simple
User=blueteam
WorkingDirectory=/home/blueteam/purpleai-logging
ExecStart=/usr/bin/python3 /home/blueteam/purpleai-logging/monitor.py
Restart=always

[Install]
WantedBy=multi-user.target
```

2. Enable and start:

```bash
sudo systemctl enable blueteam-monitor
sudo systemctl start blueteam-monitor
sudo systemctl status blueteam-monitor
```

## Security Notes

- The token is a shared secret - keep it secure
- Events are sent over HTTP (not HTTPS) on the local network
- Events can be up to 16 KB each
- Failed deliveries are logged locally but don't block execution
- The event sender has no external dependencies beyond Python standard library

## Questions?

For more details on the event format, see `docs/event-format.md`.
