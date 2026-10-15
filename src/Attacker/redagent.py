import asyncio

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


async def main() -> None:
    result = await BossAgent.ainvoke(
        {"messages": f"Scan {Target_url} for SQL injection."}
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
