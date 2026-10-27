from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "codex_proactive_trigger.py"
)
SPEC = spec_from_file_location("codex_proactive_trigger", SCRIPT)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProactiveTriggerTests(unittest.TestCase):
    def test_trigger_never_injects_a_synthetic_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "trigger.json"
            config.write_text(
                json.dumps({"enabled": True}),
                encoding="utf-8",
            )
            output = io.StringIO()
            argv = [
                "codex_proactive_trigger.py",
                "--config",
                str(config),
                "--dry-run",
                "--force",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                redirect_stdout(output),
            ):
                self.assertEqual(MODULE.main(), 0)
            self.assertIn("blocked", output.getvalue())

    def test_script_contains_no_codex_queue_command(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("codex queue", source)
        self.assertNotIn('"queue"', source)


if __name__ == "__main__":
    unittest.main()
