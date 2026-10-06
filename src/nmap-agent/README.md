# Nmap attacker agent

A LangChain/LangGraph agent that performs reconnaissance against the configured
PurpleAI target using one restricted `nmap_scan()` tool. In the two-PC sandbox,
model calls go through the local Idun gateway and scans target BlueAI port 8080.

Use the [sandbox guide](../../deploy/sandbox/README.md) for setup, network checks,
model changes, logs, and shutdown. Choose any Idun model using `AGENT_MODEL` in
this folder's `.env`. Docker overrides the target, port, API address and API key
with sandbox settings; the real Idun key stays in the gateway.

**RedAI — repository root (`~/purpleAI`):** run the attacker after the gateway is
started and both PCs pass their connection checks. Replace `~/purpleAI` if your
checkout is elsewhere.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red run
```

## Files

| File               | Purpose                                                       |
| ------------------ | ------------------------------------------------------------- |
| `main.py`          | Predefined reconnaissance task and entry point                |
| `agent.py`         | Agent construction, workflow output, and model error messages |
| `config.py`        | Settings validation and trusted target selection              |
| `tools/nmap.py`    | Restricted Nmap tool and result parsing                       |
| `logging_utils.py` | Structured console events and optional gamehost delivery      |
| `requirements.txt` | Dependencies installed by the sandbox Dockerfile              |
| `.env.example`     | Agent model setting and optional settings for direct use      |

## Tool and logs

`nmap_scan()` accepts no parameters. Trusted configuration supplies the target
and optional `NMAP_PORT`; the sandbox fixes the port to 8080. Nmap runs with an
argument list and no shell. The agent cannot choose another scan target or
execute arbitrary commands through this tool.

Actions are printed as JSON events. Optional gamehost delivery uses
`LOG_COLLECTOR_URL` and `LOG_COLLECTOR_TOKEN` together; see the
[gamehost guide](../gamehost/README.md). Leave them unset in this sandbox, whose
firewall does not permit collector connections.
