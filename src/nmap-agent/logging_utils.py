"""Structured console and gamehost logging for PurpleAI agent actions.

Each agent action is logged as one JSON line. The same event is sent to
the gamehost when a collector URL and token are configured.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from config import get_config


RUN_ID = str(uuid4())
_delivery_warning_shown = False


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
        "schema_version": 1,
        "event_id": str(uuid4()),
        "run_id": RUN_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "source": "nmap-agent",
        "actor": actor,
        "action": action,
        "tool": tool,
        "target": target,
        "status": status,
    }
    event = {key: value for key, value in event.items() if value is not None}
    payload = json.dumps(event, ensure_ascii=False)
    print(payload, flush=True)

    config = get_config()
    if not config.log_collector_url:
        return

    request = Request(
        config.log_collector_url,
        data=payload.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.log_collector_token}",
        },
        method="POST",
    )
    global _delivery_warning_shown
    try:
        with urlopen(request, timeout=0.5):
            pass
    except (OSError, URLError) as exc:
        if not _delivery_warning_shown:
            print(f"Gamehost log delivery failed: {exc}", file=sys.stderr)
            _delivery_warning_shown = True
