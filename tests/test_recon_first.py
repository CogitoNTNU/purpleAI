"""Recon ordering is enforced at delegation, including concurrent tool calls."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/attacker"))
from recon_gate import ReconFirstMiddleware


def request(agent="sql_injection_agent", status=None, name="start_async_task"):
    tasks = {"attack": {"agent_name": "sql_injection_agent", "status": "running"}}
    if status is not None:
        tasks["recon"] = {"agent_name": "recon_agent", "status": status}
    return SimpleNamespace(
        tool_call={"id": "call-test", "name": name,
                   "args": {"subagent_type": agent, "task_id": "attack"}},
        state={"async_tasks": tasks},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [None, "pending", "running", "error", "cancelled", "timeout"])
async def test_attack_never_starts_before_successful_recon(status):
    handler = AsyncMock()
    result = await ReconFirstMiddleware().awrap_tool_call(request(status=status), handler)
    assert result.status == "error"
    assert result.tool_call_id == "call-test"
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_first_wave_allows_only_recon():
    handler = AsyncMock(return_value="started")
    gate = ReconFirstMiddleware()
    agents = ["recon_agent", "sql_injection_agent", "xss_agent", "ssti_agent", "xxe_agent"]
    results = await asyncio.gather(*(gate.awrap_tool_call(request(agent), handler) for agent in agents))
    assert results[0] == "started"
    assert all(result.status == "error" for result in results[1:])
    assert handler.await_count == 1
    assert handler.call_args.args[0].tool_call["args"]["subagent_type"] == "recon_agent"


@pytest.mark.asyncio
async def test_attacks_unlock_after_recon_result_checked():
    handler = AsyncMock(return_value="started")
    assert await ReconFirstMiddleware().awrap_tool_call(request(status="success"), handler) == "started"
    handler.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["check_async_task", "list_async_tasks", "cancel_async_task"])
async def test_monitoring_and_cancellation_remain_available(tool):
    handler = AsyncMock(return_value="available")
    assert await ReconFirstMiddleware().awrap_tool_call(request(name=tool), handler) == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["task", "update_async_task"])
async def test_other_delegation_paths_cannot_bypass_recon(tool):
    handler = AsyncMock()
    result = await ReconFirstMiddleware().awrap_tool_call(request(name=tool), handler)
    assert result.status == "error"
    handler.assert_not_awaited()


def test_sync_delegation_obeys_same_order():
    handler = Mock(return_value="started")
    gate = ReconFirstMiddleware()
    assert gate.wrap_tool_call(request(), handler).status == "error"
    handler.assert_not_called()
    assert gate.wrap_tool_call(request(status="success"), handler) == "started"
