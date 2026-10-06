"""TCP smoke checks to execute inside each sandbox container.

A refused connection demonstrates no reachable service, not necessarily a
firewall drop. Pair this check with host firewall counters and a known listener.
"""

import argparse
import socket
import os
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from uuid import uuid4


def endpoint(value):
    host, port = value.rsplit(":", 1)
    return host, int(port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from",
        dest="origin",
        required=True,
        help="PC and container running the check",
    )
    parser.add_argument("--allow", action="append", default=[], type=endpoint)
    parser.add_argument("--deny", action="append", default=[], type=endpoint)
    args = parser.parse_args()
    failures = 0
    for expected, targets in ((True, args.allow), (False, args.deny)):
        for host, port in targets:
            try:
                with socket.create_connection((host, port), timeout=3):
                    reachable = True
            except OSError:
                reachable = False
            passed = reachable == expected
            failures += not passed
            print(
                f"{'PASS' if passed else 'FAIL'} [{args.origin}] {host}:{port}: {'reachable' if reachable else 'unreachable'}"
            )
    if os.environ.get("LOG_COLLECTOR_URL"):
        event = {
            "schema_version": 1,
            "event_id": str(uuid4()),
            "run_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "sandbox-check",
            "actor": "sandbox-check",
            "action": "log_check",
            "target_mode": os.environ.get("PURPLEAI_TARGET_MODE", "with_defender"),
        }
        message = Request(
            os.environ["LOG_COLLECTOR_URL"],
            data=json.dumps(event).encode(),
            headers={
                "Authorization": f"Bearer {os.environ['LOG_COLLECTOR_TOKEN']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(message, timeout=3):
                pass
            print(f"PASS [{args.origin}] collector: authenticated event accepted")
        except OSError:
            failures += 1
            print(
                f"FAIL [{args.origin}] collector: event delivery failed (check address, token and collector)"
            )
    if not args.allow and not args.deny:
        parser.error("Supply at least one --allow or --deny endpoint")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
