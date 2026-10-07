# Run experiments from gamehost

Gamehost launches the configured attacker on RedAI over SSH and coordinates
BlueAI. Its collector container stores events; defended runs also use a normal
traffic container. The Python runner operates on the host.

For a new lab, complete [first-time setup](SETUP.md) once. For individual tools
or scripts, use [manual testing](../../deploy/sandbox/TESTING.md).
All commands below run from **`~/purpleAI`**, the repository root on the named PC.
Replace that path if needed. Run gamehost commands as your normal management
user, **without sudo**, so they use your SSH keys and aliases.

## Run an experiment

**Gamehost — repository root:** start the collector if needed.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml up -d --wait collector
```

Both lab stacks must be running. [Start or rebuild them](../../deploy/sandbox/README.md#start-or-rebuild-the-lab)
if stopped or updated; unchanged stacks need no restart between runs.

**Gamehost — repository root:** run with the defender and normal traffic.

```sh
cd ~/purpleAI
python3 src/gamehost/run.py
```

The runner checks network isolation and collector delivery, assigns a shared
run ID, recreates the defender and verifies HTTP access. It then sends normal
browsing traffic while the configured attacker runs against port 8080. When the
attacker finishes, it stops traffic and returns the defender to a separate session.

Only one managed run may be active at a time; avoid manual attacks during it.
`Finished: RUN_ID` with a successful `run_end` means the workflow completed.
Check the events to assess attack results and model errors. The stacks stay
running, and VulnShop data is preserved between runs.

## Run without the defender

First [enable direct access](../../deploy/sandbox/TESTING.md#enable-direct-access-on-blueai)
on **both BlueAI and RedAI**. This is a one-time deployment setting change;
`DEV_IP` may stay empty, and gamehost's `.env` needs no change.

**Gamehost — repository root:** with the collector and lab stacks running:

```sh
cd ~/purpleAI
python3 src/gamehost/run.py --without-defender
```

This runs the attacker against VulnShop on port 8081, with **no normal traffic
or defender checks**. The defender stays running on 8080 and its session is not
recreated. The attacker still uses its gateway for its own model calls.
Preflight refuses this mode if direct access is not enabled on both PCs.

Omit the flag to use the defender again; no restart is needed to switch modes.
Both modes share the same target data. To reset it, stop/start BlueAI. To close
port 8081, [disable direct access](../../deploy/sandbox/TESTING.md#return-to-defended-only-testing).

## View logs and save events

**Gamehost — repository root:** follow live events from defended runs.
Ctrl+C stops viewing without stopping the collector.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml logs -f --tail 100 collector
```

The collector keeps the modes separate:

| Mode             | File inside the collector      | Contents                                                                       |
| ---------------- | ------------------------------ | ------------------------------------------------------------------------------ |
| With defender    | `/data/with-defender.jsonl`    | Run markers, attacker actions and defender decisions, including normal traffic |
| Without defender | `/data/without-defender.jsonl` | Run markers and attacker actions; excluded from the live stream above          |

**Gamehost — repository root:** view the latest events without the defender,
after at least one run in that mode.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml exec -T collector tail -n 100 /data/without-defender.jsonl
```

**Gamehost — repository root:** export defended events after at least one run.

```sh
cd ~/purpleAI
mkdir -p src/gamehost/data
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml exec -T collector cat /data/with-defender.jsonl > src/gamehost/data/with-defender.jsonl
```

For bypass events, replace `with-defender.jsonl` with `without-defender.jsonl`
in both paths. These exports include all saved runs in that mode; filter by
`run_id` to examine one experiment. Preflight checks and the defender's cleanup
session have separate IDs. Defender requests label traffic as `normal` or `other`.

Model failures use `status: model_error` and include `error_type`,
`model_http_status` and `error_reason`. A 404 with `status: forwarded` is a
response from the target. See [event format](../../docs/event-format.md) for details.

Events are delivered best effort; missing events are not replayed. Agent output
and diagnostics remain in the launching terminal or [sandbox logs](../../deploy/sandbox/README.md#logs-shell-and-shutdown).
Saved files survive collector recreation and ordinary shutdown, and grow until
archived or cleared. **Adding `--volumes` to shutdown deletes saved logs.**

## Update code or models

Update all checkouts to the same code version between runs.

| Change                                   | Action                                                                                          |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Agent code or dependencies               | Follow [agent integration](../../docs/agents.md#apply-changes-and-verify)                       |
| Sandbox, gateway or target code/settings | [Rebuild the affected lab stacks](../../deploy/sandbox/README.md#start-or-rebuild-the-lab)      |
| Agent `.env` only                        | [Apply agent settings](../../deploy/sandbox/README.md#change-agent-settings-without-rebuilding) |
| Runner code/settings                     | Read on the next invocation                                                                     |
| Collector code/settings or Compose       | Rebuild the collector below                                                                     |

**Gamehost — repository root:** rebuild the collector when it changed.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml up --build -d --wait collector
```

Existing SSH and sudo setup does not need to be repeated after updates or reboots.

## If a check fails

Each check line names the PC and container initiating the connection.
`PASS ... unreachable` means an intended restriction held. A `FAIL` stops the run.

| Symptom                                    | What to check                                                                                                                                            |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agents cannot reach port 8765              | Collector state and health using the block below; then addresses and host firewall                                                                       |
| Collector reachable but event rejected     | Both PCs' `LOG_COLLECTOR_TOKEN` must match gamehost's `GAMEHOST_LOG_TOKEN`; apply changed deployment settings with stop/start                            |
| SSH works manually but fails in the runner | Use the normal gamehost user without sudo; verify `RED_SSH` and `BLUE_SSH`                                                                               |
| `sudo: a password is required`             | Account and script path in the [one-time sudo rules](SETUP.md#passwordless-sudo-on-the-lab-pcs); no restart needed                                       |
| Defender model errors                      | Inspect `error_reason` and `model_http_status`; `Gateway busy` means the wait expired, while `Run call budget exhausted` requires restarting the gateway |

**Gamehost — repository root:** check collector state and health.
Replace the address if `GAMEHOST_LOG_BIND` differs. Health should return `ok`.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml ps collector
curl --max-time 5 http://192.168.0.110:8765/health
```

## Stop and recover

Normal cleanup is automatic. After a killed runner or lost SSH connection:

**Gamehost — repository root, after a defended run:** list remaining traffic
containers and stop the one matching the interrupted run. Replace `RUN_ID` with
its printed ID; skip the stop command if that container is no longer running.

```sh
cd ~/purpleAI
docker ps --filter name=purpleai-traffic --format '{{.Names}}'
docker stop purpleai-traffic-RUN_ID
```

**RedAI — repository root:** cancel remaining attacker containers.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red cancel
```

**BlueAI — repository root, after a defended run:** restore a separate defender
session while preserving target data. Skip this for a run without the defender.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue session
```

**Gamehost — repository root:** stop the collector while preserving saved events.
Stop any remaining one-off traffic container first.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml down
```

[Stop the lab stacks separately](../../deploy/sandbox/README.md#logs-shell-and-shutdown).
