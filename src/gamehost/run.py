"""Run one experiment through host SSH; the collector never executes commands."""

import fcntl
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


def remote(destination, repository, role, action, run_id=None):
    if (
        not destination
        or destination.startswith("-")
        or any(c.isspace() for c in destination)
    ):
        raise ValueError("SSH destination must be an alias or user@host")
    command = [role, action]
    if run_id:
        command += ["--run-id", run_id]
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


def main():
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

        # Pull k6 before the experiment so image download time is excluded.
        subprocess.run(
            [*compose, "pull", "traffic"], check=True, env=os.environ | settings
        )
        remote(blue, repository, "blue", "check")
        remote(red, repository, "red", "check")
        event("run_start", "started")  # Verify authentication before launching agents.
        status = "error"
        traffic_name = f"purpleai-traffic-{run_id}"
        traffic_started = False
        try:
            remote(blue, repository, "blue", "session", run_id)
            # Verify gamehost can reach the defender before launching the attacker.
            with urlopen(f"http://{blue_ip}:8080/", timeout=150) as response:
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
            remote(red, repository, "red", "run", run_id)
            running = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.State.Running}}", traffic_name],
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
