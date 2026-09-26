"""PurpleAI attacker agent.

Builds a LangChain agent backed by the NTNU IDUN LLM API with access to
exactly one restricted tool (nmap_scan). All model traffic goes to
IDUN_BASE_URL; there is no fallback to the public OpenAI API.
"""

from __future__ import annotations

# LangChain is a framework for building LLM applications. These are the
# pieces used here:
#
# - create_agent (langchain.agents): builds an *agent*, i.e. a loop where
#   the LLM decides on its own whether to answer directly or call one of
#   the provided tools, sees the tool result, and repeats until done.
# - AIMessage / HumanMessage / ToolMessage (langchain_core.messages):
#   the message types in the conversation. HumanMessage is what the user
#   says, AIMessage is what the model says (it may contain "tool_calls"
#   instead of plain text), and ToolMessage is a tool's result fed back
#   to the model.
# - ChatOpenAI (langchain_openai): an OpenAI-compatible chat client. Any
#   server that speaks the OpenAI HTTP API can be used, which is how the
#   NTNU IDUN endpoint is supported without any special SDK.
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
    # ChatOpenAI is pointed at the IDUN endpoint instead of the public
    # OpenAI API: IDUN implements the OpenAI chat protocol, so this client
    # works as-is. temperature=0 makes the model (mostly) deterministic,
    # which keeps the agent's behaviour reproducible.
    llm = ChatOpenAI(
        model=config.idun_model,
        base_url=config.idun_base_url,
        api_key=config.idun_api_key,
        temperature=0,
    )
    # create_agent wires everything together: model + tools + system
    # prompt. The system prompt is the model's standing instructions that
    # apply to the whole session; here it pins the agent to the single
    # authorized target. The result is a runnable agent that can be
    # invoked with a conversation.
    return create_agent(model=llm, tools=[nmap_scan], system_prompt=SYSTEM_PROMPT)


def run_agent(task: str) -> str:
    """Run the agent on a task and return its final answer.

    The agent loop is: the model reasons, optionally calls nmap_scan(),
    reads the result, and repeats until it answers in plain text.
    """
    agent = build_agent()
    # invoke() runs the whole agent loop to completion and returns the
    # final conversation. The input is a dict with a "messages" key —
    # that is the standard LangChain state format: the agent appends
    # every model reply and tool result to this list as it works.
    result = agent.invoke({"messages": [HumanMessage(content=task)]})

    messages = result["messages"]
    for message in messages:
        _display(message)
    # The last message is the agent's final plain-text answer; the loop
    # ends as soon as the model replies without any tool calls.
    return messages[-1].content


def _display(message) -> None:
    """Print one message from the agent loop in a readable way."""
    # The conversation contains several message types; each is rendered
    # differently so the transcript mirrors what the model actually did.
    if isinstance(message, HumanMessage):
        # The original task.
        print("\n[USER TASK]")
        print(message.content)
    elif isinstance(message, AIMessage) and message.tool_calls:
        # The model decided to use a tool. It does not run the tool
        # itself — the agent framework does that — so this message only
        # shows *which* tool with *which* arguments.
        print("\n[TOOL CALL]")
        for call in message.tool_calls:
            print(f"{call['name']}()")
    elif isinstance(message, ToolMessage):
        # The tool's return value, sent back to the model as input for
        # its next reasoning step.
        print("\n[TOOL RESULT]")
        print(message.content)
        log_event("attacker", "tool_result", tool=message.name, status="returned")
    elif isinstance(message, AIMessage) and message.content:
        # A plain-text answer with no tool calls — this ends the loop.
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
