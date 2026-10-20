# PurpleAI

PurpleAI combines an IDUN-backed Nmap reconnaissance agent, an HTTP
defender that classifies SQL injection and XSS, deliberately vulnerable
web applications, and centralized Vector logging.

## Repository components

- `src/nmap-agent/`: attacker CLI, target configuration, and restricted Nmap tool.
- `src/defender/defender-agent/`: Flask reverse proxy and request classifiers.
- `src/defender/vulnerable-app/`: VulnShop Flask/SQLite application.
- `src/defender/vulnerable-web/`: SecureReview Django/React/Nginx stack.
- `src/purpleai_logging.py`: shared JSON event logger.
- `deploy/vector/`: sender and gamehost receiver configurations and host setup guide.
- `src/gamehost/traffic/`: k6 scenarios targeting VulnShop routes.
- `src/defender/dashboard/`: Streamlit dashboard reading a local sample file.

The component READMEs contain startup commands and configuration.

## Event logging

Applications print JSON events and append them to local files. Vector on
RedAI and BlueAI tails those files and forwards them to gamehost Vector
on TCP 6000. Gamehost writes daily JSONL archives under
`/var/log/purpleai/collected/`.

The [event format](event-format.md) documents the shared envelope and
current actions. File paths, service setup, and retention behavior are
covered by `deploy/vector/README.md` in the repository.
