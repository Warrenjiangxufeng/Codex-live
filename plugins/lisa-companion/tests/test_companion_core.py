from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from companion_core import CodexLiveBridge  # noqa: E402
from codex_live.config import RuntimeConfig  # noqa: E402
from codex_live.model import ModelError  # noqa: E402


class FakeProactive:
    def generate(self, recent_messages=None, *, sequence_index=None, presence=None):
        self.presence = presence
        return (
            "今天先别把自己逼得太紧，慢慢来就好。",
            {
                "topic": "daily_emotion",
                "topic_label": "日常与情绪",
                "scheduled_topic": "daily_emotion",
                "topic_weight": 20,
            },
        )

    def record_delivery(self, text, meta, *, message_id="", trigger="scheduled"):
        self.delivery = {
            "text": text,
            "meta": meta,
            "message_id": message_id,
            "trigger": trigger,
        }
        return "memory_test"


class FailingProactive(FakeProactive):
    def generate(self, recent_messages=None, *, sequence_index=None, presence=None):
        raise ModelError("test generation failed")


def temporary_config(root: Path) -> RuntimeConfig:
    data_dir = root / "data"
    data_dir.mkdir()
    return RuntimeConfig(
        workspace=root,
        data_dir=data_dir,
        api_key="test-key",
        base_url="http://127.0.0.1",
        model="test-model",
    )


class CodexLiveBridgeTests(unittest.TestCase):
    def test_force_generate_and_ack_use_codex_live_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bridge = CodexLiveBridge(config=temporary_config(root))
            fake = FakeProactive()
            bridge._proactive = fake  # type: ignore[assignment]
            try:
                self.assertEqual(bridge.status()["engine"], "codex-live")
                brief = bridge.next_brief(
                    force=True,
                    foreground_app="Terminal",
                    activity="刚完成测试",
                )
                self.assertTrue(brief["generated"])
                self.assertIn("慢慢来", brief["text"])
                self.assertEqual(fake.presence.foreground_app, "Terminal")
                self.assertEqual(fake.presence.activity, "刚完成测试")
                self.assertEqual(bridge.status()["topic_index"], 0)

                ack = bridge.ack(
                    brief["text"],
                    brief["topic_index"],
                    token=brief["token"],
                )
                self.assertEqual(ack["memory_id"], "memory_test")
                self.assertEqual(fake.delivery["trigger"], "codex_live")
                self.assertEqual(bridge.status()["topic_index"], 1)
                with sqlite3.connect(root / "data" / "memory.db") as connection:
                    count = connection.execute(
                        "SELECT count(*) FROM proactive_messages "
                        "WHERE session_id = 'codex-live'"
                    ).fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                bridge.close()

    def test_configure_updates_codex_live_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bridge = CodexLiveBridge(config=temporary_config(root))
            try:
                status = bridge.configure(
                    {
                        "ratios": {
                            "daily_emotion": 30,
                            "work_coding": 20,
                            "self_evolution": 20,
                            "user_gender": 10,
                            "user_custom": 20,
                        },
                        "base_interval_sec": 60,
                        "custom_quirks": ["散步"],
                        "persona_name": "Lisa",
                        "persona_style": {
                            "sweetness": 0.7,
                            "playfulness": 0.6,
                        },
                        "persona_learn_from_self_share": False,
                    }
                )
                self.assertEqual(status["topic_weights"]["daily_emotion"], 30)
                self.assertEqual(status["base_interval_sec"], 60)
                self.assertEqual(status["custom_quirks"], ["散步"])
                self.assertEqual(status["persona"]["name"], "Lisa")
                self.assertEqual(
                    status["persona"]["style"],
                    {"sweetness": 0.7, "playfulness": 0.6},
                )
                payload = json.loads(
                    (root / "data" / "config.json").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    payload["proactive"]["topic_weights"]["daily_emotion"],
                    30,
                )
                self.assertEqual(
                    payload["persona"]["style"]["sweetness"],
                    0.7,
                )
            finally:
                bridge.close()

    def test_generation_failure_is_not_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bridge = CodexLiveBridge(config=temporary_config(root))
            bridge._proactive = FailingProactive()  # type: ignore[assignment]
            try:
                brief = bridge.next_brief(force=True)

                self.assertFalse(brief["generated"])
                self.assertEqual(brief["reason"], "generation_failed")
                self.assertIn("test generation failed", brief["failure_reason"])
                self.assertEqual(brief["unanswered_streak"], 0)
                self.assertGreater(brief["next_due_at"], brief["last_user_at"] or 0)
            finally:
                bridge.close()

    def test_automatic_brief_defers_outside_presence_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bridge = CodexLiveBridge(config=temporary_config(root))
            try:
                bridge.scheduler.user_activity()
                bridge.scheduler.seconds_until_due = lambda: 0  # type: ignore[method-assign]

                result = bridge.next_brief()

                self.assertFalse(result["generated"])
                self.assertEqual(result["reason"], "presence_deferred")
                self.assertLess(result["idle_seconds"], 8)
                self.assertGreater(result["deferred_sec"], 0)
            finally:
                bridge.close()

    def test_remember_persona_updates_active_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bridge = CodexLiveBridge(config=temporary_config(root))
            try:
                result = bridge.remember(
                    "persona",
                    "以后回答先给结论，尽量简洁",
                )
                self.assertTrue(result["persona_traits_updated"])
                profile = bridge.memory.persona_profile(
                    scope=str(root),
                    include_candidates=True,
                    limit=20,
                )
                self.assertIn(
                    "conclusion_first",
                    {item["trait_key"] for item in profile},
                )
            finally:
                bridge.close()


class McpServerTests(unittest.TestCase):
    def test_initialize_list_and_status_use_codex_live_engine(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ)
            env.update(
                {
                    "CODEX_LIVE_DATA_DIR": str(Path(temp) / "data"),
                    "CODEX_LIVE_API_KEY": "test-key",
                    "CODEX_LIVE_MODEL": "test-model",
                    "LISA_COMPANION_WORKSPACE": temp,
                }
            )
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(PLUGIN_ROOT / "mcp" / "server.py"),
                    "--stdio",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            assert process.stdin is not None
            assert process.stdout is not None
            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {},
                },
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "companion_status",
                        "arguments": {},
                    },
                },
            ]
            for request in requests:
                process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            replies = [
                json.loads(process.stdout.readline()),
                json.loads(process.stdout.readline()),
                json.loads(process.stdout.readline()),
            ]
            process.stdin.close()
            process.wait(timeout=10)
            process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

            self.assertEqual(
                replies[0]["result"]["serverInfo"]["name"],
                "lisa-companion",
            )
            self.assertGreaterEqual(len(replies[1]["result"]["tools"]), 5)
            status_text = replies[2]["result"]["content"][0]["text"]
            status = json.loads(status_text)
            self.assertEqual(status["engine"], "codex-live")
            self.assertIn("topic_weights", status)


if __name__ == "__main__":
    unittest.main()
