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
from llm import get_model
from prompts import BOSS_PROMPT

# Seconds to wait between autonomous iterations, so the loop monitors running
# scans without busy-spinning (and without burning tokens non-stop).
POLL_INTERVAL = 30.0

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
        "name": "sql_agent",
        "description": (
            "Execute the tasks and implement solutions delegated by the Boss "
            "Agent. Runs sqlmap against the configured target."
        ),
        "graph_id": "sql_agent",
        "url": SUBAGENT_SERVER_URL,
    },
    {
            "name": "xss_agent",
            "description": (
                "Execute the tasks and implement solutions delegated by the Boss "
                "Agent. Runs xsser against the configured target."
            ),
            "graph_id": "xss_agent",
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
    "Delegate the scan to the execution agent."
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


async def _run_once(message: str, iteration: int) -> None:
    """Advance the engagement by one turn, streaming each step live."""
    config = {"configurable": {"thread_id": SESSION_THREAD_ID}}
    print(f"\n===== iteration {iteration} =====")
    with log_span("iteration", iteration=iteration, target=Target_url):
        async for chunk in BossAgent.astream(
            {"messages": message}, config=config, stream_mode="updates"
        ):
            # Each chunk maps node name -> that node's state update.
            for node, update in chunk.items():
                _render_messages(node, update)


@log_engagement
async def main() -> None:
    """Run the Boss autonomously until interrupted (Ctrl+C)."""
    print("Autonomous attacker running. Press Ctrl+C to stop.")
    _print_trace_pointer()
    iteration = 0
    try:
        while True:
            message = INITIAL_OBJECTIVE if iteration == 0 else CONTINUE_NUDGE
            await _run_once(message, iteration)
            iteration += 1
            # Pause between turns so we monitor running scans rather than
            # hammering the model and the target back-to-back.
            await asyncio.sleep(POLL_INTERVAL)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopping autonomous attacker (interrupted). Goodbye.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C during startup/teardown, before the loop's handler is active.
        print("\nStopped.")
