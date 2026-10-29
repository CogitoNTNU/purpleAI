# Vector logging

```text
RedAI JSONL  → host Vector ─┐
                           ├→ gamehost Vector → daily JSONL files
BlueAI JSONL → host Vector ─┘
```

## Application files

Both agents use `src/purpleai_logging.py`. Python's `WatchedFileHandler`
handles file output and detects rename/create rotation. Each event is
also printed to stdout. Agent code calls `log_event("action", **fields)`.

| Component | Configuration adapter | Default host log file |
| --- | --- | --- |
| Attacker | `src/Attacker/event_logging.py` | `src/Attacker/logs/events.jsonl` |
| Defender in Compose | `src/defender/defender-agent/event_logging.py` | `src/defender/logs/events.jsonl` |

Paths in this table are relative to the repository root. Running the
Defender directly writes beside its adapter at
`src/defender/defender-agent/logs/events.jsonl`. The full Compose setup sets the container's
`PURPLEAI_LOG_FILE` and bind-mounts its log directory onto the host.

The adapters select the source, actor, and default path. The shared logger
supplies schema version, event/run IDs, and UTC timestamps. The optional
`PURPLEAI_LOG_FILE` overrides the application path; defaults require no
logging variables in application `.env` files.

Defender events record allow/block decisions, classifier errors, and
upstream results linked by `request_id`. They include method and URL path;
request bodies, query strings, headers, and exception messages are omitted.

See [event format](../../docs/event-format.md) for the envelope and actions.

## Host configuration

Vector runs as a systemd service under the host's normal login account.
Run setup commands as that account, using `sudo` only where shown.

Confirm the installed binary is available:

```bash
vector --version
```

On every host:

```bash
sudo mkdir -p /etc/vector
sudo install -d -o "$(id -un)" -g "$(id -gn)" -m 0750 /var/lib/vector
```

On gamehost, also create the archive directory:

```bash
sudo install -d -o "$(id -un)" -g "$(id -gn)" -m 0750 /var/log/purpleai/collected
```

From the repository root, copy the receiver config on gamehost:

```bash
sudo cp deploy/vector/gamehost.yaml /etc/vector/vector.yaml
```

On RedAI and BlueAI, copy the sender config:

```bash
sudo cp deploy/vector/agent.yaml /etc/vector/vector.yaml
```

Edit `/etc/vector/vector.yaml` for that host:

- Sender `include`: absolute host path from the application-files table.
- Sender `address`: `http://GAMEHOST_IP:6000`.
- Receiver `address`: gamehost's listening IP and port, or `0.0.0.0:6000`.

The checked-in examples use `192.168.0.110:6000`. The sender service account
needs read access to the log and search access to its parent directories.
The application needs write access. Create the host log directory before
starting the defender's Compose service.

Validate with the same account that will run Vector:

```bash
vector validate /etc/vector/vector.yaml
```

## Service

Run this on each host after validation. It embeds the current username
and the absolute installed Vector binary path in the service file.

```bash
sudo tee /etc/systemd/system/vector.service >/dev/null <<UNIT
[Unit]
Description=PurpleAI Vector logging
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$(id -un)
ExecStart=$(command -v vector) --config /etc/vector/vector.yaml
Restart=on-failure
RestartSec=5
TimeoutStopSec=90

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now vector
sudo systemctl status vector --no-pager
```

Start gamehost before the senders. Stop any foreground Vector process
using this configuration before starting its service. After editing an
existing service's configuration, validate and run
`sudo systemctl restart vector`.

TCP 6000 carries unencrypted Vector transport on the lab network. Permit
it on gamehost from the sending hosts. Container applications write files;
the host Vector processes make the connection to gamehost.

## Check delivery

Run an attacker task and send a request through the defender. On gamehost:

```bash
tail -F /var/log/purpleai/collected/events-$(date -u +%F).jsonl
```

Check for `attacker-agent` and `defender-agent` source values. Service diagnostics:

```bash
sudo journalctl -u vector -n 40 --no-pager
```

## Storage

Vector keeps file checkpoints and a roughly 256 MiB disk buffer per sink
under `/var/lib/vector`. Full buffers apply backpressure. Delivery retries
can produce duplicates; `event_id` identifies an event across retries.

The configs do not delete source logs or daily archives. For file rotation,
use rename/create, retain files through expected outages, and include
rotated files in the source's `include` pattern. Keep them uncompressed
until read. Preserve Vector's state directory across restarts.

References: [file source](https://vector.dev/docs/reference/configuration/sources/file/),
[Vector sink](https://vector.dev/docs/reference/configuration/sinks/vector/),
[Vector source](https://vector.dev/docs/reference/configuration/sources/vector/).

## Dashboard

The gamehost dashboard in `src/gamehost/dashboard/` reads these same daily
archives. Run it as the gamehost Vector account so it can read the archive
files. See [dashboard guide](../../src/gamehost/dashboard/DASHBOARD.md).
