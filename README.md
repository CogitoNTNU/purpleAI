# PurpleAI

PurpleAI is a Cogito NTNU lab project with an Nmap reconnaissance agent,
an LLM-based HTTP defender, deliberately vulnerable web applications, and
centralized event logging.

## Components

| Component | Location | Behavior |
| --- | --- | --- |
| Attacker | `src/nmap-agent/` | Uses an IDUN-backed LangChain agent and a restricted Nmap tool against the configured host. |
| Defender | `src/defender/defender-agent/` | Checks requests for SQL injection and XSS, then blocks or forwards them. |
| VulnShop | `src/defender/vulnerable-app/` | Deliberately vulnerable Flask/SQLite application. |
| SecureReview | `src/defender/vulnerable-web/` | Django/React application with an Nginx frontend and defender service. |
| Shared logger | `src/purpleai_logging.py` | Prints JSON events and appends them to application log files. |
| Vector configs | `deploy/vector/` | Forward host log files to gamehost and archive them as daily JSONL. |
| Traffic generator | `src/gamehost/traffic/` | k6 scenarios for VulnShop login, browsing, and purchases. |
| Dashboard | `src/defender/dashboard/` | Streamlit view reading its local `web_logger.txt` sample. |

The vulnerable applications are intended for an isolated lab network.

## Run the components

- [Attacker setup](src/nmap-agent/README.md): Python, Nmap, target URL, and IDUN credentials.
- [Defender setup](src/defender/defender-agent/README.md): Compose configurations and request classification.
- [VulnShop](src/defender/vulnerable-app/README.md): Flask application behind the defender.
- [SecureReview](src/defender/vulnerable-web/README.md): Django/React stack.
- [Vector setup](deploy/vector/README.md): host services and log forwarding.
- [Event format](docs/event-format.md): shared JSON envelope.
- [Gamehost](src/gamehost/README.md): log collection and traffic generation.

Each component has its own startup instructions. The attacker reads
`src/nmap-agent/.env`; the defender Compose services receive
`IDUNN_BASE_URL` and `IDUNN_API_KEY` from the launching environment.

## Development checks

From the repository root:

```bash
uv sync
uv run pytest
```

## Documentation site

```bash
uv sync --group docs
uv run mkdocs build
uv run mkdocs serve
```

The site configuration is `mkdocs.yml`; documentation pages are in `docs/`.

## License

See [LICENSE](LICENSE).
