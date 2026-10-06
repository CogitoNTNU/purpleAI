# Two-PC PurpleAI sandbox

RedAI runs Kali and the attacker. BlueAI runs Ubuntu, the defender reverse proxy,
and the small existing VulnShop application (SQLite included). Both PCs stay
connected to the current router. No VLAN or router changes are required.

This is a container lab for application-level experiments. Containers share their
host kernel; use disposable VMs for kernel exploits or tools requiring privileged
access. Host administrators and the Docker daemon are trusted. Do not run the
agents directly on the host or mount the Docker socket into a container.

## Boundary

| Source                       | Allowed destination                             |
| ---------------------------- | ----------------------------------------------- |
| Red attacker                 | Blue PC TCP 8080; local model gateway TCP 9000  |
| Blue defender                | VulnShop TCP 5000; local model gateway TCP 9000 |
| VulnShop                     | Responses to defender connections only          |
| Each model gateway           | One configured Idun IPv4 address TCP 443        |
| Blue published defender port | Red PC only                                     |

The host firewall blocks other container traffic, including access to the host,
router, unrelated LAN services, general internet destinations, and IPv6. Only the
defender publishes a host port. Docker's internal DNS resolves Compose service
names; external DNS forwarding is pointed at container loopback. The gateway uses
a fixed hosts entry for Idun, preserving hostname-based TLS certificate checking.
Neither agent receives the real Idun API key. Model calls can still send lab data
to Idun, so use synthetic data in the lab.

All services run as UID 10001, drop capabilities, retain Docker's default seccomp
profile, prevent privilege escalation, and have read-only images and bounded
temporary storage, CPU, memory, processes, and log files. Workspaces and the
database reset when their containers are recreated. No source or home directory
is mounted. The existing attacker still has its restricted Nmap tool; this change
does not add an LLM-controlled shell or a defender code-edit/restart tool.

The model gateway only implements non-streaming `/v1/chat/completions`, fixes the
model, limits requests to 256 KiB and responses to 2 MiB, caps output at 2048
tokens, and processes one model call at a time. Its default budget is 1000 upstream
attempts per gateway process lifetime; failed attempts count too. Restarting the
gateway resets that budget. SDK retries consume additional attempts. No token or
monetary accounting is provided. Gateway credentials are different on each PC.

## Requirements

Read-only checks on 6 October 2026 found BlueAI at `192.168.0.120` with Docker
29.8.1 and Compose 5.5.1, and RedAI at `192.168.0.130` with Docker 28.5.2 and
Compose 2.40.3 after installation.
Both reached Idun (`129.241.121.16`) and returned HTTP 401 without credentials.
These are current addresses, not verified DHCP reservations. The SSH accounts
could not inspect the Docker daemons or host firewall without administrator credentials.
Bridge-netfilter sysctl files were absent on both PCs at the time of inspection.
Enable bridge netfilter on both before deployment; no remote configuration was
changed by these checks.

- Docker Engine with its **iptables firewall backend**, and Compose 2.33.1+.
  The experimental nftables backend is not supported by these scripts.
- Python 3 on both hosts, and `iptables`/`ip6tables` commands.
- NTNU network access to Idun on both hosts.
- Reserved router DHCP addresses for both PCs, and non-overlapping sandbox ranges:
  `172.28.10.0/24`, `172.28.11.0/24`, `172.28.20.0/24`,
  `172.28.21.0/24`, `172.28.22.0/24`.

Do not use UFW alone to protect published Docker ports. Docker routes published
traffic before normal UFW input rules; these scripts filter `DOCKER-USER`, host
`INPUT`, and IPv6 forwarding/input. They preserve unrelated firewall chains.

## Configure each PC

Check out this branch on both PCs. Stop any old PurpleAI deployment, especially
the Compose examples that expose nginx or the defender without these rules.

From the repository root on **each PC**:

```sh
cp deploy/sandbox/.env.example deploy/sandbox/.env
getent ahostsv4 llm.hpc.ntnu.no
openssl rand -hex 32
```

Edit `deploy/sandbox/.env`: set the same `RED_IP` and `BLUE_IP` on both PCs;
set `IDUN_IP` to a current IPv4 address from the lookup; set `GATEWAY_TOKEN` to
the newly generated value, different on each PC; choose an available `IDUN_MODEL`.
The model default matches the current repo but is not a guarantee of availability.

Create the secret directory and put **only the real Idun API key** in
`deploy/sandbox/secrets/idun_key` using your editor:

```sh
mkdir -p deploy/sandbox/secrets
chmod 700 deploy/sandbox/secrets
# Create secrets/idun_key now, then:
chmod 444 deploy/sandbox/secrets/idun_key
chmod 600 deploy/sandbox/.env
```

The directory protects the key on the host; the file must be readable by the
non-root gateway after Docker mounts it. Compose mounts this file only into the
gateway, read-only. Both `.env` and the secret directory are Git-ignored and
excluded from image builds. The gateway token is agent-readable by design.

## Install firewall, then start

On both PCs enable bridge netfilter so rules also cover traffic on one bridge:

```sh
sudo modprobe br_netfilter
sudo sysctl -w net.bridge.bridge-nf-call-iptables=1
sudo sysctl -w net.bridge.bridge-nf-call-ip6tables=1
```

Replace the example addresses below with your `.env` values. Review the commands
first with `--dry-run`. The script rejects rule changes while its Compose
project has running containers. Keep an administrator session open during setup.

**BlueAI:**

```sh
sudo python3 deploy/sandbox/firewall.py blue \
  --red-ip 192.168.0.130 --blue-ip 192.168.0.120 --idun-ip YOUR_IDUN_IPV4 --dry-run
# Run the same command without --dry-run to apply.
sudo python3 deploy/sandbox/start.py blue
```

**RedAI:**

```sh
sudo python3 deploy/sandbox/firewall.py red \
  --red-ip 192.168.0.130 --blue-ip 192.168.0.120 --idun-ip YOUR_IDUN_IPV4 --dry-run
# Run the same command without --dry-run to apply.
sudo python3 deploy/sandbox/start.py red
```

`start.py` checks the firewall against `.env`, including its placement and IPv6
rules, before starting containers. Blue starts the full stack; Red starts its
gateway and builds its attacker image. Builds/downloads run through the trusted
Docker daemon, not the agent runtime.

Use `start.py` for startup. Direct Compose startup bypasses this guard. Rules are
not installed persistently: after a reboot, re-enable bridge netfilter and apply
the firewall before starting. There are no automatic container restart policies.
After Docker/firewall service restarts, stop the lab, reinstall/check the policy,
and rerun the isolation checks before resuming agents.

## Check isolation before agent runs

Substitute real Blue, Red, router, and Idun addresses. These commands use only TCP
connections; the first checks don't consume model calls.

On **RedAI**:

```sh
sudo docker compose --env-file deploy/sandbox/.env -f deploy/sandbox/red.compose.yml \
  run --rm --no-deps --entrypoint python attacker /app/check_network.py \
  --allow model-gateway:9000 --allow 192.168.0.120:8080 \
  --deny 172.28.10.1:22 --deny 192.168.0.120:22 \
  --deny YOUR_ROUTER_IP:80 --deny YOUR_IDUN_IPV4:443
```

On **BlueAI**:

```sh
sudo docker compose --env-file deploy/sandbox/.env -f deploy/sandbox/blue.compose.yml \
  exec defender python /app/check_network.py \
  --allow model-gateway:9000 --allow vulnerable-app:5000 \
  --deny 172.28.20.1:22 --deny YOUR_ROUTER_IP:80 --deny YOUR_IDUN_IPV4:443
sudo docker compose --env-file deploy/sandbox/.env -f deploy/sandbox/blue.compose.yml \
  exec vulnerable-app python /app/check_network.py \
  --deny 172.28.21.20:8080 --deny 192.168.0.130:22 --deny YOUR_IDUN_IPV4:443
sudo docker compose --env-file deploy/sandbox/.env -f deploy/sandbox/blue.compose.yml \
  exec model-gateway python /app/check_network.py \
  --allow llm.hpc.ntnu.no:443 --deny YOUR_ROUTER_IP:80
```

Run the same model-gateway check on RedAI, using its Compose file. Confirm an
authenticated model request works through each gateway before starting a run:

```sh
# BlueAI example; change the Compose file to red.compose.yml on RedAI.
sudo docker compose --env-file deploy/sandbox/.env -f deploy/sandbox/blue.compose.yml \
  exec model-gateway python -c 'import os, requests; r=requests.post("http://127.0.0.1:9000/v1/chat/completions", headers={"Authorization":"Bearer "+os.environ["GATEWAY_TOKEN"]}, json={"model":os.environ["IDUN_MODEL"],"messages":[{"role":"user","content":"Reply OK"}],"max_tokens":16}, timeout=140); print("HTTP",r.status_code); r.raise_for_status()'
```

An unreachable port alone is not proof of filtering: it may have no listening
service. Inspect counters with `sudo iptables -nvL PAI_RED_FWD` or
`sudo iptables -nvL PAI_BLUE_FWD` and the corresponding `*_HOST` chains;
also inspect `ip6tables` `*_FWD6` and `*_HOST6` chains. Confirm blocked tests hit
DROP counters and repeat against a known listening lab/host service. Confirm
Blue's published port is inaccessible from a third LAN machine. Stop if any
unexpected connection succeeds. Runtime isolation on the actual PCs is required
before granting agents broader tools.

## Run, inspect, reset

On RedAI, run the existing reconnaissance agent:

```sh
sudo docker compose --env-file deploy/sandbox/.env -f deploy/sandbox/red.compose.yml run --rm attacker
```

For a manual shell inside the same boundary:

```sh
sudo docker compose --env-file deploy/sandbox/.env -f deploy/sandbox/red.compose.yml run --rm --entrypoint sh attacker
```

Only Blue's 8080 port is permitted. The sandbox sets `NMAP_PORT=8080` so the
existing reconnaissance tool probes that published service. Other deployments
retain their default scan scope when this setting is absent. For a manual check,
use `nmap -sT -Pn -p 8080 BLUE_IP` from that shell.
Allowing another lab port requires an explicit firewall change on both PCs.

On BlueAI inspect defender output:

```sh
sudo docker compose --env-file deploy/sandbox/.env -f deploy/sandbox/blue.compose.yml logs --tail 100 defender
```

Defender logs may include raw lab requests: use synthetic credentials/data.
The existing gamehost collector and dashboard are not exposed by this first
deployment; container logs provide the initial observability.

Stop/reset on each PC using its Compose file:

```sh
sudo docker compose --env-file deploy/sandbox/.env -f deploy/sandbox/blue.compose.yml down
```

Temporary state is deleted. Firewall rules remain installed. For an Idun address
change, stop each stack, update `.env`, reinstall its matching policy, then start
and test again. For removal, stop containers first and invoke `firewall.py` with
the same role/address arguments and `--remove`. Removal only deletes the
`PAI_RED_*` or `PAI_BLUE_*` rules created here.

## Local validation

```sh
uv run pytest
IDUN_IP=129.241.1.1 GATEWAY_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  docker compose --env-file deploy/sandbox/.env.example -f deploy/sandbox/red.compose.yml config --quiet
IDUN_IP=129.241.1.1 GATEWAY_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  docker compose --env-file deploy/sandbox/.env.example -f deploy/sandbox/blue.compose.yml config --quiet
```

Those addresses/tokens are configuration-validation placeholders only. Gateway
tests mock Idun; they do not use real credentials or prove host firewall behavior.

References: [Docker firewall integration](https://docs.docker.com/engine/network/packet-filtering-firewalls/),
[Docker with iptables](https://docs.docker.com/engine/network/firewall-iptables/),
[internal-network host access](https://docs.docker.com/reference/cli/docker/network/create/),
[NTNU Idun access](https://www.hpc.ntnu.no/idun/documentation/ai-coding-assistant-and-large-language-models-llms-on-idun/).
