"""Shared JSONL event logging for PurpleAI agents; no network delivery."""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import WatchedFileHandler
from pathlib import Path
from threading import Lock
from uuid import uuid4


class EventLogger:
    """One event format and file handler, configured outside agent logic."""

    def __init__(self, source: str, actor: str, default_path: Path):
        self.source = source
        self.actor = actor
        self.default_path = default_path
        self.run_id = str(uuid4())
        self._logger = None
        self._setup_lock = Lock()

    def _file_logger(self):
        # Lazy setup allows the application's .env to load before the first event.
        with self._setup_lock:
            if self._logger is None:
                path = Path(os.environ.get("PURPLEAI_LOG_FILE") or self.default_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                logger = logging.Logger(self.source, level=logging.INFO)
                logger.addHandler(
                    WatchedFileHandler(path, encoding="utf-8", delay=True)
                )
                self._logger = logger
            return self._logger

    def log_event(self, action: str, **fields) -> None:
        event = {
            **{key: value for key, value in fields.items() if value is not None},
            "schema_version": 1,
            "event_id": str(uuid4()),
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "source": self.source,
            "actor": self.actor,
            "action": action,
        }
        payload = json.dumps(event, ensure_ascii=False)
        print(payload, flush=True)
        try:
            self._file_logger().info(payload)
        except OSError as exc:
            # Logging failures must not change an agent's behavior.
            print(f"Local event log write failed: {exc}", file=sys.stderr)
