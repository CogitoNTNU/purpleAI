# Gamehost logging

Use [Vector logging](../../deploy/vector/README.md) to collect events from
both attacker and defender. Each host Vector tails its application's
JSONL file and forwards to gamehost Vector on TCP 6000. Gamehost writes
daily JSONL archives under `/var/log/purpleai/collected/`.

`log_collector.py` is the legacy HTTP receiver. It is no longer needed
for this setup; the attacker no longer posts to it.
