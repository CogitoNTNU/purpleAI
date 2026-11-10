# Queued model calls and resumable engagements

All Boss processes, specialist servers and A-D instances running as the same
redai user share `~/.purpleai/queue`. Each HTTP attempt waits in a FIFO queue
and reserves one distinct API key until its response body is consumed or
closed. A crashed process releases its OS lock. Duplicate copies of the same
key do not add capacity.

In the updated control app, open **Keys**, add a key per line and **Save**.
The app publishes `~/.purpleai/keys.json` atomically over SSH, with mode 0600.
Waiting calls reload that file every admission attempt, so added keys provide
additional simultaneous model slots without restarting agents. Removed keys
finish their current request and are not assigned again. Saving an empty pool
pauses new model calls. SSH sync errors appear in the Attacker log; Save again
after restoring connectivity. If no live file exists, environment keys remain
supported. Don't put credentials in Git or command-line arguments.

The launcher runs the runtime checked out from the selected remote branch.
Commit and push the fixes to every experiment branch before starting it; the
launcher does not replace branch files with an embedded runtime. Rebuild the
Windows control app after changing its GUI or startup scripts.

Transient network/HTTP errors rejoin the queue and emit status messages.
429 honors Retry-After. 401/403 cool down the key for five minutes and try
other keys; invalid credentials or unavailable model permissions still require
operator correction. HTTP 400/404 and other permanent request errors are
surfaced to the graph rather than hidden by HTTP retries. Request timeout is
600 seconds by default; it is an individual network attempt, not an engagement
deadline. Responses already being streamed are not replayed automatically by
the transport.

The Boss checks remote task status every 15 seconds without using model tokens.
A monitoring disconnection is retried, never mistaken for task completion.
Failed/timed-out remote runs with pending checkpoint work resume on their
existing threads, with backoff and recovery-run reconciliation. Interrupted
or cancelled runs are left for operator control. Recovery can reexecute a
failed graph step; tools with external effects must be idempotent. This does
not guarantee exactly-once tool execution after an ambiguous network failure.

Boss state lives in each instance's `src/Attacker/logs/boss.sqlite3` (or the
lowercase `src/attacker` path). Start preserves this state and server threads;
**Reset all** explicitly clears them. Back up engagements before changing
branches or targets. This still uses LangGraph's development server; it does
not provide production-grade server durability or recovery from lost disks.

Environment controls:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_KEYS_FILE` | `~/.purpleai/keys.json` | Live key-pool file |
| `LLM_QUEUE_DIR` | `~/.purpleai/queue` | Shared per-host queue and OS locks |
| `LLM_READ_TIMEOUT` | `600` | Per-attempt HTTP read timeout, seconds |
| `LLM_BASE_URL` | NTNU endpoint | Model endpoint |
| `PURPLE_MAX_ITERATIONS` | `0` | Boss turns; zero continues until stopped |
| `PURPLE_POLL_SECONDS` | `15` | Remote run monitoring interval |
| `PURPLE_RECOVERY_SECONDS` | `30` | Recovery backoff |
| `PURPLE_CHECKPOINT_DB` | Instance `logs/boss.sqlite3` | Durable Boss state |

The launcher sets `BG_JOB_TIMEOUT_SECS=86400` for its specialist server to
allow lengthy queue waits. More independently usable keys increase available
concurrency, but endpoint-wide quotas, generation latency and tool execution
can still limit speed. The queue only coordinates callers using this runtime;
other programs or the defender using the same keys can still cause 429s.

Run the offline regression suite with the attacker's dependencies plus
`pytest` and `pytest-asyncio` installed:

```sh
python -m pytest tests/test_attacker_reliability.py -q
```
