"""Dynamic queued HTTP clients; transient failures rejoin the shared queue.

SDK retries are disabled: every attempt must borrow a free key. Successful
streaming bodies hold their slot until consumed/closed. Permanent request
errors are surfaced rather than silently retried forever.
"""
import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import os
import random

import httpx
from langchain_openai import ChatOpenAI

from llm_queue import KeyQueue


def _retry_delay(response):
    if response.status_code in (401, 403):
        return 300.0
    retry = response.headers.get("retry-after", "")
    try:
        return max(1.0, float(retry))
    except ValueError:
        try:
            return max(1.0, (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 5.0 + random.random() * 5


def _should_retry(response):
    return response.status_code in (401, 403, 408, 409, 429) or response.status_code >= 500


class _SyncStream(httpx.SyncByteStream):
    def __init__(self, stream, lease):
        self.stream, self.lease = stream, lease

    def __iter__(self):
        try:
            yield from self.stream
        finally:
            self.close()

    def close(self):
        try:
            self.stream.close()
        finally:
            self.lease.close()


class _AsyncStream(httpx.AsyncByteStream):
    def __init__(self, stream, lease):
        self.stream, self.lease = stream, lease

    async def __aiter__(self):
        try:
            async for chunk in self.stream:
                yield chunk
        finally:
            await self.aclose()

    async def aclose(self):
        try:
            await self.stream.aclose()
        finally:
            self.lease.close()


class QueuedTransport(httpx.BaseTransport):
    def __init__(self, queue=None, inner=None):
        self.queue = queue or KeyQueue()
        self.inner = inner or httpx.HTTPTransport()

    def handle_request(self, request):
        request.read()
        while True:
            lease = self.queue.acquire()
            transferred = False
            try:
                request.headers["Authorization"] = "Bearer " + lease.key
                response = self.inner.handle_request(request)
                if not _should_retry(response):
                    if response.is_closed:
                        lease.close()
                    else:
                        response.stream = _SyncStream(response.stream, lease)
                    transferred = True
                    return response
                delay = _retry_delay(response)
                code = response.status_code
                response.close()
                self.queue.cooldown(lease, delay)
                print(f"[llm] HTTP {code}; key cooling down {delay:.0f}s; rejoining queue. For 401/403 check key permissions.", flush=True)
            except httpx.TransportError as exc:
                self.queue.cooldown(lease, 5)
                print(f"[llm] {type(exc).__name__}; reconnecting through queue", flush=True)
            finally:
                if not transferred:
                    lease.close()

    def close(self):
        self.inner.close()


class AsyncQueuedTransport(httpx.AsyncBaseTransport):
    def __init__(self, queue=None, inner=None):
        self.queue = queue or KeyQueue()
        self.inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request):
        await request.aread()
        while True:
            lease = await self.queue.acquire_async()
            transferred = False
            try:
                request.headers["Authorization"] = "Bearer " + lease.key
                response = await self.inner.handle_async_request(request)
                if not _should_retry(response):
                    if response.is_closed:
                        lease.close()
                    else:
                        response.stream = _AsyncStream(response.stream, lease)
                    transferred = True
                    return response
                delay = _retry_delay(response)
                code = response.status_code
                await response.aclose()
                await asyncio.to_thread(self.queue.cooldown, lease, delay)
                print(f"[llm] HTTP {code}; key cooling down {delay:.0f}s; rejoining queue. For 401/403 check key permissions.", flush=True)
            except httpx.TransportError as exc:
                await asyncio.to_thread(self.queue.cooldown, lease, 5)
                print(f"[llm] {type(exc).__name__}; reconnecting through queue", flush=True)
            finally:
                if not transferred:
                    lease.close()

    async def aclose(self):
        await self.inner.aclose()


def get_model() -> ChatOpenAI:
    queue = KeyQueue()
    timeout = httpx.Timeout(float(os.environ.get("LLM_READ_TIMEOUT", "600")), connect=20, pool=20)
    return ChatOpenAI(
        model=os.environ.get("LLM_MODEL", "moonshotai/Kimi-K2.6"),
        api_key="queue-managed",
        base_url=os.environ.get("LLM_BASE_URL", "https://llm.hpc.ntnu.no/v1"),
        max_retries=0,
        timeout=timeout,
        http_client=httpx.Client(transport=QueuedTransport(queue), timeout=timeout),
        http_async_client=httpx.AsyncClient(transport=AsyncQueuedTransport(queue), timeout=timeout),
    )
