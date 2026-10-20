"""Both adapters must emit the same schema, including in the defender image."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "adapter,source,actor",
    [
        ("nmap-agent/logging_utils.py", "nmap-agent", "attacker"),
        ("defender/defender-agent/event_logging.py", "defender-agent", "defender"),
    ],
)
def test_standalone_adapters_share_event_contract(tmp_path, adapter, source, actor):
    path = tmp_path / "events.jsonl"
    script = (
        "import runpy; "
        f"log = runpy.run_path({str(ROOT / 'src' / adapter)!r})['log_event']; "
        "log('delivery_test', status='ok', unused=None); "
        "log('delivery_test', status='ok')"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PURPLEAI_LOG_FILE": str(path)},
        capture_output=True,
        text=True,
        check=True,
    )
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert path.read_text() == result.stdout
    assert all(
        event["source"] == source and event["actor"] == actor for event in events
    )
    assert set(events[0]) == {
        "schema_version",
        "event_id",
        "run_id",
        "timestamp",
        "source",
        "actor",
        "action",
        "status",
    }
    assert events[0]["run_id"] == events[1]["run_id"]
    assert events[0]["event_id"] != events[1]["event_id"]


def test_defender_image_layout_without_host_imports_or_env_override(tmp_path):
    # Mirror Docker COPY/WORKDIR in a fresh isolated Python process.
    image = tmp_path / "app"
    agent = image / "defender/defender-agent"
    agent.mkdir(parents=True)
    shutil.copy(ROOT / "src/purpleai_logging.py", image)
    shutil.copy(ROOT / "src/defender/defender-agent/event_logging.py", agent)
    env = dict(os.environ)
    env.pop("PURPLEAI_LOG_FILE", None)
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            f"import runpy; runpy.run_path({str(agent / 'event_logging.py')!r})['log_event']('image_test')",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )
    event = json.loads((agent / "logs/events.jsonl").read_text())
    assert event["source"] == "defender-agent"
    assert event["action"] == "image_test"
