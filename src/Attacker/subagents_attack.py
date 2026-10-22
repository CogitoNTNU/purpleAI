"""Execution subagent, compiled as a graph served over the Agent Protocol.

Under Plan B each subagent is an independent graph that a LangGraph server
hosts. The Boss launches it as a background task by its graph_id (see
``langgraph.json``) rather than importing this object directly, which is what
lets subagents run asynchronously and finish on their own clocks.
"""

from deepagents import create_deep_agent

from attools import sqlmap
from llm import get_model
from prompts import EXECUTION_PROMPT

# Registered in langgraph.json as the "execution_agent" graph.
execution_agent = create_deep_agent(
    model=get_model(),
    tools=[sqlmap],
    system_prompt=EXECUTION_PROMPT,
    name="execution_agent",
)
