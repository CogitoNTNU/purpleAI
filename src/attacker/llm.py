"""Shared LLM model.

Both the Boss (local process) and every served subagent graph need the same
model. Defining it once here keeps the endpoint/key in a single place.
"""

import os

from langchain_openai import ChatOpenAI


def get_model() -> ChatOpenAI:
    """Build the chat model from the LLM_API_KEY environment variable.

    The shared endpoint caps the key at ONE concurrent request
    (max_parallel_requests=1), so the Boss and its subagents constantly contend
    for the single slot and get 429s. max_retries lets a throttled call wait
    (the client backs off, honoring the server's Retry-After) and succeed on a
    later attempt instead of crashing the run. Overridable via LLM_MAX_RETRIES.
    """
    return ChatOpenAI(
        model="moonshotai/Kimi-K2.6",
        api_key=os.environ.get("LLM_API_KEY", ""),
        base_url="https://llm.hpc.ntnu.no/v1",
        max_retries=int(os.environ.get("LLM_MAX_RETRIES", "8")),
    )
