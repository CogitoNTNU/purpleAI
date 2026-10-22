"""Shared LLM model.

Both the Boss (local process) and every served subagent graph need the same
model. Defining it once here keeps the endpoint/key in a single place.
"""

import os

from langchain_openai import ChatOpenAI


def get_model() -> ChatOpenAI:
    """Build the chat model from the LLM_API_KEY environment variable."""
    return ChatOpenAI(
        model="moonshotai/Kimi-K2.6",
        api_key=os.environ.get("LLM_API_KEY", ""),
        base_url="https://llm.hpc.ntnu.no/v1",
    )
