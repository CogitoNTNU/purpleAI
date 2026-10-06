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

## First-time setup

Do this on **both PCs**, from the repository root. Docker Engine, Docker Compose
and Python 3 must be installed. Docker must use its default iptables firewall
backend. Stop the old PurpleAI containers before starting this setup.

1. Copy the settings and generate a gateway password:

   ```sh
   cp deploy/sandbox/.env.example deploy/sandbox/.env
   openssl rand -hex 32
   getent ahostsv4 llm.hpc.ntnu.no
   ```

1. Edit `deploy/sandbox/.env`. Check the PC/router addresses, set `IDUN_IP` to a
   current address from the lookup, and paste the generated password into
   `GATEWAY_TOKEN`. Use a different password on each PC. Reserve the PC addresses
   in the router so they stay fixed.

1. Create the key file with your editor. Put **only your Idun API key** in it:

   ```sh
   mkdir -p deploy/sandbox/secrets
   chmod 700 deploy/sandbox/secrets
   nano deploy/sandbox/secrets/idun_key
   chmod 444 deploy/sandbox/secrets/idun_key
   chmod 600 deploy/sandbox/.env
   ```

   The protected directory prevents other host users reading the key. The file
   is mounted read-only into the non-root gateway. Keys/settings are Git-ignored
   and excluded from image builds.

## Everyday commands

On **BlueAI**, start the defender and target:

```sh
sudo python3 deploy/sandbox/start.py blue
```

On **RedAI**, start the gateway and build the attacker:

```sh
sudo python3 deploy/sandbox/start.py red
```

Startup enables bridge filtering and installs the firewall using your `.env`
settings before starting containers. It refuses to rewrite rules while the lab
is running: use `stop` first if changing settings or restarting the setup.

Run the connection checks on **both PCs** before using the attacker:

```sh
sudo python3 deploy/sandbox/start.py blue check  # on BlueAI
sudo python3 deploy/sandbox/start.py red check   # on RedAI
```

Then, on RedAI:

```sh
sudo python3 deploy/sandbox/start.py red run
```

Other commands use the same form:

| Command                                    | Purpose                                           |
| ------------------------------------------ | ------------------------------------------------- |
| `start.py red shell`                       | Open a manual shell inside the attacker container |
| `start.py red logs` / `start.py blue logs` | Show the last 100 log lines                       |
| `start.py red stop` / `start.py blue stop` | Stop that PC's lab and discard temporary data     |

Prefix these with `sudo python3 deploy/sandbox/`, as above. Use this entry point
instead of direct Compose commands: `run`, `shell`, and `check` verify the firewall
first. After a PC reboot or Docker/firewall restart, stop/start the lab and repeat
its checks. Firewall rules remain after stopping; startup reinstalls them.

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

Gateway calls are limited to one configured model, non-streaming chat completions,
2048 output tokens, and one call at a time. `GATEWAY_CALL_LIMIT` limits attempts
per gateway process lifetime; restarting it resets the count. Use synthetic lab
data: requests may reach Idun and appear in defender logs.

The checks test TCP reachability, not authenticated inference. A failed connection
may also mean no service is listening. Confirm blocked probes increase the DROP
counters (`sudo iptables -nvL PAI_RED_FWD` or `PAI_BLUE_FWD`; host blocks use
`PAI_RED_HOST`/`PAI_BLUE_HOST`), and verify BlueAI port 8080 is blocked from a third
LAN machine before granting broader tools. These runtime checks are still needed
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
