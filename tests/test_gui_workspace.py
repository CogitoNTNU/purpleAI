"""Exercise the desktop workspace without SSH or user configuration files."""
import importlib.util
from pathlib import Path
import sys
import tkinter as tk
from unittest.mock import patch

import pytest


GUI_DIR = Path(__file__).resolve().parents[1] / "startup" / "gui"
sys.path.insert(0, str(GUI_DIR))
spec = importlib.util.spec_from_file_location("workspace_gui", GUI_DIR / "app.py")
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)


@pytest.fixture(scope="module")
def app():
    with patch.object(gui, "load_config"), patch.object(gui, "load_notes"):
        try:
            window = gui.App()
        except tk.TclError as exc:
            if "no display" in str(exc) or "couldn't connect to display" in str(exc):
                pytest.skip(f"Desktop display unavailable: {exc}")
            raise
        window.update()
        yield window
        window._on_close()


def test_navigation_and_agent_feeds_remain_accessible(app):
    assert len(app.tabs) == 3
    assert app.arena is not None
    assert len(app._nav_buttons) == 4
    for index in range(4):
        app._select_page(index)
        app.update()
        assert app.nb.index(app.nb.select()) == index
        assert app.page_title.cget("text") == app.nb.tab(index, "text")
    attacker = app._tab("attacker")
    assert set(attacker.panes) == {"boss", "recon", "sql", "xss", "ssti"}
    for pane, widget in attacker.panes.items():
        attacker.append(f"Output for {pane}\n", pane)
        assert f"Output for {pane}" in widget.get("1.0", "end")
    attacker.clear_log()
    assert all(not widget.get("1.0", "end").strip() for widget in attacker.panes.values())


def test_live_events_update_cards_and_preserve_flag_attribution(app):
    attacker = app._tab("attacker")
    attacker._handle_event({"action": "subagent_status", "subagent": "sql_injection_agent",
                            "task_id": "test-task", "status": "running"})
    assert "1 running" in attacker.lights["sqlmap"]["status"].get()
    flag = gui.KNOWN_FLAGS[0][0]
    assert attacker._add_flag(flag, "xss") == "reject"
    assert attacker._add_flag(flag, "sql") == "new"
    assert attacker._add_flag(flag, "sql") == "dup"
    assert app.red_var.get() == "1"
    assert app.blue_var.get() == str(gui.TOTAL_FLAGS - 1)
    attacker.clear_flags()
    assert app.red_var.get() == "0"


def test_workspace_fits_minimum_window_size(app):
    app.geometry("1120x860")
    app._select_page(0)
    app.update()
    attacker = app._tab("attacker")
    assert attacker.winfo_width() > 800
    for widget in attacker.panes.values():
        assert widget.winfo_ismapped()
        assert widget.winfo_width() >= 120
        assert widget.winfo_height() >= 80
    assert app.keys_btn.winfo_ismapped()


def test_notes_dialog_keeps_editor_and_actions(app):
    app.open_notes()
    app.update()
    dialogs = [child for child in app.winfo_children() if isinstance(child, tk.Toplevel)]
    assert len(dialogs) == 1
    assert dialogs[0].title() == "Engagement notes"
    dialogs[0].destroy()
