# RedAI and BlueAI sandbox

RedAI (Kali) runs the attacker and an Idun gateway. BlueAI (Ubuntu) runs the
defender, VulnShop and its own Idun gateway. Agents use the gateways; only the
gateways hold real Idun API keys.

```text
RedAI attacker → BlueAI defender → VulnShop
      ↓                 ↓
 Idun gateway      Idun gateway
      └──────→ Idun ←────┘
```

This page configures and operates the two lab PCs.

- **New lab with gamehost:** start with [first-time setup](../../src/gamehost/SETUP.md).
- **Already configured lab:** use the [gamehost run guide](../../src/gamehost/README.md).
- **Tools, scripts or agents from RedAI or your own PC:** use [manual testing](TESTING.md), with or without defender checks.
- **New or updated agents:** use the [agent integration guide](../../docs/agents.md).

Every host command below runs from **`~/purpleAI`**, the repository root.
Replace that path if your checkout is elsewhere. Use the same code version on
all PCs. Run each block only on its named PC.

## First-time configuration

Do this once on each lab PC. Docker Engine, Docker Compose, Git, Python 3,
OpenSSL and an Idun API key are required. Docker must use its iptables firewall
backend. Stop any previous PurpleAI stack before starting this sandbox.

### 1. Configure the network and gateway

**RedAI and BlueAI — separately on each PC, repository root:**

```sh
cd ~/purpleAI
cp -n deploy/sandbox/.env.example deploy/sandbox/.env
openssl rand -hex 32
getent ahostsv4 llm.hpc.ntnu.no
nano deploy/sandbox/.env
```

`cp -n` preserves an existing file. Set these deployment values:

| Setting              | What to enter                                                                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RED_IP`             | RedAI's LAN IPv4 address, currently `192.168.0.130`                                                                                               |
| `BLUE_IP`            | BlueAI's LAN IPv4 address, currently `192.168.0.120`                                                                                              |
| `ROUTER_IP`          | Router's LAN address, currently `192.168.0.1`                                                                                                     |
| `IDUN_IP`            | One current IPv4 address from the lookup above                                                                                                    |
| `GATEWAY_TOKEN`      | The generated token; use a different token on each PC                                                                                             |
| `GATEWAY_CALL_LIMIT` | Keep the default unless you need a different call budget                                                                                          |
| `DEV_IP`             | Optional development PC LAN address on BlueAI; see [manual testing](TESTING.md#from-your-own-development-pc)                                      |
| `DIRECT_TESTING`     | Keep `false`; set `true` to test VulnShop **without the defender** on port 8081. See [direct testing](TESTING.md#enable-direct-access-on-blueai). |

Reserve the PC addresses in the router so they stay fixed. The Docker subnets
`172.28.10.0/24`, `172.28.20.0/24` and `172.28.21.0/24` must not overlap your LAN
or VPN networks.

For gamehost runs, configure `GAMEHOST_IP` and `LOG_COLLECTOR_TOKEN` using the
[gamehost setup instructions](../../src/gamehost/SETUP.md#2-configure-the-collector-and-agent-delivery)
before starting either stack. Leave both empty for standalone use.

### 2. Store the Idun key

**RedAI and BlueAI — separately on each PC, repository root:**

```sh
cd ~/purpleAI
mkdir -p deploy/sandbox/secrets
chmod 700 deploy/sandbox/secrets
nano deploy/sandbox/secrets/idun_key
chmod 444 deploy/sandbox/secrets/idun_key
chmod 600 deploy/sandbox/.env
```

Put only the Idun API key in `secrets/idun_key`. The directory limits host access;
the key file is mounted read-only into the non-root gateway. Secrets and `.env`
files are excluded from Git and Docker image builds.

### 3. Choose agents and models

**RedAI — repository root:**

```sh
cd ~/purpleAI
cp -n src/attacker/.env.example src/attacker/.env
nano src/attacker/.env
chmod 600 src/attacker/.env
```

**BlueAI — repository root:**

```sh
cd ~/purpleAI
cp -n src/defender/defender-agent/.env.example src/defender/defender-agent/.env
nano src/defender/defender-agent/.env
chmod 600 src/defender/defender-agent/.env
```

The copied examples select `ATTACKER_MODULE=agents.nmap.main` on RedAI and
`DEFENDER_APP=defender:app` on BlueAI. Set `AGENT_MODEL` to your chosen Idun model
in each file. The sandbox supplies the target, gateway and collector settings.

For another agent or a coordinator with subagents, follow [adding or updating
agents](../../docs/agents.md). Existing installations need its
[one-time migration](../../docs/agents.md#upgrade-an-existing-lab) before rebuilding.

Keep settings in these files; changing a model does not require editing deployment settings:

| PC                           | File                               | Settings                                                                                          |
| ---------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------- |
| RedAI and BlueAI, separately | `deploy/sandbox/.env`              | Network addresses, gateway token, collector delivery and optional testing access                  |
| RedAI                        | `src/attacker/.env`                | `ATTACKER_MODULE`, model and workflow settings                                                    |
| BlueAI                       | `src/defender/defender-agent/.env` | `DEFENDER_APP`, model and application settings                                                    |
| Gamehost                     | `src/gamehost/.env`                | Collector token/address and SSH destinations; see [first-time setup](../../src/gamehost/SETUP.md) |

## Start or rebuild the lab

When logging is enabled, [start the collector on gamehost first](../../src/gamehost/README.md#run-an-experiment).
Use the same sequence for initial startup, code updates, deployment setting
changes, or recovery after a PC/Docker restart.
Already running, unchanged stacks need no restart before a test or experiment.

Stop/start rebuilds the images and installs the firewall before launching
containers. Startup refuses to change firewall rules while a lab stack is
running. **Stopping BlueAI discards VulnShop's temporary database, uploads and
reports.** Finish any active experiment first.

**BlueAI — repository root:**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue stop
sudo python3 deploy/sandbox/start.py blue start
sudo python3 deploy/sandbox/start.py blue check
```

**RedAI — repository root:**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red stop
sudo python3 deploy/sandbox/start.py red start
sudo python3 deploy/sandbox/start.py red check
```

RedAI startup builds the attacker image but does not run the attacker.
Every check should show `PASS`; an expected `unreachable` result is a pass:

```text
PASS [BlueAI / defender] model-gateway:9000: reachable
PASS [BlueAI / vulnerable-app] 192.168.0.110:8765: unreachable
PASS [RedAI / attacker] 192.168.0.120:8080: reachable
```

Each label identifies the PC and container initiating the connection. Checks
verify the firewall, TCP reachability and authenticated collector delivery when
enabled. They do not perform a model inference call. A failed connection can
mean either filtering or no service listening.

## Run and view the app

For shared run IDs and collected events, use the
[gamehost runner](../../src/gamehost/README.md#run-an-experiment). It runs normal
traffic with the defender by default; `--without-defender` runs only the attacker
against port 8081, with logs saved separately. See [runs without the defender](../../src/gamehost/README.md#run-without-the-defender).

For a standalone attacker run, first pass both PCs' checks above.
**RedAI — repository root:**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red run
```

From a browser on **RedAI or the configured gamehost**, open
`http://192.168.0.120:8080` (replace the address if `BLUE_IP` differs).
This reaches VulnShop through the defender. To use your own PC, configure
`DEV_IP` on BlueAI as described in [manual testing](TESTING.md#from-your-own-development-pc).
Other LAN machines are blocked. Optional port 8081 bypasses the defender;
it is disabled by default.

## Change a model without rebuilding

**RedAI — repository root:** edit the attacker model. Its next run reads the file.

```sh
cd ~/purpleAI
nano src/attacker/.env
```

**BlueAI — repository root:** edit the defender model and recreate only the
defender. This preserves VulnShop's data. The next gamehost run also recreates
the defender automatically.

```sh
cd ~/purpleAI
nano src/defender/defender-agent/.env
sudo python3 deploy/sandbox/start.py blue session
```

Model-only changes need no image rebuild. For code or deployment setting changes,
use [stop/start](#start-or-rebuild-the-lab).

## Logs, shell and shutdown

**BlueAI — repository root:** show the last 100 stack log lines.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue logs
```

**RedAI — repository root:** show gateway logs. The attacker transcript appears
in the terminal that launches it; run containers are removed when they finish.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red logs
```

**RedAI — repository root:** open a manual shell in the attacker container.
The shell starts in `/app`; enter `exit` to return to the host.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red shell
```

**RedAI — repository root:** stop its stack.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red stop
```

**BlueAI — repository root:** stop its stack and discard temporary target data.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue stop
```

Firewall rules remain after shutdown and are reinstalled at startup. Use
`start.py` for sandbox operations so agent launches and checks verify the policy.
For interrupted gamehost runs, follow [recovery](../../src/gamehost/README.md#stop-and-recover).

## Isolation and limits

| Component | May initiate connections to                                                                           |
| --------- | ----------------------------------------------------------------------------------------------------- |
| Attacker  | BlueAI port 8080 (also 8081 when direct testing is enabled); its gateway; optional gamehost port 8765 |
| Defender  | VulnShop; its gateway; optional gamehost port 8765                                                    |
| VulnShop  | Nothing; it may reply to permitted requests                                                           |
| Gateways  | Configured Idun IPv4 address on HTTPS port 443                                                        |

Containers run as non-root with read-only images, dropped capabilities, no
privilege escalation and bounded resources. Host source directories, home
folders and the Docker socket are not mounted. The firewall blocks other
container access to the host, router, LAN, internet and IPv6. VulnShop's separate
internal network prevents direct attacker access by default. Optional direct
testing attaches VulnShop to the frontend too; the firewall permits only the
configured clients to reach it and still blocks its outbound connections. External container DNS is
disabled; the gateway resolves Idun through a fixed hosts entry.

Each gateway permits one model call at a time, independently on each PC.
RedAI and BlueAI can therefore call Idun at the same time. Overlapping requests
to the same gateway wait up to 10 seconds, then return 429 if still busy.
This is a local gateway limit; it does not enforce Idun's per-minute rate limits.
Output is limited to 2048 tokens.
`GATEWAY_CALL_LIMIT` counts attempts for the gateway process lifetime, including
failed calls; only restarting the gateway resets it. Starting a gamehost run does
not reset this budget.

Use synthetic lab data: requests reach Idun and may appear in logs. Containers
share the host kernel; broader tools such as kernel exploits require a stronger
boundary, such as disposable VMs. The supplied Nmap example scans only the selected endpoint port, 8080 by default
or 8081 with `--target direct`. Other workflows still use the same network policy.

If Idun's IPv4 address changes, stop both stacks, update `IDUN_IP` on each PC,
then start/check both again. To inspect firewall DROP counters:

**RedAI — repository root:**

```sh
cd ~/purpleAI
sudo iptables -nvL PAI_RED_FWD
sudo iptables -nvL PAI_RED_HOST
```

**BlueAI — repository root:**

```sh
cd ~/purpleAI
sudo iptables -nvL PAI_BLUE_FWD
sudo iptables -nvL PAI_BLUE_HOST
```
