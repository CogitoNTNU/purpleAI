# Attacker agent

The attacker is an IDUN-backed LangChain agent with one tool:
`nmap_scan()`. It performs service reconnaissance on the host configured
in `TARGET_URL`, then interprets the tool result.

## Target boundary

`nmap_scan()` takes no arguments. Application configuration selects the
host; the model cannot supply another target. The command is a fixed
argument list with no shell:

```text
nmap -sV -Pn -oX - <configured-host>
```

`config.py` accepts an HTTP(S) target URL with an optional port and no
credentials, query, fragment, or application path. Nmap scans the host,
not just the URL's port. The subprocess timeout is 120 seconds.

## Setup

Requirements are Python 3.11+, Nmap, access to the NTNU IDUN endpoint,
and an IDUN API key. Run from `src/nmap-agent/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set the application configuration in `.env`:

```env
TARGET_URL=http://192.168.50.10:8080
IDUN_BASE_URL=https://llm.hpc.ntnu.no/v1
IDUN_API_KEY=your-idun-api-key
IDUN_MODEL=openai/gpt-oss-120b
```

Shell environment values take precedence over `.env`. The URL is an
example; use the assigned lab target.

## Run

From `src/nmap-agent/`, with its environment activated:

```bash
python main.py
```

`main.py` runs its predefined reconnaissance task. `agent.py` creates the
model and tool-enabled agent. `tools/nmap.py` invokes Nmap and parses its
XML result into structured data.

## Events

`logging_utils.py` configures the shared `src/purpleai_logging.py` with
source `nmap-agent` and actor `attacker`. Application and tool code call
`log_event("action", **fields)`.

Events are printed and appended to `logs/events.jsonl` beside the adapter,
regardless of the current working directory. `PURPLEAI_LOG_FILE` can
override this path; the default requires no logging `.env` settings.
Events include `task_start`, `task_end`, `tool_call`, and `tool_result`.

Host Vector tails that file and forwards events to gamehost. See
[Vector setup](../../deploy/vector/README.md) and
[event format](../../docs/event-format.md).
