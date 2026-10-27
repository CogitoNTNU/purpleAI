# Logging when extending the defender

Keep classification in the agents and request logging in the proxy.
Reuse [event_logging.py](event_logging.py) and the shared
`src/purpleai_logging.py`; Vector handles delivery.

## Add or change a classifier

1. Define a function in `defender.py` that accepts `request_text` and returns
   `True` for an attack, `False` otherwise. Register it in `AGENTS`.
2. Keep the request text as untrusted input to the model. Preserve the existing
   exception path: classifier failures block the request with HTTP 403.
   Do not turn an exception into an allow decision.
3. Let the proxy emit the existing request events. Adding a classifier does
   not require another file writer or duplicate decision events.

`any(...)` stops evaluation when a classifier detects an attack. The current
events describe the final proxy decision; they do not identify which
classifier triggered it or prove that every classifier ran. If attribution
is needed, add it deliberately to the decision flow and document the fields.

## Preserve the event contract

The proxy creates one `request_id` per incoming request. Reuse its
`event_fields` for every event belonging to that request.

| Path | Events | Proxy behavior |
| --- | --- | --- |
| Allowed | `request_decision`: `allowed`, `decision: allow`; then `request_result`: `returned`, with `http_status` | Forward and return the upstream response |
| Attack detected | `request_decision`: `blocked`, `decision: block` | Return 403 without forwarding |
| Classifier exception | `request_decision`: `error`, `decision: block`, with `error_type` | Return 403 without forwarding |
| Forwarding exception | `request_decision`: `allowed`; then `request_result`: `error`, with `error_type` | Preserve the existing exception/error response behavior |

Do not emit an upstream result for a request that was never forwarded.
`returned` means the upstream responded, including HTTP 4xx/5xx responses.
`blocked` describes the classifier decision, not a verified attack outcome.
The dashboard's blocked-request counter currently counts
`request_decision` events with `status: blocked`; classifier errors are separate.

## New functionality and log fields

- Call `log_event("action_name", **fields)` through the defender adapter.
  It supplies source, actor, IDs, UTC timestamps, and JSONL output.
- Include `request_id`, method, and path for request-related actions. Use a
  separate operation ID for background work without an incoming request.
- Log concise facts, not bodies, query strings, headers, cookies, credentials,
  model prompts/responses, or raw exception messages. Use `error_type`.
  Review any new path/metadata fields for sensitive values as well.
- Keep the existing decision/result events when changing proxy behavior.
  Add new event types only for distinct actions; document them in the
  [event format](../../../docs/event-format.md).
- The current Flask proxy is synchronous, so direct `log_event` calls fit its
  request flow. If adding async execution, use
  `await asyncio.to_thread(log_event, "action_name", **fields)` for file writes.
- New Python modules must also be copied into the container: the
  [Dockerfile](Dockerfile) currently names the application files explicitly.

## File output and delivery

Compose writes `/var/log/purpleai/events.jsonl` inside the container and
mounts it at `src/defender/logs/events.jsonl` on BlueAI. Direct Python runs
default to `logs/events.jsonl` beside the adapter. `PURPLEAI_LOG_FILE`
overrides the path.

Another classifier using the existing file needs no Vector changes.
A new host or log path needs its file included in that host's Vector config.
Preserve the log mount and shared-logger Docker build layout when changing
deployment. See [Vector setup](../../../deploy/vector/README.md).

## Verify before merging

1. From the repository root, run `uv run pytest -q`. Extend
   `tests/test_defender_logging.py` for changed behavior, using mocked
   classifiers/upstream requests rather than IDUN calls in unit tests.
2. Cover allowed, blocked, classifier-error, and upstream-error paths. Check
   event counts, matching `request_id`, no forwarding after a block, and no
   sensitive content in logs. Keep the concurrent-write and separate
   `Set-Cookie` header checks passing when changing logging or forwarding.
3. Rebuild the full Compose setup on BlueAI. Send a normal request and a lab
   attack request through port 8080. Inspect responses and events; a model's
   decision is not guaranteed detection accuracy.
4. Follow a real `event_id` from BlueAI's host file into gamehost's
   `/var/log/purpleai/collected/events-*.jsonl` and the dashboard. New counters
   or display fields require a corresponding dashboard change.
