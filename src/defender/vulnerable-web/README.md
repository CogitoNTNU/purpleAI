# SecureReview

SecureReview is a business and review application with a Django REST
backend, React/TypeScript frontend, SQLite database, and JWT authentication.
Its Compose stack includes the HTTP defender.

## Run

From the repository root:

```bash
export IDUNN_BASE_URL=https://llm.hpc.ntnu.no/v1
export IDUNN_API_KEY=your-idun-api-key
mkdir -p src/defender/logs
docker compose -f src/defender/vulnerable-web/docker-compose.yml up -d --build
```

| Host endpoint | Route |
| --- | --- |
| `http://localhost/` | Nginx to frontend |
| `http://localhost/api/` | Nginx directly to Django |
| `http://localhost/admin/` | Nginx directly to Django admin |
| `http://localhost:8080/` | Defender to Django |

Port 80 routes bypass the defender. The frontend/backend containers have
no directly published host ports. The backend entrypoint applies migrations
and seeds data when there are no users, then starts Django on port 8000.

## Events and services

The defender's events are saved to `src/defender/logs/events.jsonl` on the
host. See [defender documentation](../defender-agent/README.md) and
[Vector setup](../../../deploy/vector/README.md).

From the repository root:

```bash
docker compose -f src/defender/vulnerable-web/docker-compose.yml logs -f defender
docker compose -f src/defender/vulnerable-web/docker-compose.yml down
```

See the [developer guide](docs/developer-guide.md) for local backend and
frontend commands.
