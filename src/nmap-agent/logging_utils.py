"""Structured console logging for PurpleAI agent actions.

Each agent action is logged as one JSON line with a timestamp, actor,
action, tool, target, and status. Empty fields are left out.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


def log_event(
    actor: str,
    action: str,
    *,
    tool: str | None = None,
    target: str | None = None,
    status: str | None = None,
) -> None:
    """Print one JSON log line describing an agent action."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "actor": actor,
        "action": action,
        "tool": tool,
        "target": target,
        "status": status,
    }
    event = {key: value for key, value in event.items() if value is not None}
    print(json.dumps(event, ensure_ascii=False))
