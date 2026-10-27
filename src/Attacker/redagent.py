import asyncio
import os

from dotenv import load_dotenv

# Load .env before anything reads the environment: this one file feeds both
# the LLM key (llm.get_model) and the LangSmith tracing vars below. The
# langgraph dev server reads the same .env via langgraph.json's "env".
load_dotenv()

from config import Target_url
from deepagents import create_deep_agent
from event_logging import log_agent_update, log_engagement, log_span
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_sdk import get_client
from llm import get_model
from prompts import BOSS_PROMPT

# Safety cap: stop after this many Boss turns even if it keeps launching work,
# so a runaway loop can't run unbounded. The loop normally stops on its own when
# the Boss has no subagents running and launches nothing new.
MAX_ITERATIONS = 50

# Fixed thread id: with the checkpointer below, every loop iteration resumes
# the SAME conversation, so the Boss remembers which tasks it launched and can
# keep monitoring them across iterations instead of starting fresh each time.
SESSION_THREAD_ID = "attacker-session"

# URL of the Agent Protocol server that hosts the subagent graphs.
# `langgraph dev` serves here by default; override if you deploy elsewhere.
SUBAGENT_SERVER_URL = "http://localhost:2024"

# Async subagents are referenced by their graph_id on the server (see
# langgraph.json), NOT imported as objects. Launching one returns a task_id
# immediately so the Boss is never blocked by a slow subagent. Add more
# subagents here as new graphs are registered on the server.
subagents = [
    {
        "name": "sql_injection_agent",
        "description": (
            "SQL injection specialist. Runs sqlmap against the authorized "
            "target. Give it a focused task describing which attack surface, "
            "techniques, or recon hints to use so it can target its scan "
            "rather than sweeping the whole site."
        ),
        "graph_id": "sql_injection_agent",
        "url": SUBAGENT_SERVER_URL,
    },
]

# Checkpointer persists the conversation across loop iterations (in memory,
# for the life of this process). It is what makes the autonomous loop coherent
# rather than a series of amnesiac one-shots.
BossAgent = create_deep_agent(
    model=get_model(),
    system_prompt=BOSS_PROMPT,
    name="Boss Agent",
    subagents=subagents,
    checkpointer=InMemorySaver(),
)


def _print_trace_pointer() -> None:
    """Point the user at the LangSmith UI where the full reasoning lives.

    Per-run URLs vary by langsmith version, so we print a stable project
    pointer instead of a fragile deep link. Never let this break the run.
    """
    if os.getenv("LANGSMITH_TRACING", "").lower() != "true":
        return
    project = os.getenv("LANGSMITH_PROJECT", "default")
    host = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    web = "https://eu.smith.langchain.com" if "eu." in host else "https://smith.langchain.com"
    print(
        f"\nFull Boss + subagent reasoning traced to LangSmith "
        f"project '{project}': {web}"
    )


# First iteration states the objective; every later iteration nudges the Boss
# to pick up where it left off — check running tasks, act on finished ones, and
# decide the next move — so the engagement advances on its own.
INITIAL_OBJECTIVE = (
    f"Begin a penetration test of {Target_url}, starting with SQL injection. "
    "Delegate a focused scan to the sql_injection_agent."
)
CONTINUE_NUDGE = (
    "Continue the engagement. First check the status of every task you have "
    "launched. For any that finished, read and analyze the result, then decide "
    "and launch the next step. For any still running, leave them and report "
    "their status. If you are waiting on tasks and have nothing new to launch, "
    "say so briefly. Do not re-launch a scan that is already running or already "
    "answered."
)


def _text(content) -> str:
    """Flatten message content (str, or a list of content blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def _short(value, limit: int = 200) -> str:
    """One-line, length-capped repr for tool args/results."""
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit] + "…"


def _render_messages(node: str, update) -> None:
    """Print the Boss's reasoning for one streamed step as it arrives."""
    log_agent_update(update)
    messages = update.get("messages") if isinstance(update, dict) else None
    if not messages:
        return
    for msg in messages:
        kind = getattr(msg, "type", "")
        if kind == "tool":  # a tool/subagent result coming back
            name = getattr(msg, "name", "tool")
            print(f"  ← {name}: {_short(getattr(msg, 'content', ''))}")
            continue
        text = _text(getattr(msg, "content", ""))
        if text.strip():
            print(f"  [{node}] {text.strip()}")
        for call in getattr(msg, "tool_calls", None) or []:
            print(f"  → {call.get('name')}({_short(call.get('args'))})")


async def _run_once(message: str, iteration: int, config: dict) -> None:
    """Advance the engagement by one turn, streaming each step live."""
    print(f"\n===== iteration {iteration} =====")
    with log_span("iteration", iteration=iteration, target=Target_url):
        async for chunk in BossAgent.astream(
            {"messages": message}, config=config, stream_mode="updates"
        ):
            # Each chunk maps node name -> that node's state update.
            for node, update in chunk.items():
                _render_messages(node, update)


async def _running_tasks(config: dict) -> list[dict]:
    """Return the subagent tasks the Boss is tracking that are still running.

    The Boss records every launched task in its graph state under
    ``async_tasks``; we read that back from the checkpointer to learn what,
    if anything, is still in flight after a turn.
    """
    state = await BossAgent.aget_state(config)
    tasks = (state.values or {}).get("async_tasks") or {}
    return [t for t in tasks.values() if t.get("status") == "running"]


async def _wait_for_any(client, running: list[dict]) -> None:
    """Sleep until at least one running subagent reports back.

    This is the event-driven replacement for the old fixed poll interval:
    ``runs.join`` blocks on the server until a run finishes, so the loop
    consumes no CPU or tokens while every scan is still working, and wakes the
    instant the first one completes.
    """
    pending = {
        asyncio.ensure_future(client.runs.join(t["thread_id"], t["run_id"])): t
        for t in running
    }
    print(
        f"  … {len(pending)} subagent(s) running; sleeping until one reports back."
    )
    done, still_pending = await asyncio.wait(
        pending, return_when=asyncio.FIRST_COMPLETED
    )
    # Drop the long-poll connections for tasks that are still running; the Boss
    # re-checks every task's status on its next turn anyway.
    for fut in still_pending:
        fut.cancel()
    for fut in done:
        task = pending[fut]
        print(f"  ← subagent task {task['task_id']} finished; waking the Boss.")


@log_engagement
async def main() -> None:
    """Run the Boss autonomously, waking on subagent feedback (Ctrl+C to stop)."""
    print("Autonomous attacker running. Press Ctrl+C to stop.")
    _print_trace_pointer()
    config = {"configurable": {"thread_id": SESSION_THREAD_ID}}
    client = get_client(url=SUBAGENT_SERVER_URL)
    iteration = 0
    try:
        while iteration < MAX_ITERATIONS:
            message = INITIAL_OBJECTIVE if iteration == 0 else CONTINUE_NUDGE
            await _run_once(message, iteration, config)
            iteration += 1

            # Decide whether to wait only AFTER a full Boss turn, so it has
            # already had its chance to analyze results, update its plan, and
            # launch the next step. If it launched nothing and nothing is still
            # running, the engagement is genuinely done.
            running = await _running_tasks(config)
            if not running:
                print(
                    "\nNo subagents running and nothing new launched - "
                    "engagement complete."
                )
                break
            # Event-driven: block here until a subagent reports back, then loop
            # and nudge the Boss to act on it.
            await _wait_for_any(client, running)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopping autonomous attacker (interrupted). Goodbye.")
        return
    if iteration >= MAX_ITERATIONS:
        print(f"\nReached max iterations ({MAX_ITERATIONS}); stopping.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C during startup/teardown, before the loop's handler is active.
        print("\nStopped.")
