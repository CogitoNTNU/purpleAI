# Defender agent

`defender.py` is a reverse proxy in front of VulnShop. It asks the selected Idun
model to check incoming HTTP requests for SQL injection and cross-site scripting.
A positive result blocks the request with HTTP 403; otherwise the request is
forwarded to VulnShop. Model failures also block the request.

The checks are in the `AGENTS` list. Both currently use the same model, chosen by
`AGENT_MODEL` in this folder's `.env`. Copy `.env.example` during first-time setup.
Docker injects these settings and overrides the target, API address and API key
with sandbox values. The real Idun key is held by the gateway.

Follow the [sandbox guide](../../../deploy/sandbox/README.md) for setup and model
changes. The shared sandbox Dockerfile builds this agent; no separate Dockerfile
or dependency export is needed here.

**BlueAI — repository root (`~/purpleAI`):** view defender and stack logs.
Replace `~/purpleAI` if your checkout is elsewhere.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue logs
```

Logs show forwarded requests as `[ok]`, detected attacks as `[BLOCKED]`, and model
failures as `[ERROR]`. LLM classification can make mistakes, so use synthetic lab
traffic. This proxy detects and blocks requests; it does not patch target code.
