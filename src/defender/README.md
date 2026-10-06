# BlueAI defender and target

The working two-PC lab contains:

- `defender-agent/`: the LLM reverse proxy and its model settings.
- `vulnerable-app/`: VulnShop, the deliberately vulnerable Flask target.

Use the [sandbox guide](../../deploy/sandbox/README.md) for configuration,
startup, checks, model changes, logs and shutdown. For coordinated experiments,
use the [gamehost run guide](../gamehost/README.md). Docker builds and dependencies
are defined in `deploy/sandbox/Dockerfile`; services are defined in
`deploy/sandbox/blue.compose.yml`.

The defender is published on port 8080, reachable from RedAI and the configured
gamehost. VulnShop remains unpublished by default. For tools/scripts against
VulnShop with or without defender checks, use [manual testing](../../deploy/sandbox/TESTING.md). Container
logs are available through the sandbox entry point; there is no separate dashboard.
