# BlueAI defender and target

The working two-PC lab contains:

- `defender-agent/`: the LLM reverse proxy and its model settings.
- `vulnerable-app/`: VulnShop, the deliberately vulnerable Flask target.

Use the [sandbox guide](../../deploy/sandbox/README.md) for configuration,
startup, checks, model changes, logs and shutdown. For coordinated experiments,
use the [gamehost run guide](../gamehost/README.md). To add or replace agents,
follow [agent integration](../../docs/agents.md). Docker builds and dependencies
are defined in `deploy/sandbox/Dockerfile`; services are defined in
`deploy/sandbox/blue.compose.yml`.

The defender is published on port 8080, reachable from RedAI and the configured
gamehost, plus one development PC if `DEV_IP` is configured on BlueAI.
VulnShop remains unpublished by default. Optional port 8081 bypasses defender
checks while using the same target and data; the defender stays running.
For tools/scripts against either endpoint, use [manual testing](../../deploy/sandbox/TESTING.md).
Container logs are available through the sandbox entry point.
