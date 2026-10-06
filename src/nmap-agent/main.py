"""PurpleAI attacker v0 CLI entry point.

Runs a predefined reconnaissance task through the LangChain attacker
agent, backed by the NTNU IDUN LLM API and the restricted Nmap tool.
"""

from __future__ import annotations

import logging
import sys

from agent import describe_llm_error, run_agent
from config import ConfigError, get_config
from logging_utils import log_event
from purpleai.event_logging import configure_logging

logger = logging.getLogger(__name__)

TASK = (
    "Investigate the configured PurpleAI target and determine which "
    "network services are exposed."
)


def main() -> int:
    configure_logging()
    # Load and validate configuration before anything else runs, so a
    # bad .env fails fast with a clear message instead of mid-run.
    try:
        config = get_config()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    logger.info("PurpleAI attacker v0")
    logger.info("Target: %s", config.target_url)
    logger.info("Model: %s", config.idun_model)
    logger.info("LLM API: %s", config.idun_base_url)

    log_event("attacker", "task_start", target=config.target_host, status="started")

    try:
        run_agent(TASK)
    except Exception as exc:
        message = describe_llm_error(exc)
        logger.error("%s", message)
        log_event("attacker", "task_end", target=config.target_host, status="error")
        return 1

    log_event("attacker", "task_end", target=config.target_host, status="success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
