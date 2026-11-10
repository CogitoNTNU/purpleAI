"""Require a completed recon result before the Boss delegates attack work."""
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage


class ReconFirstMiddleware(AgentMiddleware):
    def _blocked(self, request):
        call = request.tool_call
        name, args = call["name"], call.get("args", {})
        tasks = request.state.get("async_tasks") or {}
        if name in ("start_async_task", "task"):
            agent = args.get("subagent_type")
        elif name == "update_async_task":
            agent = tasks.get(args.get("task_id"), {}).get("agent_name")
        else:
            return None  # status checks, results, cancellation remain available
        if agent == "recon_agent":
            return None
        if any(task.get("agent_name") == "recon_agent" and task.get("status") == "success"
               for task in tasks.values()):
            return None
        return ToolMessage(
            content=("Recon must finish before attack work can start. Launch only "
                     "recon_agent, wait for it, then use check_async_task to read its "
                     "successful result before delegating scans using its map."),
            tool_call_id=call["id"], name=name, status="error",
        )

    def wrap_tool_call(self, request, handler):
        blocked = self._blocked(request)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(self, request, handler):
        blocked = self._blocked(request)
        return blocked if blocked is not None else await handler(request)
