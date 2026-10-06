"""Gamehost coordination and real HTTP event delivery without SSH or Idun calls."""

import importlib.util
import io
import json
import sys
import threading
import types
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def collector(tmp_path):
    module = load("collector_run_test", "src/gamehost/log_collector.py")
    module.TOKEN = "x" * 32
    module.DATA_FILE = tmp_path / "events.jsonl"
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.EventHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield module, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_both_agents_deliver_shared_id_and_defender_decisions(collector, monkeypatch):
    module, base = collector
    run_id = str(uuid4())
    monkeypatch.setenv("PURPLEAI_RUN_ID", run_id)
    monkeypatch.setenv("LOG_COLLECTOR_URL", base + "/events")
    monkeypatch.setenv("LOG_COLLECTOR_TOKEN", "x" * 32)
    fake_config = types.ModuleType("config")
    fake_config.get_config = lambda: types.SimpleNamespace(
        log_collector_url=base + "/events", log_collector_token="x" * 32
    )
    monkeypatch.setitem(sys.modules, "config", fake_config)
    attacker = load("attacker_run_events", "src/nmap-agent/logging_utils.py")
    defender_events = load(
        "defender_run_events", "src/defender/defender-agent/events.py"
    )
    monkeypatch.setitem(sys.modules, "events", defender_events)
    monkeypatch.setenv("AGENT_MODEL", "lab-model")
    monkeypatch.setenv("IDUNN_BASE_URL", "http://unused/v1")
    monkeypatch.setenv("IDUNN_API_KEY", "dummy")
    defender = load("defender_run_test", "src/defender/defender-agent/defender.py")
    with redirect_stdout(io.StringIO()):
        attacker.log_event("attacker", "task_start")
        defender.AGENTS = [lambda _: True]
        assert defender.app.test_client().get("/search?q=synthetic").status_code == 403
        defender.AGENTS = [lambda _: False]
        with patch.object(defender.requests, "request") as upstream:
            upstream.return_value.status_code = 200
            upstream.return_value.content = b"ok"
            upstream.return_value.headers = {}
            assert (
                defender.app.test_client()
                .get("/", headers={"X-PurpleAI-Traffic": "normal"})
                .status_code
                == 200
            )
        defender.AGENTS = [
            lambda _: (_ for _ in ()).throw(RuntimeError("model offline"))
        ]
        assert defender.app.test_client().get("/").status_code == 403
    events = [json.loads(line) for line in module.DATA_FILE.read_text().splitlines()]
    assert {event["run_id"] for event in events} == {run_id}
    assert {event["source"] for event in events} == {"nmap-agent", "defender"}
    decisions = [event for event in events if event["action"] == "request_decision"]
    assert [e["status"] for e in decisions] == ["blocked", "forwarded", "model_error"]
    assert decisions[1]["traffic"] == "normal"


@pytest.mark.parametrize("fails", [False, True])
def test_runner_starts_traffic_and_cleans_up_on_attacker_failure(
    tmp_path, monkeypatch, fails
):
    collector = load("runner_collector", "src/gamehost/log_collector.py")
    monkeypatch.setitem(sys.modules, "log_collector", collector)
    runner = load("gamehost_runner", "src/gamehost/run.py")
    monkeypatch.setattr(runner, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(
        runner,
        "read_env_file",
        lambda _: {
            "GAMEHOST_LOG_TOKEN": "x" * 32,
            "GAMEHOST_LOG_BIND": "192.168.0.110",
            "BLUE_IP": "192.168.0.120",
            "RED_SSH": "red",
            "BLUE_SSH": "blue",
            "REMOTE_REPO": "purpleAI",
        },
    )
    calls, events = [], []

    def remote(*args):
        calls.append(args)
        if fails and args[2:4] == ("red", "run"):
            raise RuntimeError("attacker failure")

    from unittest.mock import MagicMock

    def opened(message, **kwargs):
        if not isinstance(message, str):
            events.append(json.loads(message.data))
        context = MagicMock()
        context.__enter__.return_value.status = 200
        return context

    monkeypatch.setattr(runner, "remote", remote)
    monkeypatch.setattr(runner, "urlopen", opened)
    with (
        patch.object(runner.subprocess, "run") as docker,
        patch.object(runner.subprocess, "check_output", return_value="true\n"),
    ):
        if fails:
            with pytest.raises(RuntimeError, match="attacker failure"):
                runner.main()
        else:
            runner.main()
    shared = [args[4] for args in calls if len(args) == 5 and args[3] != "cancel"]
    assert len(set(shared)) == 1 and len(shared) == 2
    assert calls[-2:] == [
        ("red", "purpleAI", "red", "cancel", shared[0]),
        ("blue", "purpleAI", "blue", "session"),
    ]
    assert [e["action"] for e in events] == [
        "run_start",
        "traffic_start",
        "traffic_end",
        "run_end",
    ]
    assert len({e["run_id"] for e in events}) == 1
    assert events[-1]["status"] == ("error" if fails else "success")
    assert any(
        "traffic" in call.args[0] and "-d" in call.args[0]
        for call in docker.call_args_list
    )
    assert any(call.args[0][:2] == ["docker", "stop"] for call in docker.call_args_list)


def test_ssh_quotes_repository_and_keeps_fixed_commands(monkeypatch):
    collector = load("quote_collector", "src/gamehost/log_collector.py")
    monkeypatch.setitem(sys.modules, "log_collector", collector)
    runner = load("quote_runner", "src/gamehost/run.py")
    with patch.object(runner.subprocess, "run") as ssh:
        runner.remote("blue", "purpleAI; echo unsafe", "blue", "check")
        command = ssh.call_args.args[0]
        assert (
            command[-1]
            == "cd -- 'purpleAI; echo unsafe' && sudo -n /usr/bin/python3 \"$(pwd)/deploy/sandbox/start.py\" blue check"
        )
        assert "BatchMode=yes" in command and "StrictHostKeyChecking=yes" in command
        with pytest.raises(ValueError):
            runner.remote("-oProxyCommand=bad", "purpleAI", "blue", "check")


@pytest.mark.parametrize(
    "kind,expected_type,status,reason",
    [
        ("busy", "RateLimitError", 429, "Gateway busy"),
        ("upstream", "APIStatusError", 502, "Idun unavailable"),
        ("unknown", "APIStatusError", 502, "Model HTTP request failed"),
        ("timeout", "APITimeoutError", None, "Model request timed out"),
        ("connection", "APIConnectionError", None, "Model connection failed"),
    ],
)
def test_model_failure_details_reach_collector_without_secrets(
    collector, monkeypatch, caplog, kind, expected_type, status, reason
):
    import httpx
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        RateLimitError,
    )

    module, base = collector
    monkeypatch.setenv("LOG_COLLECTOR_URL", base + "/events")
    monkeypatch.setenv("LOG_COLLECTOR_TOKEN", "x" * 32)
    monkeypatch.setenv("AGENT_MODEL", "lab-model")
    monkeypatch.setenv("IDUNN_BASE_URL", "http://unused/v1")
    monkeypatch.setenv("IDUNN_API_KEY", "dummy")
    events = load("error_detail_events", "src/defender/defender-agent/events.py")
    monkeypatch.setitem(sys.modules, "events", events)
    defender = load("error_detail_defender", "src/defender/defender-agent/defender.py")
    request = httpx.Request("POST", "http://model-gateway:9000/v1/chat/completions")
    secret = "private-key-and-request-text"
    if kind == "timeout":
        error = APITimeoutError(request=request)
    elif kind == "connection":
        error = APIConnectionError(message=secret, request=request)
    else:
        response = httpx.Response(status, request=request)
        body = {"error": reason if kind != "unknown" else secret}
        error_class = RateLimitError if kind == "busy" else APIStatusError
        error = error_class(secret, response=response, body=body)

    def fail(_):
        raise error

    defender.AGENTS = [fail]
    output = io.StringIO()
    with redirect_stdout(output):
        assert defender.app.test_client().get("/search").status_code == 403
    saved = module.DATA_FILE.read_text()
    event = json.loads(saved.splitlines()[-1])
    assert event["status"] == "model_error" and event["http_status"] == 403
    assert event["error_type"] == expected_type
    assert event["model_http_status"] == status
    assert event["error_reason"] == reason
    assert secret not in output.getvalue() and secret not in saved
    assert secret not in caplog.text
    assert any(
        record.levelname == "ERROR" and reason in record.message
        for record in caplog.records
    )
