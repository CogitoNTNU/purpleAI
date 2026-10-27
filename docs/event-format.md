# PurpleAI event log format

The attacker and defender use `src/purpleai_logging.py` to print each event
and append it to a local JSON Lines file. Host Vector agents tail these
files and forward events to gamehost Vector, which writes daily JSONL
archives. This page describes the shared event format.

## Envelope

Every event is a single JSON object with these fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | integer | yes | Always `1`. Bump only for breaking changes. |
| `event_id` | string | yes | UUID v4 string, unique per event. |
| `run_id` | string | yes | UUID v4 string shared by all events from one agent run. |
| `timestamp` | string | yes | ISO 8601 in UTC (offset must be `+00:00`/`Z`), e.g. `2026-10-01T12:34:56.789+00:00`. |
| `source` | string | yes | Name of the sending agent, e.g. `attacker-agent`. One word, hyphens allowed. |
| `actor` | string | yes | Who acted, e.g. `attacker`, `defender`, `analyst`. |
| `action` | string | yes | What happened, e.g. `task_start`, `tool_call`. |
| `tool` | string | no | Tool used, e.g. `nmap`. Omit when not applicable. |
| `target` | string | no | Target of the action, e.g. `192.168.50.10:8080`. Omit when not applicable. |
| `status` | string | no | Outcome, e.g. `started`, `success`, `failure`. Omit while unknown. |

Rules:

- Omit optional fields rather than sending `null` or empty strings.
- Source-specific fields may be added alongside the envelope. Defender
  events include `request_id`, `method`, `path`, `decision`, `http_status`,
  and `error_type` when applicable.
- The shared logger supplies the envelope; agent fields cannot override it.
- Vector can retry delivery. Consumers should use `event_id` to identify
  duplicates in the archive.

## Standard actions

Use this vocabulary so logs are comparable across agents:

| Action | Meaning | Typical fields |
|---|---|---|
| `task_start` | Agent run begins | `status: started` |
| `task_end` | Agent run ends | `status: stopped`, `error`, or `cancelled` for the autonomous attacker |
| `tool_call` | Agent invokes a tool | `tool`, `target` |
| `tool_result` | Tool returned output | `tool`, `target`, `status` |
| `request_decision` | Defender allows or blocks a request | `request_id`, `decision`, `status` |
| `request_result` | Upstream response or forwarding error | `request_id`, `http_status` or `error_type`, `status` |
| `iteration_start`, `iteration_end` | One autonomous Boss turn | `iteration`, `operation_id`, `duration_ms` on end |
| `agent_tool_call`, `agent_tool_result` | Boss framework tool/delegation activity | `tool`, `tool_call_id`, `task_id` when supplied |
| `subagent_status` | Remote execution task state | `task_id`, `subagent`, `remote_run_id`, `status` |

The attacker runs until interrupted: `task_end` normally has `status: stopped`.
Unexpected exceptions use `error`; cancellation propagated out of a span uses
`cancelled`. Actual tool calls/results share a `tool_call_id` and carry
`task_id` when run by the execution server. The server's task ID connects
these events to the Boss's `subagent_status` events across process-local
`run_id` values. Tool results add `duration_ms`, `exit_code` when available,
and `error_type` for exceptions. Tool `completed` and subagent `success`
describe execution, not confirmed exploitation. The dashboard counts tool
calls/errors and defender block decisions, not inferred attack success.

New actions are fine when the existing ones do not fit; keep them
snake_case and descriptive.

## Example

```json
{"schema_version": 1, "event_id": "0b8df5e2-9f4a-4f6f-8b1e-2f3d5a6b7c8d", "run_id": "e1a2b3c4-5d6e-4f70-8a9b-0c1d2e3f4a5b", "timestamp": "2026-10-01T12:34:56.789+00:00", "source": "attacker-agent", "actor": "attacker", "action": "tool_call", "tool": "sqlmap", "target": "192.168.50.10:8080"}
```

## File output and delivery

Both agents use `log_event("action", status="...", **fields)`. Their small
logging adapters configure the source, actor, and default file path; the
shared logger handles serialization, IDs, UTC timestamps, and file output
through Python's `WatchedFileHandler`.

Host Vector reads the JSONL file, parses the JSON, and preserves the event
fields while adding the sending `host`, `file`, and `source_type`. The
gamehost receives Vector transport on TCP 6000 and archives events at
`/var/log/purpleai/collected/events-%Y-%m-%d.jsonl`.

The Vector pipeline parses JSON objects; it does not validate every
envelope field. The shared logger supplies the standard envelope.
File errors are reported without stopping the agent. Host Vector handles
delivery retries and buffering separately from application execution.

See `deploy/vector/README.md` in the repository for host
configuration, permissions, buffering, and retention.
