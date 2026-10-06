# Nmap attacker agent

A LangChain/LangGraph agent that performs reconnaissance against the configured
PurpleAI target using one restricted `nmap_scan()` tool. In the two-PC sandbox,
model calls go through the local Idun gateway and scans target BlueAI port 8080
by default, or optional port 8081 without defender checks.

Use the [sandbox guide](../../deploy/sandbox/README.md) for setup, network checks,
model changes, logs, and shutdown. Choose any Idun model using `AGENT_MODEL` in
this folder's `.env`. Docker overrides the target, port, API address and API key
with sandbox settings; the real Idun key stays in the gateway.

Use the [gamehost runner](../gamehost/README.md#run-an-experiment) for coordinated
runs with a shared run ID, with normal traffic in defended mode. Use
`--without-defender` on gamehost for an attacker-only run against 8081 with
separate logs. For standalone use, follow
[manual testing](../../deploy/sandbox/TESTING.md), including running the agent
[from your own PC](../../deploy/sandbox/TESTING.md#run-the-existing-nmap-agent-on-your-pc).

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
and optional `NMAP_PORT`; the sandbox fixes the port to 8080 (through the defender),
or 8081 (without the defender) when you select `--target direct`. Nmap runs with an
argument list and no shell. The agent cannot choose another scan target or
execute arbitrary commands through this tool.
In the sandbox, this is a scan of the selected port only; it does not establish
which other services the host exposes.

Actions are printed as JSON events. Optional gamehost delivery uses
`LOG_COLLECTOR_URL` and `LOG_COLLECTOR_TOKEN` together; see the
[gamehost guide](../gamehost/README.md). In this sandbox, configure
`GAMEHOST_IP` and `LOG_COLLECTOR_TOKEN` in deployment `.env`; Compose supplies the
collector settings. The gamehost runner supplies a shared `PURPLEAI_RUN_ID`.
The sandbox sets `PURPLEAI_TARGET_MODE` automatically for log separation.
For native runs, it is optional metadata and does not change the target.

The task, tool results and final answer remain readable console output.
Diagnostics use Python `logging` on stderr. JSON events use the
[shared sender](../purpleai/README.md), with a 0.5-second delivery timeout and
no queue or retries.
