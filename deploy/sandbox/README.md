# RedAI and BlueAI sandbox

RedAI (Kali) runs the attacker and an Idun gateway. BlueAI (Ubuntu) runs the
defender, VulnShop and its own gateway. Only the gateways hold real Idun keys.

```text
RedAI attacker → BlueAI defender → VulnShop
      ↓                 ↓
 Idun gateway      Idun gateway
      └──────→ Idun ←────┘
```

Use this page to configure and operate the two lab PCs. For a new three-PC lab,
start with [gamehost setup](../../src/gamehost/SETUP.md). For an existing lab:

- [Gamehost experiments](../../src/gamehost/README.md): coordinated runs and saved events.
- [Manual testing](TESTING.md): tools or agents from RedAI or your own PC, with or without defender checks.
- [Agent integration](../../docs/agents.md): deploy new or updated implementations.

All commands run from **`~/purpleAI`**, the repository root on the named PC.
Replace that path if needed. Use the same code version on all PCs.

## First-time configuration

Configure each lab PC once. You need Docker Engine with its iptables firewall
backend, Docker Compose, Git, Python 3, OpenSSL and an Idun key. Stop any previous
PurpleAI stack before starting this sandbox.

### 1. Configure addresses and gateway access

**RedAI and BlueAI — separately on each PC, repository root:**

```sh
cd ~/purpleAI
cp -n deploy/sandbox/.env.example deploy/sandbox/.env
openssl rand -hex 32
getent ahostsv4 llm.hpc.ntnu.no
nano deploy/sandbox/.env
```

`cp -n` preserves an existing file. Set:

| Setting              | Value                                                                                           |
| -------------------- | ----------------------------------------------------------------------------------------------- |
| `RED_IP`             | RedAI's LAN IPv4 address, currently `192.168.0.130`                                             |
| `BLUE_IP`            | BlueAI's LAN IPv4 address, currently `192.168.0.120`                                            |
| `ROUTER_IP`          | Router's LAN address, currently `192.168.0.1`                                                   |
| `IDUN_IP`            | One current IPv4 address from the lookup above                                                  |
| `GATEWAY_TOKEN`      | Generated token; use a different one on each PC                                                 |
| `GATEWAY_CALL_LIMIT` | Keep the default unless you need another call budget                                            |
| `DEV_IP`             | Leave empty; [optional development-PC access](TESTING.md#from-your-own-development-pc)          |
| `DIRECT_TESTING`     | Keep `false`; [optional access without the defender](TESTING.md#enable-direct-access-on-blueai) |

Reserve host addresses in the router. Docker subnets `172.28.10.0/24`,
`172.28.20.0/24` and `172.28.21.0/24` must not overlap LAN or VPN networks.
For gamehost logging, [configure delivery](../../src/gamehost/SETUP.md#2-configure-the-collector-and-agent-delivery)
before starting either stack. Leave `GAMEHOST_IP` and `LOG_COLLECTOR_TOKEN`
empty for standalone use.

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

Put **only the raw Idun key** in `deploy/sandbox/secrets/idun_key`, not a
`NAME=value` line. The private directory limits host access; the key file is
mounted read-only into the non-root gateway. Secrets and `.env` files are
excluded from Git and image builds.

### 3. Select agents and models

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

The examples select `ATTACKER_MODULE=agents.nmap.main` and
`DEFENDER_APP=defender:app`. Set `AGENT_MODEL` in each role file to any available
Idun model. Target, gateway and collector settings are supplied by the sandbox.
For another implementation, use [agent integration](../../docs/agents.md).
Older installations need the [one-time migration](../../docs/agents.md#upgrade-an-existing-lab).

| File                               | Configure on                 | Purpose                                                                  |
| ---------------------------------- | ---------------------------- | ------------------------------------------------------------------------ |
| `deploy/sandbox/.env`              | RedAI and BlueAI, separately | Network, gateway token, collector and testing access                     |
| `src/attacker/.env`                | RedAI                        | Attacker entry point, models and tasks                                   |
| `src/defender/defender-agent/.env` | BlueAI                       | Defender entry point, models and settings                                |
| `src/gamehost/.env`                | Gamehost                     | Collector and SSH destinations; see [setup](../../src/gamehost/SETUP.md) |

## Start or rebuild the lab

If logging is configured, [start the collector first](../../src/gamehost/README.md#run-an-experiment).
Use these blocks for initial startup, source/dependency updates, deployment
setting changes, or recovery after a PC/Docker restart. Finish active runs first.
Unchanged running stacks need no restart before testing.

Stop/start rebuilds images and installs the firewall. **Stopping BlueAI clears
VulnShop's temporary database, uploads and reports.** Startup refuses to change
policy while a lab stack is running.

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

RedAI builds the attacker image but waits for a run command to launch it.
For manual testing with a stopped collector, use the checks shown in
[manual setup](TESTING.md#enable-direct-access-on-blueai).

Every check should show `PASS`, including expected blocked connections:

```text
PASS [BlueAI / defender] model-gateway:9000: reachable
PASS [BlueAI / vulnerable-app] 192.168.0.110:8765: unreachable
PASS [RedAI / attacker] 192.168.0.120:8080: reachable
```

Labels identify the PC and container initiating the connection. Checks verify
policy, TCP reachability and authenticated collector delivery when enabled;
they do not call a model. A failed connection can mean filtering or no service
listening. Use the [integration smoke workflow](../../docs/agents.md#apply-changes-and-verify)
to check HTTP and model access too.

## Run and view the app

Use [gamehost](../../src/gamehost/README.md) for coordinated runs, or
[manual testing](TESTING.md#tools-or-the-agent-inside-the-redai-sandbox) for
individual attacker runs and tools.

From RedAI or the configured gamehost, open `http://192.168.0.120:8080` in your
browser (replace the address if needed). It reaches VulnShop through the defender.
Your own PC needs [development-PC access](TESTING.md#from-your-own-development-pc).
Other LAN clients are blocked. Optional port 8081 bypasses the defender.

## Change agent settings without rebuilding

Entry points, models and task settings in the role's `.env` need no image build.
Source, dependency or deployment `.env` changes require [stop/start](#start-or-rebuild-the-lab).

**RedAI — repository root:** edit settings; the next attacker run reads them.

```sh
cd ~/purpleAI
nano src/attacker/.env
```

**BlueAI — repository root:** edit settings and recreate only the defender.
This preserves target data. The next defended gamehost run also recreates it.

```sh
cd ~/purpleAI
nano src/defender/defender-agent/.env
sudo python3 deploy/sandbox/start.py blue session
```

## Logs, shell and shutdown

**BlueAI — repository root:** show the last 100 stack log lines.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue logs
```

**RedAI — repository root:** show gateway logs. Attacker output appears in its
launching terminal; its container is removed on completion.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red logs
```

For an attacker shell, use [manual tools](TESTING.md#tools-or-the-agent-inside-the-redai-sandbox).
For interrupted managed runs, use [gamehost recovery](../../src/gamehost/README.md#stop-and-recover).

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

Firewall rules remain after shutdown and are reinstalled at startup. Use this
entry point for sandbox operations so launches and checks verify policy.
Switching Git branches does not remove containers or firewall rules.

## Isolation and limits

| Component | May initiate connections to                                            |
| --------- | ---------------------------------------------------------------------- |
| Attacker  | BlueAI 8080, also 8081 if enabled; its gateway; optional gamehost 8765 |
| Defender  | VulnShop; its gateway; optional gamehost 8765                          |
| VulnShop  | Nothing; it may reply to permitted requests                            |
| Gateways  | Configured Idun IPv4 address on HTTPS 443                              |

Containers run as non-root with read-only images, dropped capabilities, no
privilege escalation and resource limits. Host source, home folders and the
Docker socket are not mounted. Other host/LAN/internet access and IPv6 are
blocked. External container DNS is disabled; gateways use a fixed Idun hosts
entry. If Idun's address changes, update `IDUN_IP` and rebuild/check both stacks.

Each gateway allows one model call at a time **per PC**, with a 10-second wait
for overlapping calls before returning 429. RedAI and BlueAI can call concurrently.
This local safeguard does not enforce Idun's rate limits. Output is capped at
2048 tokens. `GATEWAY_CALL_LIMIT` counts attempts, including failed calls, for
the gateway process lifetime; restarting the gateway resets it, a new run does not.

Use synthetic data: requests reach Idun and may appear in logs. Containers share
the host kernel; tools that target that boundary need stronger isolation such as
disposable VMs.
