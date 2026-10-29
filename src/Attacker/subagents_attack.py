"""SQL injection and XSS subagents, compiled as graphs served over the Agent Protocol.

Under Plan B each subagent is an independent graph that a LangGraph server
hosts. The Boss launches it as a background task by its graph_id (see
``langgraph.json``) rather than importing this object directly, which is what
lets subagents run asynchronously and finish on their own clocks.
"""

from deepagents import create_deep_agent

from attools import sqlmap
from attools import xsser
from llm import get_model
from prompts import SQL_INJECTION_PROMPT, XSS_PROMPT

# Registered in langgraph.json as the "sql_injection_agent" graph.
sql_injection_agent = create_deep_agent(
    model=get_model(),
    tools=[sqlmap],
    system_prompt=SQL_INJECTION_PROMPT,
    name="sql_injection_agent",
)
xss_agent = create_deep_agent(
    model=get_model(),
    tools=[xsser],
    system_prompt=XSS_PROMPT,
    name="xss_agent",
)
