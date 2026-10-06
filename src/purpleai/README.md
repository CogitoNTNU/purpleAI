# Shared agent logging

`event_logging.py` creates JSON experiment events and sends them to gamehost.
Both agent Docker images include this package. Agent wrappers supply their
source, actor and collector settings; the shared sender handles IDs, UTC
timestamps, stdout and authenticated HTTP delivery.

Diagnostic messages use Python `logging` on stderr. Delivery failures warn once
per agent process; events are still printed locally. Each send uses a 0.5-second
timeout, without a queue or retries. The collector format is unchanged.

Use the [gamehost run guide](../gamehost/README.md) for events and diagnostics,
and the [sandbox guide](../../deploy/sandbox/README.md) for deployment. Pytest
includes `src` on its import path; Docker copies this package into both images.
Direct agent execution outside Docker also requires `src` on `PYTHONPATH`.
