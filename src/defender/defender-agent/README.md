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

## Compose setups

Run commands from the repository root. Export IDUN credentials first:

```bash
export IDUNN_BASE_URL=https://llm.hpc.ntnu.no/v1
export IDUNN_API_KEY=your-idun-api-key
mkdir -p src/defender/logs
```

Choose the application's Compose file:

| Application | Compose file | Defender target |
| --- | --- | --- |
| VulnShop | `src/defender/docker-compose.yml` | `http://vulnerable-app:5000` |
| SecureReview | `src/defender/vulnerable-web/docker-compose.yml` | `http://backend:8000` |

For VulnShop:

```bash
docker compose -f src/defender/docker-compose.yml up -d --build
docker compose -f src/defender/docker-compose.yml logs -f defender
```

For SecureReview:

```bash
docker compose -f src/defender/vulnerable-web/docker-compose.yml up -d --build
docker compose -f src/defender/vulnerable-web/docker-compose.yml logs -f defender
```

Both publish the defender on host port 8080. Start one setup at a time.
Their Docker build context is `src/`, including the shared logger.

SecureReview also publishes Nginx on port 80. Its API and admin routes
connect directly to the Django backend, bypassing the defender. Use port
8080 to exercise defender classification. VulnShop's Compose setup only
publishes the defender and keeps its backend on an internal Docker network.

## Events

`event_logging.py` configures `src/purpleai_logging.py` with source
`defender-agent` and actor `defender`. Proxy code calls
`log_event("action", **fields)`.

- `request_decision`: `allowed`, `blocked`, or `error`, plus the decision.
- `request_result`: upstream HTTP status or forwarding error type.
- `request_id`: links a decision with its upstream result.

Events include HTTP method and URL path. They are printed to stdout and
appended as JSONL. Both Compose setups mount the host directory
`src/defender/logs/` at `/var/log/purpleai` in the container and set
`PURPLEAI_LOG_FILE=/var/log/purpleai/events.jsonl`. Direct Python execution
uses `logs/events.jsonl` beside the adapter unless that variable is set.

See [Vector setup](../../../deploy/vector/README.md) for host services
and forwarding, and [event format](../../../docs/event-format.md) for fields.

## Request checks

For VulnShop:

```bash
curl http://localhost:8080/
curl -G http://localhost:8080/search --data-urlencode "q=' OR 1=1--"
```

For SecureReview:

```bash
curl -G http://localhost:8080/api/businesses/ --data-urlencode 'search=pizza'
curl -G http://localhost:8080/api/businesses/ --data-urlencode "search=' OR 1=1--"
```

Inspect both the response and the corresponding events. The classifications
are model outputs, not guaranteed detection results. Requests wait for
classification before forwarding. The proxy uses Flask's development
server and plain HTTP.
