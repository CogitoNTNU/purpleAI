# PurpleAI — attacker agent v0

A controlled cybersecurity research lab: a LangChain/LangGraph attacker
agent that performs basic Nmap reconnaissance against one predefined
test service. The LLM runs on NTNU's IDUN LLM API — never the public
OpenAI API.

## Architecture

```text
User task
   ↓
LangChain/LangGraph attacker agent
   ↓
NTNU IDUN LLM API  (https://llm.hpc.ntnu.no/v1)
   ↓
LLM decides whether to call tool
   ↓
nmap_scan()  (restricted tool, target fixed in config)
   ↓
Configured PurpleAI target
   ↓
Structured Nmap result
   ↓
LLM interprets result
```

```text
LangChain/LangGraph
       │
       ▼
NTNU IDUN LLM API
       │
       ▼
attacker reasoning
       │
       ▼
restricted Nmap tool
       │
       ▼
PurpleAI target
```

## Safety boundary

The agent's only tool is `nmap_scan()`, which takes **no parameters**.
The scan target is derived from `TARGET_URL` in `.env` by trusted
application code (`config.py` → `tools/nmap.py`). The LLM can never
choose or modify the target, and Nmap is invoked as a fixed argument
list (`nmap -sV -Pn -oX - <host>`, no `shell=True`). There is no
arbitrary shell execution, no arbitrary targets, and no exploitation.

## Prerequisites

* Python 3.11+
* [Nmap](https://nmap.org/) installed locally (`brew install nmap` or `sudo apt install nmap`)
* NTNU network access or NTNU VPN — IDUN is only reachable from NTNU networks
* A personal NTNU IDUN API key, requestable at:
  https://ai.hpc.ntnu.no/request-api-key

IDUN LLM endpoint: `https://llm.hpc.ntnu.no/v1`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env` and insert your own IDUN API key:

```env
TARGET_URL=http://192.168.50.10:8080

IDUN_BASE_URL=https://llm.hpc.ntnu.no/v1
IDUN_API_KEY=your-idun-api-key
IDUN_MODEL=openai/gpt-oss-120b
```

## Run

```bash
python main.py
```

Example output:

```text
PurpleAI attacker v0
Target: http://192.168.50.10:8080
Model: openai/gpt-oss-120b
LLM API: https://llm.hpc.ntnu.no/v1

[USER TASK]
Investigate the configured PurpleAI target...

[TOOL CALL]
nmap_scan()

[TOOL RESULT]
{"target": "192.168.50.10", "ports": [...]}

[AGENT]
The target exposes...
```

Every agent action is also logged as a structured JSON line
(timestamp, actor, action, tool, target, status) for later evaluation.

## Project structure

```text
purpleai/
├── main.py            # CLI entry point
├── agent.py           # agent construction + workflow printing
├── config.py          # .env loading, validation, target parsing
├── logging_utils.py   # structured JSON event logging
├── tools/
│   └── nmap.py        # restricted nmap_scan() tool
├── requirements.txt
├── .env.example
└── README.md
```

## Extending

New restricted tools (e.g. `http_get(path)`, `inspect_headers(path)`)
follow the same principle: the LLM selects actions, but trusted
application code enforces the allowed target. Registration happens in
`agent.py`; the target must always come from `config.py`, never from
the LLM.
