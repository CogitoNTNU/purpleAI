# BlueAI defender and target

The working two-PC lab contains:

- `defender-agent/`: the LLM reverse proxy and its model settings.
- `vulnerable-app/`: VulnShop, the deliberately vulnerable Flask target.

Use the [sandbox guide](../../deploy/sandbox/README.md) for first-time setup,
network checks, model changes, logs, and shutdown. Docker builds and dependencies
are defined in `deploy/sandbox/Dockerfile`; services are defined in
`deploy/sandbox/blue.compose.yml`.

**BlueAI — repository root (`~/purpleAI`):** start and check the stack after setup.
Replace `~/purpleAI` if your checkout is elsewhere.

```sh
cd ~/purpleAI
sudo python3 deploy/sandbox/start.py blue start
sudo python3 deploy/sandbox/start.py blue check
```

Only the defender is published on port 8080, reachable from RedAI. VulnShop remains
on the internal Docker network. Container logs are available through the sandbox
entry point; there is no separate dashboard.
