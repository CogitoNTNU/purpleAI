# VulnShop

VulnShop is a deliberately vulnerable Flask/SQLite web application for
isolated lab exercises. `app.py` implements login, profiles, product
search and comments, checkout, uploads/downloads, and admin routes.
See [VULNERABILITIES.md](VULNERABILITIES.md) for the planted vulnerabilities.

## Run behind the defender

The Compose file is `src/defender/docker-compose.full.yml`. It runs
`vulnerable-app` on an internal backend network and publishes the defender
on port 8080. Create `src/.env` with `IDUNN_BASE_URL` and `IDUNN_API_KEY` for the
Compose `env_file`. Then run from the repository root:

```bash
mkdir -p src/defender/logs
docker compose -f src/defender/docker-compose.full.yml up -d --build
```

Send requests through `http://localhost:8080`. The app's port 5000 is not
published by this Compose configuration.

```bash
docker compose -f src/defender/docker-compose.full.yml logs -f defender
```

The defender writes structured events to `src/defender/logs/events.jsonl`
on the host. See [Vector setup](../../../deploy/vector/README.md).

## Run directly

From this directory, with a Python environment activated:

```bash
pip install -r requirements.txt
python app.py
```

This starts the Flask development server on `0.0.0.0:5000` with debug
mode enabled. The database is `vulnshop.db` beside `app.py`; initialization
creates tables and seeds records when the database is first created.

[Defender setup](DEFENDER_SETUP.md) covers requests through the proxy.
The k6 traffic generator is in `src/gamehost/traffic/`, with its own
Compose file under `src/gamehost/`.
