"""Structured console and gamehost logging for PurpleAI agent actions.

Each action is printed and appended to a JSONL file for the host Vector
agent.
"""

from __future__ import annotations

import json
import logging
import sys
from functools import lru_cache
from logging.handlers import WatchedFileHandler
from datetime import datetime, timezone
from uuid import uuid4

from config import get_config


RUN_ID = str(uuid4())


@lru_cache(maxsize=1)
def _file_logger(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.Logger("purpleai.attacker", level=logging.INFO)
    logger.addHandler(WatchedFileHandler(path, encoding="utf-8", delay=True))
    return logger


def log_event(
    actor: str,
    action: str,
    *,
    tool: str | None = None,
    target: str | None = None,
    status: str | None = None,
) -> None:
    """Print and save one JSON event describing an agent action."""
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
    try:
        _file_logger(config.log_file).info(payload)
    except OSError as exc:
        print(f"Local event log write failed: {exc}", file=sys.stderr)
