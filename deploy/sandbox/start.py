"""One entry point for the two-PC lab. Run from either PC with sudo."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from firewall import ipv4

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
        choices=["start", "stop", "check", "run", "shell", "logs"],
    )
    args = parser.parse_args()
    if args.role == "blue" and args.action in ("run", "shell"):
        parser.error("run/shell are for the RedAI attacker; BlueAI runs continuously")
    try:
        settings = read_settings(ROOT / ".env")
        red, blue, idun = [
            ipv4(settings[name]) for name in ("RED_IP", "BLUE_IP", "IDUN_IP")
        ]
    except (OSError, ValueError, KeyError) as error:
        parser.error(f"Configure deploy/sandbox/.env first: {error}")
    env = os.environ.copy()
    env.update(settings)  # Compose and the firewall use the same values.
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / ".env"),
        "-f",
        str(ROOT / f"{args.role}.compose.yml"),
    ]

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
    else:
        call(*firewall, "--check")  # Never launch an agent without its matching policy.
        if args.action in ("run", "shell"):
            command = [*compose, "run", "--rm", "--no-deps"]
            if args.action == "shell":
                command += ["--entrypoint", "sh"]
            call(*command, "attacker")
        else:
            router = ipv4(settings["ROUTER_IP"])

            def probe(service, allowed=(), denied=()):
                """Run TCP checks in the selected service, without running the agent."""
                command = ["exec", service, "python"]
                if args.role == "red" and service == "attacker":
                    command = "run --rm --no-deps --entrypoint python attacker".split()
                endpoints = [("--allow", host) for host in allowed]
                endpoints += [("--deny", host) for host in denied]
                options = [value for pair in endpoints for value in pair]
                call(*compose, *command, "/app/check_network.py", *options)

            blocked = [f"{router}:80", f"{idun}:443"]
            if args.role == "red":
                probe(
                    "attacker",
                    ["model-gateway:9000", f"{blue}:8080"],
                    [f"{blue}:22", "172.28.10.1:22", *blocked],
                )
            else:
                probe(
                    "defender",
                    ["model-gateway:9000", "vulnerable-app:5000"],
                    ["172.28.20.1:22", *blocked],
                )
                probe(
                    "vulnerable-app",
                    denied=["172.28.20.20:9000", "172.28.21.20:8080", *blocked],
                )
            probe("model-gateway", ["llm.hpc.ntnu.no:443"], [f"{router}:80"])


if __name__ == "__main__":
    main()
