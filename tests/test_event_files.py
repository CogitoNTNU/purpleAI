"""Application event file rotation and write-failure checks."""

import importlib.util
import io
import json
import os
import tempfile
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
    def load_logging(self, path):
        self.env = patch.dict(os.environ, {"PURPLEAI_LOG_FILE": str(path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        return load_module(
            "test_nmap_logging", ROOT / "src/nmap-agent/logging_utils.py"
        )

    def test_events_are_available_before_the_run_ends(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logs/events.jsonl"
            logging = self.load_logging(path)
            with redirect_stdout(io.StringIO()):
                logging.log_event("task_start", status="started")
                self.assertEqual(json.loads(path.read_text())["action"], "task_start")
                # External rename/create rotation must work without restarting.
                path.rename(path.with_suffix(".old"))
                logging.log_event("task_end", status="success")
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
                logging.log_event("task_start")
            self.assertEqual(json.loads(output.getvalue())["action"], "task_start")
            self.assertIn("Local event log write failed", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
