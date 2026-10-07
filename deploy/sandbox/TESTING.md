# Manual testing

Use this guide for tools, scripts and individual agent runs. Gamehost and its
collector are optional. For coordinated runs and saved events, use the
[gamehost guide](../../src/gamehost/README.md).

| Test                              | Target URL                  | Behavior                                                            |
| --------------------------------- | --------------------------- | ------------------------------------------------------------------- |
| With defender                     | `http://192.168.0.120:8080` | Defender checks requests, then blocks or forwards them              |
| Without defender (direct testing) | `http://192.168.0.120:8081` | Requests go straight to VulnShop; no defender checks or model calls |

Both ports use the **same app and data**. Enabling direct testing leaves the
defender running on 8080; choose the URL for each test. Avoid manual attacks
during a managed gamehost run.

Start with the [sandbox setup](README.md). Replace `192.168.0.120` if your
`BLUE_IP` differs. Commands identify the PC and start from **`~/purpleAI`**,
the repository root; replace that path if needed.

- **Native tools on RedAI:** only BlueAI's stack needs to run.
- **Tools or agents in RedAI's container:** both stacks must run.
- **Your own PC:** allow its address on BlueAI as described below.

## Enable direct access on BlueAI

Skip this section for tests through the defender only. For port 8081, set
`DIRECT_TESTING=true` in `deploy/sandbox/.env` on:

- **BlueAI:** always, to publish VulnShop on 8081.
- **RedAI:** also for container attacks, including gamehost's `--without-defender`.
  Native Kali tools and attacks from your PC need only the BlueAI change.

Docker Compose 2.33.1 or newer is required for the
[direct endpoint's network setting](https://docs.docker.com/reference/compose-file/services/#gw_priority).
If these settings are already applied, no restart is needed.

**BlueAI — repository root:** edit `DIRECT_TESTING`, save, then apply it.
**Stopping BlueAI clears VulnShop's temporary database, uploads and reports.**

```sh
cd ~/purpleAI
docker compose version
nano deploy/sandbox/.env
sudo python3 deploy/sandbox/start.py blue stop
sudo python3 deploy/sandbox/start.py blue start
sudo python3 deploy/sandbox/start.py blue check --no-collector
```

**RedAI — repository root, for container attacks:** apply the same setting.
BlueAI must already permit 8081.

```sh
cd ~/purpleAI
nano deploy/sandbox/.env
sudo python3 deploy/sandbox/start.py red stop
sudo python3 deploy/sandbox/start.py red start
sudo python3 deploy/sandbox/start.py red check --no-collector
```

Every check should pass. `--no-collector` skips collector reachability and event
delivery while keeping isolation checks. Omit it to verify delivery too.
`DIRECT_TESTING` enables access; it does not change the default target.

## From your own development PC

Your PC needs a route to BlueAI. Set `DEV_IP` in **BlueAI's**
`deploy/sandbox/.env` to your PC's LAN IPv4 address, for example `192.168.0.150`.
Leave `DIRECT_TESTING=false` for port 8080 only; set it to `true` for both ports.
Neither setting is needed for a normal gamehost run.

**BlueAI — repository root:** edit these values, save, and apply them.
Skip this block if they are already applied.

```sh
cd ~/purpleAI
nano deploy/sandbox/.env
sudo python3 deploy/sandbox/start.py blue stop
sudo python3 deploy/sandbox/start.py blue start
sudo python3 deploy/sandbox/start.py blue check --no-collector
```

This clears temporary target data. Only BlueAI needs a change for your PC.
`DEV_IP` grants access to the app, not the private gateway or backend network.
Reserve your PC's address in the router. With a VPN/Tailscale subnet route, use
**the source address BlueAI sees**, which may be translated and shared by other
PCs. Do not use localhost or BlueAI's own address.

Open the chosen URL from the table in your browser, or use the tool commands
below. No local checkout is needed for browser or raw tool tests; run from any
existing directory if you have no `~/purpleAI` checkout.

## Tools and scripts directly on RedAI

These commands also work on an allowed development PC with curl and Nmap
installed. Raw tools need no agent settings or Idun key. Native tools run with
your host permissions; use the container section for sandboxed execution.

**RedAI or development PC — repository root:** test with the defender.

```sh
cd ~/purpleAI
curl --max-time 180 -i http://192.168.0.120:8080/
nmap -sT -sV -Pn -p 8080 192.168.0.120
```

**RedAI or development PC — repository root:** test without the defender,
after enabling direct access.

```sh
cd ~/purpleAI
curl --max-time 10 -i http://192.168.0.120:8081/
nmap -sT -sV -Pn -p 8081 192.168.0.120
```

Give other tools/scripts the matching URL or IP and port. Nmap identifies the
service on that port; use HTTP requests or scripts to test vulnerabilities.
For tools available only on Kali, SSH to RedAI and run them there.

## Tools or the agent inside the RedAI sandbox

Start both stacks. For direct tests, enable `DIRECT_TESTING` on both as above.
Choose the attacker entry point and model in `src/attacker/.env`.

**RedAI — repository root:** run the selected agent through the defender.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red run --target defender
```

**RedAI — repository root:** run it directly against VulnShop.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red run --target direct
```

Omitting `--target` selects the defender. The launcher supplies the matching
`TARGET_URL`, `TARGET_PORT` and event mode; do not set `PURPLEAI_TARGET_MODE`
in the agent's `.env` for sandbox runs. The attacker still uses its own model
when testing without the defender.

**RedAI — repository root:** open a shell for manual tools against port 8081.
Use `--target defender` instead for port 8080.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red shell --target direct
```

**Inside the attacker container — `/app`:**

```sh
cd /app
curl --max-time 10 -i "$TARGET_URL/"
nmap -sT -sV -Pn -p "$TARGET_PORT" 192.168.0.120
exit
```

The image includes Nmap, curl and Python. To add tools, update
`src/attacker/system-packages.txt` and [rebuild RedAI](README.md#start-or-rebuild-the-lab).
Use the [integration guide](../../docs/agents.md) for agent dependencies.
The shell cannot install system packages or access host files.
Events print locally; configured collector delivery remains best effort.
For a fully standalone lab, leave `GAMEHOST_IP` and `LOG_COLLECTOR_TOKEN` empty
in deployment `.env`.

## Run an attacker workflow on your PC

This example runs the supplied Nmap workflow on macOS/Linux with Python 3.12+
and Nmap on `PATH`. Your PC needs a checkout, allowed access to BlueAI and access
to Idun. It calls Idun directly with your key; BlueAI's gateway remains private.
The same procedure works for a native workflow on RedAI.

**Development PC — repository root:** install role dependencies and configure it.

```sh
cd ~/purpleAI
python3 -m venv src/attacker/.venv
src/attacker/.venv/bin/python3 -m pip install -r src/attacker/requirements.txt
cp -n src/attacker/.env.example src/attacker/.env
nano src/attacker/.env
chmod 600 src/attacker/.env
```

For direct testing, set these in `src/attacker/.env`:

```dotenv
ATTACKER_MODULE=agents.nmap.main
TARGET_URL=http://192.168.0.120:8081
IDUN_BASE_URL=https://llm.hpc.ntnu.no/v1
IDUN_API_KEY=your-idun-api-key
AGENT_MODEL=openai/gpt-oss-120b
PURPLEAI_TARGET_MODE=without_defender
```

For defended testing, use port 8080 and `PURPLEAI_TARGET_MODE=with_defender`.
The mode labels events; `TARGET_URL` selects the destination. Leave collector
settings unset for local output only. Exported environment variables override
`.env`. Keep the key in the ignored file, never in source or command arguments.

**Development PC — `~/purpleAI/src/attacker`:** launch the configured workflow.
This directory lets it load `.env`; `PYTHONPATH` supplies the shared runtime.

```sh
cd ~/purpleAI/src/attacker
PYTHONPATH="$PWD/.." .venv/bin/python3 -m purpleai.agent_runtime attacker
```

## Return to defended-only testing

Set `DIRECT_TESTING=false` in deployment `.env` on each PC where you enabled it,
then [stop/start/check those stacks](README.md#start-or-rebuild-the-lab).
To remove your PC's access as well, clear `DEV_IP` on BlueAI before rebuilding.
For manual checks with a stopped collector, use `--no-collector` as shown above.

BlueAI closes 8081; RedAI's check should show it `unreachable` as a `PASS`.
Editing `.env` or switching Git branches alone does not remove running
containers or firewall rules. Switching ports also does not reset app data;
stop/start BlueAI when a test needs a fresh target.

## Troubleshooting

| Symptom                | Check                                                                                                                          |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| 8080 returns 403       | Inspect [BlueAI logs](README.md#logs-shell-and-shutdown): the defender may have blocked an attack or encountered a model error |
| 8081 unreachable       | Direct access must be applied on BlueAI; container attacks also need it on RedAI                                               |
| Your PC cannot connect | Check its route and the source address in BlueAI's `DEV_IP`; VPNs, VMs and containers may use another address                  |
| Policy mismatch        | [Stop/start/check](README.md#start-or-rebuild-the-lab); editing deployment `.env` alone does not apply it                      |
| Collector unavailable  | Use `--no-collector` for manual checks, or [start the collector](../../src/gamehost/README.md#run-an-experiment)               |

Use synthetic lab data. Direct access still blocks VulnShop from initiating
connections to the host, LAN, gateway or internet.
