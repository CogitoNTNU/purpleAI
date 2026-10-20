"""JSONL decision events consumed by the host Vector agent."""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache
from logging.handlers import WatchedFileHandler
from uuid import uuid4

RUN_ID = str(uuid4())


@lru_cache(maxsize=1)
def _file_logger(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.Logger("purpleai.defender", level=logging.INFO)
    logger.addHandler(WatchedFileHandler(path, encoding="utf-8", delay=True))
    return logger


def log_event(action, *, status, **fields):
    event = {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "run_id": RUN_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "source": "defender-agent",
        "actor": "defender",
        "action": action,
        "status": status,
        **fields,
    }
    payload = json.dumps(event, ensure_ascii=False)
    path = Path(
        os.environ.get("PURPLEAI_LOG_FILE")
        or Path(__file__).resolve().parent / "logs/events.jsonl"
    )
    print(payload, flush=True)
    try:
        _file_logger(path).info(payload)
    except OSError as exc:
        # A full disk must not change the proxy's allow/block decision.
        print(f"Local event log write failed: {exc}", file=sys.stderr)
