"""Defender logging configuration. Event handling lives in purpleai_logging.py."""

import sys
from pathlib import Path

# The container mirrors the src/ layout so direct runs use the same imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from purpleai_logging import EventLogger  # noqa: E402

log_event = EventLogger(
    source="defender-agent",
    actor="defender",
    default_path=Path(__file__).resolve().parent / "logs/events.jsonl",
).log_event
