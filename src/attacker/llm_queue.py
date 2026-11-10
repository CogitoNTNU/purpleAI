"""Host-wide FIFO admission shared by Boss, specialists and A-D instances.

SQLite orders waiters; OS locks enforce one live request per distinct key,
including streaming responses. The OS releases locks after crashes. The key
file is reread while waiting; only fingerprints enter the database or logs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from uuid import uuid4


def key_file() -> Path:
    return Path(os.environ.get("LLM_KEYS_FILE", str(Path.home() / ".purpleai" / "keys.json"))).expanduser()


def _env_keys() -> list[str]:
    raw = os.environ.get("LLM_API_KEYS") or os.environ.get("LLM_API_KEY", "")
    return list(dict.fromkeys(k.strip() for k in raw.replace("\n", ",").replace(";", ",").split(",") if k.strip()))


class Lease:
    def __init__(self, handle, key: str, fingerprint: str):
        self.handle, self.key, self.fingerprint = handle, key, fingerprint
        self.started = time.monotonic()
        self.closed = threading.Event()
        threading.Thread(target=self._heartbeat, daemon=True).start()

    def _heartbeat(self):
        while not self.closed.wait(30):
            print(f"[llm] model request active for {int(time.monotonic() - self.started)}s; waiting for response/completion", flush=True)

    def close(self):
        if not self.closed.is_set():
            self.closed.set()
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()


class KeyQueue:
    def __init__(self, directory: Path | None = None, keys_path: Path | None = None):
        self.directory = directory or Path(os.environ.get("LLM_QUEUE_DIR", str(Path.home() / ".purpleai" / "queue"))).expanduser()
        self.keys_path = keys_path or key_file()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS waiters (ticket INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT UNIQUE, seen REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS keys (fingerprint TEXT PRIMARY KEY, used REAL DEFAULT 0, cooldown REAL DEFAULT 0)")

        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in db.execute("PRAGMA table_info(waiters)")}
            if "pid" not in columns:
                db.execute("ALTER TABLE waiters ADD COLUMN pid INTEGER DEFAULT 0")

    def _db(self):
        return sqlite3.connect(self.directory / "queue.sqlite3", timeout=10)

    def keys(self):
        try:
            keys = json.loads(self.keys_path.read_text(encoding="utf-8"))["keys"]
            if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys):
                raise ValueError("invalid key pool")
            return list(dict.fromkeys(k.strip() for k in keys if k.strip()))
        except FileNotFoundError:
            return _env_keys()
        except (OSError, ValueError, KeyError, TypeError):
            return []  # don't resurrect removed env keys on an invalid file

    def ticket(self):
        token = uuid4().hex
        with self._db() as db:
            db.execute("INSERT INTO waiters(token,seen,pid) VALUES (?,?,?)", (token, time.time(), os.getpid()))
        return token

    def discard(self, token):
        with self._db() as db:
            db.execute("DELETE FROM waiters WHERE token=?", (token,))

    def try_acquire(self, token):
        keys = {hashlib.sha256(k.encode()).hexdigest(): k for k in self.keys()}
        now = time.time()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM waiters WHERE seen < ?", (now - 120,))
            db.execute("INSERT OR IGNORE INTO waiters(token,seen,pid) VALUES (?,?,?)", (token, now, os.getpid()))
            db.execute("UPDATE waiters SET seen=? WHERE token=?", (now, token))
            first = db.execute("SELECT token FROM waiters ORDER BY ticket LIMIT 1").fetchone()
            if not first or first[0] != token:
                return None
            for fingerprint in keys:
                db.execute("INSERT OR IGNORE INTO keys(fingerprint) VALUES (?)", (fingerprint,))
            available = db.execute("SELECT fingerprint FROM keys WHERE cooldown <= ? ORDER BY used, fingerprint", (now,)).fetchall()
            for (fingerprint,) in available:
                if fingerprint not in keys:
                    continue
                handle = open(self.directory / (fingerprint + ".lock"), "a+b")
                try:
                    if os.name == "nt":
                        import msvcrt
                        if handle.seek(0, 2) == 0:
                            handle.write(b"0")
                            handle.flush()
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (BlockingIOError, OSError):
                    handle.close()
                    continue
                try:
                    db.execute("DELETE FROM waiters WHERE token=?", (token,))
                    db.execute("UPDATE keys SET used=? WHERE fingerprint=?", (now, fingerprint))
                    db.commit()
                    return Lease(handle, keys[fingerprint], fingerprint)
                except BaseException:
                    handle.close()
                    raise
        return None

    def cooldown(self, lease, seconds):
        with self._db() as db:
            db.execute("UPDATE keys SET cooldown=MAX(cooldown,?) WHERE fingerprint=?", (time.time() + seconds, lease.fingerprint))

    def acquire(self):
        token, report = self.ticket(), 0
        try:
            while True:
                lease = self.try_acquire(token)
                if lease:
                    print("[llm] admitted model request", flush=True)
                    return lease
                if time.monotonic() >= report:
                    print(f"[llm] queued; {len(self.keys())} distinct key(s); waiting for an available slot", flush=True)
                    report = time.monotonic() + 30
                time.sleep(0.25)
        finally:
            self.discard(token)

    async def acquire_async(self):
        admission = asyncio.create_task(asyncio.to_thread(self.ticket))
        try:
            token = await asyncio.shield(admission)
        except asyncio.CancelledError:
            token = await admission
            await asyncio.to_thread(self.discard, token)
            raise
        report = 0
        try:
            while True:
                attempt = asyncio.create_task(asyncio.to_thread(self.try_acquire, token))
                try:
                    lease = await asyncio.shield(attempt)
                except asyncio.CancelledError:
                    # Admission may win concurrently with cancellation.
                    lease = await attempt
                    if lease:
                        lease.close()
                    raise
                if lease:
                    print("[llm] admitted model request", flush=True)
                    return lease
                if time.monotonic() >= report:
                    count = len(await asyncio.to_thread(self.keys))
                    print(f"[llm] queued; {count} distinct key(s); waiting for an available slot", flush=True)
                    report = time.monotonic() + 30
                await asyncio.sleep(0.25)
        finally:
            await asyncio.to_thread(self.discard, token)
