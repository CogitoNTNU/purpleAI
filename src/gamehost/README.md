# Gamehost event collector

This small Python service receives PurpleAI events and immediately prints
each one to its terminal and appends it to `data/events.jsonl`. The first
sender is the nmap agent; the event envelope also supports later sources.
It uses only Python's standard library.

Every accepted event has `schema_version: 1`, a unique `event_id`, a
`run_id` shared by one agent run, a UTC `timestamp`, and `source`, `actor`,
and `action` strings. Sources can add fields such as `tool`, `target`, and
`status`. The collector accepts one JSON event per POST to `/events`.

On the gamehost (`192.168.0.110`), from the repository root:

```bash
cp src/gamehost/.env.example src/gamehost/.env
chmod 600 src/gamehost/.env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Paste the generated token into `GAMEHOST_LOG_TOKEN` in
`src/gamehost/.env`, then start the collector:

```bash
python3 src/gamehost/log_collector.py
```

The `.env` file is ignored by Git. Shell environment variables with the
same names take precedence over its values.

The collector listens on TCP port `8765` by default. Permit that port only
from the lab machines that send events. The terminal prints each received
event immediately; another terminal can follow the saved file with:

```bash
tail -f src/gamehost/data/events.jsonl
```

On the machine running the nmap agent, set these values in
`src/nmap-agent/.env` (or export them in the shell):

```env
LOG_COLLECTOR_URL=http://192.168.0.110:8765/events
LOG_COLLECTOR_TOKEN=the-same-shared-token
```

Run `python main.py` from `src/nmap-agent`. Check the collector terminal
for `task_start`, `tool_call`, `tool_result`, and `task_end` events.
The shared token is sent over HTTP, so keep this listener on the controlled
lab network. If traffic crosses an untrusted network, place it behind HTTPS.
The collector appends events without deduplicating them; the sender makes
one delivery attempt per event.
