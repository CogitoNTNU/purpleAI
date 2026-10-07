"""Launch an operator-selected Python workflow or WSGI application."""

import argparse
import logging
import os
import re
import sys
from pathlib import Path

from purpleai.event_logging import configure_logging

MODULE = r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*"
logger = logging.getLogger(__name__)


def command(role, settings):
    """Use argument lists, with no shell or agent-specific defaults."""
    if role == "attacker":
        module = settings.get("ATTACKER_MODULE", "").strip()
        if not re.fullmatch(MODULE, module):
            raise ValueError(
                "Set ATTACKER_MODULE to a Python module in the attacker .env"
            )
        return [sys.executable, "-m", module]
    if role == "defender":
        application = settings.get("DEFENDER_APP", "").strip()
        if not re.fullmatch(f"{MODULE}:{MODULE}", application):
            raise ValueError("Set DEFENDER_APP to module:app in the defender .env")
        return [
            "gunicorn",
            "--bind",
            "0.0.0.0:8080",
            "--workers",
            "1",
            "--threads",
            "4",
            "--timeout",
            "180",
            application,
        ]
    raise ValueError("Role must be attacker or defender")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["attacker", "defender"])
    args = parser.parse_args()
    configure_logging()
    try:
        # Compose injects settings. Native runs may read the role's own .env.
        if Path(".env").is_file():
            from dotenv import load_dotenv

            load_dotenv(".env")
        arguments = command(args.role, os.environ)
        # Replace the launcher so container shutdown reaches the actual agent/server.
        os.execvp(arguments[0], arguments)
    except (ValueError, OSError, ImportError) as error:
        logger.error("Cannot start %s: %s", args.role, error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
