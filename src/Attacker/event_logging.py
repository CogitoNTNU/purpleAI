"""Attacker events and execution helpers; Vector handles delivery."""

import asyncio
import sys
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from time import monotonic
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from purpleai_logging import EventLogger

log_event = EventLogger(
    source="attacker-agent",
    actor="attacker",
    default_path=Path(__file__).resolve().parent / "logs/events.jsonl",
).log_event


@contextmanager
def log_span(name, *, completed_status="completed", **fields):
    """Pair lifecycle events, including failures and operator interruption."""
    started = monotonic()
    fields = {**fields, "operation_id": str(uuid4())}
    log_event(f"{name}_start", status="started", **fields)
    status, error_type = completed_status, None
    try:
        yield
    except (KeyboardInterrupt, asyncio.CancelledError):
        status = "cancelled"
        raise
    except Exception as exc:
        status, error_type = "error", type(exc).__name__
        raise
    finally:
        log_event(
            f"{name}_end",
            status=status,
            error_type=error_type,
            duration_ms=round((monotonic() - started) * 1000),
            **fields,
        )


def log_engagement(function):
    """The autonomous Boss normally returns only when the operator stops it."""

    @wraps(function)
    async def wrapped(*args, **kwargs):
        with log_span("task", completed_status="stopped"):
            return await function(*args, **kwargs)

    return wrapped


def log_agent_update(update):
    """Record Boss tool IDs and task IDs, without prompts or raw output."""
    if not isinstance(update, dict):
        return
    # DeepAgents publishes task state in the same update as the tool result.
    # Its task_id is the remote server's thread_id, linking both processes.
    for task in (update.get("async_tasks") or {}).values():
        log_event(
            "subagent_status",
            task_id=task.get("task_id"),
            subagent=task.get("agent_name"),
            remote_run_id=task.get("run_id"),
            status=task.get("status"),
        )
    for message in update.get("messages") or []:
        for call in getattr(message, "tool_calls", None) or []:
            args = call.get("args") or {}
            log_event(
                "agent_tool_call",
                tool=call.get("name"),
                tool_call_id=call.get("id"),
                task_id=args.get("task_id") if isinstance(args, dict) else None,
            )
        if getattr(message, "type", "") == "tool":
            log_event(
                "agent_tool_result",
                tool=getattr(message, "name", None),
                tool_call_id=getattr(message, "tool_call_id", None),
                status=getattr(message, "status", None),
            )


async def run_logged_tool(cmd, *, target, timeout=1800):
    """Run a tool and log metadata, preserving its text result for the agent."""
    # Read the server's current task context without changing the tool schema.
    from langchain_core.runnables.config import ensure_config

    tool = Path(cmd[0]).name
    fields = {
        "tool": tool,
        "target": target,
        "tool_call_id": str(uuid4()),
        "task_id": ensure_config().get("configurable", {}).get("thread_id"),
        "scan_options": [
            arg
            for arg in cmd[1:]
            if arg.startswith(
                ("--level=", "--risk=", "--crawl=", "--timeout=", "--technique=")
            )
            or arg == "--forms"
        ],
    }
    started = monotonic()
    log_event("tool_call", status="started", **fields)
    proc = None
    status, error_type = "error", None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out, err = stdout.decode(errors="replace"), stderr.decode(errors="replace")
        if proc.returncode != 0:
            message = err or out or f"process exited with status {proc.returncode}"
            return f"{tool} failed: {message}"
        status = "completed"
        return out or err
    except FileNotFoundError:
        error_type = "FileNotFoundError"
        return f"{tool} is not installed or not on PATH."
    except TimeoutError:
        status, error_type = "timeout", "TimeoutError"
        return f"{tool} scan timed out after {timeout} seconds."
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.communicate()
        log_event(
            "tool_result",
            status=status,
            error_type=error_type,
            exit_code=proc.returncode if proc is not None else None,
            duration_ms=round((monotonic() - started) * 1000),
            **fields,
        )
