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
    module.DATA_FILE = tmp_path / "with-defender.jsonl"
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
    fake_config = types.ModuleType("agents.nmap.config")
    fake_config.get_config = lambda: types.SimpleNamespace(
        log_collector_url=base + "/events", log_collector_token="x" * 32
    )
    monkeypatch.setitem(sys.modules, "agents.nmap.config", fake_config)
    attacker = load(
        "agents.nmap.attacker_run_events", "src/attacker/agents/nmap/logging_utils.py"
    )
    defender_events = load(
        "defender_run_events", "src/defender/defender-agent/events.py"
    )
    monkeypatch.setitem(sys.modules, "events", defender_events)
    monkeypatch.setenv("AGENT_MODEL", "lab-model")
    monkeypatch.setenv("IDUN_BASE_URL", "http://unused/v1")
    monkeypatch.setenv("IDUN_API_KEY", "dummy")
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


def test_collector_separates_modes_and_keeps_direct_events_out_of_live_defender_logs(
    collector, monkeypatch
):
    from datetime import datetime, timezone
    from urllib.request import Request, urlopen
    from purpleai.event_logging import EventSender

    module, base = collector
    run_id = str(uuid4())
    monkeypatch.setenv("PURPLEAI_RUN_ID", run_id)
    # Agent events must inherit the selected mode, including during failed runs.
    for mode in ("with_defender", "without_defender"):
        monkeypatch.setenv("PURPLEAI_TARGET_MODE", mode)
        sender = EventSender(
            "nmap-agent", "attacker", url=base + "/events", token="x" * 32
        )
        sender.emit("task_start")
        sender.emit("task_end", status="error")
    for mode, path in [
        ("with_defender", module.DATA_FILE),
        ("without_defender", module.DATA_FILE.with_name("without-defender.jsonl")),
    ]:
        saved = [json.loads(line) for line in path.read_text().splitlines()]
        assert [e["action"] for e in saved] == ["task_start", "task_end"]
        assert {e["target_mode"] for e in saved} == {mode}
        assert {e["run_id"] for e in saved} == {run_id}

    event = {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "gamehost",
        "actor": "gamehost",
        "action": "run_start",
        "target_mode": "without_defender",
    }
    output = io.StringIO()
    with redirect_stdout(output):
        request = Request(
            base + "/events",
            data=json.dumps(event).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + "x" * 32,
            },
        )
        with urlopen(request, timeout=2) as response:
            assert response.status == 202
    assert output.getvalue() == ""
    assert (
        json.loads(
            module.DATA_FILE.with_name("without-defender.jsonl")
            .read_text()
            .splitlines()[-1]
        )
        == event
    )
    for invalid in ("typo", "../../file", "direct", None):
        assert not module.valid_event(event | {"target_mode": invalid})


@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("target", ["defender", "direct"])
def test_runner_starts_traffic_and_cleans_up_on_attacker_failure(
    tmp_path, monkeypatch, fails, target
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
    calls, events, urls = [], [], []

    def remote(destination, repository, role, action, run_id=None, target=None):
        calls.append((role, action, run_id, target))
        if fails and (role, action) == ("red", "run"):
            raise RuntimeError("attacker failure")

    from unittest.mock import MagicMock

    def opened(message, **kwargs):
        if isinstance(message, str):
            urls.append(message)
        else:
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
                runner.main([] if target == "defender" else ["--without-defender"])
        else:
            runner.main([] if target == "defender" else ["--without-defender"])
    run_id = next(call[2] for call in calls if call[:2] == ("red", "run"))
    assert calls[:2] == [
        ("blue", "check", None, target),
        ("red", "check", None, target),
    ]
    assert ("red", "run", run_id, target) in calls
    sessions = [call for call in calls if call[:2] == ("blue", "session")]
    if target == "direct":
        assert sessions == []
        assert calls[-1] == ("red", "cancel", run_id, None)
    else:
        assert sessions == [
            ("blue", "session", run_id, None),
            ("blue", "session", None, None),
        ]
        assert calls[-2] == ("red", "cancel", run_id, None)
    expected = (
        ["run_start", "run_end"]
        if target == "direct"
        else ["run_start", "traffic_start", "traffic_end", "run_end"]
    )
    assert [e["action"] for e in events] == expected
    assert {e["run_id"] for e in events} == {run_id}
    mode = "without_defender" if target == "direct" else "with_defender"
    assert {e["target_mode"] for e in events} == {mode}
    assert events[-1]["status"] == ("error" if fails else "success")
    if target == "direct":
        docker.assert_not_called()
        assert urls == ["http://192.168.0.110:8765/health"]
    else:
        traffic = next(
            call
            for call in docker.call_args_list
            if "traffic" in call.args[0] and "-d" in call.args[0]
        )
        assert traffic.kwargs["env"]["PURPLEAI_RUN_ID"] == run_id
        assert urls == [
            "http://192.168.0.110:8765/health",
            "http://192.168.0.120:8080/",
        ]
        assert any(
            call.args[0][:2] == ["docker", "stop"] for call in docker.call_args_list
        )


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
        runner.remote("red", "purpleAI", "red", "run", str(uuid4()), target="direct")
        assert ssh.call_args.args[0][-1].endswith("--target direct")


@pytest.mark.parametrize("failure", ["blue_check", "red_check"])
def test_direct_preflight_failure_never_starts_traffic_or_attacker(
    tmp_path, monkeypatch, failure
):
    from unittest.mock import MagicMock

    collector = load("failed_preflight_collector", "src/gamehost/log_collector.py")
    monkeypatch.setitem(sys.modules, "log_collector", collector)
    runner = load("failed_preflight_runner", "src/gamehost/run.py")
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
        },
    )
    calls, events = [], []

    def remote(destination, repository, role, action, run_id=None, target=None):
        calls.append((role, action))
        if failure == f"{role}_check" and action == "check":
            raise RuntimeError("direct testing disabled")

    def opened(message, **kwargs):
        if not isinstance(message, str):
            events.append(json.loads(message.data))
        result = MagicMock()
        result.__enter__.return_value.status = 200
        return result

    monkeypatch.setattr(runner, "remote", remote)
    monkeypatch.setattr(runner, "urlopen", opened)
    with (
        patch.object(runner.subprocess, "run") as docker,
        pytest.raises((RuntimeError, OSError)),
    ):
        runner.main(["--without-defender"])
    assert not any(call[1] in ("run", "session") for call in calls)
    docker.assert_not_called()
    assert events == []


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
    monkeypatch.setenv("IDUN_BASE_URL", "http://unused/v1")
    monkeypatch.setenv("IDUN_API_KEY", "dummy")
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
