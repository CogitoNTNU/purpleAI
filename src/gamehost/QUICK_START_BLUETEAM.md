# Quick Start: Blue Team Logging

## 5-Minute Setup

### On Gamehost PC (192.168.0.110)

1. **Start the log collector** (if not already running):
   ```bash
   cd src/gamehost/dashboard
   python3 log_collector.py
   ```

2. **Get your token**:
   ```bash
   cat .env | grep GAMEHOST_LOG_TOKEN
   ```
   Copy this token - you'll need it on the blue team PC.

3. **Start the dashboard** (in a new terminal):
   ```bash
   cd src/gamehost/dashboard
   ./run_dashboard.sh
   ```
   Dashboard will be at: http://192.168.0.110:8501

### On Blue Team PC

1. **Copy these files from gamehost**:
   - `src/gamehost/event_sender.py`
   - `src/gamehost/blueteam_example.py`

2. **Edit the token** in `blueteam_example.py`:
   ```python
   token="paste-your-token-here",  # <-- Replace this
   ```

3. **Run the example**:
   ```bash
   python3 blueteam_example.py
   ```

4. **Check the dashboard** at http://192.168.0.110:8501
   You should see defender events appearing!

## Basic Usage

```python
from event_sender import EventSender

sender = EventSender(
    collector_url="http://192.168.0.110:8765/events",
    token="your-gamehost-token",
    source="blue-team-pc",
)

# Log a defensive action
sender.log_event(
    actor="defender",
    action="block_attack",
    tool="iptables",
    target="192.168.50.10",
    status="blocked",
)
```

## Common Use Cases

### Block an IP
```python
sender.log_event(
    actor="defender",
    action="block_attack",
    tool="iptables",
    target="192.168.50.10",
    status="blocked",
)
```

### Detect suspicious activity
```python
sender.log_event(
    actor="defender",
    action="detection",
    tool="ids",
    target="192.168.50.10:22",
    status="suspicious",
)
```

### Restart a service
```python
sender.log_event(
    actor="defender",
    action="service_restart",
    tool="systemctl",
    target="nginx",
    status="success",
)
```

### Apply a patch
```python
sender.log_event(
    actor="defender",
    action="patch",
    tool="apt",
    target="nginx",
    status="success",
)
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot reach gamehost" | Check network: `ping 192.168.0.110` |
| "401 Unauthorized" | Double-check token matches gamehost |
| Events not showing | Ensure log_collector.py is running |
| Dashboard not loading | Run `./run_dashboard.sh` on gamehost |

## Next Steps

- See `BLUETEAM_SETUP.md` for detailed documentation
- See `blueteam_example.py` for more examples
- See `docs/event-format.md` for event specification
