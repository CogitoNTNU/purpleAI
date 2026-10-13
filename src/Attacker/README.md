# Attacker Agents

A multi-agent penetration-testing framework. A planner ("Boss Agent") delegates
work to an execution agent that runs security tools (`sqlmap`, and more to come)
against a target defined in `config.py`.

> Use only against systems you are authorized to test (your own lab / CTF).

## Setup on Kali

Kali (Debian) blocks installing into the system Python — you'll see
`error: externally-managed-environment`. Use an isolated environment with
[`uv`](https://docs.astral.sh/uv/) instead.

```bash
# 1. Install uv (once per machine)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc        # or open a new terminal so `uv` is on PATH

# 2. From this folder (purpleAI/src/Attacker), create the env + install deps
cd purpleAI/src/Attacker
uv venv
uv pip install -r requirements.txt

# 3. Provide the LLM API key and run
export LLM_API_KEY="your-key"
uv run python redagent.py
```

`uv run` uses the project's `.venv` automatically, so you don't need to activate
it. If you prefer activating it yourself:

```bash
source .venv/bin/activate
python redagent.py
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
- **Model / endpoint** — set in `redagent.py` (`model=`, `base_url=`).

## Layout

| File | Purpose |
| --- | --- |
| `redagent.py` | Boss Agent (planner); entry point. |
| `subagents_attack.py` | Execution agent definition. |
| `attools.py` | Tools exposed to the agent (`sqlmap`). |
| `redfunction.py` | Helper functions (nmap run/parse) — not yet wired as tools. |
| `config.py` | Target URL. |
| `requirements.txt` | Python deps for the attacker framework only. |
