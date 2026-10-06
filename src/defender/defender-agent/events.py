"""Best-effort JSON events for the gamehost; failures never change decisions."""

import json
import os
import sys
from datetime import datetime, timezone
from threading import Lock
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

RUN_ID = (
    str(UUID(os.environ["PURPLEAI_RUN_ID"]))
    if os.environ.get("PURPLEAI_RUN_ID")
    else str(uuid4())
)
URL = os.environ.get("LOG_COLLECTOR_URL", "")
TOKEN = os.environ.get("LOG_COLLECTOR_TOKEN", "")
_warning_shown = False
_lock = Lock()


def log_event(action, **fields):
    event = {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "run_id": RUN_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "source": "defender",
        "actor": "defender",
        "action": action,
        **fields,
    }
    payload = json.dumps(event, ensure_ascii=False)
    print(payload, flush=True)
    if not URL:
        return
    try:
        message = Request(
            URL,
            data=payload.encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN}",
            },
            method="POST",
        )
        with urlopen(message, timeout=0.5):
            pass
    except OSError as error:
        global _warning_shown
        with _lock:
            if not _warning_shown:
                print(f"Gamehost log delivery failed: {error}", file=sys.stderr)
                _warning_shown = True
