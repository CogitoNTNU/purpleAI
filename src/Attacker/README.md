# Attacker Agents

A multi-agent penetration-testing framework. A planner ("Boss Agent") delegates
work to execution subagents that run security tools (`sqlmap`, and more to come)
against a target defined in `config.py`.

Subagents run **asynchronously** as background tasks on a local Agent Protocol
server: the Boss launches one, gets a `task_id` back immediately, and keeps
working while the subagent runs. This means several subagents (each doing
different work that takes different amounts of time) can run concurrently
without the Boss blocking on the slowest one.

> Use only against systems you are authorized to test (your own lab / CTF).

## Setup on Kali

Kali (Debian) blocks installing into the system Python — you'll see
`error: externally-managed-environment`. Use an isolated environment with
[`uv`](https://docs.astral.sh/uv/) instead.

```bash
# 1. Install uv (once per machine)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc        # or open a new terminal so `uv` is on PATH

# 2. From this folder (purpleAI/src/Attacker), create a LOCAL env + install deps
cd purpleAI/src/Attacker
uv venv
uv pip install --python .venv/bin/python -r requirements.txt

# 3. Provide the LLM API key (the server and the Boss both read it)
export LLM_API_KEY="your-key"
```

Because subagents now run on a server, this is a **two-process** setup. Open
two terminals in `purpleAI/src/Attacker`, both with `LLM_API_KEY` exported:

```bash
# Terminal 1 — start the Agent Protocol server that hosts the subagents.
# It reads langgraph.json and serves each graph at http://localhost:2024.
.venv/bin/langgraph dev

# Terminal 2 — run the Boss once the server above is up.
.venv/bin/python redagent.py
```

> The server picks up `LLM_API_KEY` from a `.env` file in this folder too
> (see `env` in `langgraph.json`); exporting it in the shell works as well.
> If you serve the subagents somewhere other than `localhost:2024`, update
> `SUBAGENT_SERVER_URL` in `redagent.py`.

> **Do not use `uv run` here.** The repo root is itself a uv project (it has
> its own `pyproject.toml` / `.venv`), so `uv run` binds to the *root* env —
> which lacks `deepagents` — and you get `ModuleNotFoundError: No module named
> 'deepagents'`. The `--python .venv/bin/python` flag and calling
> `.venv/bin/python` directly keep everything in this folder's own env.

Verify the install landed in the local env:

```bash
.venv/bin/python -c "import deepagents; print(deepagents.__file__)"
# should print a path under src/Attacker/.venv/
```

## System tools

The agent's tools shell out to binaries that are **not** pip packages. On Kali
they're preinstalled; elsewhere:

```bash
sudo apt install sqlmap nmap
```

## Configuration

- **Target** — edit `Target_url` in `config.py`.
- **API key** — read from the `LLM_API_KEY` environment variable (never commit it).
- **Model / endpoint** — set in `llm.py` (`get_model()`), shared by the Boss and
  every served subagent.
- **Prompts** — all agent system prompts live in `prompts.py`.
- **Subagent server URL** — `SUBAGENT_SERVER_URL` in `redagent.py`.

## Layout

| File | Purpose |
| --- | --- |
| `redagent.py` | Boss Agent (planner); entry point. Launches subagents as async background tasks by `graph_id`. |
| `subagents_attack.py` | Execution subagent, compiled as a graph the server hosts. |
| `langgraph.json` | Registers subagent graphs for the Agent Protocol server (`langgraph dev`). |
| `prompts.py` | System prompts for all agents (`BOSS_PROMPT`, `EXECUTION_PROMPT`). |
| `llm.py` | Shared chat model (`get_model()`). |
| `attools.py` | Tools exposed to the subagents (`sqlmap`, async). |
| `redfunction.py` | Helper functions (nmap run/parse) — not yet wired as tools. |
| `config.py` | Target URL. |
| `requirements.txt` | Python deps for the attacker framework only. |

## Adding a subagent

1. Build it as a compiled graph (like `execution_agent` in `subagents_attack.py`),
   with its prompt in `prompts.py`. It can live in its own module.
2. Register it in `langgraph.json` under `graphs` with a unique `graph_id`.
3. Add an entry to the `subagents` list in `redagent.py` with a matching
   `graph_id` and a clear `description` so the Boss knows when to delegate to it.
