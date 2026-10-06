"""Run one experiment through host SSH; the collector never executes commands."""

import fcntl
import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import ipaddress
from urllib.request import Request, urlopen
from uuid import uuid4

from log_collector import ENV_FILE, read_env_file


def remote(destination, repository, role, action, run_id=None, target=None):
    if (
        not destination
        or destination.startswith("-")
        or any(c.isspace() for c in destination)
    ):
        raise ValueError("SSH destination must be an alias or user@host")
    command = [role, action]
    if run_id:
        command += ["--run-id", run_id]
    if target:
        command += ["--target", target]
    script = (
        f"cd -- {shlex.quote(repository)} && "
        'sudo -n /usr/bin/python3 "$(pwd)/deploy/sandbox/start.py" '
        f"{shlex.join(command)}"
    )
    subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            destination,
            script,
        ],
        check=True,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--without-defender",
        action="store_true",
        help="Run only the attacker against port 8081, bypassing the defender",
    )
    args = parser.parse_args(argv)
    direct = args.without_defender
    target = "direct" if direct else "defender"
    port = "8081" if direct else "8080"
    settings = {**read_env_file(ENV_FILE), **os.environ}
    token = settings.get("GAMEHOST_LOG_TOKEN", "")
    if len(token) < 32:
        raise SystemExit(
            "Set GAMEHOST_LOG_TOKEN to at least 32 characters in src/gamehost/.env"
        )
    red, blue = settings.get("RED_SSH", ""), settings.get("BLUE_SSH", "")
    repository = settings.get("REMOTE_REPO", "purpleAI")
    address = settings.get("GAMEHOST_LOG_BIND", "")
    if not red or not blue or not address or not repository:
        raise SystemExit("Set GAMEHOST_LOG_BIND, RED_SSH, BLUE_SSH and REMOTE_REPO")
    try:
        address = str(ipaddress.IPv4Address(address))
        blue_ip = str(ipaddress.IPv4Address(settings["BLUE_IP"]))
    except (ValueError, KeyError):
        raise SystemExit(
            "Set GAMEHOST_LOG_BIND and BLUE_IP to the PCs' LAN IPv4 addresses"
        ) from None
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(Path(__file__).parent / "docker-compose.yml"),
    ]
    target_url = f"http://{blue_ip}:{port}"
    # A local lock prevents two gamehost runs from assigning different defender IDs.
    directory = Path(__file__).parent / "data"
    directory.mkdir(exist_ok=True)
    with (directory / "run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another gamehost run is active") from None
        base = f"http://{address}:8765"
        with urlopen(f"{base}/health", timeout=3):
            pass
        run_id = str(uuid4())
        print(f"Run ID: {run_id}", flush=True)
        print(
            f"Target: {target_url} ({'without defender' if direct else 'through defender'})",
            flush=True,
        )

        def event(action, status):
            payload = {
                "schema_version": 1,
                "event_id": str(uuid4()),
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(
                    timespec="milliseconds"
                ),
                "source": "gamehost",
                "actor": "gamehost",
                "action": action,
                "status": status,
                "target_mode": "without_defender" if direct else "with_defender",
            }
            message = Request(
                f"{base}/events",
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urlopen(message, timeout=3):
                pass

        # Direct runs need only the attacker. Pull traffic before defended runs.
        if not direct:
            subprocess.run(
                [*compose, "pull", "traffic"], check=True, env=os.environ | settings
            )
        remote(blue, repository, "blue", "check", target=target)
        remote(red, repository, "red", "check", target=target)
        event("run_start", "started")  # Verify authentication before launching agents.
        status = "error"
        traffic_name = f"purpleai-traffic-{run_id}"
        traffic_started = False
        try:
            if not direct:
                remote(blue, repository, "blue", "session", run_id)
                # Verify defended browsing before launching traffic or the attacker.
                with urlopen(target_url + "/", timeout=150) as response:
                    if response.status != 200:
                        raise RuntimeError("Normal request failed the defender check")
                subprocess.run(
                    [
                        *compose,
                        "run",
                        "-d",
                        "--rm",
                        "--no-deps",
                        "--name",
                        traffic_name,
                        "traffic",
                    ],
                    check=True,
                    env=os.environ | settings | {"PURPLEAI_RUN_ID": run_id},
                )
                traffic_started = True
                event("traffic_start", "started")
            remote(red, repository, "red", "run", run_id, target=target)
            if traffic_started:
                running = subprocess.check_output(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{.State.Running}}",
                        traffic_name,
                    ],
                    text=True,
                ).strip()
                if running != "true":
                    raise RuntimeError(
                        "Normal traffic stopped before the attacker finished"
                    )
            status = "success"
        finally:
            # Always stop traffic and any remaining attacker, including on Ctrl+C.
            try:
                if traffic_started:
                    subprocess.run(
                        ["docker", "stop", "--time", "5", traffic_name], check=True
                    )
                    event("traffic_end", "stopped")
            finally:
                try:
                    remote(red, repository, "red", "cancel", run_id)
                finally:
                    try:
                        if not direct:
                            remote(blue, repository, "blue", "session")
                    finally:
                        event("run_end", "error" if sys.exc_info()[0] else status)
        print(f"Finished: {run_id}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Run interrupted; cleanup attempted", file=sys.stderr)
        raise SystemExit(130) from None
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Run failed: {error}") from None
