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


def validate_addresses(addresses):
    if len(set(addresses)) != len(addresses):
        raise ValueError(
            "PC, gamehost, development PC and Idun addresses must be distinct"
        )
    managed = [ipaddress.ip_network(f"172.28.{n}.0/24") for n in (10, 20, 21)]
    if any(ipaddress.ip_address(ip) in net for ip in addresses for net in managed):
        raise ValueError("PC/Idun addresses must not overlap sandbox subnets")


def policy(
    role, red_ip, blue_ip, idun_ip, gamehost_ip=None, direct_testing=False, dev_ip=None
):
    """Return permitted TCP initiations, managed subnets and bridge names."""
    logging = (
        [("172.28.10.10" if role == "red" else "172.28.20.10", gamehost_ip, 8765)]
        if gamehost_ip
        else []
    )
    if role == "red":
        return (
            [
                ("172.28.10.10", "172.28.10.20", 9000),
                ("172.28.10.10", blue_ip, 8080),
                ("172.28.10.20", idun_ip, 443),
            ]
            + logging
            + ([("172.28.10.10", blue_ip, 8081)] if direct_testing else []),
            ["172.28.10.0/24"],
            ["pai-red-lab"],
        )
    return (
        [
            (red_ip, "172.28.20.10", 8080),
            ("172.28.20.10", "172.28.20.20", 9000),
            ("172.28.21.20", "172.28.21.10", 5000),
            ("172.28.20.20", idun_ip, 443),
        ]
        + logging
        + ([(gamehost_ip, "172.28.20.10", 8080)] if gamehost_ip else [])
        + (
            [(red_ip, "172.28.20.30", 5000), ("172.28.20.10", "172.28.20.30", 5000)]
            if direct_testing
            else []
        )
        + ([(dev_ip, "172.28.20.10", 8080)] if dev_ip else [])
        + ([(dev_ip, "172.28.20.30", 5000)] if dev_ip and direct_testing else []),
        ["172.28.20.0/24", "172.28.21.0/24"],
        ["pai-blue-front", "pai-blue-back"],
    )


def rules(
    role, red_ip, blue_ip, idun_ip, gamehost_ip=None, direct_testing=False, dev_ip=None
):
    flows, subnets, bridges = policy(
        role, red_ip, blue_ip, idun_ip, gamehost_ip, direct_testing, dev_ip
    )
    forward = []
    for source, destination, port in flows:
        # Only replies to an allowed TCP connection may travel back.
        forward += [
            shlex.split(
                f"-s {source} -d {destination} -p tcp --dport {port} "
                "-m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT"
            ),
            shlex.split(
                f"-s {destination} -d {source} -p tcp --sport {port} "
                "-m conntrack --ctstate ESTABLISHED -j ACCEPT"
            ),
        ]
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
    parser.add_argument("--gamehost-ip", type=ipv4)
    parser.add_argument("--dev-ip", type=ipv4)
    parser.add_argument("--direct-testing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--remove", action="store_true")
    mode.add_argument(
        "--check", action="store_true", help="Verify rules without changing them"
    )
    args = parser.parse_args()
    addresses = [args.red_ip, args.blue_ip, args.idun_ip] + [
        ip for ip in (args.gamehost_ip, args.dev_ip) if ip
    ]
    try:
        validate_addresses(addresses)
    except ValueError as error:
        parser.error(str(error))
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
        if result.stdout.strip() and not args.check:
            parser.error("Stop the sandbox containers before changing firewall rules")

    def run(binary, *parts, check=True):
        command = [binary, "-w", *parts]
        if args.dry_run:
            print(shlex.join(command))
            return 1  # Show create/insert operations in preview.
        return subprocess.run(command, check=check, capture_output=True).returncode

    prefix = f"PAI_{args.role.upper()}"
    v4_forward, v4_host, v6_forward, v6_host = rules(
        args.role,
        args.red_ip,
        args.blue_ip,
        args.idun_ip,
        args.gamehost_ip,
        args.direct_testing,
        args.dev_ip,
    )
    for binary, parent, suffix, entries in (
        ("iptables", "DOCKER-USER", "FWD", v4_forward),
        ("iptables", "INPUT", "HOST", v4_host),
        ("ip6tables", "FORWARD", "FWD6", v6_forward),
        ("ip6tables", "INPUT", "HOST6", v6_host),
    ):
        chain = f"{prefix}_{suffix}"
        if args.check:
            lines = subprocess.check_output(
                [binary, "-w", "-S", parent], text=True
            ).splitlines()
            first = next(
                (shlex.split(line) for line in lines if line.startswith("-A ")), None
            )
            if first != ["-A", parent, "-j", chain]:
                parser.error(
                    "Firewall missing or misplaced; stop the lab, then start it again"
                )
            actual = subprocess.check_output(
                [binary, "-w", "-S", chain], text=True
            ).splitlines()
            if len([line for line in actual if line.startswith("-A ")]) != len(
                entries
            ) + 1 or shlex.split(actual[-1]) != ["-A", chain, "-j", "RETURN"]:
                parser.error(
                    "Firewall rules changed; stop the lab, then start it again"
                )
            for entry in [*entries, ["-j", "RETURN"]]:
                run(binary, "-C", chain, *entry)
            continue
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
