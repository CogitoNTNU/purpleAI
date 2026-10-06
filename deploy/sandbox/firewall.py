"""Install narrow Docker firewall rules on the selected Linux lab PC.

Requires Docker's iptables backend and bridge netfilter. Never flushes global
rules. Run with --dry-run to review commands; remove only after stopping the lab.
"""

import argparse
import ipaddress
import os
import platform
import shlex
import subprocess
from pathlib import Path


def ipv4(value):
    address = ipaddress.IPv4Address(value)
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise argparse.ArgumentTypeError(
            "A unicast, non-loopback IPv4 address is required"
        )
    return str(address)


def policy(role, red_ip, blue_ip, idun_ip):
    """Return permitted TCP initiations, managed subnets and bridge names."""
    if role == "red":
        return (
            [
                ("172.28.10.10", "172.28.10.20", 9000),
                ("172.28.10.10", blue_ip, 8080),
                ("172.28.11.20", idun_ip, 443),
            ],
            ["172.28.10.0/24", "172.28.11.0/24"],
            ["pai-red-lab", "pai-red-out"],
        )
    return (
        [
            (red_ip, "172.28.20.10", 8080),
            ("172.28.20.10", "172.28.20.20", 9000),
            ("172.28.21.20", "172.28.21.10", 5000),
            ("172.28.22.20", idun_ip, 443),
        ],
        ["172.28.20.0/24", "172.28.21.0/24", "172.28.22.0/24"],
        ["pai-blue-front", "pai-blue-back", "pai-blue-out"],
    )


def rules(role, red_ip, blue_ip, idun_ip):
    flows, subnets, bridges = policy(role, red_ip, blue_ip, idun_ip)
    forward = []
    for source, destination, port in flows:
        forward.extend(
            [
                [
                    "-s",
                    source,
                    "-d",
                    destination,
                    "-p",
                    "tcp",
                    "--dport",
                    str(port),
                    "-m",
                    "conntrack",
                    "--ctstate",
                    "NEW,ESTABLISHED",
                    "-j",
                    "ACCEPT",
                ],
                [
                    "-s",
                    destination,
                    "-d",
                    source,
                    "-p",
                    "tcp",
                    "--sport",
                    str(port),
                    "-m",
                    "conntrack",
                    "--ctstate",
                    "ESTABLISHED",
                    "-j",
                    "ACCEPT",
                ],
            ]
        )
    for subnet in subnets:
        forward.extend([["-s", subnet, "-j", "DROP"], ["-d", subnet, "-j", "DROP"]])
    # Interface rules also catch unexpected or spoofed container addresses.
    for bridge in bridges:
        forward.extend([["-i", bridge, "-j", "DROP"], ["-o", bridge, "-j", "DROP"]])
    host = [["-i", bridge, "-j", "DROP"] for bridge in bridges]
    host += [["-s", subnet, "-j", "DROP"] for subnet in subnets]
    ipv6_forward = []
    for bridge in bridges:
        ipv6_forward.extend(
            [["-i", bridge, "-j", "DROP"], ["-o", bridge, "-j", "DROP"]]
        )
    return forward, host, ipv6_forward, [["-i", b, "-j", "DROP"] for b in bridges]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["red", "blue"])
    parser.add_argument("--red-ip", required=True, type=ipv4)
    parser.add_argument("--blue-ip", required=True, type=ipv4)
    parser.add_argument("--idun-ip", required=True, type=ipv4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    if len({args.red_ip, args.blue_ip, args.idun_ip}) != 3:
        parser.error("PC and Idun addresses must be distinct")
    managed = [ipaddress.ip_network(f"172.28.{n}.0/24") for n in (10, 11, 20, 21, 22)]
    if any(
        ipaddress.ip_address(ip) in net
        for ip in (args.red_ip, args.blue_ip, args.idun_ip)
        for net in managed
    ):
        parser.error("PC/Idun addresses must not overlap sandbox subnets")
    if not args.dry_run:
        if platform.system() != "Linux" or os.geteuid() != 0:
            parser.error(
                "Apply only as root on the Linux lab PC; use --dry-run elsewhere"
            )
        for setting in ("bridge-nf-call-iptables", "bridge-nf-call-ip6tables"):
            path = Path("/proc/sys/net/bridge") / setting
            if not path.exists() or path.read_text().strip() != "1":
                parser.error(f"Enable br_netfilter and net.bridge.{setting}=1 first")
        subprocess.run(
            ["iptables", "-w", "-S", "DOCKER-USER"], check=True, capture_output=True
        )
        # Stop containers first: updating an active policy would create a gap.
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-q",
                "--filter",
                f"label=com.docker.compose.project=purpleai-{args.role}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            parser.error("Stop the sandbox containers before changing firewall rules")

    def run(binary, *parts, check=True):
        command = [binary, "-w", *parts]
        if args.dry_run:
            print(shlex.join(command))
            return 1  # Show create/insert operations in preview.
        return subprocess.run(command, check=check, capture_output=True).returncode

    prefix = f"PAI_{args.role.upper()}"
    v4_forward, v4_host, v6_forward, v6_host = rules(
        args.role, args.red_ip, args.blue_ip, args.idun_ip
    )
    for binary, parent, suffix, entries in (
        ("iptables", "DOCKER-USER", "FWD", v4_forward),
        ("iptables", "INPUT", "HOST", v4_host),
        ("ip6tables", "FORWARD", "FWD6", v6_forward),
        ("ip6tables", "INPUT", "HOST6", v6_host),
    ):
        chain = f"{prefix}_{suffix}"
        if args.remove:
            run(binary, "-D", parent, "-j", chain, check=False)
            run(binary, "-F", chain, check=False)
            run(binary, "-X", chain, check=False)
            continue
        if run(binary, "-S", chain, check=False):
            run(binary, "-N", chain)
        run(binary, "-F", chain)
        for entry in entries:
            run(binary, "-A", chain, *entry)
        run(binary, "-A", chain, "-j", "RETURN")
        # Keep our policy before any existing broad ACCEPT rules.
        run(binary, "-D", parent, "-j", chain, check=False)
        run(binary, "-I", parent, "1", "-j", chain)


if __name__ == "__main__":
    main()
