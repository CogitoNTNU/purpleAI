"""Behavioral regression tests; no real LLM endpoint or lab targets are used."""
import asyncio
import ast
import base64
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import sys
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
ATTACKER = ROOT / "src" / "attacker"
if not ATTACKER.is_dir():
    ATTACKER = ROOT / "src" / "Attacker"
sys.path.insert(0, str(ATTACKER))
from llm_queue import KeyQueue
from llm import AsyncQueuedTransport, QueuedTransport, get_model


def make_queue(tmp_path, keys=("test-key-a",)):
    file = tmp_path / "keys.json"
    file.write_text(json.dumps({"keys": keys}))
    return KeyQueue(tmp_path / "queue", file)


def hold_key(directory, file, ready):
    queue = KeyQueue(Path(directory), Path(file))
    lease = queue.acquire()
    ready.set()
    # Parent deliberately terminates this process to test OS lock recovery.
    import time
    time.sleep(60)
    lease.close()


def test_cross_process_exclusivity_and_crash_release(tmp_path):
    queue = make_queue(tmp_path)
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    child = context.Process(target=hold_key, args=(str(queue.directory), str(queue.keys_path), ready))
    child.start()
    try:
        assert ready.wait(15)
        ticket = queue.ticket()
        assert queue.try_acquire(ticket) is None
    finally:
        child.terminate()
        child.join(10)
    lease = queue.try_acquire(ticket)
    assert lease is not None
    lease.close()


def test_fifo_duplicate_keys_and_removal(tmp_path):
    queue = make_queue(tmp_path, ["same", "same"])
    first, second = queue.ticket(), queue.ticket()
    assert queue.try_acquire(second) is None
    lease = queue.try_acquire(first)
    assert queue.try_acquire(second) is None
    queue.keys_path.write_text('{"keys": []}')
    lease.close()
    assert queue.try_acquire(second) is None
    queue.discard(second)


@pytest.mark.asyncio
async def test_new_key_increases_live_capacity_without_releasing_old(tmp_path):
    queue = make_queue(tmp_path)
    first = queue.acquire()
    pending = asyncio.create_task(queue.acquire_async())
    await asyncio.sleep(0.35)
    assert not pending.done()
    queue.keys_path.write_text(json.dumps({"keys": [first.key, "new-key"]}))
    second = await asyncio.wait_for(pending, 3)
    assert second.key == "new-key"
    second.close()
    first.close()


@pytest.mark.asyncio
async def test_cancel_waiter_does_not_block_next(tmp_path):
    queue = make_queue(tmp_path, [])
    pending = asyncio.create_task(queue.acquire_async())
    await asyncio.sleep(0.1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    queue.keys_path.write_text('{"keys": ["new-key"]}')
    lease = await asyncio.wait_for(queue.acquire_async(), 2)
    lease.close()
    with queue._db() as db:
        assert db.execute("SELECT COUNT(*) FROM waiters").fetchone()[0] == 0


def test_expired_waiter_does_not_block_queue(tmp_path):
    queue = make_queue(tmp_path)
    abandoned, active = queue.ticket(), queue.ticket()
    with queue._db() as db:
        db.execute("UPDATE waiters SET seen=0 WHERE token=?", (abandoned,))
    lease = queue.try_acquire(active)
    assert lease
    lease.close()


def test_invalid_file_does_not_restore_removed_env_key(tmp_path, monkeypatch):
    queue = make_queue(tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "must-not-use")
    queue.keys_path.write_text("invalid")
    assert queue.keys() == []


def test_sync_response_holds_key_until_closed(tmp_path):
    queue = make_queue(tmp_path)
    transport = QueuedTransport(queue, httpx.MockTransport(lambda req: httpx.Response(200, stream=httpx.ByteStream(b"ok"))))
    with httpx.Client(transport=transport) as client:
        response = client.send(client.build_request("POST", "https://test.invalid/v1", json={}), stream=True)
        ticket = queue.ticket()
        assert queue.try_acquire(ticket) is None
        assert response.read() == b"ok"
        lease = queue.try_acquire(ticket)
        assert lease
        lease.close()


@pytest.mark.asyncio
async def test_async_retry_uses_another_key_and_keeps_body(tmp_path):
    queue = make_queue(tmp_path, ["a", "b"])
    calls = []
    async def endpoint(request):
        calls.append((request.headers["Authorization"], await request.aread()))
        return httpx.Response(429, headers={"retry-after": "300"}) if len(calls) == 1 else httpx.Response(200, content=b"ok")
    transport = AsyncQueuedTransport(queue, httpx.MockTransport(endpoint))
    async with httpx.AsyncClient(transport=transport) as client:
        response = await asyncio.wait_for(client.post("https://test.invalid", content=b"payload"), 3)
    assert response.content == b"ok"
    assert calls[0][0] != calls[1][0]
    assert calls[0][1] == calls[1][1] == b"payload"


@pytest.mark.asyncio
async def test_cancel_active_request_releases_key(tmp_path):
    queue = make_queue(tmp_path)
    entered = asyncio.Event()
    async def endpoint(request):
        entered.set()
        await asyncio.Event().wait()
    async with httpx.AsyncClient(transport=AsyncQueuedTransport(queue, httpx.MockTransport(endpoint))) as client:
        task = asyncio.create_task(client.get("https://test.invalid"))
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    lease = await asyncio.wait_for(queue.acquire_async(), 3)
    lease.close()


@pytest.mark.asyncio
async def test_stream_holds_slot_until_async_close(tmp_path):
    queue = make_queue(tmp_path)
    async with httpx.AsyncClient(transport=AsyncQueuedTransport(queue, httpx.MockTransport(lambda r: httpx.Response(200, stream=httpx.ByteStream(b"ok"))))) as client:
        response = await client.send(client.build_request("GET", "https://test.invalid"), stream=True)
        ticket = queue.ticket()
        assert queue.try_acquire(ticket) is None
        await response.aclose()
        lease = queue.try_acquire(ticket)
        assert lease
        lease.close()


def test_permanent_request_errors_are_not_retried(tmp_path):
    queue = make_queue(tmp_path)
    calls = []
    def endpoint(request):
        calls.append(1)
        return httpx.Response(400, json={"error": "bad request"})
    with httpx.Client(transport=QueuedTransport(queue, httpx.MockTransport(endpoint))) as client:
        assert client.get("https://test.invalid").status_code == 400
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_actual_model_and_boss_construct_with_durable_saver(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_QUEUE_DIR", str(tmp_path / "queue"))
    monkeypatch.setenv("LLM_KEYS_FILE", str(tmp_path / "keys.json"))
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    import redagent
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "boss.sqlite3")) as saver:
        boss = redagent.create_boss(saver)
        config = {"configurable": {"thread_id": "test"}}
        await boss.aupdate_state(config, {"messages": [{"role": "user", "content": "saved"}]}, as_node="__start__")
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "boss.sqlite3")) as saver:
        boss = redagent.create_boss(saver)
        state = await boss.aget_state(config)
        assert state.values["messages"][0].content == "saved"


@pytest.mark.asyncio
async def test_monitor_reconnects_without_marking_error_complete(monkeypatch):
    import redagent
    client = SimpleNamespace(runs=SimpleNamespace(get=AsyncMock(side_effect=[httpx.ConnectError("offline"), {"status": "running"}, {"status": "success"}])))
    monkeypatch.setattr(redagent, "POLL_SECONDS", 0.001)
    await asyncio.wait_for(redagent._wait_for_any(client, [{"thread_id": "t", "run_id": "r", "task_id": "task"}]), 2)
    assert client.runs.get.await_count == 3


@pytest.mark.asyncio
async def test_recovery_adopts_existing_run_after_lost_reply(monkeypatch):
    import redagent
    task = {"thread_id": "t", "run_id": "old", "task_id": "task", "agent_name": "sql_injection_agent", "status": "running"}
    boss = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={"async_tasks": {"task": task}})), aupdate_state=AsyncMock())
    monkeypatch.setattr(redagent, "BossAgent", boss)
    client = SimpleNamespace(runs=SimpleNamespace(
        get=AsyncMock(return_value={"status": "error"}),
        list=AsyncMock(return_value=[{"run_id": "new", "status": "pending", "metadata": {"recovery_of": "old"}}]),
        create=AsyncMock()))
    await redagent._recover_failed(client, {})
    client.runs.create.assert_not_awaited()
    assert boss.aupdate_state.call_args.args[1]["async_tasks"]["task"]["run_id"] == "new"


def load_gui():
    spec = importlib.util.spec_from_file_location("purple_control_test", ROOT / "startup/gui/app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gui_live_keys_stay_out_of_process_args():
    gui = load_gui()
    script = gui.publish_keys_script(["fake-key", "fake-key"])
    assert "fake-key" not in script  # payload encoded, never command args
    assert "os.replace" in script
    assert "mkstemp" in script  # private mode 0600
    assert gui.ssh_script_argv("redai") == ["ssh", "gamehost", "ssh redai bash -s"]
    python = script.split("\n", 1)[1].rsplit("PURPLE_KEYS", 1)[0]
    compile(python, "key-publish", "exec")


def test_start_preserves_state_and_uses_checked_out_runtime():
    gui = load_gui()
    script = gui.att_start(gui.INSTANCES[0])
    assert "__RUNTIME_PATCH__" not in script
    assert "rm -rf \"$ATT/.langgraph_api\"" not in script
    assert "langgraph-checkpoint-sqlite" in script
    assert "BG_JOB_TIMEOUT_SECS=86400" in script
    assert "PURPLE_RUNTIME" not in script
    assert "runtime_overlay_script" not in (ROOT / "startup/gui/app.py").read_text(encoding="utf-8")


@pytest.mark.skipif(os.name == "nt", reason="Exercises Linux private key publication")
def test_live_key_publication_is_private_and_atomic(tmp_path):
    tree = ast.parse((ROOT / "startup/gui/app.py").read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "publish_keys_script")
    scope = {"base64": base64, "json": json, "KEY_SET": []}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "publish", "exec"), scope)
    script = scope["publish_keys_script"](["a", "b", "a"])
    subprocess.run(["bash", "-s"], input=script.encode(), env={**os.environ, "HOME": str(tmp_path)}, check=True, capture_output=True)
    file = tmp_path / ".purpleai/keys.json"
    assert json.loads(file.read_text()) == {"keys": ["a", "b"]}
    assert file.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_real_chat_model_invocation_uses_live_key(tmp_path, monkeypatch):
    queue = make_queue(tmp_path, ["live-test-key"])
    monkeypatch.setenv("LLM_QUEUE_DIR", str(queue.directory))
    monkeypatch.setenv("LLM_KEYS_FILE", str(queue.keys_path))
    def endpoint(request):
        assert request.headers["authorization"] == "Bearer live-test-key"
        return httpx.Response(200, json={
            "id": "offline-test", "object": "chat.completion", "created": 0,
            "model": "test", "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    monkeypatch.setattr(httpx, "HTTPTransport", lambda: httpx.MockTransport(endpoint))
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda: httpx.MockTransport(endpoint))
    model = get_model()
    try:
        assert (await model.ainvoke("ping")).content == "ok"
        assert model.invoke("ping").content == "ok"
    finally:
        model.http_client.close()
        await model.http_async_client.aclose()
