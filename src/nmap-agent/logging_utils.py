"""Attacker logging configuration. Event handling lives in purpleai_logging.py."""

import sys
from pathlib import Path

# Support running main.py directly, without installing a Python package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from purpleai_logging import EventLogger  # noqa: E402

log_event = EventLogger(
    source="nmap-agent",
    actor="attacker",
    default_path=Path(__file__).resolve().parent / "logs/events.jsonl",
).log_event
