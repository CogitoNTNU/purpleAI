# PurpleAI event log format

All PurpleAI agents log every action as one JSON event. Events are printed
to the agent's console and POSTed to the gamehost collector, which appends
them to a shared JSON Lines file. This page is the reference for anyone
writing a new agent or reading the collected logs.

## Envelope

Every event is a single JSON object with these fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | integer | yes | Always `1`. Bump only for breaking changes. |
| `event_id` | string | yes | UUID v4 string, unique per event. |
| `run_id` | string | yes | UUID v4 string shared by all events from one agent run. |
| `timestamp` | string | yes | ISO 8601 in UTC (offset must be `+00:00`/`Z`), e.g. `2026-10-01T12:34:56.789+00:00`. |
| `source` | string | yes | Name of the sending agent, e.g. `nmap-agent`. One word, hyphens allowed. |
| `actor` | string | yes | Who acted, e.g. `attacker`, `defender`, `analyst`. |
| `action` | string | yes | What happened, e.g. `task_start`, `tool_call`. |
| `tool` | string | no | Tool used, e.g. `nmap`. Omit when not applicable. |
| `target` | string | no | Target of the action, e.g. `192.168.50.10:8080`. Omit when not applicable. |
| `status` | string | no | Outcome, e.g. `started`, `success`, `failure`. Omit while unknown. |

Rules:

- Omit optional fields rather than sending `null` or empty strings.
- Do not add top-level fields with other names; put source-specific detail
  inside `tool`, `target`, or `status`.
- One event per action. The collector does not deduplicate, so never retry
  a delivery that already succeeded.

## Standard actions

Use this vocabulary so logs are comparable across agents:

| Action | Meaning | Typical fields |
|---|---|---|
| `task_start` | Agent run begins | `status: started` |
| `task_end` | Agent run ends | `status: success` or `failure` |
| `tool_call` | Agent invokes a tool | `tool`, `target` |
| `tool_result` | Tool returned output | `tool`, `target`, `status` |

New actions are fine when the existing ones do not fit; keep them
snake_case and descriptive.

## Example

```json
{"schema_version": 1, "event_id": "0b8df5e2-9f4a-4f6f-8b1e-2f3d5a6b7c8d", "run_id": "e1a2b3c4-5d6e-4f70-8a9b-0c1d2e3f4a5b", "timestamp": "2026-10-01T12:34:56.789+00:00", "source": "nmap-agent", "actor": "attacker", "action": "tool_call", "tool": "nmap", "target": "192.168.50.10:8080"}
```

## Delivery to the gamehost collector

One event per HTTP request:

- `POST /events` on TCP port `8765` (default)
- `Content-Type: application/json`
- `Authorization: Bearer <GAMEHOST_LOG_TOKEN>` (shared token from the
  gamehost's `src/gamehost/.env`)
- Body: exactly one event, at most 16 KiB
- Responses: `202` accepted, `401` bad token, `422` invalid envelope,
  `413` too large

`GET /health` returns `ok` for connectivity checks. Delivery failures must
not stop the agent; log to the console and continue.

## Collector-side validation

The collector (`src/gamehost/log_collector.py`) rejects events that:

- have `schema_version` other than `1`
- have an `event_id` or `run_id` that is not a valid UUID
- have a missing, empty, or non-string `timestamp`, `source`, `actor`, or
  `action`
- have a `timestamp` that is not ISO 8601 or is not UTC

Optional fields are not validated beyond the size limit, so new agents can
start sending events without collector changes.
