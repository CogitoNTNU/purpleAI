# VulnShop with the defender

```text
Client → defender:8080 → vulnerable-app:5000 (internal Docker network)
```

The defender uses IDUN classifiers for SQL injection and XSS. A positive
classification or classifier exception produces HTTP 403. Otherwise,
the proxy forwards the request and returns the app's response.

## Start

From the repository root, with Docker/Compose installed and network access
to IDUN:

```bash
export IDUNN_BASE_URL=https://llm.hpc.ntnu.no/v1
export IDUNN_API_KEY=your-idun-api-key
mkdir -p src/defender/logs
docker compose -f src/defender/docker-compose.yml up -d --build
```

The defender publishes port 8080. The backend has no published host port.

## Requests and events

```bash
curl http://localhost:8080/
curl -G http://localhost:8080/search --data-urlencode "q=' OR 1=1--"
docker compose -f src/defender/docker-compose.yml logs -f defender
```

Inspect `request_decision` events for `allowed`, `blocked`, or `error`.
Forwarded requests also produce `request_result` events. Classification
results depend on the model response.

The shared logger writes `src/defender/logs/events.jsonl` on the host.
Host Vector forwards these events according to
[Vector setup](../../../deploy/vector/README.md).

## Stop

From the repository root:

```bash
docker compose -f src/defender/docker-compose.yml down
```
