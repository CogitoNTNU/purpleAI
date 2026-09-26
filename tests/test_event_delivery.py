"""End-to-end checks for live gamehost event delivery."""

import importlib.util
import io
import json
import sys
import tempfile
import threading
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EventDeliveryTest(unittest.TestCase):
    def test_events_are_available_before_the_run_ends(self):
        collector = load_module("test_collector", ROOT / "src/gamehost/log_collector.py")
        fake_config = types.ModuleType("config")
        fake_config.get_config = lambda: None
        with patch.dict(sys.modules, {"config": fake_config}):
            logging = load_module("test_nmap_logging", ROOT / "src/nmap-agent/logging_utils.py")

        with tempfile.TemporaryDirectory() as directory:
            collector.DATA_FILE = Path(directory) / "events.jsonl"
            collector.TOKEN = "test-token"
            server = ThreadingHTTPServer(("127.0.0.1", 0), collector.EventHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                logging.get_config = lambda: types.SimpleNamespace(
                    log_collector_url=f"http://127.0.0.1:{server.server_port}/events",
                    log_collector_token="test-token",
                )
                with redirect_stdout(io.StringIO()):
                    logging.log_event("attacker", "task_start", status="started")
                    first = json.loads(collector.DATA_FILE.read_text().splitlines()[0])
                    self.assertEqual(first["action"], "task_start")
                    logging.log_event("attacker", "task_end", status="success")

                events = [json.loads(line) for line in collector.DATA_FILE.read_text().splitlines()]
                self.assertEqual([event["action"] for event in events], ["task_start", "task_end"])
                self.assertEqual(events[0]["run_id"], events[1]["run_id"])
                self.assertNotEqual(events[0]["event_id"], events[1]["event_id"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_unavailable_collector_does_not_stop_logging(self):
        fake_config = types.ModuleType("config")
        fake_config.get_config = lambda: None
        with patch.dict(sys.modules, {"config": fake_config}):
            logging = load_module("test_nmap_logging_offline", ROOT / "src/nmap-agent/logging_utils.py")
        logging.get_config = lambda: types.SimpleNamespace(
            log_collector_url="http://127.0.0.1:1/events",
            log_collector_token="test-token",
        )
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            logging.log_event("attacker", "task_start")
            logging.log_event("attacker", "task_end")
        self.assertEqual(len(output.getvalue().splitlines()), 2)
        self.assertEqual(errors.getvalue().count("Gamehost log delivery failed"), 1)


if __name__ == "__main__":
    unittest.main()
