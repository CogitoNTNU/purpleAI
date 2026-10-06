# Two-PC lab

RedAI (Kali) runs the attacker. BlueAI (Ubuntu) runs the defender and VulnShop.
Each PC has a small gateway that forwards model calls to Idun and keeps the real
API key away from the agent.

```text
RedAI:   attacker ───────────────► BlueAI: defender ──► VulnShop
             │                               │
         Idun gateway                    Idun gateway
             │                               │
             └────────────► Idun ◄────────────┘
```

The router and Ethernet wiring stay as they are. Docker contains the processes;
the PC firewalls restrict where they can connect.

## Working directory

These commands assume the repository is at `~/purpleAI` on each PC. If you cloned
it elsewhere, replace `~/purpleAI` with that path in every `cd` command.
Run host commands from the **repository root**, not `deploy/sandbox`.
Every command block below starts by changing to that directory.

## First-time setup

Do this on **both PCs**. Docker Engine, Docker Compose and Python 3 must be
installed. Docker must use its default iptables firewall backend. Stop the old
PurpleAI containers before starting this setup.

1. **Both PCs — repository root (`~/purpleAI`):** copy the deployment settings,
   generate a gateway password, and look up Idun's current IPv4 address.
   `cp -n` preserves an existing `.env`.

   ```sh
   cd ~/purpleAI
   cp -n deploy/sandbox/.env.example deploy/sandbox/.env
   openssl rand -hex 32
   getent ahostsv4 llm.hpc.ntnu.no
   nano deploy/sandbox/.env
   ```

   Check the PC/router addresses, set `IDUN_IP` to a current address from the
   lookup, and paste the generated password into `GATEWAY_TOKEN`. Use a different
   password on each PC. Reserve the PC addresses in the router so they stay fixed.

1. **Both PCs — repository root (`~/purpleAI`):** create the key file with your
   editor. Put **only your Idun API key** in it.

   ```sh
   cd ~/purpleAI
   mkdir -p deploy/sandbox/secrets
   chmod 700 deploy/sandbox/secrets
   nano deploy/sandbox/secrets/idun_key
   chmod 444 deploy/sandbox/secrets/idun_key
   chmod 600 deploy/sandbox/.env
   ```

   The protected directory prevents other host users reading the key. The file
   is mounted read-only into the non-root gateway. Keys/settings are Git-ignored
   and excluded from image builds.

1. Create the agent settings on the appropriate PC. Set `AGENT_MODEL` to any
   model available on Idun. If reusing an existing attacker `.env`, rename
   `IDUN_MODEL` to `AGENT_MODEL`.

   **RedAI only — repository root (`~/purpleAI`):**

   ```sh
   cd ~/purpleAI
   cp -n src/nmap-agent/.env.example src/nmap-agent/.env
   nano src/nmap-agent/.env
   chmod 600 src/nmap-agent/.env
   ```

   **BlueAI only — repository root (`~/purpleAI`):**

   ```sh
   cd ~/purpleAI
   cp -n src/defender/defender-agent/.env.example src/defender/defender-agent/.env
   nano src/defender/defender-agent/.env
   chmod 600 src/defender/defender-agent/.env
   ```

   Docker reads each agent's `.env` when creating its container. The sandbox
   overrides the API address, API key and target with its protected gateway
   settings. The agent does not need a real Idun key in its `.env` for sandbox use.
   Deployment `.env` contains only network and gateway settings; remove its old
   model setting. There is no legacy model fallback or model allowlist.

## Start and check

**BlueAI — repository root (`~/purpleAI`):** start the defender and target.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue start
```

**RedAI — repository root (`~/purpleAI`):** start the gateway and build the
attacker. This does not run the attacker yet.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red start
```

Startup enables bridge filtering and installs the firewall using deployment
`.env` settings before starting containers. It refuses to rewrite rules while
the lab is running: stop that PC's stack before restarting it.

Run the connection checks on **both PCs** before using the attacker.

**BlueAI — repository root (`~/purpleAI`):**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue check
```

**RedAI — repository root (`~/purpleAI`):**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red check
```

**RedAI — repository root (`~/purpleAI`):** when ready, run the attacker.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red run
```

## Change a model

**RedAI — repository root (`~/purpleAI`):** edit `AGENT_MODEL`; the next attacker
run reads the updated value. The gateway must already be running.

```sh
cd ~/purpleAI
nano src/nmap-agent/.env
sudo python3 deploy/sandbox/start.py red run
```

**BlueAI — repository root (`~/purpleAI`):** edit `AGENT_MODEL`, then stop and
recreate the defender. Stopping also discards the target's temporary data.

```sh
cd ~/purpleAI
nano src/defender/defender-agent/.env
sudo python3 deploy/sandbox/start.py blue stop
sudo python3 deploy/sandbox/start.py blue start
sudo python3 deploy/sandbox/start.py blue check
```

Startup rebuilds the images, so use stop/start after updating this branch too.

## Other commands

Run each command below from the **repository root (`~/purpleAI`)** on the listed
PC. Run `cd ~/purpleAI` first if your terminal is in another directory.

| PC     | Full command                                     | Purpose                                           |
| ------ | ------------------------------------------------ | ------------------------------------------------- |
| RedAI  | `sudo python3 deploy/sandbox/start.py red shell` | Open a manual shell inside the attacker container |
| RedAI  | `sudo python3 deploy/sandbox/start.py red logs`  | Show the last 100 log lines                       |
| BlueAI | `sudo python3 deploy/sandbox/start.py blue logs` | Show the last 100 log lines                       |
| RedAI  | `sudo python3 deploy/sandbox/start.py red stop`  | Stop the RedAI stack and discard temporary data   |
| BlueAI | `sudo python3 deploy/sandbox/start.py blue stop` | Stop the BlueAI stack and discard temporary data  |

The manual shell opens **inside the attacker container**, initially in `/app`.
Type `exit` to return to the host terminal.

Use this entry point instead of direct Compose commands: agent launches and
connection checks verify the firewall first. After a PC reboot or Docker/firewall
restart, stop/start the lab on that PC and repeat both PCs' connection checks.
Firewall rules remain after stopping; startup reinstalls them.

## What is protected

| Component | May initiate connections to                   |
| --------- | --------------------------------------------- |
| Attacker  | BlueAI port 8080; its local Idun gateway      |
| Defender  | VulnShop; its local Idun gateway              |
| VulnShop  | Nothing; it may reply to the defender         |
| Gateways  | The configured Idun address on HTTPS port 443 |

Only BlueAI port 8080 is published, and only RedAI may reach it. The firewall
blocks other container access to the host, router, LAN, internet, and IPv6.
VulnShop is on a separate internal network, so the attacker cannot bypass the
defender. External DNS is disabled for containers; Idun uses a fixed hosts entry.

Containers run as non-root, without capabilities or privilege escalation, with
read-only images and bounded temporary storage, CPU, memory, processes, and logs.
No host source directories, home directories, or Docker socket are mounted.
The existing agent tools remain; this does not add autonomous shell execution or
code-edit/restart tools. The attacker scan is scoped to port 8080.

Gateway calls use non-streaming chat completions,
2048 output tokens, and one call at a time. `GATEWAY_CALL_LIMIT` limits attempts
per gateway process lifetime; restarting it resets the count. Use synthetic lab
data: requests may reach Idun and appear in defender logs.

The checks test TCP reachability, not authenticated inference. A failed connection
may also mean no service is listening. Confirm blocked probes increase the DROP
counters with these read-only host commands.

**RedAI — repository root (`~/purpleAI`):**

```sh
cd ~/purpleAI
sudo iptables -nvL PAI_RED_FWD
sudo iptables -nvL PAI_RED_HOST
```

**BlueAI — repository root (`~/purpleAI`):**

```sh
cd ~/purpleAI
sudo iptables -nvL PAI_BLUE_FWD
sudo iptables -nvL PAI_BLUE_HOST
```

Verify BlueAI port 8080 is blocked from a third LAN machine before granting broader
tools. These runtime checks are still needed
on the actual PCs. Containers share the host kernel; use disposable VMs for
kernel exploits or privileged tools.

## Files

- `red.compose.yml` / `blue.compose.yml`: services, limits and networks.
- `Dockerfile`: builds the four service images from named stages.
- `gateway.py`: fixed Idun forwarding and request limits.
- `firewall.py`: permitted connections and host protection.
- `start.py`: operator commands; `check_network.py`: TCP checks.

Only three Docker subnets are used: `172.28.10.0/24` on RedAI and
`172.28.20.0/24` / `172.28.21.0/24` on BlueAI. They must not overlap your networks.
If Idun's address changes, stop both stacks, update `IDUN_IP`, and start/check again.

For implementation details, see [Docker's firewall documentation](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
UFW alone does not protect Docker-published ports.
