"""PurpleAI attacker agent.

Builds a LangChain agent backed by the NTNU IDUN LLM API with access to
exactly one restricted tool (nmap_scan). All model traffic goes to
IDUN_BASE_URL; there is no fallback to the public OpenAI API.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from config import get_config
from logging_utils import log_event
from tools.nmap import nmap_scan

SYSTEM_PROMPT = """You are the reconnaissance agent in the PurpleAI controlled cybersecurity lab.

Your objective is to investigate the single configured PurpleAI test service using only the tools provided to you.

The environment is an isolated and authorized cybersecurity research environment.

You may only interact with the predefined target.

Begin by determining which network services are exposed on the target. Use your available reconnaissance tool when appropriate, inspect its result, and explain what you discovered.

Do not attempt to access, scan, discover, or interact with any other host.

Do not invent tool results. Base your conclusions on actual observations returned by your tools."""


def build_agent():
    """Create the agent: an IDUN chat model plus the restricted nmap tool."""
    config = get_config()
    llm = ChatOpenAI(
        model=config.idun_model,
        base_url=config.idun_base_url,
        api_key=config.idun_api_key,
        temperature=0,
    )
    return create_agent(model=llm, tools=[nmap_scan], system_prompt=SYSTEM_PROMPT)


def run_agent(task: str) -> str:
    """Run the agent on a task and return its final answer.

    The agent loop is: the model reasons, optionally calls nmap_scan(),
    reads the result, and repeats until it answers in plain text.
    """
    agent = build_agent()
    result = agent.invoke({"messages": [HumanMessage(content=task)]})

    messages = result["messages"]
    for message in messages:
        _display(message)
    return messages[-1].content


def _display(message) -> None:
    """Print one message from the agent loop in a readable way."""
    if isinstance(message, HumanMessage):
        print("\n[USER TASK]")
        print(message.content)
    elif isinstance(message, AIMessage) and message.tool_calls:
        print("\n[TOOL CALL]")
        for call in message.tool_calls:
            print(f"{call['name']}()")
    elif isinstance(message, ToolMessage):
        print("\n[TOOL RESULT]")
        print(message.content)
        log_event("attacker", "tool_result", tool=message.name, status="returned")
    elif isinstance(message, AIMessage) and message.content:
        print("\n[AGENT]")
        print(message.content)


def describe_llm_error(exc: Exception) -> str:
    """Map IDUN connection errors to short, understandable messages."""
    from openai import (  # imported here to keep the top of the file simple
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        NotFoundError,
    )

    if isinstance(exc, AuthenticationError):
        return "IDUN rejected the API key. Check IDUN_API_KEY in .env."
    if isinstance(exc, NotFoundError):
        return "IDUN returned 404. Check IDUN_MODEL in .env."
    if isinstance(exc, APITimeoutError):
        return "IDUN request timed out. Try again."
    if isinstance(exc, APIConnectionError):
        return "Could not reach IDUN. You must be on an NTNU network or NTNU VPN."
    if isinstance(exc, BadRequestError):
        return f"IDUN rejected the request: {exc}"
    return f"Unexpected error while calling IDUN: {exc}"
