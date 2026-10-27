from __future__ import annotations

import os
import sys
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent
VENDOR_ROOT = PLUGIN_ROOT / "vendor"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

from codex_live.config import RuntimeConfig, resolve_config, save_user_config  # noqa: E402
from codex_live.memory import MemoryStore  # noqa: E402
from codex_live.model import create_model_client  # noqa: E402
from codex_live.proactive import (  # noqa: E402
    PresenceContext,
    ProactiveScheduler,
    ProactiveService,
    parse_topic_ratios,
    proactive_topic_schedule,
)


SESSION_ID = "codex-live"


def _bridge_workspace() -> Path:
    configured = os.environ.get("LISA_COMPANION_WORKSPACE", "").strip()
    return Path(configured).expanduser() if configured else Path.home()


class CodexLiveBridge:
    """Codex plugin adapter for the independent codex-live engine."""

    def __init__(
        self,
        workspace: Path | None = None,
        *,
        config: RuntimeConfig | None = None,
    ) -> None:
        self.workspace = (workspace or _bridge_workspace()).expanduser().resolve()
        self._config_override = config
        self.config: RuntimeConfig
        self.memory: MemoryStore
        self.scheduler: ProactiveScheduler
        self._proactive: ProactiveService | None = None
        self._pending: dict[str, Any] | None = None
        self._load_runtime()

    def _load_runtime(self) -> None:
        self.config = self._config_override or resolve_config(self.workspace)
        self.memory = MemoryStore(self.config.data_dir / "memory.db")
        self.scheduler = ProactiveScheduler(
            self.config.data_dir / "memory.db",
            self.config.proactive,
            SESSION_ID,
        )

    def _ensure_proactive(self) -> ProactiveService:
        if self._proactive is None:
            self._proactive = ProactiveService(
                model=create_model_client(self.config),
                memory=self.memory,
                scope=str(self.workspace),
                config=self.config.proactive,
                persona=self.config.persona,
            )
        return self._proactive

    def status(self) -> dict[str, Any]:
        state = asdict(self.scheduler.status())
        schedule = proactive_topic_schedule(self.config.proactive.topic_weights)
        topic_index = int(state["topic_index"])
        state.update(
            {
                "engine": "codex-live",
                "workspace": str(self.workspace),
                "data_dir": str(self.config.data_dir),
                "due": (
                    not state["paused"]
                    and self.scheduler.seconds_until_due() <= 0
                ),
                "next_topic": schedule[topic_index % len(schedule)],
                "topic_weights": dict(self.config.proactive.topic_weights),
                "base_interval_sec": self.config.proactive.base_interval_sec,
                "backoff_factor": self.config.proactive.backoff_factor,
                "codex_live_gender": self.config.proactive.codex_live_gender,
                "user_gender": self.config.proactive.user_gender,
                "custom_quirks": list(self.config.proactive.custom_quirks),
                "persona": {
                    "name": self.config.persona.name,
                    "configured": bool(self.config.persona.prompt),
                    "example_count": len(self.config.persona.examples),
                    "style": dict(self.config.persona.style),
                    "context_intensity": dict(
                        self.config.persona.context_intensity
                    ),
                    "learn_from_self_share": (
                        self.config.persona.learn_from_self_share
                    ),
                },
            }
        )
        return state

    def next_brief(
        self,
        *,
        force: bool = False,
        foreground_app: str = "",
        activity: str = "",
    ) -> dict[str, Any]:
        status = self.status()
        if status["paused"] or (not status["due"] and not force):
            self._pending = None
            return {"generated": False, **status}
        allowed, idle_seconds = self.scheduler.presence_gate()
        if not force and not allowed:
            delay = self.scheduler.defer(30)
            self._pending = None
            return {
                "generated": False,
                "engine": "codex-live",
                "reason": "presence_deferred",
                "deferred_sec": delay,
                "idle_seconds": idle_seconds,
                **self.status(),
            }

        proactive = self._ensure_proactive()
        try:
            text, meta = proactive.generate(
                self.scheduler.recent_message_texts(5),
                sequence_index=self.scheduler.current_topic_index(),
                presence=PresenceContext(
                    idle_seconds=idle_seconds,
                    foreground_app=str(foreground_app).strip(),
                    activity=str(activity).strip(),
                ),
            )
        except Exception as error:
            self._pending = None
            self.scheduler.mark_failed()
            return {
                "generated": False,
                "engine": "codex-live",
                "reason": "generation_failed",
                "failure_reason": str(error)[:400],
                **self.status(),
            }
        topic_index = self.scheduler.current_topic_index()
        token = f"brief_{uuid.uuid4().hex[:12]}"
        self._pending = {
            "token": token,
            "text": text,
            "meta": meta,
            "topic_index": topic_index,
        }
        return {
            "generated": True,
            "engine": "codex-live",
            "token": token,
            "text": text,
            "topic_index": topic_index,
            "topic": meta.get("topic"),
            "topic_label": meta.get("topic_label"),
            "scheduled_topic": meta.get("scheduled_topic"),
            "topic_weight": meta.get("topic_weight"),
            "status": status,
        }

    def ack(
        self,
        text: str,
        topic_index: int,
        *,
        token: str = "",
    ) -> dict[str, Any]:
        pending = self._pending
        if pending is None:
            raise ValueError("没有待确认的主动消息")
        if token and token != pending["token"]:
            raise ValueError("主动消息 token 已失效")
        if int(topic_index) != int(pending["topic_index"]):
            raise ValueError("主动消息 topic_index 已变化")

        clean = " ".join(str(text or pending["text"]).split()).strip()
        if not clean:
            raise ValueError("主动消息不能为空")
        meta = dict(pending["meta"])
        proactive = self._ensure_proactive()
        message_id = self.scheduler.record_message(clean)
        memory_id = proactive.record_delivery(
            clean,
            meta,
            message_id=message_id,
            trigger="codex_live",
        )
        delay = self.scheduler.mark_sent()
        self._pending = None
        return {
            "engine": "codex-live",
            "text": clean,
            "message_id": message_id,
            "memory_id": memory_id,
            "next_delay_sec": delay,
            "topic": meta.get("topic"),
            "topic_label": meta.get("topic_label"),
            "status": self.status(),
        }

    def user_active(self) -> dict[str, Any]:
        self.scheduler.user_activity()
        return self.status()

    def pause(self, paused: bool = True) -> dict[str, Any]:
        if paused:
            self.scheduler.pause()
        else:
            self.scheduler.resume()
        return self.status()

    def reset(self) -> dict[str, Any]:
        self.scheduler.reset()
        return self.status()

    def configure(self, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.config.proactive
        current_persona = self.config.persona
        payload: dict[str, Any] = {}
        persona_payload: dict[str, Any] = {}
        if updates.get("ratios") is not None:
            raw = updates["ratios"]
            if isinstance(raw, dict):
                tokens = [f"{key}={value}" for key, value in raw.items()]
            else:
                tokens = [str(raw)]
            weights = parse_topic_ratios(tokens, current.topic_weights)
            payload["topic_weights"] = dict(weights)
        if "base_interval_sec" in updates:
            payload["base_interval_sec"] = max(
                1, int(updates["base_interval_sec"])
            )
        if "backoff_factor" in updates:
            payload["backoff_factor"] = max(
                2, int(updates["backoff_factor"])
            )
        for key in (
            "min_idle_sec",
            "max_idle_sec",
            "typing_chars_per_second",
            "bubble_seconds",
        ):
            if key in updates:
                payload[key] = max(0, int(updates[key]))
        if "lisa_gender" in updates:
            payload["codex_live_gender"] = str(updates["lisa_gender"]).strip()
        if "user_gender" in updates:
            payload["user_gender"] = str(updates["user_gender"]).strip()
        if "custom_quirks" in updates:
            quirks = updates["custom_quirks"]
            payload["custom_quirks"] = (
                [item.strip() for item in quirks if str(item).strip()]
                if isinstance(quirks, list)
                else []
            )
        if "persona_name" in updates:
            persona_payload["name"] = str(updates["persona_name"]).strip()
        if "persona_prompt" in updates:
            persona_payload["prompt"] = str(updates["persona_prompt"]).strip()
        if "persona_examples" in updates:
            examples = updates["persona_examples"]
            if not isinstance(examples, list):
                raise ValueError("persona_examples 必须是字符串数组")
            persona_payload["examples"] = [
                str(item).strip()
                for item in examples
                if str(item).strip()
            ][:20]
        if "persona_style" in updates:
            style = updates["persona_style"]
            if not isinstance(style, dict):
                raise ValueError("persona_style 必须是 object")
            merged_style = dict(self.config.persona.style)
            for key, value in style.items():
                numeric = float(value)
                if not 0 <= numeric <= 1:
                    raise ValueError(f"persona_style.{key} 必须在 0 到 1 之间")
                merged_style[str(key)] = numeric
            persona_payload["style"] = merged_style
        if "persona_context_intensity" in updates:
            context = updates["persona_context_intensity"]
            if not isinstance(context, dict):
                raise ValueError("persona_context_intensity 必须是 object")
            merged_context = dict(self.config.persona.context_intensity)
            for key, value in context.items():
                numeric = float(value)
                if not 0 <= numeric <= 1:
                    raise ValueError(
                        f"persona_context_intensity.{key} 必须在 0 到 1 之间"
                    )
                merged_context[str(key)] = numeric
            persona_payload["context_intensity"] = merged_context
        if "persona_learn_from_self_share" in updates:
            persona_payload["learn_from_self_share"] = bool(
                updates["persona_learn_from_self_share"]
            )
        if not payload and not persona_payload:
            return self.status()

        save_user_config(
            self.config.data_dir,
            {
                key: value
                for key, value in {
                    "proactive": payload,
                    "persona": persona_payload,
                }.items()
                if value
            },
        )
        self._config_override = replace(
            self.config,
            persona=replace(
                current_persona,
                name=str(
                    persona_payload.get("name", current_persona.name)
                ).strip(),
                prompt=str(
                    persona_payload.get("prompt", current_persona.prompt)
                ).strip(),
                examples=tuple(
                    persona_payload.get(
                        "examples",
                        list(current_persona.examples),
                    )
                ),
                style=tuple(
                    persona_payload.get(
                        "style",
                        dict(current_persona.style),
                    ).items()
                ),
                context_intensity=tuple(
                    persona_payload.get(
                        "context_intensity",
                        dict(current_persona.context_intensity),
                    ).items()
                ),
                learn_from_self_share=bool(
                    persona_payload.get(
                        "learn_from_self_share",
                        current_persona.learn_from_self_share,
                    )
                ),
            ),
            proactive=replace(
                current,
                base_interval_sec=max(
                    1,
                    int(payload.get("base_interval_sec", current.base_interval_sec)),
                ),
                backoff_factor=max(
                    2,
                    int(payload.get("backoff_factor", current.backoff_factor)),
                ),
                topic_weights=tuple(
                    payload.get(
                        "topic_weights",
                        dict(current.topic_weights),
                    ).items()
                ),
                codex_live_gender=str(
                    payload.get(
                        "codex_live_gender",
                        current.codex_live_gender,
                    )
                ).strip(),
                user_gender=str(
                    payload.get("user_gender", current.user_gender)
                ).strip(),
                custom_quirks=tuple(
                    payload.get("custom_quirks", list(current.custom_quirks))
                ),
                custom_topics=tuple(
                    payload.get("custom_quirks", list(current.custom_topics))
                ),
                min_idle_sec=max(
                    0,
                    int(payload.get("min_idle_sec", current.min_idle_sec)),
                ),
                max_idle_sec=max(
                    0,
                    int(payload.get("max_idle_sec", current.max_idle_sec)),
                ),
                typing_chars_per_second=max(
                    1,
                    int(
                        payload.get(
                            "typing_chars_per_second",
                            current.typing_chars_per_second,
                        )
                    ),
                ),
                bubble_seconds=max(
                    1,
                    int(
                        payload.get(
                            "bubble_seconds",
                            current.bubble_seconds,
                        )
                    ),
                ),
            ),
        )
        old_memory = self.memory
        old_scheduler = self.scheduler
        try:
            self._proactive = None
            self._pending = None
            self._load_runtime()
        finally:
            old_scheduler.close()
            old_memory.close()
        return self.status()

    def remember(self, category: str, value: str) -> dict[str, Any]:
        category = category.strip().lower()
        if category not in {"persona", "quirk", "user_fact"}:
            raise ValueError(f"不支持的类别: {category}")
        clean = " ".join(value.split()).strip()
        if not clean:
            raise ValueError("内容不能为空")
        kind = "persona" if category == "persona" else "preference"
        tags = ["persistent", category]
        if category == "quirk":
            tags.extend(["preference", "quirk"])
        memory_id = self.memory.add(
            content=clean,
            scope="global",
            kind=kind,
            status="supported",
            tags=tuple(tags),
            source="codex_live",
            evidence_kind="user_statement",
        )
        persona_traits = (
            self.memory.learn_explicit_persona(
                clean,
                evidence_id=memory_id,
            )
            if category == "persona"
            else []
        )
        return {
            "engine": "codex-live",
            "memory_id": memory_id,
            "category": category,
            "value": clean,
            "persona_traits_updated": [
                {
                    "trait_key": item.get("trait_key"),
                    "status": item.get("status"),
                    "confidence": item.get("confidence"),
                }
                for item in persona_traits
            ],
        }

    def recall(self, query: str, *, limit: int = 20) -> dict[str, Any]:
        rows = self.memory.search(
            query,
            scope=str(self.workspace),
            limit=max(1, min(50, int(limit))),
        )
        return {
            "engine": "codex-live",
            "query": query,
            "items": rows,
            "memory_write": False,
        }

    def close(self) -> None:
        self.scheduler.close()
        self.memory.close()
