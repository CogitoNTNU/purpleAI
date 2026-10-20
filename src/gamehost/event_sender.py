"""Standalone event sender for PurpleAI.

This module can be copied to any machine (like the blue team PC) to send
events to the gamehost log collector. It has no dependencies beyond the
Python standard library.

Usage:
    from event_sender import EventSender

    sender = EventSender(
        collector_url="http://192.168.0.110:8765/events",
        token="your-gamehost-token",
        source="blue-team",  # Identifies this agent/PC
    )

    # Log an event
    sender.log_event(
        actor="defender",
        action="tool_call",
        tool="iptables",
        target="192.168.50.10",
        status="blocked"
    )
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4


class EventSender:
    """Send PurpleAI events to the gamehost log collector."""

    def __init__(
        self,
        collector_url: str,
        token: str,
        source: str,
        timeout: float = 2.0,
        silent_failures: bool = True,
    ):
        """Initialize the event sender.

        Args:
            collector_url: Full URL to the collector endpoint (e.g., "http://192.168.0.110:8765/events")
            token: Authentication token matching GAMEHOST_LOG_TOKEN on the gamehost
            source: Name identifying this agent/PC (e.g., "blue-team", "defender-pc")
            timeout: HTTP request timeout in seconds (default: 2.0)
            silent_failures: If True, only show one warning on delivery failure (default: True)
        """
        if not collector_url.endswith("/events"):
            raise ValueError("collector_url must end with /events")
        if not token:
            raise ValueError("token cannot be empty")
        if not source or " " in source:
            raise ValueError("source must be a non-empty string without spaces")

        self.collector_url = collector_url
        self.token = token
        self.source = source
        self.timeout = timeout
        self.silent_failures = silent_failures
        self.run_id = str(uuid4())
        self._delivery_warning_shown = False

    def log_event(
        self,
        actor: str,
        action: str,
        *,
        tool: str | None = None,
        target: str | None = None,
        status: str | None = None,
        print_to_console: bool = True,
    ) -> bool:
        """Log a single event to the gamehost.

        Args:
            actor: Who acted (e.g., "defender", "attacker", "analyst")
            action: What happened (e.g., "tool_call", "task_start", "blocked")
            tool: Optional tool name (e.g., "iptables", "nmap")
            target: Optional target (e.g., "192.168.50.10:8080")
            status: Optional status (e.g., "success", "blocked", "failure")
            print_to_console: If True, print the event JSON to stdout (default: True)

        Returns:
            True if the event was successfully delivered, False otherwise
        """
        event = {
            "schema_version": 1,
            "event_id": str(uuid4()),
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "source": self.source,
            "actor": actor,
            "action": action,
            "tool": tool,
            "target": target,
            "status": status,
        }
        # Remove None values
        event = {key: value for key, value in event.items() if value is not None}

        payload = json.dumps(event, ensure_ascii=False)

        if print_to_console:
            print(payload, flush=True)

        return self._send_to_collector(payload)

    def _send_to_collector(self, payload: str) -> bool:
        """Send the event payload to the gamehost collector.

        Args:
            payload: JSON string containing the event

        Returns:
            True if successful, False on any error
        """
        request = Request(
            self.collector_url,
            data=payload.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout):
                pass
            return True
        except (OSError, URLError) as exc:
            if self.silent_failures:
                if not self._delivery_warning_shown:
                    print(
                        f"[{self.source}] Gamehost log delivery failed: {exc}",
                        file=sys.stderr,
                    )
                    print(
                        f"[{self.source}] Further delivery failures will be silent.",
                        file=sys.stderr,
                    )
                    self._delivery_warning_shown = True
            else:
                print(
                    f"[{self.source}] Gamehost log delivery failed: {exc}",
                    file=sys.stderr,
                )
            return False

    def health_check(self) -> bool:
        """Check if the gamehost collector is reachable.

        Returns:
            True if the /health endpoint responds, False otherwise
        """
        health_url = self.collector_url.replace("/events", "/health")
        try:
            with urlopen(health_url, timeout=self.timeout):
                return True
        except (OSError, URLError):
            return False
