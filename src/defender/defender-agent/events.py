"""Best-effort JSON events for the gamehost; failures never change decisions."""

import os

from openai import APIConnectionError, APITimeoutError
from purpleai.event_logging import EventSender

_sender = EventSender(
    "defender",
    "defender",
    url=os.environ.get("LOG_COLLECTOR_URL", ""),
    token=os.environ.get("LOG_COLLECTOR_TOKEN", ""),
)


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
    _sender.emit(action, **fields)
