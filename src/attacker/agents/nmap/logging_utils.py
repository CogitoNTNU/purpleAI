"""Nmap event fields; shared code handles console output and delivery."""

from .config import get_config
from purpleai.event_logging import EventSender

_sender = None


def log_event(actor, action, *, tool=None, target=None, status=None):
    global _sender
    if _sender is None:
        config = get_config()
        _sender = EventSender(
            "nmap-agent",
            "attacker",
            url=config.log_collector_url or "",
            token=config.log_collector_token or "",
        )
    fields = {"actor": actor, "tool": tool, "target": target, "status": status}
    _sender.emit(
        action, **{key: value for key, value in fields.items() if value is not None}
    )
