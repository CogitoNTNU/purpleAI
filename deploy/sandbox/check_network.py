"""TCP smoke checks to execute inside each sandbox container.

A refused connection demonstrates no reachable service, not necessarily a
firewall drop. Pair this check with host firewall counters and a known listener.
"""

import argparse
import socket


def endpoint(value):
    host, port = value.rsplit(":", 1)
    return host, int(port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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
                f"{'PASS' if passed else 'FAIL'} {host}:{port}: {'reachable' if reachable else 'unreachable'}"
            )
    if not args.allow and not args.deny:
        parser.error("Supply at least one --allow or --deny endpoint")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
