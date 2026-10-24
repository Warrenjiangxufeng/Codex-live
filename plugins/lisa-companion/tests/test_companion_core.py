from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from companion_core import (  # noqa: E402
    CompanionStore,
    LisaMemoryReader,
    schedule_for,
)


class FakeMemoryReader:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def recall(self, query: str, *, timeout_sec: int = 10):
        self.queries.append(query)
        return {
            "ok": True,
            "text": f"memory evidence for: {query}",
        }

    def recent_notes(self, *, lines_per_file: int = 16):
        return [
            {
                "path": "/tmp/user-memory.md",
                "text": "最近睡眠不好，情绪有些低落",
            }
        ]


class CompanionCoreTests(unittest.TestCase):
    def test_default_schedule_is_five_equal_topics(self) -> None:
        schedule = schedule_for(
            (
                ("daily_emotion", 20),
                ("work_coding", 20),
                ("self_evolution", 20),
                ("user_gender", 20),
                ("user_custom", 20),
            )
        )
        self.assertEqual(
            Counter(schedule),
            {
                "daily_emotion": 20,
                "work_coding": 20,
                "self_evolution": 20,
                "user_gender": 20,
                "user_custom": 20,
            },
        )
        self.assertEqual(len(set(schedule[:5])), 5)

    def test_configure_persona_ack_and_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            memory = FakeMemoryReader()
            store = CompanionStore(
                Path(temp),
                memory_reader=memory,  # type: ignore[arg-type]
                clock=lambda: 1_000.0,
            )
            configured = store.configure(
                ratios={
                    "日常": 30,
                    "工作": 20,
                    "成长": 20,
                    "性别": 10,
                    "癖好": 20,
                },
                lisa_gender="女",
                user_gender="男",
                custom_quirks=["散步"],
            )
            self.assertEqual(configured["ratios"]["daily_emotion"], 30)
            self.assertTrue(configured["lisa_gender_configured"])

            store.remember("persona", "回答先给结论，表达简洁")
            brief = store.next_brief()
            self.assertIn("memory evidence", brief["lisa_memory"]["text"])
            self.assertEqual(brief["isolation"]["lisa_memory_write"], False)
            acknowledged = store.ack("今天也按你的节奏来。", brief["topic_index"])
            self.assertEqual(acknowledged["topic_index"], 1)
            store.close()

            reopened = CompanionStore(Path(temp), memory_reader=memory)  # type: ignore[arg-type]
            self.assertEqual(reopened.status()["topic_index"], 1)
            reopened.close()

    def test_gender_layer_alternates_daily_and_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = CompanionStore(
                Path(temp),
                memory_reader=FakeMemoryReader(),  # type: ignore[arg-type]
                clock=lambda: 1_000.0,
            )
            briefs = []
            for index in range(5):
                brief = store.next_brief()
                briefs.append(brief)
                store.ack(f"message {index}", brief["topic_index"])
            gender = next(item for item in briefs if item["topic"] == "user_gender")
            self.assertIn(gender["base_topic"], {"daily_emotion", "work_coding"})
            self.assertIn("性别风格", gender["topic_label"])
            store.close()

    def test_user_activity_resets_backoff_without_touching_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            memory_home = Path(temp) / "Lisa记忆"
            memory_home.mkdir()
            user_memory = memory_home / "用户记忆.md"
            user_memory.write_text("稳定内容\n", encoding="utf-8")
            before = user_memory.read_text(encoding="utf-8")
            reader = LisaMemoryReader(memory_home)
            notes = reader.recent_notes()
            self.assertEqual(notes[0]["path"], str(user_memory))
            self.assertEqual(user_memory.read_text(encoding="utf-8"), before)


class McpServerTests(unittest.TestCase):
    def test_initialize_list_and_status_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ)
            env["LISA_COMPANION_HOME"] = temp
            env["LISA_MEMORY_HOME"] = str(Path(temp) / "missing-memory")
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

            self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "lisa-companion")
            self.assertGreaterEqual(len(replies[1]["result"]["tools"]), 5)
            status_text = replies[2]["result"]["content"][0]["text"]
            status = json.loads(status_text)
            self.assertEqual(status["ratios"]["daily_emotion"], 20)
            self.assertEqual(status["lisa_gender_configured"], False)


if __name__ == "__main__":
    unittest.main()
