# Defender agent

`defender.py` is a reverse proxy in front of VulnShop. It asks the selected Idun
model to check incoming HTTP requests for SQL injection and cross-site scripting.
A positive result blocks the request with HTTP 403; otherwise the request is
forwarded to VulnShop. Model failures also block the request.

The checks are in the `AGENTS` list. Both currently use the same model, chosen by
`AGENT_MODEL` in this folder's `.env`. Copy `.env.example` during first-time setup.
Docker injects these settings and overrides the target, API address and API key
with sandbox values. The real Idun key is held by the gateway.

Follow the [sandbox guide](../../../deploy/sandbox/README.md) for setup and
[model changes](../../../deploy/sandbox/README.md#change-a-model-without-rebuilding).
The shared sandbox Dockerfile builds this agent; no separate Dockerfile
or dependency export is needed here.

**BlueAI — repository root (`~/purpleAI`):** view defender and stack logs.
Replace `~/purpleAI` if your checkout is elsewhere.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue logs
```

Diagnostics use Python `logging` on stderr: forwarding and blocking are `INFO`,
and model or target failures are `ERROR`. LLM classification can make mistakes,
so use synthetic lab traffic. This proxy detects and blocks requests; it does
not patch target code.

Structured events are also sent to the collector when gamehost logging is enabled
in deployment `.env`. The [gamehost runner](../../gamehost/README.md) assigns a
shared run ID to the defender and attacker and sends normal traffic. Delivery
failures do not change defender decisions.
Gamehost's `--without-defender` mode bypasses this proxy and sends no normal
traffic; it leaves the defender's current session running.

JSON events use the [shared sender](../../purpleai/README.md), with a 0.5-second
delivery timeout and no queue or retries. Events stay on stdout if delivery fails.

Model failure events include `error_type`, `model_http_status` and a safe
`error_reason` for diagnosing busy gateways, timeouts and connection failures.
Requests still receive HTTP 403 if model checks fail.
