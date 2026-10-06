# Run experiments from gamehost

Gamehost runs the log collector and normal-traffic containers. The host-side
runner coordinates RedAI and BlueAI over SSH. The collector only stores events;
it does not run commands.

For a new installation, follow [first-time setup](SETUP.md). SSH, Docker access
and passwordless sudo are configured there once. For an existing installation,
use the commands below. All blocks run from **`~/purpleAI`**, the repository root,
on the named PC. Replace that directory if your checkout is elsewhere.

## Run an experiment

**Gamehost — repository root:** first ensure the collector is running.
Use your normal management user for all gamehost commands.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml up -d --wait collector
```

The RedAI and BlueAI stacks must also be running. If stopped or updated,
[start and check them now](../../deploy/sandbox/README.md#start-or-rebuild-the-lab).
Already running stacks need no restart between experiments.

**Gamehost — repository root:** start one experiment. Do not use sudo.

```sh
cd ~/purpleAI
python3 src/gamehost/run.py
```

The runner:

1. Checks collector availability, both sandbox policies and event delivery.
1. Assigns a shared run ID and recreates the defender for that run.
1. Verifies a request through the defender, then starts normal browsing traffic.
1. Runs the Nmap attacker on RedAI against BlueAI port 8080.
1. Stops traffic and recreates the defender in a separate session at the end.

Normal traffic visits `/`, `/search`, `/product/1`, `/login` and `/register`, using
one user and sequential requests. The runner stops it when the attacker finishes.
Only one gamehost run may be active at a time. Avoid launching extra attackers
manually during a managed run.

`Finished: RUN_ID` and a `run_end` event with `status: success` mean the workflow
completed. Check defender events to assess decisions and model errors; a
successful workflow does not mean every request returned 200. The collector and
lab stacks stay running, and VulnShop data is preserved between experiments.

## View logs and save events

**Gamehost — repository root:** follow live collected events. Ctrl+C stops viewing
without stopping the collector.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml logs -f --tail 100 collector
```

**Gamehost — repository root:** export all saved events to a local JSONL file.

```sh
cd ~/purpleAI
mkdir -p src/gamehost/data
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml exec -T collector cat /data/events.jsonl > src/gamehost/data/events.jsonl
```

The shared `run_id` groups gamehost markers, attacker actions and defender
request decisions. Preflight `sandbox-check` events and the defender's separate
session after cleanup have their own IDs. Normal traffic is labelled `normal`;
other requests are labelled `other`.

Defender model failures have `status: model_error`, `http_status: 403`,
`error_type`, `model_http_status` and a safe `error_reason`. The model status is
null when there was no HTTP response. A 404 with `status: forwarded` is a target
response, often from an Nmap probe to an unknown path; it is not a model error.

Both agents print structured JSON and send it directly to the collector.
Diagnostics use Python `logging` on stderr. The attacker's readable transcript
and diagnostic messages stay in console output; they are not collector events.
Use the [sandbox log commands](../../deploy/sandbox/README.md#logs-shell-and-shutdown)
for stack diagnostics. Attacker run containers are removed after completion.

Delivery is best effort with a 0.5-second send timeout, no queue and no retries.
Missing events are not replayed. Raw exception messages, request/response bodies
and API keys are not included in structured events. Agent events and traffic tags
are observations, not proof of attack success.

Saved events live in the collector's Docker volume and survive container
recreation and shutdown. The JSONL file grows until archived or cleared;
Docker's separate console logs rotate automatically.

## Update code or models

Update all three checkouts to the same code version between experiments.
For agent, gateway, target or sandbox changes,
[stop/start both lab stacks](../../deploy/sandbox/README.md#start-or-rebuild-the-lab).
This rebuilds their images; stopping BlueAI clears temporary target data.

The gamehost runner reads its Python source on each invocation. If collector code
or its Compose configuration changed, rebuild it too. **Gamehost — repository root:**

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml up --build -d --wait collector
```

For model-only changes, edit each agent's `AGENT_MODEL` as described in the
[sandbox guide](../../deploy/sandbox/README.md#change-a-model-without-rebuilding).
The next managed run reads both agents' updated model settings. Existing SSH and
sudo permissions do not need to be reapplied after code updates or reboots.

## If a check fails

Each line identifies the origin, for example:

```text
PASS [BlueAI / defender] model-gateway:9000: reachable
PASS [BlueAI / vulnerable-app] 192.168.0.110:8765: unreachable
```

`PASS ... unreachable` means an intended restriction held. `FAIL` stops the run;
the Python traceback reports that failed check.

| Symptom                                              | What to check                                                                                                                                                            |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Both agents cannot reach gamehost port 8765          | Start the collector using the first command block above. Check its health as shown below.                                                                                |
| Collector reachable but authenticated event rejected | `LOG_COLLECTOR_TOKEN` on both PCs must match gamehost's `GAMEHOST_LOG_TOKEN`. After changing deployment settings, stop/start both lab stacks.                            |
| SSH alias works manually but fails in the runner     | Run `python3 src/gamehost/run.py` as the normal gamehost user, without sudo. Check `RED_SSH` and `BLUE_SSH` in its `.env`.                                               |
| `sudo: a password is required`                       | Check the account and absolute script path in the [one-time sudo rules](SETUP.md#passwordless-sudo-on-the-lab-pcs). No restart is required.                              |
| Defender returns 403 with `status: model_error`      | Read `error_reason` and `model_http_status` in the saved event. `Gateway busy` means the 10-second wait expired; `Run call budget exhausted` requires a gateway restart. |

**Gamehost — repository root:** inspect collector state and health. Replace the
address if `GAMEHOST_LOG_BIND` differs.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml ps collector
curl --max-time 5 http://192.168.0.110:8765/health
```

Health should return `ok`. If not, inspect collector logs with the command above.
If health succeeds but agents still cannot connect, check addresses and host
firewall rules; the agent token is not used by a TCP reachability test.

## Stop and recover

After a normal run, cleanup is automatic. After a killed runner or lost SSH
connection, check for remaining traffic and attacker containers.

**Gamehost — repository root:** list traffic containers and stop the one matching
the interrupted run. Replace `RUN_ID` with the ID printed by that run.

```sh
cd ~/purpleAI
docker ps --filter name=purpleai-traffic --format '{{.Names}}'
docker stop purpleai-traffic-RUN_ID
```

**RedAI — repository root:** cancel remaining managed attackers.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red cancel
```

**BlueAI — repository root:** restore a separate defender session while preserving
target data.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue session
```

**Gamehost — repository root:** stop its Compose stack while preserving saved
events. Stop any one-off traffic container using the block above first.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml down
```

Stop the lab stacks separately using the
[sandbox shutdown commands](../../deploy/sandbox/README.md#logs-shell-and-shutdown).
Do not add `--volumes` to gamehost shutdown unless you intend to delete saved logs.
