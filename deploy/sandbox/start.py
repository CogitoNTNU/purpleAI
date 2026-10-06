"""One entry point for the two-PC lab. Run from either PC with sudo."""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from firewall import ipv4, validate_addresses

ROOT = Path(__file__).resolve().parent


def read_settings(path):
    settings = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, value = line.split("=", 1)
            settings[name.strip()] = value.strip().strip("\"'")
    return settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["red", "blue"])
    parser.add_argument(
        "action",
        nargs="?",
        default="start",
        choices=["start", "stop", "check", "run", "shell", "logs", "session", "cancel"],
    )
    parser.add_argument(
        "--run-id", help="Shared gamehost run UUID (red run/cancel or blue session)"
    )
    parser.add_argument(
        "--target",
        choices=["defender", "direct"],
        help="Target for red run/shell; defaults to defender",
    )
    parser.add_argument(
        "--no-collector",
        action="store_true",
        help="Skip collector availability/delivery during check",
    )
    args = parser.parse_args()
    if args.target and (args.role != "red" or args.action not in ("run", "shell")):
        parser.error("--target applies to red run/shell")
    if args.no_collector and args.action != "check":
        parser.error("--no-collector applies to check")
    if args.action == "cancel" and args.role != "red":
        parser.error("cancel is for RedAI")
    if args.action == "session" and args.role != "blue":
        parser.error("session is for BlueAI")
    if args.run_id:
        if (args.role, args.action) not in (
            ("red", "run"),
            ("red", "cancel"),
            ("blue", "session"),
        ):
            parser.error("--run-id applies to red run/cancel or blue session")
        try:
            args.run_id = str(UUID(args.run_id))
        except ValueError:
            parser.error("--run-id must be a UUID")
    if args.role == "blue" and args.action in ("run", "shell"):
        parser.error("run/shell are for the RedAI attacker; BlueAI runs continuously")
    try:
        settings = read_settings(ROOT / ".env")
        red, blue, idun = [
            ipv4(settings[name]) for name in ("RED_IP", "BLUE_IP", "IDUN_IP")
        ]
    except (OSError, ValueError, KeyError) as error:
        parser.error(f"Configure deploy/sandbox/.env first: {error}")
    direct_setting = settings.get("DIRECT_TESTING", "false").lower()
    if direct_setting not in ("true", "false"):
        parser.error("DIRECT_TESTING must be true or false")
    direct_testing = direct_setting == "true"
    if args.target == "direct" and not direct_testing:
        parser.error("Set DIRECT_TESTING=true on both PCs before using --target direct")
    env = os.environ.copy()
    env.update(settings)  # Compose and the firewall use the same values.
    env["PURPLEAI_RUN_ID"] = args.run_id or ""
    env["TARGET_PORT"] = "8081" if args.target == "direct" else "8080"
    gamehost = settings.get("GAMEHOST_IP", "")
    log_token = settings.get("LOG_COLLECTOR_TOKEN", "")
    if bool(gamehost) != bool(log_token):
        parser.error("Set GAMEHOST_IP and LOG_COLLECTOR_TOKEN together")
    dev = settings.get("DEV_IP", "") if args.role == "blue" else ""
    try:
        gamehost = ipv4(gamehost) if gamehost else ""
        dev = ipv4(dev) if dev else ""
        validate_addresses([red, blue, idun] + [ip for ip in (gamehost, dev) if ip])
    except (ValueError, argparse.ArgumentTypeError) as error:
        parser.error(str(error))
    if gamehost:
        if len(log_token) < 32:
            parser.error("LOG_COLLECTOR_TOKEN must have at least 32 characters")
    env["LOG_COLLECTOR_URL"] = f"http://{gamehost}:8765/events" if gamehost else ""
    env["LOG_COLLECTOR_TOKEN"] = log_token
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / ".env"),
        "-f",
        str(ROOT / f"{args.role}.compose.yml"),
    ]
    if args.role == "blue" and direct_testing:
        compose += ["-f", str(ROOT / "blue.direct.compose.yml")]

    def call(*command):
        subprocess.run(command, check=True, env=env)

    firewall = [
        sys.executable,
        str(ROOT / "firewall.py"),
        args.role,
        "--red-ip",
        red,
        "--blue-ip",
        blue,
        "--idun-ip",
        idun,
    ]
    if gamehost:
        firewall += ["--gamehost-ip", gamehost]
    if direct_testing:
        firewall += ["--direct-testing"]
    if dev:
        firewall += ["--dev-ip", dev]
    if args.action == "start":
        if not sys.platform.startswith("linux") or os.geteuid() != 0:
            parser.error("Start with sudo on the Kali/Ubuntu PC")
        if (
            len(settings.get("GATEWAY_TOKEN", "")) < 32
            or not (ROOT / "secrets/idun_key").is_file()
        ):
            parser.error("Set GATEWAY_TOKEN and create secrets/idun_key first")
        call(*compose, "config", "--quiet")
        call("modprobe", "br_netfilter")
        for setting in ("bridge-nf-call-iptables", "bridge-nf-call-ip6tables"):
            call("sysctl", "-w", f"net.bridge.{setting}=1")
        call(*firewall)
        call(
            *compose,
            "up",
            "--build",
            "-d",
            "--wait",
            *(["model-gateway"] if args.role == "red" else []),
        )
        if args.role == "red":
            call(*compose, "build", "attacker")
        print("Ready. Run the check command on both PCs before running the attacker.")
    elif args.action == "stop":
        call(*compose, "down")
    elif args.action == "logs":
        call(*compose, "logs", "--tail", "100")
    elif args.action == "cancel":
        name = (
            f"name=^purpleai-red-attacker-run-{args.run_id}$"
            if args.run_id
            else "name=^purpleai-red-attacker-run"
        )
        running = subprocess.check_output(
            [
                "docker",
                "ps",
                "-q",
                "--filter",
                name,
                "--filter",
                "label=com.docker.compose.project=purpleai-red",
            ],
            text=True,
        ).strip()
        if running:
            call("docker", "stop", "--time", "5", *running.split())
    else:
        call(*firewall, "--check")  # Never launch an agent without its matching policy.
        if args.action == "session":
            call(
                *compose,
                "up",
                "-d",
                "--no-deps",
                "--force-recreate",
                "--wait",
                "defender",
            )
        elif args.action in ("run", "shell"):
            command = [*compose, "run", "--rm", "--no-deps"]
            if args.action == "shell":
                command += ["--entrypoint", "sh"]
            else:
                command += [
                    "--name",
                    "purpleai-red-attacker-run"
                    + (f"-{args.run_id}" if args.run_id else ""),
                ]
            call(*command, "attacker")
        else:
            router = ipv4(settings["ROUTER_IP"])

            def probe(service, allowed=(), denied=()):
                """Run TCP checks in the selected service, without running the agent."""
                skip_delivery = (
                    ["-e", "LOG_COLLECTOR_URL="] if args.no_collector else []
                )
                command = ["exec", *skip_delivery, service, "python"]
                if args.role == "red" and service == "attacker":
                    command = [
                        "run",
                        "--rm",
                        "--no-deps",
                        "--entrypoint",
                        "python",
                        *skip_delivery,
                        "attacker",
                    ]
                endpoints = [("--allow", host) for host in allowed]
                endpoints += [("--deny", host) for host in denied]
                options = [value for pair in endpoints for value in pair]
                pc = "RedAI" if args.role == "red" else "BlueAI"
                call(
                    *compose,
                    *command,
                    "/app/check_network.py",
                    "--from",
                    f"{pc} / {service}",
                    *options,
                )

            blocked = [f"{router}:80", f"{idun}:443"]
            check_collector = gamehost and not args.no_collector
            if args.role == "red":
                probe(
                    "attacker",
                    ["model-gateway:9000", f"{blue}:8080"]
                    + ([f"{blue}:8081"] if direct_testing else [])
                    + ([f"{gamehost}:8765"] if check_collector else []),
                    [f"{blue}:22", "172.28.10.1:22", *blocked]
                    + ([] if direct_testing else [f"{blue}:8081"]),
                )
            else:
                probe(
                    "defender",
                    ["model-gateway:9000", "vulnerable-app:5000"]
                    + ([f"{gamehost}:8765"] if check_collector else []),
                    ["172.28.20.1:22", *blocked],
                )
                probe(
                    "vulnerable-app",
                    denied=[
                        "172.28.20.20:9000",
                        "172.28.21.20:8080",
                        "172.28.20.10:8080",
                        "172.28.20.1:22",
                        *blocked,
                    ]
                    + ([f"{gamehost}:8765"] if gamehost else []),
                )
            probe(
                "model-gateway",
                ["llm.hpc.ntnu.no:443"],
                [f"{router}:80"] + ([f"{gamehost}:8765"] if gamehost else []),
            )


if __name__ == "__main__":
    main()
