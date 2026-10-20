# Defender agent

The defender is a Flask reverse proxy on port 8080. It sends each request's
method, URL, and body to IDUN classifiers for SQL injection and XSS. A
positive classification blocks the request with HTTP 403. A classifier
exception also blocks with HTTP 403. Otherwise, the request is forwarded
to `TARGET` and the upstream response is returned.

`defender.py` defines the proxy, `sql_injection_agent`,
`cross_site_scripting_agent`, and their `AGENTS` list. Evaluation stops
when a classifier reports an attack. The configured model is
`openai/gpt-oss-120b`.

## Compose setup

`src/defender/docker-compose.full.yml` runs VulnShop and the defender.
Create `src/.env` with the IDUN credentials read by that Compose file:

```env
IDUNN_BASE_URL=https://llm.hpc.ntnu.no/v1
IDUNN_API_KEY=your-idun-api-key
```

From the repository root:

```bash
mkdir -p src/defender/logs
docker compose -f src/defender/docker-compose.full.yml up -d --build
docker compose -f src/defender/docker-compose.full.yml logs -f defender
```

This publishes the defender on host port 8080 and keeps VulnShop's port
5000 inside the backend network. The defender target is
`http://vulnerable-app:5000`. The Docker build context is `src/`, including
the shared logger.

`docker-compose.app.yml` is the app-only alternative: it publishes VulnShop
directly on host port 8080. Run one setup at a time.

## Events

`event_logging.py` configures `src/purpleai_logging.py` with source
`defender-agent` and actor `defender`. Proxy code calls
`log_event("action", **fields)`.

- `request_decision`: `allowed`, `blocked`, or `error`, plus the decision.
- `request_result`: upstream HTTP status or forwarding error type.
- `request_id`: links a decision with its upstream result.

Events include HTTP method and URL path. They are printed to stdout and
appended as JSONL. The full Compose setup mounts the host directory
`src/defender/logs/` at `/var/log/purpleai` in the container and sets
`PURPLEAI_LOG_FILE=/var/log/purpleai/events.jsonl`. Direct Python execution
uses `logs/events.jsonl` beside the adapter unless that variable is set.

See [Vector setup](../../../deploy/vector/README.md) for host services
and forwarding, and [event format](../../../docs/event-format.md) for fields.

## Request checks

```bash
curl http://localhost:8080/
curl -G http://localhost:8080/search --data-urlencode "q=' OR 1=1--"
```

Inspect both the response and the corresponding events. The classifications
are model outputs, not guaranteed detection results. Requests wait for
classification before forwarding. The proxy uses Flask's development
server and plain HTTP.
