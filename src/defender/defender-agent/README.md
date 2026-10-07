# Defender agent

`defender.py` is a reverse proxy in front of VulnShop. The checks in its `AGENTS`
list ask an Idun model to classify incoming requests for SQL injection and
cross-site scripting. A positive classification blocks with HTTP 403; otherwise
the proxy forwards to the backend. Model failures also block with 403.
It checks requests but does not patch target code. Classification can be wrong;
use synthetic lab traffic.

This folder's `.env` selects `DEFENDER_APP=defender:app` and `AGENT_MODEL`.
The current checks share that model. Compose supplies `TARGET`, `IDUN_BASE_URL`
and `IDUN_API_KEY`; the credential is the gateway token, and the real key stays
in the gateway.

- [Sandbox setup and settings](../../../deploy/sandbox/README.md): start, recreate and view logs.
- [Agent integration](../../../docs/agents.md): replace the HTTP application or update dependencies.
- [Gamehost runs](../../gamehost/README.md): coordinated experiments and collected logs.
- [Event format](../../../docs/event-format.md): request decisions and model error fields.

Request decisions are JSON events on stdout, delivered best effort when logging
is configured. Python `logging` writes diagnostics to stderr. Delivery failures
do not change defender decisions.
