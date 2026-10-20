# Vector logging

```text
attacker JSONL → host Vector ─┐
                             ├→ gamehost Vector → daily JSONL files
defender JSONL → host Vector ─┘
```

Use `agent.yaml` on both sending hosts and `gamehost.yaml` on gamehost.
The examples use gamehost `192.168.0.110:6000`; change both configs if needed.
No custom Python collector or shared HTTP token is needed.

## 1. Write the files

The attacker writes `src/nmap-agent/logs/events.jsonl` by default.
The defender Compose setups bind-mount `src/defender/logs/` and write
`src/defender/logs/events.jsonl` on the host. Create that directory before
starting Compose. Rebuild the defender image to include the logger.

On each sending host, change `include` in `agent.yaml` to the **absolute
host path** of its `events.jsonl`. This avoids moving files or changing
application permissions. Alternatively, set `PURPLEAI_LOG_FILE` for an
application to write at a different path. It must be writable by the
application and readable by the `vector` service user; Vector also needs
search permission on every parent directory.

Events retain their IDs, timestamps, source, actor, and action. Vector
adds the sending hostname and input file path. Defender events include
allow/block decisions, classifier errors, and upstream results linked by
`request_id`. Bodies, query strings, headers, and exception messages are
excluded; URL paths are recorded.

File output uses Python's built-in `logging.handlers.WatchedFileHandler`;
no additional logging dependency is required.

Remove old `LOG_COLLECTOR_URL` and `LOG_COLLECTOR_TOKEN` settings from the
attacker environment. The attacker now writes files only.

## 2. Configure the installed Vector services

On gamehost, prepare its output directory:

```bash
sudo install -d -o vector -g vector -m 0750 /var/log/purpleai/collected
```

Copy `gamehost.yaml` to `/etc/vector/vector.yaml` on gamehost, and your
edited `agent.yaml` to `/etc/vector/vector.yaml` on attacker and defender.
Back up any existing configuration first. These instructions assume the
standard Linux package's `vector` user, state directory `/var/lib/vector`,
and systemd unit. Keep that state directory writable by Vector.

Validate and restart on each host, starting with gamehost:

```bash
sudo -u vector vector validate /etc/vector/vector.yaml
sudo systemctl restart vector
sudo journalctl -u vector -n 30 --no-pager
```

Permit TCP `6000` on gamehost only from the two sending hosts. These
minimal configs use unencrypted Vector transport on the controlled lab
network. Containers need no access to the gamehost: only the host Vector
processes send logs. For an untrusted network, add TLS with client
certificates using Vector's native TLS settings.

## 3. Check delivery

Run an attacker task and send a request through the defender. On gamehost:

```bash
tail -F /var/log/purpleai/collected/events-$(date -u +%F).jsonl
```

Check for both `nmap-agent` and `defender-agent` source values. Stop
gamehost Vector, produce more events, restart it, and confirm the pending
events arrive. Restart a sender's Vector and confirm it resumes from its
checkpoint. This verifies actual host paths, permissions, and connectivity.

## Storage

Vector keeps file checkpoints and a roughly 256 MiB disk buffer per sink
under `/var/lib/vector`. A full buffer applies backpressure; unread events
remain in the source files. Keep those files and the state directory across
restarts. Delivery can produce duplicates, identified by `event_id`; this
is not an exactly-once archive or a power-loss-proof audit store.

The file handler checks for rotation before each event. For rotation, use
rename/create (not copytruncate), keep rotated files uncompressed until
Vector has read them, and set retention longer than the longest expected
outage. If rotating, extend `include` to `events.jsonl*` and exclude `*.gz`
so unread rotated files are discovered even after a Vector restart.
Daily gamehost files also need a retention policy. Neither source
files nor daily archives are automatically deleted by these configs.

Configs validated and delivery/restart recovery tested locally with Vector
0.60.0. Run validation with the version installed on each host before use.

References: [file source](https://vector.dev/docs/reference/configuration/sources/file/),
[Vector sink](https://vector.dev/docs/reference/configuration/sinks/vector/),
[Vector source](https://vector.dev/docs/reference/configuration/sources/vector/).
