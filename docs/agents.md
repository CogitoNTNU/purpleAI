# Integrate an agent with the sandbox

This guide describes what the sandbox expects from an agent and how to deploy it.
It applies to a single agent or a coordinator with subagents in the same container.
Gamehost launches the selected implementation without needing to know its internals.

For initial host configuration, use [first-time setup](../src/gamehost/SETUP.md).
If upgrading from the old Nmap folder, follow the [migration](#upgrade-an-existing-lab).
Commands below run from **`~/purpleAI`**, the repository root on the named PC;
replace that path if needed.

## Files and entry points

| Role     | Put code in                    | Select in that folder's `.env`            | Dependencies                                 |
| -------- | ------------------------------ | ----------------------------------------- | -------------------------------------------- |
| Attacker | `src/attacker/`                | `ATTACKER_MODULE=agents.my_workflow.main` | `requirements.txt` and `system-packages.txt` |
| Defender | `src/defender/defender-agent/` | `DEFENDER_APP=my_proxy:app`               | `requirements.txt`                           |

The attacker entry point must be a runnable Python module. The defender entry
point must export a WSGI application; the runtime serves it with Gunicorn on
port 8080. The supplied examples are `agents.nmap.main` and `defender:app`.
Both images copy the whole role folder. Adding modules or Python dependencies
within it requires no Dockerfile changes. Attacker system tools are Debian
package names, one per line in `system-packages.txt`.

Keep model/task settings in the role's `.env`, including `AGENT_MODEL` if your
implementation uses it. Subagents may choose different Idun models per call.
`.env` files and secrets are excluded from the images; Compose injects settings
at launch. Exported sandbox settings take precedence over the role's `.env`.

## Settings the sandbox supplies

Read these from the process environment:

| Setting                                    | What the agent should use it for                                                          |
| ------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `TARGET_URL`, `TARGET_PORT`                | Attacker destination: port 8080 through the defender, or 8081 directly to VulnShop        |
| `TARGET`                                   | Defender's backend URL for forwarding accepted requests                                   |
| `IDUN_BASE_URL`, `IDUN_API_KEY`            | Model API endpoint and credential: the local gateway and its token, not the real Idun key |
| `PURPLEAI_RUN_ID`, `PURPLEAI_TARGET_MODE`  | Shared run ID and event label; preserve them in subagents                                 |
| `LOG_COLLECTOR_URL`, `LOG_COLLECTOR_TOKEN` | Optional event delivery address and credential                                            |

Use the injected target rather than hardcoding an IP or port. The target mode
labels logs; it does not select the destination. Clients must support
non-streaming `/v1/chat/completions`, including tool calls. Model calls share the
[gateway's limits](../deploy/sandbox/README.md#isolation-and-limits) on that PC.

For events, use `EventSender` from `purpleai.event_logging`, which is included in
both images. Give each agent/subagent a distinct `source` and pass the collector
URL and token to the sender. It generates event IDs and timestamps and reads the
run ID and mode automatically. Follow the [event format](event-format.md) for
fields and actions. Use Python `logging` for diagnostics; exclude API keys and
raw request/response bodies from events.

## Runtime and network boundaries

- The attacker may contact the selected BlueAI endpoint, its gateway and the
  configured collector. The defender may contact its backend, gateway and collector.
- Processes run as non-root in a read-only image. Write temporary files to
  `/workspace` or `/tmp`; install packages during image build.
- Subagents in one container share its workspace, permissions and resource limits.
  They do not gain separate network access.
- An attacker should exit 0 on completion and nonzero on failure, and stop its
  child processes when interrupted. Gamehost uses that exit status to record the run.
- A defender must forward accepted requests to `TARGET` and define its blocking
  and error behavior. The supplied proxy blocks with 403 when model checks fail.

New network destinations, ports, containers or privileges require a sandbox
policy change and corresponding isolation checks. Updating logic, selecting
models or adding tools that work within these boundaries does not. A defender
that patches target files or manages containers needs extra integration: the
current sandbox provides neither the target filesystem nor the Docker socket.

## Apply changes and verify

Update the checkouts to the same code version, then apply the affected change:

| Change                               | Apply it                                                                                                                                     |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Attacker `.env` only                 | The next attacker run reads it                                                                                                               |
| Defender `.env` only                 | [Recreate the defender](../deploy/sandbox/README.md#change-agent-settings-without-rebuilding); the next defended gamehost run also does this |
| Source, dependencies or system tools | [Rebuild and check the affected PC](../deploy/sandbox/README.md#start-or-rebuild-the-lab)                                                    |

Rebuilding BlueAI clears temporary target data. Finish active runs first.

For a basic integration check, select `ATTACKER_MODULE=agents.smoke` in RedAI's
`src/attacker/.env`. It makes one HTTP request and one model call, then emits
completion events. Run it using [gamehost](../src/gamehost/README.md) or the
[manual run commands](../deploy/sandbox/TESTING.md#tools-or-the-agent-inside-the-redai-sandbox).
Restore your intended entry point afterwards.

Verify these before using the updated agent in experiments:

1. Every sandbox network check passes.
1. The selected agent starts, reaches its target and can call the model.
1. If collecting events, they arrive under the printed run ID and correct mode file.
   A successful agent exit alone does not prove delivery.
1. Failures produce useful events/diagnostics, and interrupted runs leave no child processes.
1. An updated defender forwards a benign request, blocks a known test attack and
   handles a model failure according to its documented behavior.

## Upgrade an existing lab

Do this once after pulling the move from `src/nmap-agent/` to `src/attacker/`.
Existing gateway keys, deployment settings and sudo rules stay valid.

**RedAI — repository root:** preserve the old settings if the new file does not exist.

```sh
cd ~/purpleAI
cp -n src/nmap-agent/.env src/attacker/.env
nano src/attacker/.env
chmod 600 src/attacker/.env
```

Add `ATTACKER_MODULE=agents.nmap.main` and keep `AGENT_MODEL`. Remove `NMAP_PORT`;
the workflow now reads its port from the injected `TARGET_URL`. The old `.env`
is no longer used; remove it after the migrated setup works.

**BlueAI — repository root:** update its existing agent settings.

```sh
cd ~/purpleAI
nano src/defender/defender-agent/.env
```

Add `DEFENDER_APP=defender:app` and keep `AGENT_MODEL`. For native defender runs,
rename any old `IDUNN_` settings to `IDUN_BASE_URL` and `IDUN_API_KEY`.
Then [rebuild and check both PCs](../deploy/sandbox/README.md#start-or-rebuild-the-lab).
No gamehost `.env` changes are needed.
