#!/usr/bin/env python3
"""Example script for blue team PC to send events to the gamehost.

This demonstrates how to use the EventSender class to log defensive actions
from the blue team PC to the gamehost dashboard.

Copy event_sender.py and this file to your blue team PC, then run:
    python3 blueteam_example.py
"""

import time
from event_sender import EventSender


def main():
    """Example showing various defensive monitoring and actions."""

    # Initialize the sender with your gamehost details
    sender = EventSender(
        collector_url="http://192.168.0.110:8765/events",  # Your gamehost IP
        token="or9FN0WytGlAAnkDABMdOI7M6zoxNMIqtWpe9nTaC5A",  # Get from gamehost/.env
        source="blue-team-pc",  # Identifies this machine in the dashboard
    )

    # Check if the gamehost is reachable
    print("Checking connection to gamehost...")
    if sender.health_check():
        print("Connected to gamehost successfully!")
    else:
        print("Warning: Cannot reach gamehost. Events will be logged locally only.")

    # Example 1: Log start of defensive monitoring
    sender.log_event(
        actor="defender",
        action="task_start",
        status="started",
    )

    # Example 2: Log a firewall rule being added
    sender.log_event(
        actor="defender",
        action="tool_call",
        tool="iptables",
        target="192.168.50.10:8080",
        status="blocked",
    )

    # Example 3: Log intrusion detection
    sender.log_event(
        actor="defender",
        action="detection",
        tool="ids",
        target="192.168.50.10:22",
        status="suspicious",
    )

    # Example 4: Log a service restart
    sender.log_event(
        actor="defender",
        action="service_restart",
        tool="systemctl",
        target="nginx",
        status="success",
    )

    # Example 5: Log file integrity check
    sender.log_event(
        actor="defender",
        action="integrity_check",
        tool="aide",
        target="/etc/passwd",
        status="success",
    )

    # Example 6: Log blocked attack attempt
    sender.log_event(
        actor="defender",
        action="block_attack",
        tool="fail2ban",
        target="192.168.50.100:22",
        status="blocked",
    )

    # Example 7: End of defensive monitoring
    sender.log_event(
        actor="defender",
        action="task_end",
        status="success",
    )

    print("\nExample events sent to gamehost!")
    print("Check the dashboard at http://192.168.0.110:8501")


def monitoring_loop_example():
    """Example of a continuous monitoring loop."""

    sender = EventSender(
        collector_url="http://192.168.0.110:8765/events",
        token="replace-with-your-gamehost-token",
        source="blue-team-monitor",
    )

    sender.log_event(actor="defender", action="task_start", status="started")

    try:
        iteration = 0
        while True:
            iteration += 1

            # Example: Check for suspicious activity
            sender.log_event(
                actor="defender",
                action="scan",
                tool="netstat",
                status="clean",
            )

            # Example: Monitor specific ports
            sender.log_event(
                actor="defender",
                action="port_check",
                tool="nmap",
                target="192.168.50.10:8080",
                status="open",
            )

            print(f"Monitoring iteration {iteration} complete")
            time.sleep(30)  # Check every 30 seconds

    except KeyboardInterrupt:
        sender.log_event(actor="defender", action="task_end", status="stopped")
        print("\nMonitoring stopped.")


def parse_log_file_example():
    """Example of parsing existing log files and sending events."""

    sender = EventSender(
        collector_url="http://192.168.0.110:8765/events",
        token="replace-with-your-gamehost-token",
        source="blue-team-parser",
    )

    # Example: Parse /var/log/auth.log for SSH attempts
    log_file = "/var/log/auth.log"  # Adjust path as needed

    try:
        with open(log_file, "r") as f:
            for line in f:
                # Simple example: detect failed SSH attempts
                if "Failed password" in line:
                    # Extract IP if possible (simplified)
                    parts = line.split()
                    ip = "unknown"
                    for i, part in enumerate(parts):
                        if part == "from" and i + 1 < len(parts):
                            ip = parts[i + 1]
                            break

                    sender.log_event(
                        actor="defender",
                        action="detection",
                        tool="sshd",
                        target=ip,
                        status="failed_auth",
                    )

        print(f"Finished parsing {log_file}")

    except FileNotFoundError:
        print(f"Log file {log_file} not found")
    except PermissionError:
        print(f"Permission denied reading {log_file}")


if __name__ == "__main__":
    # Run the basic example
    main()

    # Uncomment to run the monitoring loop instead:
    # monitoring_loop_example()

    # Uncomment to parse log files:
    # parse_log_file_example()
