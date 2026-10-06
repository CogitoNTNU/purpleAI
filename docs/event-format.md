# PurpleAI event log format

Agents print structured events for tasks, tool calls and defender decisions.
When collector delivery is configured, they also POST each event to gamehost.
The collector saves one JSON object per line, with separate files for runs
with and without the defender. Diagnostic messages use Python `logging` on
stderr and are not collected as events.

Use the [gamehost guide](../src/gamehost/README.md#view-logs-and-save-events) to
view or export logs. This page describes the fields for reading events or adding
a new agent.

## Envelope

Every event is a single JSON object with these fields:

| Field            | Type    | Required | Description                                                                                                                    |
| ---------------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `schema_version` | integer | yes      | Always `1`. Bump only for breaking changes.                                                                                    |
| `event_id`       | string  | yes      | UUID string, unique per event; the sender generates UUID v4.                                                                   |
| `run_id`         | string  | yes      | UUID string grouping events for one run or session. Gamehost supplies one ID to both agents for a defended run.                |
| `timestamp`      | string  | yes      | ISO 8601 in UTC (offset must be `+00:00`/`Z`), e.g. `2026-10-01T12:34:56.789+00:00`.                                           |
| `source`         | string  | yes      | Sending component, e.g. `nmap-agent`, `defender` or `gamehost`.                                                                |
| `actor`          | string  | yes      | Who acted, e.g. `attacker`, `defender`, `analyst`.                                                                             |
| `action`         | string  | yes      | What happened, e.g. `task_start`, `tool_call`.                                                                                 |
| `target_mode`    | string  | no       | `with_defender` or `without_defender`. Current senders include it; missing values default to `with_defender` in the collector. |
| `tool`           | string  | no       | Tool used, e.g. `nmap_scan`. Omit when not applicable.                                                                         |
| `target`         | string  | no       | Target of the action, e.g. `192.168.0.120`. Omit when not applicable.                                                          |
| `status`         | string  | no       | Outcome, e.g. `started`, `success`, `failure`. Omit while unknown.                                                             |

Rules:

- Omit fields that do not apply. For model errors, `model_http_status` is
  explicitly `null` when there was no HTTP response.
- Add source-specific fields at the top level, such as `method`, `path`,
  `http_status` or `error_reason`. Do not include API keys or raw request/response
  bodies. Keep field names consistent between sources.
- One event per action. The collector does not deduplicate, so never retry
  a delivery that already succeeded.

## Standard actions

Use this vocabulary so logs are comparable across agents:

| Action                          | Meaning                                                   | Typical fields                                       |
| ------------------------------- | --------------------------------------------------------- | ---------------------------------------------------- |
| `task_start`                    | Agent run begins                                          | `status: started`                                    |
| `task_end`                      | Agent run ends                                            | `status: success` or `failure`                       |
| `tool_call`                     | Agent invokes a tool                                      | `tool`, `target`                                     |
| `tool_result`                   | Tool returned output                                      | `tool`, `target`, `status`                           |
| `session_start`                 | Defender session begins                                   | `model`                                              |
| `request_decision`              | Defender blocks or forwards an HTTP request               | `method`, `path`, `traffic`, `status`, `http_status` |
| `run_start` / `run_end`         | Gamehost run begins or ends                               | `status`, `target_mode`                              |
| `traffic_start` / `traffic_end` | Gamehost starts or stops normal traffic in a defended run | `status`                                             |
| `log_check`                     | Sandbox preflight verifies collector delivery             | Separate check `run_id`                              |

New actions are fine when the existing ones do not fit; keep them
snake_case and descriptive.

For `request_decision`, `status` is `forwarded`, `blocked`, `model_error` or
`target_error`. `http_status` is the response sent to the client. A model error
also includes `error_type`, `model_http_status` and a safe `error_reason`.
`model_http_status` describes the agent's model API response (the local gateway
in sandbox runs), not necessarily Idun's upstream status. `traffic: normal`
means the request carried the normal-traffic tag; other requests use `other`.

## Example

```json
{
  "schema_version": 1,
  "event_id": "0b8df5e2-9f4a-4f6f-8b1e-2f3d5a6b7c8d",
  "run_id": "e1a2b3c4-5d6e-4f70-8a9b-0c1d2e3f4a5b",
  "timestamp": "2026-10-01T12:34:56.789+00:00",
  "source": "nmap-agent",
  "actor": "attacker",
  "action": "tool_call",
  "target_mode": "without_defender",
  "tool": "nmap_scan",
  "target": "192.168.0.120",
  "status": "started"
}
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
- include a `target_mode` other than `with_defender` or `without_defender`

Other source-specific fields are not validated beyond the size limit, so new
agents can add fields without collector changes.

## Delivery and storage

The shared sender attempts delivery once, with a 0.5-second timeout and no queue
or retries. Failures warn once per agent process; events still print locally.
The collector does not replay missed events or deduplicate repeated deliveries.

In Docker, the collector writes defended events to `/data/with-defender.jsonl`
and bypass events to `/data/without-defender.jsonl`. Only defended events are
also printed in the collector's console log. The volume survives container
recreation and ordinary shutdown.

The sandbox sets `PURPLEAI_TARGET_MODE` automatically. Native agent runs may set
it to label their events; it does not select the target or enable access.
