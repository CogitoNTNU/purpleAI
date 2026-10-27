"""Attacker logging with mocked tools: no IDUN calls or target traffic."""

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def logging(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLEAI_LOG_FILE", str(tmp_path / "events.jsonl"))
    spec = importlib.util.spec_from_file_location(
        "attacker_event_logging", ROOT / "src/Attacker/event_logging.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def events(tmp_path):
    return [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text().splitlines()
    ]


@pytest.mark.parametrize("exit_code", [0, 2])
def test_tool_result_and_effective_options(logging, monkeypatch, tmp_path, exit_code):
    proc = SimpleNamespace(
        returncode=exit_code,
        communicate=AsyncMock(return_value=(b"private tool output", b"")),
    )
    monkeypatch.setattr(
        logging.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)
    )
    result = asyncio.run(
        logging.run_logged_tool(
            [
                "sqlmap",
                "-u",
                "http://lab/",
                "--level=2",
                "--risk=1",
                "--forms",
                "--dbms=private",
            ],
            target="http://lab/",
        )
    )
    start, end = events(tmp_path)
    assert start["tool_call_id"] == end["tool_call_id"]
    assert start["scan_options"] == ["--level=2", "--risk=1", "--forms"]
    assert end["status"] == ("completed" if exit_code == 0 else "error")
    assert end["exit_code"] == exit_code
    assert end["duration_ms"] >= 0
    assert "private tool output" in result
    assert "private" not in (tmp_path / "events.jsonl").read_text()


def test_missing_executable(logging, monkeypatch, tmp_path):
    monkeypatch.setattr(
        logging.asyncio,
        "create_subprocess_exec",
        AsyncMock(side_effect=FileNotFoundError),
    )
    result = asyncio.run(logging.run_logged_tool(["sqlmap"], target="http://lab/"))
    assert result == "sqlmap is not installed or not on PATH."
    end = events(tmp_path)[-1]
    assert end["status"] == "error"
    assert end["error_type"] == "FileNotFoundError"
    assert "exit_code" not in end


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_and_cancellation_reap_process(logging, monkeypatch, tmp_path, cancel):
    class Process:
        returncode = None
        killed = False
        reaped = False

        async def communicate(self):
            if self.killed:
                self.reaped = True
                return b"", b""
            if cancel:
                raise asyncio.CancelledError
            raise TimeoutError

        def kill(self):
            self.killed = True
            self.returncode = -9

    proc = Process()
    monkeypatch.setattr(
        logging.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)
    )
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(logging.run_logged_tool(["sqlmap"], target="http://lab/"))
    else:
        assert "timed out" in asyncio.run(
            logging.run_logged_tool(["sqlmap"], target="http://lab/")
        )
    assert proc.killed and proc.reaped
    end = events(tmp_path)[-1]
    assert end["status"] == ("cancelled" if cancel else "timeout")
    assert end["exit_code"] == -9


def test_concurrent_tools_keep_pairs_and_remote_task_context(
    logging, monkeypatch, tmp_path
):
    from langchain_core.runnables.config import var_child_runnable_config

    async def spawn(*args, **kwargs):
        return SimpleNamespace(
            returncode=0, communicate=AsyncMock(return_value=(b"ok", b""))
        )

    monkeypatch.setattr(logging.asyncio, "create_subprocess_exec", spawn)

    async def run(task_id):
        token = var_child_runnable_config.set({"configurable": {"thread_id": task_id}})
        try:
            return await logging.run_logged_tool(["sqlmap"], target="http://lab/")
        finally:
            var_child_runnable_config.reset(token)

    async def run_both():
        return await asyncio.gather(run("remote-a"), run("remote-b"))

    assert asyncio.run(run_both()) == ["ok", "ok"]
    records = events(tmp_path)
    for task_id in ["remote-a", "remote-b"]:
        pair = [event for event in records if event["task_id"] == task_id]
        assert [event["action"] for event in pair] == ["tool_call", "tool_result"]
        assert pair[0]["tool_call_id"] == pair[1]["tool_call_id"]
    assert len({event["tool_call_id"] for event in records}) == 2


@pytest.mark.parametrize("error", [None, RuntimeError, asyncio.CancelledError])
def test_lifecycle_status_and_pairing(logging, tmp_path, error):
    async def run():
        with logging.log_span("iteration", iteration=3):
            if error:
                raise error("private exception")

    if error:
        with pytest.raises(error):
            asyncio.run(run())
    else:
        asyncio.run(run())
    start, end = events(tmp_path)
    assert start["operation_id"] == end["operation_id"]
    assert end["iteration"] == 3
    assert (
        end["status"]
        == (
            {
                None: "completed",
                RuntimeError: "error",
                asyncio.CancelledError: "cancelled",
            }[error]
        )
    )
    assert "private exception" not in (tmp_path / "events.jsonl").read_text()


def test_boss_task_updates_exclude_content(logging, tmp_path):
    logging.log_agent_update(
        {
            "async_tasks": {
                "remote-a": {
                    "task_id": "remote-a",
                    "agent_name": "execution_agent",
                    "run_id": "remote-run",
                    "status": "running",
                }
            },
            "messages": [
                SimpleNamespace(
                    tool_calls=[
                        {
                            "name": "start_async_task",
                            "id": "call-a",
                            "args": {"description": "private prompt"},
                        }
                    ]
                ),
                SimpleNamespace(
                    type="tool",
                    name="start_async_task",
                    tool_call_id="call-a",
                    content="private result",
                    status="success",
                ),
            ],
        }
    )
    records = events(tmp_path)
    assert records[0]["task_id"] == "remote-a"
    assert records[0]["remote_run_id"] == "remote-run"
    assert records[1]["tool_call_id"] == records[2]["tool_call_id"] == "call-a"
    assert "private" not in (tmp_path / "events.jsonl").read_text()


def test_normal_engagement_stop(logging, tmp_path):
    @logging.log_engagement
    async def run():
        return "stopped by operator"

    assert asyncio.run(run()) == "stopped by operator"
    assert events(tmp_path)[-1]["status"] == "stopped"
