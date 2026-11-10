"""Shared LLM model.

Both the Boss (local process) and every served subagent graph need the same
model. Defining it once here keeps the endpoint in a single place.

The endpoint caps EACH key at one concurrent request (max_parallel_requests=1),
so a single run's Boss + subagents contend for one slot and 429. To spread the
load, pass a POOL of keys in LLM_API_KEYS (comma/newline separated) and each
agent is handed the next key in rotation at construction, so concurrent agents
use different keys (each key then only sees one request at a time). Falls back
to the single LLM_API_KEY when no pool is set.
"""

import itertools
import os
import threading

from langchain_openai import ChatOpenAI

_LOCK = threading.Lock()
_CYCLE = None


def _key_pool() -> list[str]:
    raw = os.environ.get("LLM_API_KEYS") or os.environ.get("LLM_API_KEY", "")
    keys = [k.strip() for k in raw.replace("\n", ",").replace(";", ",").split(",")
            if k.strip()]
    return keys or [""]


def _next_key() -> str:
    """Round-robin the next key from the pool (one per get_model call)."""
    global _CYCLE
    with _LOCK:
        if _CYCLE is None:
            _CYCLE = itertools.cycle(_key_pool())
        return next(_CYCLE)


def get_model() -> ChatOpenAI:
    """Build the chat model. Each call takes the next key from the pool, so the
    Boss and each subagent graph run on different keys and don't starve one
    another's single concurrency slot. max_retries lets a throttled call back
    off and wait (honoring Retry-After) instead of crashing. Both the pool
    (LLM_API_KEYS) and the retry count (LLM_MAX_RETRIES) come from the env.
    """
    return ChatOpenAI(
        model="moonshotai/Kimi-K2.6",
        api_key=_next_key(),
        base_url="https://llm.hpc.ntnu.no/v1",
        max_retries=int(os.environ.get("LLM_MAX_RETRIES", "12")),
    )
