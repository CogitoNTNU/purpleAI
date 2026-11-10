import importlib.util
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
def gui():
    spec=importlib.util.spec_from_file_location('reset_gui',ROOT/'startup/gui/app.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_clear_uses_engagement_reset():
    app=SimpleNamespace(end_engagement=Mock())
    gui().ComponentTab.on_clear(SimpleNamespace(app=app))
    app.end_engagement.assert_called_once()

def test_reset_erases_checkpoint_threads_and_tool_cache_only_in_selected_instance(tmp_path,monkeypatch):
    selected=tmp_path/'purpleAI-a'
    other=tmp_path/'purpleAI-b'
    for root in (selected,other):
        (root/'src/attacker/logs').mkdir(parents=True)
        (root/'src/attacker/logs/boss.sqlite3').write_text('saved')
        (root/'src/attacker/.langgraph_api').mkdir()
        (root/'src/attacker/.langgraph_api/thread').write_text('pending')
        (root/'startup/tool-state').mkdir(parents=True)
        (root/'startup/tool-state/session').write_text('old scan')
    script=gui().att_end(gui().INSTANCES[0])
    programs=dict(re.findall(r"<<'(RESET_\w+)'\n(.*?)\n\1",script,re.S))
    monkeypatch.setattr(sys,'argv',['reset',str(selected)])
    exec(compile(programs['RESET_STATE'],'reset-state','exec'),{})
    assert not (selected/'src/attacker/logs/boss.sqlite3').exists()
    assert not (selected/'src/attacker/.langgraph_api').exists()
    assert not (selected/'startup/tool-state').exists()
    assert (other/'src/attacker/logs/boss.sqlite3').read_text()=='saved'
    assert 'C-c' not in script
    assert 'DELETE FROM waiters WHERE pid=?' in script
