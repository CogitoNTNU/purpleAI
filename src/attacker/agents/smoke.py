"""Check target HTTP access, model access and events before an experiment."""

import logging
import os
import sys

import requests

from purpleai.event_logging import EventSender, configure_logging


def main():
    configure_logging()
    sender = EventSender(
        "smoke-agent",
        "attacker",
        url=os.environ.get("LOG_COLLECTOR_URL", ""),
        token=os.environ.get("LOG_COLLECTOR_TOKEN", ""),
    )
    sender.emit("task_start", status="started")
    try:
        target = os.environ["TARGET_URL"]
        with requests.Session() as client:
            client.trust_env = False
            response = client.get(target + "/", timeout=(5, 150))
            response.raise_for_status()
            sender.emit(
                "tool_result",
                tool="http_check",
                target=target,
                status="returned",
                http_status=response.status_code,
            )
            model = client.post(
                os.environ["IDUN_BASE_URL"].rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + os.environ["IDUN_API_KEY"]},
                json={
                    "model": os.environ["AGENT_MODEL"],
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 128,
                },
                timeout=(5, 150),
            )
            model.raise_for_status()
            if not model.json().get("choices"):
                raise ValueError("Model response contains no choices")
            sender.emit(
                "tool_result",
                tool="model_check",
                status="returned",
                model=os.environ["AGENT_MODEL"],
            )
    except (KeyError, ValueError, requests.RequestException) as error:
        logging.getLogger(__name__).error(
            "Smoke check failed (%s)", type(error).__name__
        )
        sender.emit("task_end", status="error", error_type=type(error).__name__)
        return 1
    sender.emit("task_end", status="success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
