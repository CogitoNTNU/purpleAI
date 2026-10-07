# Shared agent runtime and logging

Both role images include this package:

- `agent_runtime.py` launches the selected attacker module or defender WSGI app.
  It replaces itself so shutdown signals reach the launched process.
- `event_logging.py` provides `EventSender` and diagnostic logging. Wrappers
  supply source, actor and collector credentials; the sender adds event IDs,
  timestamps, run ID and target mode, prints JSON and attempts delivery.

Use [agent integration](../../docs/agents.md) for the runtime contract,
[event format](../../docs/event-format.md) for fields and delivery behavior,
and [gamehost](../gamehost/README.md#view-logs-and-save-events) for saved logs.
[Native agent execution](../../deploy/sandbox/TESTING.md#run-an-attacker-workflow-on-your-pc)
requires this package on `PYTHONPATH`; Docker includes it automatically.
