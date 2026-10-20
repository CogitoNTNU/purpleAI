# VulnShop

VulnShop is a deliberately vulnerable Flask/SQLite web application for
isolated lab exercises. `app.py` implements login, profiles, product
search and comments, checkout, uploads/downloads, and admin routes.
See [VULNERABILITIES.md](VULNERABILITIES.md) for the planted vulnerabilities.

## Run behind the defender

The Compose file is `src/defender/docker-compose.yml`. It runs
`vulnerable-app` on an internal backend network and publishes the defender
on port 8080. From the repository root:

```bash
export IDUNN_BASE_URL=https://llm.hpc.ntnu.no/v1
export IDUNN_API_KEY=your-idun-api-key
mkdir -p src/defender/logs
docker compose -f src/defender/docker-compose.yml up -d --build
```

Send requests through `http://localhost:8080`. The app's port 5000 is not
published by this Compose configuration.

```bash
docker compose -f src/defender/docker-compose.yml logs -f defender
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
