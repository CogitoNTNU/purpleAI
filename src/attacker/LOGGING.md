# Logging new attacker functionality

Log where an action actually executes. The Boss already logs delegation and
remote task status; new subagents' internal actions need their own logging.

## Subprocess tools

Reuse `run_logged_tool` from [event_logging.py](event_logging.py), as sqlmap
does in `attools.py`. Inside the async tool, build the command as an argument
list using the configured target, then:

```python
from event_logging import run_logged_tool

# Inside the async tool:
return await run_logged_tool(cmd, target=Target_url, timeout=1800)
```

The helper logs paired `tool_call` / `tool_result` events with a shared
`tool_call_id`, the remote `task_id` when available, duration, exit code,
and error/timeout/cancellation status. It also kills and reaps the subprocess
on timeout or cancellation. Returned tool output stays available to the agent.

The `scan_options` whitelist currently covers sqlmap options. Extend it
deliberately when adding another tool; avoid recording unrestricted arguments.

## Other actions

Use the same adapter for meaningful events. In async execution-server code,
keep file writes off the event loop:

```python
import asyncio

from event_logging import log_event
from langchain_core.runnables.config import ensure_config

async def record_finding(target, finding_type):
    task_id = ensure_config().get("configurable", {}).get("thread_id")
    await asyncio.to_thread(
        log_event,
        "finding_detected",
        target=target,
        task_id=task_id,
        finding_type=finding_type,
    )
```

Call this only when observed evidence supports the finding. For actions
needing paired start/end events, add a reusable async helper to
`event_logging.py` that handles completion, exceptions, and cancellation.
Keep logging mechanics out of agent/tool logic. Direct `log_event` calls and
the synchronous `log_span` must not run on the execution server's event loop:
LangGraph's blocking-call checker rejects synchronous file I/O there.

## New agents and event meanings

- Import the existing adapter; do not add another file writer or network sender.
  It supplies the event envelope and writes to `logs/events.jsonl` beside it.
- Processes have different `run_id` values. Use `task_id` to connect remote
  execution to Boss delegation, and paired IDs for individual operations.
- Another graph or process using the same file needs no Vector changes. A new
  host or log path needs its file included in that host's Vector configuration.
- `completed` means execution completed. Confirmed findings are separate events;
  a clean exit or successful status check does not prove exploitation.
- Exclude credentials, raw responses, full prompts, and model reasoning.
- New event types need dashboard changes only when they need new counters or
  display fields. Document new fields/actions in the [event format](../../docs/event-format.md).

## Verify before merging

1. Test completion, failure, timeout/cancellation where applicable, and concurrent
   execution. Check paired IDs and task correlation. Run `uv run pytest -q` from
   the repository root; existing examples are in `tests/test_attacker_logging.py`.
2. Exercise async logging under the blocking-call checker with ordinary
   `langgraph dev`; keep the checker enabled during verification.
3. Run one real lab action. Follow its `event_id` from the local JSONL file to
   gamehost's `/var/log/purpleai/collected/events-*.jsonl` and the dashboard.

See [Vector setup](../../deploy/vector/README.md) for forwarding configuration.
