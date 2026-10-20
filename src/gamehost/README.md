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

## Normal traffic

`docker-compose.yml` runs `traffic/normal-traffic.js` with k6. Its scenarios
exercise VulnShop login, browsing, and purchases. From the repository root,
set the defender address reachable from the traffic container:

```bash
TARGET=http://BLUEAI_IP:8080 docker compose -f src/gamehost/docker-compose.yml run --rm traffic
```

Replace `BLUEAI_IP` with BlueAI's lab address. The Compose default is
`http://localhost:8080`, which refers to the traffic container's loopback
address. An explicit target is needed when the defender runs on another
host. Scenario durations and concurrency are defined in the script.
