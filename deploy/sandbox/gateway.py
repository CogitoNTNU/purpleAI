"""Bounded chat-completions gateway. Only this process receives the Idun key."""

import hmac
import os
import threading
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, request

UPSTREAM = "https://llm.hpc.ntnu.no/v1/chat/completions"


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    key = Path(os.environ["IDUN_KEY_FILE"]).read_text().strip()
    token = os.environ["GATEWAY_TOKEN"]
    if not key or len(token) < 32:
        raise ValueError(
            "An Idun key and gateway token of at least 32 characters are required"
        )
    budget = int(os.environ.get("GATEWAY_CALL_LIMIT", "1000"))
    if budget < 1:
        raise ValueError("GATEWAY_CALL_LIMIT must be positive")
    lock = threading.Lock()
    calls = 0

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.post("/v1/chat/completions")
    def completion():
        nonlocal calls
        if (
            request.content_length
            and request.content_length > app.config["MAX_CONTENT_LENGTH"]
        ):
            return jsonify(error="Request too large"), 413
        if not hmac.compare_digest(
            request.headers.get("Authorization", ""), f"Bearer {token}"
        ):
            return jsonify(error="Unauthorized"), 401
        payload = request.get_json(silent=True)
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("model"), str)
            or not payload["model"].strip()
        ):
            return jsonify(error="A model ID is required"), 400
        allowed_fields = {
            "model",
            "messages",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "temperature",
            "top_p",
            "stop",
            "response_format",
            "seed",
            "max_tokens",
            "max_completion_tokens",
            "stream",
        }
        if payload.keys() - allowed_fields or payload.get("stream", False) is not False:
            return jsonify(
                error="Unsupported request options; streaming is disabled"
            ), 400
        if not isinstance(payload.get("messages"), list) or not payload["messages"]:
            return jsonify(error="Messages required"), 400
        for name in ("max_tokens", "max_completion_tokens"):
            if name in payload and (
                type(payload[name]) is not int or not 1 <= payload[name] <= 2048
            ):
                return jsonify(
                    error="Output limit must be between 1 and 2048 tokens"
                ), 400
        if "max_tokens" in payload and "max_completion_tokens" in payload:
            return jsonify(error="Specify only one output limit"), 400
        if not {"max_tokens", "max_completion_tokens"} & payload.keys():
            payload["max_tokens"] = 2048
        if not lock.acquire(blocking=False):
            return jsonify(error="Gateway busy"), 429
        try:
            if calls >= budget:
                return jsonify(error="Run call budget exhausted"), 429
            calls += 1  # Failed requests also consume the budget.
            with requests.Session() as session:
                session.trust_env = False
                with session.post(
                    UPSTREAM,
                    json=payload,
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=(10, 120),
                    allow_redirects=False,
                    stream=True,
                ) as upstream:
                    if upstream.status_code != 200:
                        return jsonify(error="Idun request failed"), 502
                    body = bytearray()
                    for chunk in upstream.iter_content(8192):
                        body.extend(chunk)
                        if len(body) > 2 * 1024 * 1024:
                            return jsonify(error="Idun response too large"), 502
                    return Response(bytes(body), content_type="application/json")
        except requests.RequestException:
            return jsonify(error="Idun unavailable"), 502
        finally:
            lock.release()

    return app
