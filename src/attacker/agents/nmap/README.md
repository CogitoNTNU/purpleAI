# Nmap example workflow

This LangChain/LangGraph example uses a restricted `nmap_scan()` tool. Select it
with `ATTACKER_MODULE=agents.nmap.main` in `src/attacker/.env`.

Use the [attacker runtime guide](../../README.md) for deployment and configuration,
or [manual testing](../../../../deploy/sandbox/TESTING.md#run-an-attacker-workflow-on-your-pc)
to run it on your own PC.

The scan host and port come from `TARGET_URL`. The tool accepts no model-supplied
arguments and invokes Nmap without a shell. It scans that port only; its output
does not establish which other services the host exposes.

| File               | Purpose                                      |
| ------------------ | -------------------------------------------- |
| `main.py`          | Reconnaissance task and workflow entry point |
| `agent.py`         | Model/tool orchestration and readable output |
| `config.py`        | Workflow settings and target validation      |
| `tools/nmap.py`    | Nmap execution and XML result parsing        |
| `logging_utils.py` | Workflow events using the shared sender      |

Dependencies and system tools are listed at the attacker role root. Events use
source `nmap-agent`; diagnostics and the readable transcript remain console output.
