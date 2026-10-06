# Shared agent logging

`event_logging.py` creates JSON experiment events and sends them to gamehost.
Both agent Docker images include this package. Agent wrappers supply their
source, actor and collector settings; the shared sender handles IDs, UTC
timestamps, stdout and authenticated HTTP delivery.

Diagnostic messages use Python `logging` on stderr. Delivery failures warn once
per agent process; events are still printed locally. Each send uses a 0.5-second
timeout, without a queue or retries. The collector format is unchanged.

**Development machine — repository root:** run tests with the repository's
Python environment. Pytest includes `src` on its import path.

```sh
cd /Users/frederik/Projects/purpleAI
.venv/bin/python -m pytest -q
```

For direct agent execution outside Docker, include the shared package on
`PYTHONPATH` (and install that agent's dependencies first).

**RedAI — agent directory (`~/purpleAI/src/nmap-agent`):** this reads the agent's
own `.env`.

```sh
cd ~/purpleAI/src/nmap-agent
PYTHONPATH=.. python3 ~/purpleAI/src/nmap-agent/main.py
```

Use the [sandbox guide](../../deploy/sandbox/README.md) for normal deployment.
