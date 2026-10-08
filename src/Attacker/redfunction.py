

import subprocess
import xml.etree.ElementTree as ET




def _run_nmap(target_host: str, timeout: int) -> str:
    """Run nmap against the configured host and return raw XML output."""
    # Argument list instead of a shell string: no shell means the LLM can
    # never inject extra nmap flags or commands. -sV probes service
    # versions, -Pn skips ping checks (the lab host blocks ICMP), and
    # -oX - writes the report as XML to stdout.
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

