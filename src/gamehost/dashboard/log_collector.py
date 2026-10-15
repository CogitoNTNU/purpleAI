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
ENV_FILE = Path(__file__).parent / ".env"
ENV_KEYS = {"GAMEHOST_LOG_TOKEN", "GAMEHOST_LOG_BIND", "GAMEHOST_LOG_PORT", "GAMEHOST_LOG_FILE"}
DATA_FILE = Path(__file__).parent / "data" / "events.jsonl"
TOKEN = ""


def read_env_file(path: Path) -> dict[str, str]:
    """Read the collector's small, literal KEY=VALUE configuration file."""
    if not path.exists():
        return {}
    values = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if separator != "=" or key not in ENV_KEYS:
            raise ValueError(f"{path}:{number}: expected a supported KEY=VALUE setting")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"{path}:{number}: unmatched quote")
            value = value[1:-1]
        values[key] = value
    return values


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
    global TOKEN, DATA_FILE
    try:
        settings = {**read_env_file(ENV_FILE), **os.environ}
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    TOKEN = settings.get("GAMEHOST_LOG_TOKEN", "")
    if not TOKEN:
        raise SystemExit(f"Set GAMEHOST_LOG_TOKEN in {ENV_FILE} or the shell environment.")
    DATA_FILE = Path(settings.get("GAMEHOST_LOG_FILE", DATA_FILE))
    host = settings.get("GAMEHOST_LOG_BIND", "127.0.0.1")
    port = int(settings.get("GAMEHOST_LOG_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), EventHandler)
    print(f"Listening for PurpleAI events on {host}:{port}; writing to {DATA_FILE}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
