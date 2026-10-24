from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TOPIC_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("daily_emotion", 20),
    ("work_coding", 20),
    ("self_evolution", 20),
    ("user_gender", 20),
    ("user_custom", 20),
)
TOPIC_LABELS = {
    "daily_emotion": "日常与情绪",
    "work_coding": "工作与 coding",
    "self_evolution": "Lisa 性格与成长",
    "user_gender": "性别风格融合",
    "user_custom": "用户自定义癖好",
}
TOPIC_ALIASES = {
    "daily_emotion": "daily_emotion",
    "daily": "daily_emotion",
    "日常": "daily_emotion",
    "情绪": "daily_emotion",
    "work_coding": "work_coding",
    "work": "work_coding",
    "coding": "work_coding",
    "工作": "work_coding",
    "self_evolution": "self_evolution",
    "persona": "self_evolution",
    "成长": "self_evolution",
    "性格": "self_evolution",
    "user_gender": "user_gender",
    "gender": "user_gender",
    "性别": "user_gender",
    "user_custom": "user_custom",
    "custom": "user_custom",
    "癖好": "user_custom",
    "兴趣": "user_custom",
}
ENTRY_CATEGORIES = {"persona", "quirk", "user_fact"}


def default_state_home() -> Path:
    override = os.environ.get("LISA_COMPANION_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "LisaCompanion"


def schedule_for(weights: tuple[tuple[str, int], ...]) -> tuple[str, ...]:
    ratios = dict(weights)
    if set(ratios) != set(TOPIC_LABELS):
        raise ValueError("主题集合不完整")
    if any(weight < 0 for weight in ratios.values()):
        raise ValueError("比例不能为负数")
    if sum(ratios.values()) != 100:
        raise ValueError(f"比例合计必须为 100，当前为 {sum(ratios.values())}")
    order = [topic for topic, _ in weights]
    current = {topic: 0 for topic in order}
    schedule: list[str] = []
    for _ in range(100):
        for topic in order:
            current[topic] += ratios[topic]
        chosen = max(
            order,
            key=lambda topic: (current[topic], -order.index(topic)),
        )
        current[chosen] -= 100
        schedule.append(chosen)
    return tuple(schedule)


def parse_ratio_values(
    values: list[str],
    current: tuple[tuple[str, int], ...] = TOPIC_WEIGHTS,
) -> tuple[tuple[str, int], ...]:
    ratios = dict(current)
    for value in values:
        for token in str(value).replace("，", ",").split(","):
            if not token.strip():
                continue
            match = re.fullmatch(r"([^=:：]+)[=:：](\d+)", token.strip())
            if not match:
                raise ValueError(f"无法解析比例: {token}")
            topic = TOPIC_ALIASES.get(match.group(1).strip().lower())
            if topic is None:
                raise ValueError(f"未知主题: {match.group(1)}")
            ratios[topic] = int(match.group(2))
    schedule_for(tuple((topic, ratios[topic]) for topic, _ in current))
    return tuple((topic, ratios[topic]) for topic, _ in current)


class LisaMemoryReader:
    """Read-only access to Lisa's existing memory system."""

    def __init__(self, memory_home: Path | None = None) -> None:
        self.memory_home = (
            memory_home
            or Path(
                os.environ.get(
                    "LISA_MEMORY_HOME",
                    Path.home() / "Documents" / "Lisa记忆",
                )
            ).expanduser()
        )
        self.script = self.memory_home / "scripts" / "mem.sh"

    def recall(self, query: str, *, timeout_sec: int = 10) -> dict[str, Any]:
        if not self.script.is_file():
            return {"ok": False, "error": f"memory script not found: {self.script}"}
        try:
            completed = subprocess.run(
                ["/bin/bash", str(self.script), "recall", query],
                text=True,
                capture_output=True,
                timeout=max(1, min(30, timeout_sec)),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"ok": False, "error": str(error)}
        text = (completed.stdout or completed.stderr or "").strip()
        return {
            "ok": completed.returncode == 0,
            "source": str(self.script),
            "text": text[:8000],
        }

    def recent_notes(self, *, lines_per_file: int = 16) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for name in ("会话状态.md", "用户记忆.md"):
            path = self.memory_home / name
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            rows.append(
                {
                    "path": str(path),
                    "text": "\n".join(lines[-max(1, lines_per_file) :])[:5000],
                }
            )
        return rows


@dataclass(frozen=True)
class CompanionConfig:
    ratios: tuple[tuple[str, int], ...]
    base_interval_sec: int
    backoff_factor: int
    lisa_gender: str
    user_gender: str
    custom_quirks: tuple[str, ...]


class CompanionStore:
    def __init__(
        self,
        home: Path | None = None,
        *,
        memory_reader: LisaMemoryReader | None = None,
        clock=time.time,
    ) -> None:
        self.home = (home or default_state_home()).expanduser()
        self.home.mkdir(parents=True, exist_ok=True)
        try:
            self.home.chmod(0o700)
        except OSError:
            pass
        self.db_path = self.home / "state.db"
        self.memory = memory_reader or LisaMemoryReader()
        self.clock = clock
        self._connection = sqlite3.connect(str(self.db_path), timeout=30)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._initialize()
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        now = self.clock()
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS companion_state (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    paused INTEGER NOT NULL DEFAULT 0,
                    ratios TEXT NOT NULL,
                    topic_index INTEGER NOT NULL DEFAULT 0,
                    next_due_at REAL NOT NULL,
                    last_sent_at REAL,
                    last_user_at REAL,
                    unanswered_streak INTEGER NOT NULL DEFAULT 0,
                    base_interval_sec INTEGER NOT NULL DEFAULT 300,
                    backoff_factor INTEGER NOT NULL DEFAULT 2,
                    lisa_gender TEXT NOT NULL DEFAULT '',
                    user_gender TEXT NOT NULL DEFAULT '',
                    custom_quirks TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS companion_entries (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    value TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS companion_messages (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    topic_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO companion_state(
                    id, paused, ratios, topic_index, next_due_at,
                    unanswered_streak, base_interval_sec, backoff_factor,
                    lisa_gender, user_gender, custom_quirks, updated_at
                ) VALUES (1, 0, ?, 0, ?, 0, 300, 2, '', '', '[]', ?)
                """,
                (
                    json.dumps(dict(TOPIC_WEIGHTS), ensure_ascii=False),
                    now + 300,
                    self._timestamp(),
                ),
            )

    def _timestamp(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock()))

    def _state_row(self) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM companion_state WHERE id = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("companion state is not initialized")
        return row

    def config(self) -> CompanionConfig:
        row = self._state_row()
        raw_ratios = json.loads(str(row["ratios"]))
        ratios = tuple((topic, int(raw_ratios[topic])) for topic, _ in TOPIC_WEIGHTS)
        return CompanionConfig(
            ratios=ratios,
            base_interval_sec=int(row["base_interval_sec"]),
            backoff_factor=int(row["backoff_factor"]),
            lisa_gender=str(row["lisa_gender"]),
            user_gender=str(row["user_gender"]),
            custom_quirks=tuple(json.loads(str(row["custom_quirks"]))),
        )

    def status(self) -> dict[str, Any]:
        row = self._state_row()
        config = self.config()
        streak = int(row["unanswered_streak"])
        delay = min(
            2**31 - 1,
            config.base_interval_sec * config.backoff_factor**streak,
        )
        schedule = schedule_for(config.ratios)
        index = int(row["topic_index"])
        return {
            "paused": bool(row["paused"]),
            "ratios": dict(config.ratios),
            "topic_index": index,
            "next_topic": schedule[index % len(schedule)],
            "next_due_at": float(row["next_due_at"]),
            "seconds_until_due": max(0.0, float(row["next_due_at"]) - self.clock()),
            "due": (
                not bool(row["paused"])
                and float(row["next_due_at"]) <= self.clock()
            ),
            "unanswered_streak": streak,
            "next_delay_sec": delay,
            "lisa_gender_configured": bool(config.lisa_gender),
            "user_gender_configured": bool(config.user_gender),
            "custom_quirks": list(config.custom_quirks),
            "state_db": str(self.db_path),
        }

    def configure(self, **updates: Any) -> dict[str, Any]:
        row = self._state_row()
        ratios = tuple(self.config().ratios)
        if "ratios" in updates and updates["ratios"] is not None:
            ratio_value = updates["ratios"]
            if isinstance(ratio_value, dict):
                tokens = [f"{key}={value}" for key, value in ratio_value.items()]
            elif isinstance(ratio_value, list):
                tokens = [str(value) for value in ratio_value]
            else:
                tokens = [str(ratio_value)]
            ratios = parse_ratio_values(tokens, ratios)
        base = max(
            30,
            int(updates.get("base_interval_sec", row["base_interval_sec"])),
        )
        backoff = max(
            2,
            int(updates.get("backoff_factor", row["backoff_factor"])),
        )
        quirks = updates.get(
            "custom_quirks",
            json.loads(str(row["custom_quirks"])),
        )
        if isinstance(quirks, str):
            quirks = [item.strip() for item in re.split(r"[,，\n]", quirks) if item.strip()]
        quirks = list(dict.fromkeys(str(item).strip() for item in quirks if str(item).strip()))
        with self._connection:
            self._connection.execute(
                """
                UPDATE companion_state
                SET ratios = ?, base_interval_sec = ?, backoff_factor = ?,
                    lisa_gender = ?, user_gender = ?, custom_quirks = ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    json.dumps(dict(ratios), ensure_ascii=False),
                    base,
                    backoff,
                    str(updates.get("lisa_gender", row["lisa_gender"]) or "").strip(),
                    str(updates.get("user_gender", row["user_gender"]) or "").strip(),
                    json.dumps(quirks, ensure_ascii=False),
                    self._timestamp(),
                ),
            )
        return self.status()

    def remember(self, category: str, value: str) -> dict[str, Any]:
        category = category.strip().lower()
        if category not in ENTRY_CATEGORIES:
            raise ValueError(f"不支持的类别: {category}")
        clean = " ".join(value.split()).strip()
        if not clean:
            raise ValueError("内容不能为空")
        clean = clean[:2000]
        fingerprint = hashlib.sha256(
            f"{category}|{clean}".encode("utf-8")
        ).hexdigest()
        entry_id = f"c_{uuid.uuid4().hex[:12]}"
        with self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO companion_entries(
                    id, category, value, fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (entry_id, category, clean, fingerprint, self._timestamp()),
            )
        row = self._connection.execute(
            "SELECT * FROM companion_entries WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return dict(row) if row is not None else {
            "id": entry_id,
            "category": category,
            "value": clean,
        }

    def recall_entries(
        self,
        *,
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if category:
            rows = self._connection.execute(
                """
                SELECT * FROM companion_entries
                WHERE category = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (category, max(1, min(100, limit))),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM companion_entries ORDER BY created_at DESC LIMIT ?",
                (max(1, min(100, limit)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def _topic_query(self, base_topic: str) -> str:
        return {
            "daily_emotion": "最近 心情 情绪 睡眠 休息 生活 状态 周末",
            "work_coding": "工作 项目 代码 开发 测试 任务 目标 复盘",
            "self_evolution": "沟通 表达 性格 习惯 反思 成长",
            "user_custom": "癖好 兴趣 爱好 收藏 习惯 关注 期待",
        }.get(base_topic, "最近 记忆")

    def next_brief(self) -> dict[str, Any]:
        row = self._state_row()
        config = self.config()
        schedule = schedule_for(config.ratios)
        topic_index = int(row["topic_index"])
        schedule_index = topic_index % len(schedule)
        topic = schedule[schedule_index]
        if topic == "user_gender":
            gender_seen = sum(
                1 for item in schedule[: schedule_index + 1]
                if item == "user_gender"
            )
            base_topic = (
                "daily_emotion" if gender_seen % 2 == 1 else "work_coding"
            )
        else:
            base_topic = topic
        query = self._topic_query(base_topic)
        memory_recall = self.memory.recall(query)
        recent_notes = self.memory.recent_notes()
        entries = self.recall_entries(
            category="persona" if topic == "self_evolution" else
            "quirk" if topic == "user_custom" else None,
            limit=8,
        )
        persona = self.recall_entries(category="persona", limit=8)
        quirks = config.custom_quirks or [
            item["value"] for item in entries if item["category"] == "quirk"
        ]
        instruction = {
            "daily_emotion": (
                "基于最近记忆中的生活状态或情绪线索，生成一句轻量关心或自然闲聊。"
            ),
            "work_coding": (
                "基于最近项目/coding 记忆，给一个很小、无压力的推进提醒。"
            ),
            "self_evolution": (
                "只从已积累 persona 和最近沟通中提炼一个稳定表达习惯，不虚构成长。"
            ),
            "user_custom": (
                "优先围绕用户癖好；没有设定时从明确记忆中学习，不编造。"
            ),
        }.get(
            base_topic,
            (
                f"底层主题是{TOPIC_LABELS[base_topic]}。"
                "把 Lisa 明确性别设定和用户明确性别证据融合到语气、称呼中，"
                "不构成单独身份话题，不做刻板推断。"
            ),
        )
        return {
            "topic": topic,
            "topic_label": (
                f"{TOPIC_LABELS[base_topic]} × 性别风格"
                if topic == "user_gender"
                else TOPIC_LABELS[topic]
            ),
            "topic_index": topic_index,
            "ratio": dict(config.ratios)[topic],
            "base_topic": base_topic,
            "instruction": instruction,
            "lisa_memory": memory_recall,
            "recent_memory_notes": recent_notes,
            "companion_entries": entries,
            "persona": persona,
            "lisa_gender": config.lisa_gender,
            "user_gender": config.user_gender,
            "custom_quirks": quirks,
            "isolation": {
                "lisa_memory_write": False,
                "sonus_dependency": False,
                "state_home": str(self.home),
            },
        }

    def ack(self, text: str, topic_index: int) -> dict[str, Any]:
        clean = " ".join(str(text).split()).strip()
        if not clean:
            raise ValueError("主动消息不能为空")
        config = self.config()
        schedule = schedule_for(config.ratios)
        current = self._state_row()
        expected = int(current["topic_index"])
        if int(topic_index) != expected:
            raise ValueError(
                f"topic_index 已变化：期望 {expected}，收到 {topic_index}"
            )
        topic = schedule[expected % len(schedule)]
        now = self.clock()
        streak = int(current["unanswered_streak"]) + 1
        delay = min(
            2**31 - 1,
            config.base_interval_sec * config.backoff_factor**streak,
        )
        fingerprint = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]
        message_id = f"m_{uuid.uuid4().hex[:12]}"
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO companion_messages(
                    id, topic, topic_index, text, fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    topic,
                    expected,
                    clean[:4000],
                    fingerprint,
                    self._timestamp(),
                ),
            )
            self._connection.execute(
                """
                UPDATE companion_state
                SET topic_index = ?, last_sent_at = ?, next_due_at = ?,
                    unanswered_streak = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    expected + 1,
                    now,
                    now + delay,
                    streak,
                    self._timestamp(),
                ),
            )
        return {
            "message_id": message_id,
            "fingerprint": fingerprint,
            "next_delay_sec": delay,
            **self.status(),
        }

    def user_active(self) -> dict[str, Any]:
        config = self.config()
        now = self.clock()
        with self._connection:
            self._connection.execute(
                """
                UPDATE companion_state
                SET last_user_at = ?, unanswered_streak = 0,
                    next_due_at = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    now,
                    now + config.base_interval_sec,
                    self._timestamp(),
                ),
            )
        return self.status()

    def reset(self) -> dict[str, Any]:
        config = self.config()
        now = self.clock()
        with self._connection:
            self._connection.execute(
                """
                UPDATE companion_state
                SET topic_index = 0, unanswered_streak = 0,
                    next_due_at = ?, updated_at = ?
                WHERE id = 1
                """,
                (now + config.base_interval_sec, self._timestamp()),
            )
        return self.status()

    def pause(self, paused: bool = True) -> dict[str, Any]:
        with self._connection:
            self._connection.execute(
                "UPDATE companion_state SET paused = ?, updated_at = ? WHERE id = 1",
                (1 if paused else 0, self._timestamp()),
            )
        return self.status()

