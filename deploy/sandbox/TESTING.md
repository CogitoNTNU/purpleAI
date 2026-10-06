# Manual testing

Use this guide for tools, scripts and individual agent runs. Gamehost, normal
traffic and a log collector are not required. For coordinated experiments, use
the [gamehost runner](../../src/gamehost/README.md).

**Direct testing means testing VulnShop without the defender checking your
requests.** Requests go straight to VulnShop on port 8081. Port 8080 still goes
through the defender, which remains running.

First configure and start BlueAI using the [sandbox setup](README.md).
The examples below use `BLUE_IP=192.168.0.120`; replace that address if yours differs.
Every host command block starts from `~/purpleAI`, the repository root on the
named PC. Replace that directory if your checkout is elsewhere.

| Target           | URL                         | Behavior                                                               |
| ---------------- | --------------------------- | ---------------------------------------------------------------------- |
| With defender    | `http://192.168.0.120:8080` | Defender checks requests using Idun, then blocks or forwards them.     |
| Without defender | `http://192.168.0.120:8081` | Optional direct access to VulnShop; no defender checks or model calls. |

Both endpoints use the **same VulnShop instance and data**. The defender stays
running on 8080 when direct testing is enabled; choose the URL for each test.
Avoid manual attacks during a managed gamehost run.

## Enable direct access on BlueAI

This is optional and disabled by default. It permits RedAI, plus the optional development PC configured below, to
access 8081. Gamehost can coordinate [runs without the defender](../../src/gamehost/README.md#run-without-the-defender)
using the RedAI attacker; gamehost itself does not need direct HTTP access. Docker Compose 2.33.1 or newer is required for the
[direct endpoint's network gateway setting](https://docs.docker.com/reference/compose-file/services/#gw_priority).

**BlueAI — repository root:**

```sh
cd ~/purpleAI
docker compose version
nano deploy/sandbox/.env
```

Set `DIRECT_TESTING=true`, save, then apply it. **BlueAI — repository root:**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue stop
sudo python3 deploy/sandbox/start.py blue start
sudo python3 deploy/sandbox/start.py blue check --no-collector
```

Stop/start clears the target's temporary database, uploads and reports. It also
rebuilds images and installs the matching firewall policy. Use this sequence
after changing deployment settings. `--no-collector` skips collector availability
and event delivery during checks; firewall and network isolation checks still run.
It lets you test while a previously configured collector is stopped.

## Tools and scripts directly on RedAI

Only BlueAI needs to be running. Native Kali tools do not require the RedAI
Docker stack, agent settings or an Idun key. Open either URL above in RedAI's
browser, or test from a terminal.

**RedAI — repository root:** test through the defender.

```sh
cd ~/purpleAI
curl --max-time 180 -i http://192.168.0.120:8080/
nmap -sT -sV -Pn -p 8080 192.168.0.120
```

**RedAI — repository root:** test directly after enabling 8081 on BlueAI.

```sh
cd ~/purpleAI
curl --max-time 10 -i http://192.168.0.120:8081/
nmap -sT -sV -Pn -p 8081 192.168.0.120
```

Give your other tools/scripts the matching target URL or IP and port. Scanning
8080 shows the defender service; scanning 8081 shows the target service. A scan
alone does not exercise the planted vulnerabilities; use HTTP requests or scripts
for that. Tools running on the Kali host have your host permissions. Use the
attacker container below when you want the sandbox's restrictions.

## Tools or the agent inside the RedAI sandbox

Configure and start RedAI using the [sandbox setup](README.md). It defaults to
8080\. To also permit direct requests from its attacker container:

**RedAI — repository root:**

```sh
cd ~/purpleAI
nano deploy/sandbox/.env
```

Set `DIRECT_TESTING=true`, save, then apply it. **RedAI — repository root:**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red stop
sudo python3 deploy/sandbox/start.py red start
sudo python3 deploy/sandbox/start.py red check --no-collector
```

The check now requires both 8080 and 8081 to be reachable. BlueAI must already
have direct testing enabled. All check lines should show `PASS`.

**RedAI — repository root:** run the existing Nmap agent through the defender.
Choose its model in `src/nmap-agent/.env` as usual.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red run --target defender
```

**RedAI — repository root:** run that agent directly against VulnShop.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red run --target direct
```

Omitting `--target` selects the defender. The selected endpoint supplies both
`TARGET_URL` and `NMAP_PORT`; the agent cannot select another host or port.
The agent still needs Idun for its own model calls, even when the target bypasses
the defender.

**RedAI — repository root:** open a sandbox shell for manual tools.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py red shell --target direct
```

**Inside the attacker container — `/app`:**

```sh
cd /app
curl --max-time 10 -i "$TARGET_URL/"
nmap -sT -sV -Pn -p "$NMAP_PORT" 192.168.0.120
exit
```

Use `--target defender` for the protected URL instead. The image includes Nmap,
curl and Python. Add other tools to the attacker stage in the sandbox Dockerfile
and rebuild if needed. This shell runs as non-root; it cannot install packages or
access your host files. No collector is required; agent events still appear in
the terminal. If you previously configured collector delivery, the agents keep
attempting it on a best-effort basis. Leave `GAMEHOST_IP` and
`LOG_COLLECTOR_TOKEN` empty in deployment `.env` for a fully standalone lab.

## From your own development PC

Your PC must have a LAN route to BlueAI. No RedAI container or gamehost is needed.
Find your PC's **LAN IPv4 address** in its network settings, for example
`192.168.0.150`. Use that address, not `127.0.0.1`, a Docker address or the public
internet address. Reserve it in the router so it stays fixed.

**BlueAI — repository root:** allow that development PC.

```sh
cd ~/purpleAI
nano deploy/sandbox/.env
```

Set `DEV_IP=192.168.0.150`, replacing the example with your PC's address. Leave
`DIRECT_TESTING=false` for defender-only access, or set it to `true` for both
endpoints. Save, then apply the settings. **BlueAI — repository root:**

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue stop
sudo python3 deploy/sandbox/start.py blue start
sudo python3 deploy/sandbox/start.py blue check --no-collector
```

This clears temporary target data. Only BlueAI needs this change. `DEV_IP`
permits one development PC at a time; to use another, replace the address and
repeat stop/start/check. Other LAN PCs remain blocked from these endpoints.
It grants no access to the model gateway or the internal backend network.

**Development PC — repository root:** open the app in your browser at
`http://192.168.0.120:8080`, or `http://192.168.0.120:8081` with direct testing enabled.
For command-line tests on macOS/Linux (curl and Nmap must be installed):

```sh
cd ~/purpleAI
curl --max-time 180 -i http://192.168.0.120:8080/
curl --max-time 10 -i http://192.168.0.120:8081/
nmap -sT -sV -Pn -p 8080,8081 192.168.0.120
```

The 8081 request/scan succeeds only with direct testing enabled. Give your own
scripts or agents the chosen URL. No checkout is needed for browser/tools alone;
run those commands from any existing directory if you have no local repository.
Tools run locally with your PC's permissions. For tools available only on Kali,
SSH to RedAI and use the [native Kali instructions](#tools-and-scripts-directly-on-redai).

### Run the existing Nmap agent on your PC

This optional example is for macOS/Linux with Python 3.12 or newer and Nmap on
`PATH`. Use a local checkout of this branch. The agent calls Idun directly using
its own API key; BlueAI's model gateway remains private. Your PC therefore also
needs access to Idun. Raw tools/scripts that do not use a model need no Idun key.

**Development PC — repository root:** create an agent-specific virtual environment.
This does not change the repository's root virtual environment.

```sh
cd ~/purpleAI
python3 -m venv src/nmap-agent/.venv
src/nmap-agent/.venv/bin/python3 -m pip install -r src/nmap-agent/requirements.txt
cp -n src/nmap-agent/.env.example src/nmap-agent/.env
nano src/nmap-agent/.env
chmod 600 src/nmap-agent/.env
```

Set these values in `src/nmap-agent/.env` for direct testing, using your own Idun
key and chosen model:

```dotenv
TARGET_URL=http://192.168.0.120:8081
NMAP_PORT=8081
PURPLEAI_TARGET_MODE=without_defender
IDUN_BASE_URL=https://llm.hpc.ntnu.no/v1
IDUN_API_KEY=your-idun-api-key
AGENT_MODEL=openai/gpt-oss-120b
```

For defended testing, change `TARGET_URL` and `NMAP_PORT` to use 8080, and set
`PURPLEAI_TARGET_MODE=with_defender`. The mode labels any locally printed or sent events.
Leave `LOG_COLLECTOR_URL` and `LOG_COLLECTOR_TOKEN` unset; events print in the
terminal. Existing exported environment variables take precedence over `.env`.

**Development PC — `~/purpleAI/src/nmap-agent`:** run the agent. The working
folder lets it read its own `.env`; `PYTHONPATH` makes the shared sender available.

```sh
cd ~/purpleAI/src/nmap-agent
PYTHONPATH="$PWD/.." .venv/bin/python3 "$PWD/main.py"
```

The same setup works for a native agent run on RedAI. Direct local runs have
local host permissions; use the RedAI container for sandboxed agent execution.
Keep your Idun key in the ignored `.env`, never in source or command arguments.

To remove development-PC access, clear `DEV_IP` on BlueAI and repeat its
stop/start/check sequence. Changing or switching a Git branch alone does not
remove running containers or firewall rules.

## Return to defended-only testing

Set `DIRECT_TESTING=false` in deployment `.env` on each PC where you enabled it,
then stop/start each stack to apply the change.

**BlueAI — repository root:**

```sh
cd ~/purpleAI
nano deploy/sandbox/.env
sudo python3 deploy/sandbox/start.py blue stop
sudo python3 deploy/sandbox/start.py blue start
sudo python3 deploy/sandbox/start.py blue check --no-collector
```

**RedAI — repository root, if you enabled direct container access:**

```sh
cd ~/purpleAI
nano deploy/sandbox/.env
sudo python3 deploy/sandbox/start.py red stop
sudo python3 deploy/sandbox/start.py red start
sudo python3 deploy/sandbox/start.py red check --no-collector
```

BlueAI no longer publishes 8081. RedAI's check should show 8081 `unreachable` as
a `PASS`. Gamehost runs default to 8080; `--without-defender` selects 8081 and
runs only the attacker. See [both gamehost modes](../../src/gamehost/README.md).
Use its usual checks without `--no-collector` before a managed run.

## Troubleshooting

| Symptom                                     | Check                                                                                                                                                                                                     |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 8080 returns 403                            | Read `sudo python3 deploy/sandbox/start.py blue logs` from BlueAI's `~/purpleAI`. The defender may have detected an attack or failed to call its model. Use 8081 to test the target without those checks. |
| 8081 is unreachable from RedAI              | Set `DIRECT_TESTING=true` on BlueAI and stop/start it. For the attacker container, also enable it and stop/start on RedAI. Native Kali tools need only the BlueAI change.                                 |
| Cannot connect from your own PC             | Check `DEV_IP` on BlueAI, its applied policy and your LAN route. A VPN, VM or container may use a different source address; use the address BlueAI sees.                                                  |
| Firewall missing or changed                 | From that PC's `~/purpleAI`, run the full stop/start/check sequence above. Editing `.env` alone does not apply a policy.                                                                                  |
| Collector unreachable during a manual check | Use the full `sudo python3 deploy/sandbox/start.py blue check --no-collector` or `sudo python3 deploy/sandbox/start.py red check --no-collector` command from that PC's `~/purpleAI`.                     |

Direct access opens a path to the vulnerable app, so enable it only when needed.
VulnShop still cannot initiate connections to the host, LAN, gateway or internet.
Use synthetic data. For a clean comparison between test cases, stop/start BlueAI
between cases; switching ports alone does not reset target data.
