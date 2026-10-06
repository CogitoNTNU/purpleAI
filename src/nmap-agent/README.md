# Nmap attacker agent

A LangChain/LangGraph agent that performs reconnaissance against the configured
PurpleAI target using one restricted `nmap_scan()` tool. In the two-PC sandbox,
model calls go through the local Idun gateway and scans target BlueAI port 8080.

Use the [sandbox guide](../../deploy/sandbox/README.md) for setup, network checks,
model changes, logs, and shutdown. Choose any Idun model using `AGENT_MODEL` in
this folder's `.env`. Docker overrides the target, port, API address and API key
with sandbox settings; the real Idun key stays in the gateway.

Use the [gamehost runner](../gamehost/README.md#run-an-experiment) for coordinated
runs with normal traffic and a shared run ID. For standalone use, follow
[manual testing](../../deploy/sandbox/TESTING.md).

## Files

| File               | Purpose                                                       |
| ------------------ | ------------------------------------------------------------- |
| `main.py`          | Predefined reconnaissance task and entry point                |
| `agent.py`         | Agent construction, workflow output, and model error messages |
| `config.py`        | Settings validation and trusted target selection              |
| `tools/nmap.py`    | Restricted Nmap tool and result parsing                       |
| `logging_utils.py` | Agent event fields passed to the shared sender                |
| `requirements.txt` | Dependencies installed by the sandbox Dockerfile              |
| `.env.example`     | Agent model setting and optional settings for direct use      |

## Tool and logs

`nmap_scan()` accepts no parameters. Trusted configuration supplies the target
and optional `NMAP_PORT`; the sandbox fixes the port to 8080, or 8081 when you select `--target direct`. Nmap runs with an
argument list and no shell. The agent cannot choose another scan target or
execute arbitrary commands through this tool.

Actions are printed as JSON events. Optional gamehost delivery uses
`LOG_COLLECTOR_URL` and `LOG_COLLECTOR_TOKEN` together; see the
[gamehost guide](../gamehost/README.md). In this sandbox, configure
`GAMEHOST_IP` and `LOG_COLLECTOR_TOKEN` in deployment `.env`; Compose supplies the
collector settings. The gamehost runner supplies a shared `PURPLEAI_RUN_ID`.

Both agents use `src/purpleai/event_logging.py`, copied into their Docker images,
for JSON event output and delivery. Startup diagnostics use Python `logging` at
`INFO`, errors at `ERROR`, and delivery failures at `WARNING` on stderr. The task,
tool results and final answer remain readable console output. Sending uses a
0.5-second timeout, with no queue or retries.
