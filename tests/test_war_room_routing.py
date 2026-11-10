"""Exercise chat routing without opening a Tk window or remote connection."""
import importlib.util
from pathlib import Path
import queue
from types import SimpleNamespace
from unittest.mock import Mock
import sys


def test_status_stays_in_logs_while_dialogue_reaches_chat():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("war_room_gui", root / "startup/gui/app.py")
    gui = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gui)
    arena = SimpleNamespace(say=Mock())
    tab = SimpleNamespace(
        q=queue.Queue(), cfg={"panes": True},
        reasoning_only=SimpleNamespace(get=lambda: False),
        append=Mock(), _arena=lambda: arena, after=Mock(), _drain=Mock(),
    )
    status = [
        "[monitor] 4 tasks active; next check in 15s\n",
        "[llm] queued; waiting for an available slot\n",
        "[recovery] status unavailable; reconnecting\n",
        "[attacker:attacker-a] started\n",
    ]
    dialogue = "[model] Recon found a new endpoint; assigning a focused scan.\n"
    for line in [*status, dialogue]:
        tab.q.put(("line", "logs", line))
    gui.ComponentTab._drain(tab)
    assert [call.args[0] for call in tab.append.call_args_list] == [*status, dialogue]
    arena.say.assert_called_once_with("boss", "Recon found a new endpoint; assigning a focused scan.")


def test_complete_boss_summary_reaches_chat_without_exposing_private_reasoning(monkeypatch, capsys):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src/attacker"))
    import redagent
    from langchain_core.messages import AIMessage
    monkeypatch.setattr(redagent, "log_agent_update", Mock())
    message = AIMessage(
        content="Finding: endpoint discovered.\n\nImplication: needs validation.\nNext action: focused check.",
        additional_kwargs={"reasoning_content": "private internal reasoning"},
    )
    redagent._render_messages("model", {"messages": [message]})
    output = capsys.readouterr().out
    assert len(output.splitlines()) == 1
    assert "Finding: endpoint discovered." in output
    assert "Implication: needs validation." in output
    assert "Next action: focused check." in output
    assert "private internal reasoning" not in output
