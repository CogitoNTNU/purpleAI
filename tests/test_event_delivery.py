"""Application event file and legacy collector configuration checks."""

import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EventDeliveryTest(unittest.TestCase):
    def test_gamehost_env_file(self):
        collector = load_module(
            "test_collector_env", ROOT / "src/gamehost/log_collector.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                '# collector settings\nGAMEHOST_LOG_TOKEN="test-token"\n'
                "GAMEHOST_LOG_BIND=192.168.0.110\n"
            )
            self.assertEqual(
                collector.read_env_file(env_file),
                {
                    "GAMEHOST_LOG_TOKEN": "test-token",
                    "GAMEHOST_LOG_BIND": "192.168.0.110",
                },
            )

    def load_logging(self, path):
        fake_config = types.ModuleType("config")
        fake_config.get_config = lambda: types.SimpleNamespace(log_file=path)
        with patch.dict(sys.modules, {"config": fake_config}):
            return load_module(
                "test_nmap_logging", ROOT / "src/nmap-agent/logging_utils.py"
            )

    def test_events_are_available_before_the_run_ends(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logs/events.jsonl"
            logging = self.load_logging(path)
            with redirect_stdout(io.StringIO()):
                logging.log_event("attacker", "task_start", status="started")
                self.assertEqual(json.loads(path.read_text())["action"], "task_start")
                # External rename/create rotation must work without restarting.
                path.rename(path.with_suffix(".old"))
                logging.log_event("attacker", "task_end", status="success")
            first = json.loads(path.with_suffix(".old").read_text())
            last = json.loads(path.read_text())
            self.assertEqual(first["run_id"], last["run_id"])
            self.assertNotEqual(first["event_id"], last["event_id"])
            self.assertEqual(last["action"], "task_end")

    def test_unwritable_log_does_not_stop_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-a-directory"
            path.write_text("occupied")
            logging = self.load_logging(path / "events.jsonl")
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                logging.log_event("attacker", "task_start")
            self.assertEqual(json.loads(output.getvalue())["action"], "task_start")
            self.assertIn("Local event log write failed", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
