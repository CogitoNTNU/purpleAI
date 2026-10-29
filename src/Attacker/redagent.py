import asyncio
import os
import re

from dotenv import load_dotenv

# Load .env before anything reads the environment: this one file feeds both
# the LLM key (llm.get_model) and the LangSmith tracing vars below. The
# langgraph dev server reads the same .env via langgraph.json's "env".
load_dotenv()

from config import Target_url
from deepagents import create_deep_agent
from event_logging import log_agent_update, log_engagement, log_event, log_span
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
    {
        "name": "xss_agent",
        "description": (
            "Cross-site scripting specialist. Runs xsser against the authorized "
            "target. Give it a focused task describing the endpoint, parameter, "
            "or form and XSS context to test rather than sweeping the whole site."
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
    f"Begin a penetration test of {Target_url}. Launch two focused scans in "
    "parallel right away, since they are independent: delegate a SQL injection "
    "scan to the sql_injection_agent and a cross-site scripting scan to the "
    "xss_agent. Give each a specific task for its specialty."
)
CONTINUE_NUDGE = (
    "Continue the engagement. First check the status of every task you have "
    "launched. For any that finished, read and analyze the result, then decide "
    "and launch the next step. For any still running, leave them and report "
    "their status. If you are waiting on tasks and have nothing new to launch, "
    "say so briefly. Do not re-launch a scan that is already running or already "
    "answered."
)
# Sent when every task has finished and the Boss launched nothing new: the
# engagement is NOT over, so push it to find a fresh angle rather than idling.
PROBE_NUDGE = (
    "Every task has finished and nothing is running, but the engagement is NOT "
    "over. Look for a new angle to capture more FLAG{...}: an untested endpoint, "
    "parameter, form, cookie, or a different vulnerability class, and delegate a "
    "focused new scan to the specialist that fits (sql_injection_agent or "
    "xss_agent). Do not repeat a scan already run or already answered. Only if "
    "you have genuinely exhausted every reasonable avenue, say so in one line - "
    "you will be asked again until the operator stops you."
)
# Sent once as the loop exits (any reason) to get a final findings report. The
# Boss still has the whole engagement in memory, so it can summarise from it.
SUMMARY_PROMPT = (
    "The engagement is ending. Write a concise final penetration-test summary "
    "from everything you did this session: which attack surfaces and parameters "
    "were tested, which SQL injections were confirmed or ruled out (with the "
    "supporting evidence), every FLAG{...} value you captured and which "
    "vulnerability yielded it, anything still inconclusive, and your recommended "
    "next steps. Do NOT launch any new tasks - just report."
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


# Flags are secret strings of the form FLAG{...} planted in the target; capturing
# them is the objective. We scan every piece of text that streams back (agent
# reasoning and, crucially, subagent/tool results) for this pattern.
FLAG_RE = re.compile(r"FLAG\{[^}\n]{0,200}\}")
# Session-wide set of flags seen so far, so each is announced and reported once.
CAPTURED_FLAGS: set[str] = set()


def _scan_for_flags(text: str) -> None:
    """Record and announce any newly seen FLAG{...} values in `text`."""
    for flag in FLAG_RE.findall(text or ""):
        if flag not in CAPTURED_FLAGS:
            CAPTURED_FLAGS.add(flag)
            print(f"  🚩 CAPTURED FLAG: {flag}")
            log_event("flag_captured", flag=flag, target=Target_url)


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
            content = _text(getattr(msg, "content", ""))
            # Scan the FULL result (not the truncated preview) for flags.
            _scan_for_flags(content)
            print(f"  ← {name}: {_short(content)}")
            continue
        text = _text(getattr(msg, "content", ""))
        if text.strip():
            _scan_for_flags(text)
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


async def _tasks(config: dict) -> dict[str, dict]:
    """Return the Boss's tracked subagent tasks, keyed by task_id.

    The Boss records every launched task in its graph state under
    ``async_tasks``; we read that back from the checkpointer to learn what it
    has launched and what is still in flight after a turn.
    """
    state = await BossAgent.aget_state(config)
    return (state.values or {}).get("async_tasks") or {}


def _running(tasks: dict[str, dict]) -> list[dict]:
    """Filter tracked tasks down to the ones still running."""
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


async def _summarize(config: dict) -> None:
    """Run one final Boss turn that reports the engagement's findings.

    Reuses the same thread, so the Boss summarises from its full memory of the
    scans it launched and the results it read.
    """
    print("\n===== ENGAGEMENT SUMMARY =====")
    flags_note = (
        " Flags captured so far: " + ", ".join(sorted(CAPTURED_FLAGS)) + "."
        if CAPTURED_FLAGS
        else " No FLAG{...} values have been captured yet."
    )
    with log_span("summary", target=Target_url):
        async for chunk in BossAgent.astream(
            {"messages": SUMMARY_PROMPT + flags_note},
            config=config,
            stream_mode="updates",
        ):
            for node, update in chunk.items():
                _render_messages(node, update)
    # Mechanical tally so captured flags are unmissable regardless of the model.
    if CAPTURED_FLAGS:
        print(f"\nFlags captured ({len(CAPTURED_FLAGS)}):")
        for flag in sorted(CAPTURED_FLAGS):
            print(f"  🚩 {flag}")
    else:
        print("\nNo flags captured this engagement.")


@log_engagement
async def main() -> None:
    """Run the Boss autonomously, waking on subagent feedback (Ctrl+C to stop)."""
    print("Autonomous attacker running. Press Ctrl+C to stop.")
    _print_trace_pointer()
    config = {"configurable": {"thread_id": SESSION_THREAD_ID}}
    client = get_client(url=SUBAGENT_SERVER_URL)
    iteration = 0
    message = INITIAL_OBJECTIVE
    try:
        while iteration < MAX_ITERATIONS:
            # Snapshot the tasks before the turn so we can tell whether the Boss
            # launched anything new during it.
            before = set(await _tasks(config))
            await _run_once(message, iteration, config)
            iteration += 1

            tasks = await _tasks(config)
            running = _running(tasks)
            launched_new = any(tid not in before for tid in tasks)

            if running:
                # Event-driven: sleep until a subagent reports back, then nudge
                # the Boss to act on it.
                await _wait_for_any(client, running)
                message = CONTINUE_NUDGE
            elif launched_new:
                # The Boss launched work that already finished (e.g. a fast
                # failure). Loop so it reads those results before we judge it
                # idle - never stop with unreacted results on the table.
                message = CONTINUE_NUDGE
            else:
                # Nothing running and nothing launched this turn: the Boss is
                # idle. Keep probing for new angles rather than stopping; the
                # engagement ends only at MAX_ITERATIONS or on Ctrl+C.
                print("\n  (idle - probing for a new angle)")
                message = PROBE_NUDGE
        print(f"\nReached max iterations ({MAX_ITERATIONS}); stopping.")
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopping autonomous attacker (interrupted).")
    finally:
        # Always end with a findings report, even on Ctrl+C. A second Ctrl+C
        # during the summary skips it so the user can still bail out.
        try:
            await _summarize(config)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nSummary interrupted; exiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C during startup/teardown, before the loop's handler is active.
        print("\nStopped.")
