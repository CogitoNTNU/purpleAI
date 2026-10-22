# Gamehost

## Event collection

Gamehost runs Vector as a systemd service. Host Vector agents on RedAI
and BlueAI tail application JSONL files and forward them to TCP 6000.
Gamehost writes daily archives under `/var/log/purpleai/collected/`.

Configuration is `/etc/vector/vector.yaml`. See
[Vector setup](../../deploy/vector/README.md) and the
[event format](../../docs/event-format.md).

```bash
sudo systemctl status vector --no-pager
sudo journalctl -u vector -n 40 --no-pager
tail -F /var/log/purpleai/collected/events-$(date -u +%F).jsonl
```

## Dashboard

`dashboard/dashboard.py` reads the same daily archives and refreshes every
five seconds while the browser session is active. The dashboard account
needs read access to the archive files and search access to their parent
directories. Run it as the account used by the gamehost Vector service.

From the repository root:

```bash
uv sync --locked
bash src/gamehost/dashboard/run_dashboard.sh
```

Open `http://GAMEHOST_IP:8501`. The dashboard reads all matching daily
archives, orders events by timestamp, and counts repeated `event_id`
values once. See [dashboard guide](dashboard/DASHBOARD.md).

## Normal traffic

The gamehost Compose service uses k6 to send ordinary browsing, login,
and purchase requests through BlueAI's defender. It uses the app's seeded
`alice` and `bob` accounts and the products defined in VulnShop.

From the repository root on gamehost, start it with BlueAI's lab address:

```bash
export TARGET=http://192.168.0.120:8080
docker compose -f src/gamehost/docker-compose.yml up -d traffic
```

The address is an example; use your BlueAI defender's reachable IP and
port. `TARGET` is required, so the service cannot silently target the
traffic container's loopback address.

The default is one virtual user, with three seconds between activities.
Each k6 run lasts ten minutes; Compose restarts it for continuing background
traffic. `K6_VUS` and `K6_DURATION` can override the defaults when starting
the service. Requests also wait for defender classification, so actual
request rate depends on IDUN latency.

Inspect or stop it, keeping `TARGET` exported in that terminal:

```bash
docker compose -f src/gamehost/docker-compose.yml logs -f traffic
docker compose -f src/gamehost/docker-compose.yml down
```

For a single foreground run that exits after one minute:

```bash
K6_DURATION=1m docker compose -f src/gamehost/docker-compose.yml run --rm traffic
```

Every HTTP request goes through the existing defender, which produces
`request_decision` and, when forwarded, `request_result` events. BlueAI's
Vector sends those events to gamehost, where they appear in the archive
and dashboard. k6's checks report HTTP outcomes in its own output; the
dashboard does not label these requests as normal traffic or calculate a
false-positive rate.
