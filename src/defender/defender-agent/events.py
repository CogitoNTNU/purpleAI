"""Best-effort JSON events for the gamehost; failures never change decisions."""

import json
import os
import sys
from datetime import datetime, timezone
from threading import Lock
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from openai import APIConnectionError, APITimeoutError

RUN_ID = (
    str(UUID(os.environ["PURPLEAI_RUN_ID"]))
    if os.environ.get("PURPLEAI_RUN_ID")
    else str(uuid4())
)
URL = os.environ.get("LOG_COLLECTOR_URL", "")
TOKEN = os.environ.get("LOG_COLLECTOR_TOKEN", "")
_warning_shown = False
_lock = Lock()


def model_error_details(error):
    """Keep diagnostic facts, without copying arbitrary response bodies or secrets."""
    status = getattr(error, "status_code", None)
    if type(status) is not int or not 100 <= status <= 599:
        status = None
    body = getattr(error, "body", None)
    reason = body.get("error") if isinstance(body, dict) else None
    safe_reasons = {
        "Gateway busy",
        "Run call budget exhausted",
        "Unauthorized",
        "Idun request failed",
        "Idun unavailable",
        "Idun response too large",
    }
    if not isinstance(reason, str) or reason not in safe_reasons:
        if isinstance(error, APITimeoutError):
            reason = "Model request timed out"
        elif isinstance(error, APIConnectionError):
            reason = "Model connection failed"
        elif status is not None:
            reason = "Model HTTP request failed"
        else:
            reason = "Model evaluation failed"
    return {
        "error_type": type(error).__name__,
        "model_http_status": status,
        "error_reason": reason,
    }


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
