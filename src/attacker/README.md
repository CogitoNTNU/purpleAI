# RedAI attacker runtime

This folder contains operator-selected attacker workflows. A workflow may run
one agent or coordinate several agents and subagents inside the same container.

Set `ATTACKER_MODULE` in this folder's `.env` to a Python module, for example
`agents.nmap.main`. Set its model with `AGENT_MODEL`. Gamehost and the sandbox
launch the selected module using the same `red run` command.

- [Sandbox setup](../../deploy/sandbox/README.md): configure and start RedAI/BlueAI.
- [Agent integration](../../docs/agents.md): add code, dependencies and tools; migrate an existing lab.
- [Manual testing](../../deploy/sandbox/TESTING.md): run from RedAI or your own PC, with or without the defender.
- [Gamehost experiments](../gamehost/README.md): coordinated runs and saved events.

The image includes the whole folder and installs `requirements.txt` and
`system-packages.txt`. Model, target and collector access come from injected
settings. The real Idun key stays in the gateway.

Included workflows:

| Module             | Purpose                                                                                  |
| ------------------ | ---------------------------------------------------------------------------------------- |
| `agents.nmap.main` | [Nmap reconnaissance example](agents/nmap/README.md), scanning the configured URL's port |
| `agents.smoke`     | One HTTP request and one model call, with events, to verify integration                  |

Changes to Python code, dependencies or tools require rebuilding the image.
Changing `ATTACKER_MODULE` or a model in `.env` takes effect on the next run.
