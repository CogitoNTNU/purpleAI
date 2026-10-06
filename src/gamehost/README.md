# Gamehost: runs, normal traffic and logs

Gamehost runs the collector and normal-traffic containers. A small host-side
Python script coordinates RedAI and BlueAI over SSH. SSH keys stay on gamehost;
the collector only accepts events and never runs commands.

All commands below assume the repository is `~/purpleAI`. Replace that path if
your checkout is elsewhere. All three PCs must have this branch's code.

## First-time setup

**Gamehost — repository root (`~/purpleAI`):**

```sh
cd ~/purpleAI
cp -n src/gamehost/.env.example src/gamehost/.env
openssl rand -hex 32
nano src/gamehost/.env
chmod 600 src/gamehost/.env
```

Set these values in `src/gamehost/.env`:

| Setting                | Value                                                          |
| ---------------------- | -------------------------------------------------------------- |
| `GAMEHOST_LOG_BIND`    | Gamehost's LAN IPv4 address, for example `192.168.0.110`       |
| `GAMEHOST_LOG_TOKEN`   | The generated token                                            |
| `RED_SSH` / `BLUE_SSH` | SSH aliases or `user@PC-address` reachable from gamehost       |
| `REMOTE_REPO`          | Repository path on both lab PCs; `purpleAI` means `~/purpleAI` |
| `BLUE_IP`              | BlueAI's LAN address, for example `192.168.0.120`              |

Docker Engine, Compose, Python 3 and SSH must be available on gamehost. Your host
user must be able to run Docker. Confirm SSH keys and host keys by connecting to
each PC once from gamehost. The runner uses non-interactive SSH and `sudo -n`;
the SSH users need permission to run the sandbox entry point without a password.
Keep that management access outside the agent containers. If it fails, configure
SSH/sudo on the hosts before starting an experiment.

**RedAI and BlueAI — repository root (`~/purpleAI`), separately on each PC:**

```sh
cd ~/purpleAI
nano deploy/sandbox/.env
```

Add `GAMEHOST_IP` with gamehost's LAN address and `LOG_COLLECTOR_TOKEN` with the
same token as `GAMEHOST_LOG_TOKEN`. Set both together. Models still come from each
agent's own `.env`. Existing agent-level collector settings are overridden by the
sandbox's deployment settings.

## Start the collector and lab

**Gamehost — repository root (`~/purpleAI`):** start the collector first.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml up --build -d --wait collector
```

The collector listens on gamehost port **8765**. It requires the token, validates
JSON events, prints them immediately, and saves them in a persistent Docker
volume. It runs as non-root with a read-only image. This is a plain HTTP service
for the controlled lab LAN; do not forward its port through the router.

**BlueAI — repository root (`~/purpleAI`):** stop/start to install the new policy
and rebuild the defender. Stopping discards temporary target data.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue stop
sudo python3 deploy/sandbox/start.py blue start
sudo python3 deploy/sandbox/start.py blue check
```

**RedAI — repository root (`~/purpleAI`):**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red stop
sudo python3 deploy/sandbox/start.py red start
sudo python3 deploy/sandbox/start.py red check
```

Checks now verify authenticated event delivery as well as network reachability.
Both agents may send logs only to gamehost port 8765. Gamehost may send normal
traffic only to BlueAI's defender port 8080. VulnShop and model gateways cannot
connect to the collector. See the [sandbox guide](../../deploy/sandbox/README.md)
for the rest of first-time lab setup.

## Start one run

**Gamehost — repository root (`~/purpleAI`):**

```sh
cd ~/purpleAI
python3 src/gamehost/run.py
```

This command:

1. Checks the collector, SSH access, and both sandboxes.
1. Creates a shared run ID and recreates the defender with it.
1. Checks a normal request through the defender.
1. Starts one k6 user browsing ordinary shop pages while the Nmap agent runs.
1. Stops normal traffic, cancels any remaining attacker container, and returns the
   defender to a separate session after completion, errors, or Ctrl+C.

The collector stays running. The target's database is preserved between runs.
A local lock prevents overlapping runs from this gamehost. Use this runner for
experiments instead of starting additional attackers manually.

The run ID groups gamehost markers, attacker actions, and defender decisions.
Normal requests are tagged in defender events. These tags and agent events are
untrusted observations, not instructions or proof of attack success. A successful
run means execution completed, not that every normal request was accepted.

The runner pulls the pinned k6 image before starting the experiment. Normal
traffic uses one user, sequential requests and a three-second pause; its emergency
maximum duration is 24 hours. The runner normally stops it as soon as the attacker
ends. A killed process or lost SSH connection may prevent cleanup; recovery
commands are below.

## View logs and saved events

**Gamehost — repository root (`~/purpleAI`):** follow live events. Ctrl+C exits log
viewing without stopping the collector.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml logs -f --tail 100 collector
```

**Gamehost — repository root (`~/purpleAI`):** export the saved JSON lines.

```sh
cd ~/purpleAI
mkdir -p src/gamehost/data
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml exec -T collector cat /data/events.jsonl > src/gamehost/data/events.jsonl
```

Events include IDs, UTC timestamps, actions and statuses. Defender events include
method, path, decision and response status; request bodies and API keys are not
included. Agent delivery is best effort: an unavailable collector does not stop
an agent, and missed events are not replayed. The preflight check catches incorrect
tokens or unreachable collectors before a run.

Saved events persist when the collector stops. The JSONL file grows until you
archive or clear it; Docker's separate console logs rotate automatically.

## Stop and recover

**Gamehost — repository root (`~/purpleAI`):** stop the collector while preserving
saved events.

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml down
```

After an interrupted run, use the displayed run ID to find any remaining normal
traffic container named `purpleai-traffic-RUN_ID` and stop it with
`docker stop purpleai-traffic-RUN_ID` on gamehost. Do not delete the events volume
unless you intend to discard saved logs.

**RedAI — repository root (`~/purpleAI`):** cancel any remaining managed attacker.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red cancel
```

**BlueAI — repository root (`~/purpleAI`):** restore an independent defender
session while preserving target data.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue session
```
