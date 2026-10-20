"""Exercise real proxy branches without an LLM or upstream network call."""

import importlib.util
import io
import json
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "src/defender/defender-agent" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def defender(tmp_path, monkeypatch):
    monkeypatch.setenv("PURPLEAI_LOG_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("IDUNN_BASE_URL", "https://unused.invalid/v1")
    monkeypatch.setenv("IDUNN_API_KEY", "unused")
    logger = load("test_defender_events", "event_logging.py")
    fake_llm = types.ModuleType("langchain_openai")
    fake_llm.ChatOpenAI = Mock()
    with patch.dict(
        sys.modules, {"event_logging": logger, "langchain_openai": fake_llm}
    ):
        module = load("test_defender", "defender.py")
    return module, tmp_path / "events.jsonl", logger


@pytest.mark.parametrize(
    "outcome", ["allowed", "blocked", "classifier_error", "upstream_error"]
)
def test_decisions_and_results(defender, outcome):
    module, path, _ = defender
    agent = Mock(return_value=outcome == "blocked")
    if outcome == "classifier_error":
        agent.side_effect = RuntimeError("secret classifier data")
    module.AGENTS = [agent]
    upstream = Mock(status_code=200, content=b"ok", headers={})
    with patch.object(module.requests, "request", return_value=upstream) as send:
        if outcome == "upstream_error":
            send.side_effect = requests.ConnectionError("secret upstream data")
        with redirect_stdout(io.StringIO()):
            response = module.app.test_client().post(
                "/probe?token=secret-query", data="secret-body"
            )
    events = [json.loads(line) for line in path.read_text().splitlines()]
    decision = events[0]
    assert decision["source"] == "defender-agent"
    assert decision["action"] == "request_decision"
    assert decision["status"] == (
        "error"
        if outcome == "classifier_error"
        else "allowed"
        if outcome == "upstream_error"
        else outcome
    )
    if outcome in ("blocked", "classifier_error"):
        assert response.status_code == 403
        send.assert_not_called()
        assert len(events) == 1
    else:
        assert response.status_code == (500 if outcome == "upstream_error" else 200)
        assert events[1]["request_id"] == decision["request_id"]
        assert events[1]["status"] == (
            "error" if outcome == "upstream_error" else "returned"
        )
    assert "secret" not in path.read_text()


def test_concurrent_decisions_are_complete_json_lines(defender):
    _, path, logger = defender
    with redirect_stdout(io.StringIO()):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(
                pool.map(
                    lambda _: logger.log_event("request_decision", status="blocked"),
                    range(100),
                )
            )
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(events) == len({event["event_id"] for event in events}) == 100
