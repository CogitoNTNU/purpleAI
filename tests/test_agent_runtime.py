"""Different workflows use the same launcher, settings and event protocol."""

import importlib.util
import json
import os
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest

from purpleai.agent_runtime import command

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module", ["agents.recon.main", "agents.coordinator.main"])
def test_attacker_selection_uses_a_module_without_shell(module):
    assert command("attacker", {"ATTACKER_MODULE": module}) == [
        sys.executable,
        "-m",
        module,
    ]


def test_defender_selection_preserves_server_interface():
    args = command("defender", {"DEFENDER_APP": "custom_proxy:app"})
    assert args[0] == "gunicorn" and args[-1] == "custom_proxy:app"
    assert args[args.index("--bind") + 1] == "0.0.0.0:8080"
    assert args[args.index("--workers") + 1] == "1"


@pytest.mark.parametrize(
    "role,settings",
    [
        ("attacker", {}),
        ("defender", {}),
        ("attacker", {"ATTACKER_MODULE": "agents.recon; echo nope"}),
        ("attacker", {"ATTACKER_MODULE": "-c"}),
        ("defender", {"DEFENDER_APP": "proxy:app --bind 0.0.0.0:22"}),
    ],
)
def test_invalid_entrypoints_fail_before_execution(role, settings):
    with pytest.raises(ValueError):
        command(role, settings)


def launch(directory, **settings):
    # Keep test jobs independent of the developer's exported lab settings.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PURPLEAI_", "LOG_COLLECTOR_", "ATTACKER_", "IDUN_"))
    }
    env.update(settings)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT / "src/attacker")])
    return subprocess.run(
        [sys.executable, "-m", "purpleai.agent_runtime", "attacker"],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_selected_coordinator_and_subagent_deliver_shared_run(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "runtime_collector", ROOT / "src/gamehost/log_collector.py"
    )
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    collector.TOKEN = "x" * 32
    collector.DATA_FILE = tmp_path / "with-defender.jsonl"
    server = ThreadingHTTPServer(("127.0.0.1", 0), collector.EventHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    (tmp_path / "coordinator.py").write_text("""
import os
import subprocess
import sys
from purpleai.event_logging import EventSender
sender = EventSender("coordinator", "attacker", url=os.environ["LOG_COLLECTOR_URL"], token=os.environ["LOG_COLLECTOR_TOKEN"])
sender.emit("task_start", target=os.environ["TARGET_URL"], model=os.environ["AGENT_MODEL"])
assert os.environ["IDUN_BASE_URL"] == "http://model-gateway:9000/v1"
assert os.environ["IDUN_API_KEY"] == "gateway-credential"
subprocess.run([sys.executable, "-m", "worker"], check=True)
sender.emit("task_end", status="success")
""")
    (tmp_path / "worker.py").write_text("""
import os
from purpleai.event_logging import EventSender
sender = EventSender("worker", "attacker", url=os.environ["LOG_COLLECTOR_URL"], token=os.environ["LOG_COLLECTOR_TOKEN"])
sender.emit("tool_result", target=os.environ["TARGET_URL"], status="returned")
""")
    run_id = str(uuid4())
    try:
        result = launch(
            tmp_path,
            ATTACKER_MODULE="coordinator",
            TARGET_URL="http://lab-target:8081",
            IDUN_BASE_URL="http://model-gateway:9000/v1",
            IDUN_API_KEY="gateway-credential",
            AGENT_MODEL="chosen-model",
            PURPLEAI_RUN_ID=run_id,
            PURPLEAI_TARGET_MODE="without_defender",
            LOG_COLLECTOR_URL=f"http://127.0.0.1:{server.server_port}/events",
            LOG_COLLECTOR_TOKEN=collector.TOKEN,
        )
        assert result.returncode == 0, result.stderr
        assert not collector.DATA_FILE.exists()
        events = [
            json.loads(line)
            for line in collector.DATA_FILE.with_name("without-defender.jsonl")
            .read_text()
            .splitlines()
        ]
        assert [event["source"] for event in events] == [
            "coordinator",
            "worker",
            "coordinator",
        ]
        assert {event["run_id"] for event in events} == {run_id}
        assert {event["target_mode"] for event in events} == {"without_defender"}
        assert {event.get("target") for event in events[:2]} == {
            "http://lab-target:8081"
        }
        assert events[0]["model"] == "chosen-model"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_workflow_failure_exit_code_reaches_caller(tmp_path):
    (tmp_path / "failed_workflow.py").write_text("raise SystemExit(7)\n")
    assert launch(tmp_path, ATTACKER_MODULE="failed_workflow").returncode == 7
    missing = launch(tmp_path, ATTACKER_MODULE="missing_workflow")
    assert missing.returncode != 0 and "missing_workflow" in missing.stderr
    invalid = launch(tmp_path)
    assert invalid.returncode == 1 and "ATTACKER_MODULE" in invalid.stderr


@pytest.mark.parametrize("model_status", [200, 500])
def test_smoke_workflow_checks_real_http_and_reports_model_failure(
    tmp_path, model_status
):
    spec = importlib.util.spec_from_file_location(
        "smoke_collector", ROOT / "src/gamehost/log_collector.py"
    )
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    collector.TOKEN = "x" * 32
    collector.DATA_FILE = tmp_path / "with-defender.jsonl"
    calls = []

    class Handler(collector.EventHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"lab target")

        def do_POST(self):
            if self.path == "/events":
                return super().do_POST()
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, self.headers.get("Authorization"), body))
            self.send_response(model_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    run_id = str(uuid4())
    try:
        result = launch(
            tmp_path,
            ATTACKER_MODULE="agents.smoke",
            TARGET_URL=base,
            IDUN_BASE_URL=base + "/v1",
            IDUN_API_KEY="gateway-token",
            AGENT_MODEL="test-model",
            PURPLEAI_RUN_ID=run_id,
            LOG_COLLECTOR_URL=base + "/events",
            LOG_COLLECTOR_TOKEN=collector.TOKEN,
        )
        assert result.returncode == (0 if model_status == 200 else 1), result.stderr
        assert len(calls) == 1
        assert calls[0][:2] == ("/v1/chat/completions", "Bearer gateway-token")
        assert calls[0][2]["model"] == "test-model"
        events = [
            json.loads(line) for line in collector.DATA_FILE.read_text().splitlines()
        ]
        assert {event["run_id"] for event in events} == {run_id}
        assert events[-1]["status"] == ("success" if model_status == 200 else "error")
        assert events[1]["tool"] == "http_check"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
