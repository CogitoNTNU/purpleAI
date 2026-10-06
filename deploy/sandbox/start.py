"""Validate the matching firewall before starting a Linux sandbox stack."""

import argparse
import os
import shlex
import subprocess
from pathlib import Path

from firewall import ipv4, rules

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
    args = parser.parse_args()
    settings = read_settings(ROOT / ".env")
    red, blue, idun = [
        ipv4(settings[name]) for name in ("RED_IP", "BLUE_IP", "IDUN_IP")
    ]
    if len(settings.get("GATEWAY_TOKEN", "")) < 32:
        parser.error("Generate a gateway token of at least 32 characters")
    if not (ROOT / "secrets/idun_key").is_file():
        parser.error("Create secrets/idun_key first")
    prefix = f"PAI_{args.role.upper()}"
    for binary, parent, suffix, entries in zip(
        ("iptables", "iptables", "ip6tables", "ip6tables"),
        ("DOCKER-USER", "INPUT", "FORWARD", "INPUT"),
        ("FWD", "HOST", "FWD6", "HOST6"),
        rules(args.role, red, blue, idun),
    ):
        chain = f"{prefix}_{suffix}"
        lines = subprocess.check_output(
            [binary, "-w", "-S", parent], text=True
        ).splitlines()
        first = next(
            (shlex.split(line) for line in lines if line.startswith("-A ")), None
        )
        if first != ["-A", parent, "-j", chain]:
            parser.error(
                f"Install the {args.role} firewall first ({parent} jump missing or misplaced)"
            )
        actual = subprocess.check_output(
            [binary, "-w", "-S", chain], text=True
        ).splitlines()
        if len([line for line in actual if line.startswith("-A ")]) != len(entries) + 1:
            parser.error(f"Unexpected rules in {chain}; reinstall the firewall")
        if shlex.split(actual[-1]) != ["-A", chain, "-j", "RETURN"]:
            parser.error(f"Invalid rule order in {chain}; reinstall the firewall")
        for entry in [*entries, ["-j", "RETURN"]]:
            subprocess.run([binary, "-w", "-C", chain, *entry], check=True)
    for setting in ("bridge-nf-call-iptables", "bridge-nf-call-ip6tables"):
        if (Path("/proc/sys/net/bridge") / setting).read_text().strip() != "1":
            parser.error("Enable bridge netfilter before starting")
    # Ignore shell overrides of .env, so Compose uses exactly the checked addresses.
    env = os.environ.copy()
    env.update(settings)
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / ".env"),
        "-f",
        str(ROOT / f"{args.role}.compose.yml"),
    ]
    subprocess.run([*compose, "config", "--quiet"], check=True, env=env)
    services = ["model-gateway"] if args.role == "red" else []
    subprocess.run([*compose, "up", "--build", "-d", *services], check=True, env=env)
    if args.role == "red":
        subprocess.run([*compose, "build", "attacker"], check=True, env=env)
    print("Stack started. Follow README.md for isolation checks before running agents.")


if __name__ == "__main__":
    main()
