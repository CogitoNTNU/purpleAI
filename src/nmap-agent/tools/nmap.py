"""Restricted Nmap reconnaissance tool for PurpleAI.

Safety boundary: the tool takes no parameters. The scan target is
determined internally from the trusted configuration, never from the
LLM. Nmap is invoked as a fixed argument list (no shell) against the
configured host only.
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET

from langchain_core.tools import tool

from config import get_config
from logging_utils import log_event


def _run_nmap(target_host: str, timeout: int) -> str:
    """Run nmap against the configured host and return raw XML output."""
    command = ["nmap", "-sV", "-Pn", "-oX", "-", target_host]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError(
            "Nmap is not installed. Install it, e.g. 'brew install nmap' "
            "or 'sudo apt install nmap'."
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Nmap scan timed out after {timeout} seconds.")

    if result.returncode != 0:
        first_error_line = (result.stderr or "").strip().splitlines()[0]
        raise RuntimeError(f"Nmap failed: {first_error_line}")
    return result.stdout


def _parse_nmap_xml(xml_output: str) -> list[dict]:
    """Parse nmap XML and return a simple list of port entries."""
    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError as exc:
        raise RuntimeError(f"Could not parse Nmap XML output: {exc}")

    ports = []
    for port_el in root.iter("port"):
        state = port_el.find("state")
        service = port_el.find("service")
        ports.append(
            {
                "port": int(port_el.get("portid", "0")),
                "protocol": port_el.get("protocol"),
                "state": state.get("state") if state is not None else None,
                "service": service.get("name") if service is not None else None,
                "product": service.get("product") if service is not None else None,
                "version": service.get("version") if service is not None else None,
            }
        )
    return ports


@tool
def nmap_scan() -> dict:
    """Scan the single configured target and report exposed
    network services. Takes no arguments; the target is fixed in the
    configuration. Returns the target host and a list of
    discovered ports with service, state, product, and version."""
    config = get_config()
    target_host = config.target_host

    try:
        xml_output = _run_nmap(target_host, config.nmap_timeout)
        ports = _parse_nmap_xml(xml_output)
    except RuntimeError as exc:
        log_event("attacker", "tool_call", tool="nmap_scan", target=target_host, status="error")
        return {"error": str(exc)}

    log_event("attacker", "tool_call", tool="nmap_scan", target=target_host, status="success")
    return {"target": target_host, "ports": ports}
