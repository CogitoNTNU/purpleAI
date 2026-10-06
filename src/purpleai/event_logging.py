"""JSON experiment events and best-effort delivery to the gamehost."""

import json
import logging
import os
from datetime import datetime, timezone
from threading import Lock
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


def configure_logging():
    """Send diagnostics to stderr; stdout remains available for events/output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class EventSender:
    """Send once per event, without retries or a delivery queue."""

    def __init__(self, source, actor, *, url="", token=""):
        self.source = source
        self.actor = actor
        self.url = url
        self.token = token
        run_id = os.environ.get("PURPLEAI_RUN_ID")
        self.run_id = str(UUID(run_id)) if run_id else str(uuid4())
        self.target_mode = os.environ.get("PURPLEAI_TARGET_MODE", "with_defender")
        self._warning_shown = False
        self._lock = Lock()

    def emit(self, action, **fields):
        event = {
            "schema_version": 1,
            "event_id": str(uuid4()),
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "source": self.source,
            "actor": self.actor,
            "action": action,
            "target_mode": self.target_mode,
            **fields,
        }
        payload = json.dumps(event, ensure_ascii=False)
        print(payload, flush=True)
        if not self.url:
            return
        try:
            message = Request(
                self.url,
                data=payload.encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.token}",
                },
                method="POST",
            )
            with urlopen(message, timeout=0.5):
                pass
        except OSError:
            with self._lock:
                if not self._warning_shown:
                    logger.warning(
                        "Gamehost log delivery failed for %s; events are still printed locally",
                        self.source,
                    )
                    self._warning_shown = True
