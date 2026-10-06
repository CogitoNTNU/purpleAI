# First-time gamehost setup

Do this once for a new installation. Existing hosts with working Docker, SSH and
sudo permissions can skip those sections. Revisit them only if host accounts,
SSH keys or repository paths change. Permission changes take effect immediately;
a reboot is not required. Docker group changes require a new login session.

After setup, follow the [run guide](README.md). It contains the everyday commands.
Every command block identifies the PC and working directory. Apart from the
initial clone, commands run from **`~/purpleAI`**, the repository root. Replace
that path if needed. All three PCs must use the same code version.

Follow the sections in order: prepare the checkouts, configure the sandbox and
collector, set up management access, then start collector → BlueAI → RedAI.
For a new installation, keep `DIRECT_TESTING=false` and `DEV_IP` empty.
Optional access for tests is covered in the [manual testing guide](../../deploy/sandbox/TESTING.md).

## 1. Prepare the hosts

On each PC, use a checkout of this sandbox branch at `~/purpleAI`. For a new
checkout only, clone it from the home directory. Skip this block if the
repository already exists.

**Gamehost, RedAI and BlueAI — separately on each PC, home directory (`~`):**

```sh
cd ~
git clone --branch two-pc-sandbox https://github.com/CogitoNTNU/purpleAI.git purpleAI
```

RedAI and BlueAI need Docker Engine, Docker Compose and Python 3. Complete the
[sandbox's first-time configuration](../../deploy/sandbox/README.md#first-time-configuration)
on both PCs; leave them stopped until collector delivery is configured below.

Gamehost needs Docker Engine, Docker Compose, Python 3, Git, OpenSSL, curl and SSH.
Run the gamehost script as your normal management user so it uses your SSH keys
and aliases. That user needs Docker access.

**Gamehost — repository root:** verify Docker access.

```sh
cd ~/purpleAI
docker compose version
docker ps
```

If `docker ps` reports permission denied, grant your trusted management account
Docker access. **Gamehost — repository root:**

```sh
cd ~/purpleAI
sudo usermod -aG docker "$USER"
```

Log out and back in, then repeat `docker ps` from the first block. Docker access
grants host administration privileges; keep it outside agent containers.

## 2. Configure the collector and agent delivery

**Gamehost — repository root:** create settings and generate one collector token.
`cp -n` preserves an existing file.

```sh
cd ~/purpleAI
cp -n src/gamehost/.env.example src/gamehost/.env
openssl rand -hex 32
nano src/gamehost/.env
chmod 600 src/gamehost/.env
```

| Setting in `src/gamehost/.env` | What to enter                                                  |
| ------------------------------ | -------------------------------------------------------------- |
| `GAMEHOST_LOG_BIND`            | Gamehost's LAN IPv4 address, currently `192.168.0.110`         |
| `GAMEHOST_LOG_TOKEN`           | The generated token                                            |
| `RED_SSH`                      | Gamehost's SSH destination for RedAI, for example `redai`      |
| `BLUE_SSH`                     | Gamehost's SSH destination for BlueAI, for example `blueai`    |
| `REMOTE_REPO`                  | Repository path on both lab PCs; `purpleAI` means `~/purpleAI` |
| `BLUE_IP`                      | BlueAI's LAN IPv4 address, currently `192.168.0.120`           |

SSH destinations may be existing aliases or `user@PC-address`. Reserve gamehost's
LAN address in the router. A new collector token can be generated at any time,
but all three PCs must be updated together.

**RedAI and BlueAI — separately on each PC, repository root:**

```sh
cd ~/purpleAI
nano deploy/sandbox/.env
```

Set `GAMEHOST_IP=192.168.0.110` (or your gamehost address) and set
`LOG_COLLECTOR_TOKEN` to the same value as gamehost's `GAMEHOST_LOG_TOKEN`.
Set both together. This collector token is shared across the PCs; each PC's
`GATEWAY_TOKEN` is separate. Models stay in the agents' own `.env` files.

## 3. Set up management access once

### SSH from gamehost

The gamehost user must be able to connect to both lab PCs using SSH keys.
Connect once to confirm host identities and test access. The examples use the
aliases in `.env`; replace them if your `RED_SSH` / `BLUE_SSH` values differ.

**Gamehost — repository root:**

```sh
cd ~/purpleAI
ssh blueai hostname
ssh redai hostname
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes blueai hostname
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes redai hostname
```

The last two commands must succeed without a password prompt. If they fail,
configure SSH key access before continuing. SSH keys stay on gamehost, outside
the collector and agent containers.

### Passwordless sudo on the lab PCs

The runner uses `sudo -n` over SSH to operate the sandbox. Configure this once
per lab-PC account; **skip it on the existing working hosts**. The examples use
BlueAI account `blue-ai` and RedAI account `purpleai`. If an account or checkout
path differs, change the username and absolute script path in its rule.

**BlueAI — repository root:**

```sh
cd ~/purpleAI
sudo visudo -f /etc/sudoers.d/purpleai-sandbox
```

Add:

```text
blue-ai ALL=(root) NOPASSWD: /usr/bin/python3 /home/blue-ai/purpleAI/deploy/sandbox/start.py blue *
```

**RedAI — repository root:**

```sh
cd ~/purpleAI
sudo visudo -f /etc/sudoers.d/purpleai-sandbox
```

Add:

```text
purpleai ALL=(root) NOPASSWD: /usr/bin/python3 /home/purpleai/purpleAI/deploy/sandbox/start.py red *
```

Save and exit. `visudo` validates the file, and valid rules take effect immediately.
These trusted host accounts can execute the sandbox script as root. Containers
have no access to this repository or sudo permission. Other sudo commands still
require a password.

## 4. Start and verify

Start the collector first. **Gamehost — repository root:**

```sh
cd ~/purpleAI
docker compose --env-file src/gamehost/.env -f src/gamehost/docker-compose.yml up --build -d --wait collector
curl --max-time 5 http://192.168.0.110:8765/health
```

Replace the curl address if `GAMEHOST_LOG_BIND` differs. The response should be
`ok`. Now [start and check both lab PCs](../../deploy/sandbox/README.md#start-or-rebuild-the-lab).
Every check should pass, including authenticated event delivery.

Finally verify the runner's exact SSH/sudo access from gamehost. Adjust the SSH
aliases and home paths if your installation differs.

**Gamehost — repository root:**

```sh
cd ~/purpleAI
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes blueai 'sudo -n /usr/bin/python3 /home/blue-ai/purpleAI/deploy/sandbox/start.py blue check'
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes redai 'sudo -n /usr/bin/python3 /home/purpleai/purpleAI/deploy/sandbox/start.py red check'
```

Once both commands pass, setup is complete. Continue with
[running an experiment](README.md#run-an-experiment). Future runs require no
SSH, sudo or token setup changes.
