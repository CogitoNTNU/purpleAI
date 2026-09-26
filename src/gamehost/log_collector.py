"""Receive PurpleAI events on the gamehost and store them as JSON Lines."""

from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
from uuid import UUID


MAX_EVENT_BYTES = 16 * 1024
WRITE_LOCK = Lock()
DATA_FILE = Path(os.environ.get("GAMEHOST_LOG_FILE", Path(__file__).parent / "data" / "events.jsonl"))
TOKEN = os.environ.get("GAMEHOST_LOG_TOKEN", "")


def valid_event(event: object) -> bool:
    """Check the common event envelope without constraining future sources."""
    if not isinstance(event, dict) or event.get("schema_version") != 1:
        return False
    for key in ("event_id", "run_id"):
        try:
            UUID(event[key])
        except (KeyError, TypeError, ValueError, AttributeError):
            return False
    for key in ("timestamp", "source", "actor", "action"):
        if not isinstance(event.get(key), str) or not event[key]:
            return False
    try:
        timestamp = datetime.fromisoformat(event["timestamp"])
    except ValueError:
        return False
    if timestamp.utcoffset() != timedelta(0):
        return False
    return True


class EventHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        """Keep the live terminal focused on events rather than access lines."""

    def do_GET(self) -> None:
        if urlsplit(self.path).path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok\n")

    def do_POST(self) -> None:
        if self.path != "/events":
            self.send_error(404)
            return
        if not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {TOKEN}"):
            self.send_error(401)
            return
        if self.headers.get_content_type() != "application/json":
            self.send_error(415)
            return
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_error(411)
            return
        if not 0 < size <= MAX_EVENT_BYTES:
            self.send_error(413)
            return
        try:
            event = json.loads(self.rfile.read(size))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400)
            return
        if not valid_event(event):
            self.send_error(422)
            return

        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with WRITE_LOCK:
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with DATA_FILE.open("a", encoding="utf-8") as output:
                output.write(line + "\n")
            print(line, flush=True)
        self.send_response(202)
        self.end_headers()


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set GAMEHOST_LOG_TOKEN before starting the collector.")
    host = os.environ.get("GAMEHOST_LOG_BIND", "127.0.0.1")
    port = int(os.environ.get("GAMEHOST_LOG_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), EventHandler)
    print(f"Listening for PurpleAI events on {host}:{port}; writing to {DATA_FILE}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
