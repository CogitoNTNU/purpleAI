# Add or update agents

The sandbox launches the implementation selected in each role's `.env`.
Gamehost uses the same run commands for every implementation. A selected
workflow can coordinate several agents and subagents inside its container.

| Role     | Source folder                  | Entry point in that folder's `.env`                |
| -------- | ------------------------------ | -------------------------------------------------- |
| Attacker | `src/attacker/`                | `ATTACKER_MODULE=agents.nmap.main` (Python module) |
| Defender | `src/defender/defender-agent/` | `DEFENDER_APP=defender:app` (WSGI application)     |

Use [first-time setup](../src/gamehost/SETUP.md) for a new lab. For an existing
installation using the old Nmap folder, complete the [migration below](#upgrade-an-existing-lab) once.
All host command blocks start from `~/purpleAI` on the named PC; replace that path if needed.

## Add an attacker workflow

Put your code under `src/attacker/agents/`, for example:

```text
src/attacker/agents/my_workflow/
  __init__.py
  main.py
  tools.py
```

`main.py` must run the workflow when invoked as a Python module. It may launch
subagents, use another framework or call tools. Use relative imports inside the
package, such as `from .tools import scan`.

**RedAI — repository root:** select it in the role's `.env`.

```sh
cd ~/purpleAI
nano src/attacker/.env
```

Set `ATTACKER_MODULE=agents.my_workflow.main`. Keep `AGENT_MODEL` or add the
model/task settings your workflow needs to that same file. Each subagent can
select a different model when calling the shared gateway.

Add Python dependencies to `src/attacker/requirements.txt`. Add system tools to
`src/attacker/system-packages.txt`, one Debian package name per line; empty lines
and full-line comments are accepted. Both lists serve every workflow in this role.
The image includes the whole role folder, so new modules need no Dockerfile edits.

## Update or replace the defender

Put source files and modules under `src/defender/defender-agent/` and Python
dependencies in its `requirements.txt`. This folder is also copied in full.

You can extend the current proxy's `AGENTS` list, or supply another WSGI HTTP
application. For example, a file `my_proxy.py` exporting `app` is selected with
`DEFENDER_APP=my_proxy:app` in the defender's `.env`. The runtime serves it with
Gunicorn on port 8080. It may coordinate multiple detection agents internally.

Preserve forwarding to the injected `TARGET`, defined error/blocking behavior,
and request-decision events. The supplied proxy returns 403 when model checks
fail. Its [README](../src/defender/defender-agent/README.md) describes that behavior.

A defender that patches VulnShop's code or administers containers needs additional
integration: the current defender has neither target filesystem access nor Docker access.

## Settings and events your implementation should use

| Setting                                    | Meaning                                                                                                  |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| `TARGET_URL`                               | Attacker's selected target URL: port 8080 with the defender or 8081 without it                           |
| `TARGET_PORT`                              | Selected port for command-line tools in the attacker container; native workflows can read the URL's port |
| `TARGET`                                   | Defender's backend URL                                                                                   |
| `IDUN_BASE_URL`, `IDUN_API_KEY`            | Model API address and credential; in Docker these point to the local gateway and use its token           |
| `PURPLEAI_RUN_ID`                          | Shared run/session ID; pass it unchanged to subagents                                                    |
| `PURPLEAI_TARGET_MODE`                     | Log label supplied by the sandbox; does not select the target                                            |
| `LOG_COLLECTOR_URL`, `LOG_COLLECTOR_TOKEN` | Optional event delivery settings                                                                         |

Use `EventSender` from `purpleai.event_logging`, choosing a distinct `source`
for each agent/subagent. It reads the run ID and target mode automatically.
Child processes inherit those settings unless you replace their environment.
See [event format](event-format.md) for fields and [shared logging](../src/purpleai/README.md)
for delivery behavior. Do not put keys or raw request/response bodies in events.

The attacker should exit 0 when its workflow completes and nonzero on failure.
Set tool timeouts and agent step limits appropriate to its tasks, and clean up
subagents when stopping. A completed workflow is not proof that an attack succeeded.

Keep temporary work in `/workspace` or `/tmp`. Install tools during image build;
the running agent cannot install system packages or write the image filesystem.
All subagents in a container share its permissions, workspace and resource limits.

The gateway supports non-streaming `/v1/chat/completions`, including tool calls,
with a 2048-token output cap. Framework clients must use that interface. Parallel
model calls currently share one gateway slot per PC; see [gateway limits](../deploy/sandbox/README.md#isolation-and-limits).

## Apply changes and verify

| Change                                                    | How to apply                                                                             |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Attacker entry point/model/task settings in its `.env`    | Next attacker run reads them                                                             |
| Defender entry point/model settings in its `.env`         | Recreate the defender with `blue session`; the next defended gamehost run also does this |
| Source, Python dependencies or system tools               | Rebuild the affected PC using the blocks below                                           |
| New network destinations, ports, containers or privileges | Review the sandbox policy and extend its isolation tests before running                  |

Use the same code version on all PCs. Finish active experiments before rebuilding.
Start the collector first if configured. **BlueAI — repository root, when its code changed:**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue stop
sudo python3 deploy/sandbox/start.py blue start
sudo python3 deploy/sandbox/start.py blue check
```

Stopping BlueAI clears temporary VulnShop data. **RedAI — repository root, when its code changed:**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red stop
sudo python3 deploy/sandbox/start.py red start
sudo python3 deploy/sandbox/start.py red check
```

For a defender setting change only, preserve target data with this command.
**BlueAI — repository root:**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue session
```

Every network check should pass. For standalone testing with a stopped collector,
use `--no-collector` on the check commands; isolation checks still run.

A reusable integration check is included as `ATTACKER_MODULE=agents.smoke`.
Select it in RedAI's `src/attacker/.env`, then run a gamehost experiment using the
[run guide](../src/gamehost/README.md). It makes one target HTTP request and one
model call and emits events. Check that its events reached the collector, then
restore your intended workflow. Delivery is best effort; a successful smoke
workflow alone does not confirm collector delivery.

Test your actual workflow [without the defender](../src/gamehost/README.md#run-without-the-defender)
first, then with it. Verify its events share the printed run ID and use the
correct mode file. Test model/tool failures and interrupted runs too. A new
defender should forward a benign request, block a known test attack and handle
model failure as documented.

**Development PC — repository root:** run the regression and runtime integration tests.
Use the configured repository development environment.

```sh
cd ~/purpleAI
uv run pytest -q
```

These tests cover entry-point selection, subagent event delivery, failure exits,
gateway behavior and policy rules. Live network checks on the physical PCs are
still needed after deployment. See [manual testing](../deploy/sandbox/TESTING.md)
for native tools or agents on your own PC.

## Upgrade an existing lab

Do this once after updating the checkouts. The sandbox entry-point path and
sudo rules are unchanged. Preserve existing tokens and keys.

**RedAI — repository root:** copy the old settings if the new file does not exist.

```sh
cd ~/purpleAI
cp -n src/nmap-agent/.env src/attacker/.env
nano src/attacker/.env
chmod 600 src/attacker/.env
```

Add `ATTACKER_MODULE=agents.nmap.main` and keep your existing `AGENT_MODEL`.
`NMAP_PORT` is no longer used; the example reads its port from `TARGET_URL`.
Docker supplies that URL automatically. The old `.env` is no longer read by the
sandbox; keep it until the migrated setup works, then remove it if no longer needed.

**BlueAI — repository root:** update its existing agent settings.

```sh
cd ~/purpleAI
nano src/defender/defender-agent/.env
```

Add `DEFENDER_APP=defender:app` and keep `AGENT_MODEL`. Docker now supplies
`IDUN_BASE_URL` and `IDUN_API_KEY` consistently for both roles. Native defender
settings using the old `IDUNN_` names must use these names too.

Rebuild and check both PCs using [apply changes](#apply-changes-and-verify) above.
No gamehost `.env` or deployment `.env` changes are required for this migration.
Gamehost runs launch the configured workflow automatically.
