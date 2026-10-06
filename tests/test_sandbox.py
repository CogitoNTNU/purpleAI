"""Gateway and network policy regression tests; no real Idun requests."""

import importlib.util
import json
import sys
import types
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_openai import ChatOpenAI
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / f"deploy/sandbox/{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    key = tmp_path / "key"
    key.write_text("private-upstream-key")
    monkeypatch.setenv("IDUN_KEY_FILE", str(key))
    monkeypatch.setenv("GATEWAY_TOKEN", "x" * 32)
    monkeypatch.setenv("GATEWAY_CALL_LIMIT", "1")
    return load("gateway")


def test_gateway_authentication_and_options(gateway):
    client = gateway.create_app().test_client()
    payload = {"model": "lab-model", "messages": [{"role": "user", "content": "hello"}]}
    headers = {"Authorization": "Bearer " + "x" * 32}
    with patch.object(gateway.requests, "Session") as upstream:
        assert client.post("/v1/chat/completions", json=payload).status_code == 401
        for options in (
            {"model": ""},
            {"model": "   "},
            {"model": ["lab-model"]},
            {"model": None},
            {"stream": True},
            {"url": "http://router/"},
            {"max_tokens": 2049},
            {"max_tokens": True},
            {"messages": []},
        ):
            assert (
                client.post(
                    "/v1/chat/completions", json=payload | options, headers=headers
                ).status_code
                == 400
            )
        assert (
            client.post("/v1/responses", json=payload, headers=headers).status_code
            == 404
        )
        assert client.get("/v1/models", headers=headers).status_code == 404
        assert (
            client.post(
                "/v1/chat/completions", data="x" * (256 * 1024 + 1), headers=headers
            ).status_code
            == 413
        )
        upstream.assert_not_called()


@pytest.mark.parametrize("model", ["lab-model", "other-model"])
def test_gateway_fixed_upstream_key_replacement_and_budget(gateway, model):
    client = gateway.create_app().test_client()
    headers = {"Authorization": "Bearer " + "x" * 32}
    payload = {"model": model, "messages": [{"role": "user", "content": "hello"}]}
    session = MagicMock()
    response = session.post.return_value.__enter__.return_value
    response.status_code = 200
    response.iter_content.return_value = [json.dumps({"choices": []}).encode()]
    with patch.object(gateway.requests, "Session") as factory:
        factory.return_value.__enter__.return_value = session
        result = client.post("/v1/chat/completions", json=payload, headers=headers)
        assert result.status_code == 200
        assert "private-upstream-key" not in result.text
        args, kwargs = session.post.call_args
        assert args == ("https://llm.hpc.ntnu.no/v1/chat/completions",)
        assert kwargs["headers"] == {"Authorization": "Bearer private-upstream-key"}
        assert kwargs["json"]["max_tokens"] == 2048
        assert kwargs["json"]["model"] == model
        assert kwargs["allow_redirects"] is False
        assert session.trust_env is False
        other = "other-model" if model == "lab-model" else "lab-model"
        assert (
            client.post(
                "/v1/chat/completions", json=payload | {"model": other}, headers=headers
            ).status_code
            == 429
        )
        assert session.post.call_count == 1


def test_langchain_client_can_call_the_gateway(gateway, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    app = gateway.create_app()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    upstream_body = {
        "id": "lab-test",
        "object": "chat.completion",
        "created": 0,
        "model": "lab-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "NO"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    try:
        with patch.object(gateway.requests, "Session") as factory:
            response = factory.return_value.__enter__.return_value.post.return_value.__enter__.return_value
            response.status_code = 200
            response.iter_content.return_value = [json.dumps(upstream_body).encode()]
            client = ChatOpenAI(
                model="lab-model",
                api_key="x" * 32,
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                max_retries=0,
            )
            assert client.invoke("Classify this synthetic lab request").content == "NO"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_gateway_rejects_overlapping_calls(gateway):
    app = gateway.create_app()
    started, release = threading.Event(), threading.Event()
    payload = {"model": "lab-model", "messages": [{}]}
    headers = {"Authorization": "Bearer " + "x" * 32}
    results = []

    def chunks(_):
        started.set()
        assert release.wait(timeout=5)
        yield b'{"choices": []}'

    with patch.object(gateway.requests, "Session") as factory:
        session = factory.return_value.__enter__.return_value
        response = session.post.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_content.side_effect = chunks
        thread = threading.Thread(
            target=lambda: results.append(
                app.test_client()
                .post("/v1/chat/completions", json=payload, headers=headers)
                .status_code
            )
        )
        thread.start()
        try:
            assert started.wait(timeout=5)
            busy = app.test_client().post(
                "/v1/chat/completions", json=payload, headers=headers
            )
            assert busy.status_code == 429
            assert busy.json["error"] == "Gateway busy"
            assert session.post.call_count == 1
        finally:
            release.set()
            thread.join(timeout=5)
        assert results == [200]


def test_gateway_limits_upstream_response_size(gateway):
    with patch.object(gateway.requests, "Session") as factory:
        response = factory.return_value.__enter__.return_value.post.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_content.return_value = [b"x" * (2 * 1024 * 1024 + 1)]
        result = (
            gateway.create_app()
            .test_client()
            .post(
                "/v1/chat/completions",
                json={"model": "lab-model", "messages": [{}]},
                headers={"Authorization": "Bearer " + "x" * 32},
            )
        )
        assert result.status_code == 502
        assert result.json["error"] == "Idun response too large"


@pytest.mark.parametrize("status", [302, 401, 500])
def test_upstream_errors_do_not_leak_credentials(gateway, status):
    client = gateway.create_app().test_client()
    with patch.object(gateway.requests, "Session") as factory:
        response = factory.return_value.__enter__.return_value.post.return_value.__enter__.return_value
        response.status_code = status
        response.text = "private-upstream-key"
        result = client.post(
            "/v1/chat/completions",
            json={"model": "lab-model", "messages": [{}]},
            headers={"Authorization": "Bearer " + "x" * 32},
        )
        assert result.status_code == 502
        assert "private-upstream-key" not in result.text


def test_network_policy_blocks_escape_and_backend_bypass():
    import ipaddress

    firewall = load("firewall")
    red, blue, idun = "192.168.0.130", "192.168.0.120", "129.241.121.16"

    def permitted(role, source, destination, port, state="NEW", sport=45000):
        entries = firewall.rules(role, red, blue, idun)[0]
        for entry in entries:

            def option(name):
                return entry[entry.index(name) + 1] if name in entry else None

            if "-i" in entry or "-o" in entry:
                continue
            if option("-s") and ipaddress.ip_address(
                source
            ) not in ipaddress.ip_network(option("-s"), strict=False):
                continue
            if option("-d") and ipaddress.ip_address(
                destination
            ) not in ipaddress.ip_network(option("-d"), strict=False):
                continue
            if option("--dport") and port != int(option("--dport")):
                continue
            if option("--sport") and sport != int(option("--sport")):
                continue
            if option("--ctstate") and state not in option("--ctstate").split(","):
                continue
            return option("-j") == "ACCEPT"
        return False

    assert permitted("red", "172.28.10.10", blue, 8080)
    assert permitted("red", "172.28.10.10", "172.28.10.20", 9000)
    assert permitted("red", "172.28.10.20", idun, 443)
    assert not permitted("red", "172.28.10.20", "1.1.1.1", 443)
    for destination, port in [
        (blue, 22),
        ("192.168.0.1", 80),
        (idun, 443),
        ("1.1.1.1", 443),
    ]:
        assert not permitted("red", "172.28.10.10", destination, port)
    assert permitted("blue", red, "172.28.20.10", 8080)
    assert not permitted("blue", "192.168.0.50", "172.28.20.10", 8080)
    assert not permitted("blue", red, "172.28.21.10", 5000)
    assert permitted("blue", "172.28.21.20", "172.28.21.10", 5000)
    assert permitted("blue", "172.28.20.20", idun, 443)
    assert not permitted("blue", "172.28.20.20", "1.1.1.1", 443)
    assert not permitted("blue", "172.28.21.10", idun, 443)
    assert not permitted("blue", "172.28.21.10", "172.28.21.20", 8080)
    assert permitted("blue", "172.28.21.10", "172.28.21.20", 45000, "ESTABLISHED", 5000)
    assert not permitted("blue", "172.28.21.10", "172.28.21.20", 45000, "NEW", 5000)
    for role in ("red", "blue"):
        _, host, forward6, host6 = firewall.rules(role, red, blue, idun)
        assert all(entry[-1] == "DROP" for entry in host + forward6 + host6)


@pytest.mark.parametrize("port", ["8080", "0", "65536", "8080; curl example.com"])
def test_scan_port_is_validated_in_trusted_config(monkeypatch, port):
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda _: None
    monkeypatch.setitem(sys.modules, "dotenv", dotenv)
    spec = importlib.util.spec_from_file_location(
        "test_sandbox_config", ROOT / "src/nmap-agent/config.py"
    )
    config = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, config)
    spec.loader.exec_module(config)
    for name, value in {
        "TARGET_URL": "http://192.168.0.120:8080",
        "IDUN_BASE_URL": "http://model-gateway:9000/v1",
        "IDUN_API_KEY": "dummy",
        "AGENT_MODEL": "lab-model",
        "NMAP_PORT": port,
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LOG_COLLECTOR_URL", raising=False)
    monkeypatch.delenv("LOG_COLLECTOR_TOKEN", raising=False)
    if port == "8080":
        assert config.load_config().nmap_port == 8080
        monkeypatch.delenv("NMAP_PORT")
        assert config.load_config().nmap_port is None
        monkeypatch.delenv("AGENT_MODEL")
        with pytest.raises(config.ConfigError, match="AGENT_MODEL"):
            config.load_config()
    else:
        with pytest.raises(config.ConfigError):
            config.load_config()


def operator(tmp_path, monkeypatch, *arguments):
    monkeypatch.setitem(sys.modules, "firewall", load("firewall"))
    module = load("start")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["start.py", *arguments])
    (tmp_path / ".env").write_text(
        "RED_IP=192.168.0.130\nBLUE_IP=192.168.0.120\n"
        "IDUN_IP=129.241.121.16\nROUTER_IP=192.168.0.1\n"
        "GATEWAY_TOKEN=" + "x" * 32 + "\n"
    )
    return module


def test_operator_refuses_agent_launch_when_firewall_check_fails(tmp_path, monkeypatch):
    module = operator(tmp_path, monkeypatch, "red", "run")
    with patch.object(
        module.subprocess,
        "run",
        side_effect=module.subprocess.CalledProcessError(1, "firewall"),
    ) as run:
        with pytest.raises(module.subprocess.CalledProcessError):
            module.main()
        assert run.call_count == 1
        assert "--check" in run.call_args.args[0]


def test_operator_installs_firewall_before_starting_containers(tmp_path, monkeypatch):
    module = operator(tmp_path, monkeypatch, "red")
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets/idun_key").write_text("dummy-key")
    with patch.object(module.subprocess, "run") as run:
        module.main()
        commands = [call.args[0] for call in run.call_args_list]
        firewall_index = next(
            i for i, cmd in enumerate(commands) if str(tmp_path / "firewall.py") in cmd
        )
        up_index = next(i for i, cmd in enumerate(commands) if "up" in cmd)
        assert firewall_index < up_index
        assert any(cmd[0] == "modprobe" for cmd in commands[:firewall_index])


def test_operator_runs_attacker_with_compose_environment(tmp_path, monkeypatch):
    module = operator(tmp_path, monkeypatch, "red", "run")
    with patch.object(module.subprocess, "run") as run:
        module.main()
        assert run.call_args.args[0][-6:] == (
            "run",
            "--rm",
            "--no-deps",
            "--name",
            "purpleai-red-attacker-run",
            "attacker",
        )


def test_gamehost_policy_adds_only_logging_and_normal_traffic():
    firewall = load("firewall")
    args = ("192.168.0.130", "192.168.0.120", "129.241.121.16")
    host = "192.168.0.110"
    for role, agent in [("red", "172.28.10.10"), ("blue", "172.28.20.10")]:
        base = set(firewall.policy(role, *args)[0])
        enabled = set(firewall.policy(role, *args, host)[0])
        additions = {(agent, host, 8765)}
        if role == "blue":
            additions.add((host, agent, 8080))
        assert enabled - base == additions
        assert base <= enabled


def test_operator_shared_session_checks_firewall_and_preserves_target(
    tmp_path, monkeypatch
):
    from uuid import uuid4

    run_id = str(uuid4())
    module = operator(tmp_path, monkeypatch, "blue", "session", "--run-id", run_id)
    with patch.object(module.subprocess, "run") as run:
        module.main()
        assert "--check" in run.call_args_list[0].args[0]
        command = run.call_args.args[0]
        assert "--no-deps" in command and command[-1] == "defender"
        assert run.call_args.kwargs["env"]["PURPLEAI_RUN_ID"] == run_id
