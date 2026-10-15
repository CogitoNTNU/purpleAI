import asyncio
import os

from dotenv import load_dotenv

# Load .env before anything reads the environment: this one file feeds both
# the LLM key (llm.get_model) and the LangSmith tracing vars below. The
# langgraph dev server reads the same .env via langgraph.json's "env".
load_dotenv()

from deepagents import create_deep_agent

from config import Target_url
from llm import get_model
from prompts import BOSS_PROMPT

# URL of the Agent Protocol server that hosts the subagent graphs.
# `langgraph dev` serves here by default; override if you deploy elsewhere.
SUBAGENT_SERVER_URL = "http://localhost:2024"

# Async subagents are referenced by their graph_id on the server (see
# langgraph.json), NOT imported as objects. Launching one returns a task_id
# immediately so the Boss is never blocked by a slow subagent. Add more
# subagents here as new graphs are registered on the server.
subagents = [
    {
        "name": "execution_agent",
        "description": (
            "Execute the tasks and implement solutions delegated by the Boss "
            "Agent. Runs sqlmap against the configured target."
        ),
        "graph_id": "execution_agent",
        "url": SUBAGENT_SERVER_URL,
    },
]

BossAgent = create_deep_agent(
    model=get_model(),
    system_prompt=BOSS_PROMPT,
    name="Boss Agent",
    subagents=subagents,
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


async def main() -> None:
    result = await BossAgent.ainvoke(
        {"messages": f"Scan {Target_url} for SQL injection."}
    )
    # The rich reasoning is in LangSmith; keep the terminal to the final answer.
    final = result["messages"][-1]
    print(getattr(final, "content", final))
    _print_trace_pointer()


if __name__ == "__main__":
    asyncio.run(main())
