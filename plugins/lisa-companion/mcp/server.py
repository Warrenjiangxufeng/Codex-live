#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from companion_core import CodexLiveBridge  # noqa: E402


TOOLS = [
    {
        "name": "companion_status",
        "description": "Show Codex Live proactive configuration, due state and progress.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "companion_next_brief",
        "description": "Generate a live message with the independent Codex Live engine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "force": {"type": "boolean", "default": False},
                "foreground_app": {"type": "string"},
                "activity": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "companion_ack",
        "description": (
            "Record one generated proactive message, advance the topic index and backoff. "
            "Call only after the model wrote the final message."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "topic_index": {"type": "integer", "minimum": 0},
                "token": {"type": "string"},
            },
            "required": ["text", "topic_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "companion_configure",
        "description": (
            "Update Codex Live ratios, timing, gender, quirks, or stable persona "
            "style. Ratios must total 100."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ratios": {
                    "type": "object",
                    "additionalProperties": {"type": "integer", "minimum": 0},
                },
                "lisa_gender": {"type": "string"},
                "user_gender": {"type": "string"},
                "custom_quirks": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "base_interval_sec": {"type": "integer", "minimum": 30},
                "backoff_factor": {"type": "integer", "minimum": 2},
                "min_idle_sec": {"type": "integer", "minimum": 0},
                "max_idle_sec": {"type": "integer", "minimum": 0},
                "typing_chars_per_second": {"type": "integer", "minimum": 1},
                "bubble_seconds": {"type": "integer", "minimum": 1},
                "persona_name": {"type": "string"},
                "persona_prompt": {"type": "string"},
                "persona_examples": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 20,
                },
                "persona_style": {
                    "type": "object",
                    "properties": {
                        "sweetness": {"type": "number", "minimum": 0, "maximum": 1},
                        "playfulness": {"type": "number", "minimum": 0, "maximum": 1},
                        "warmth": {"type": "number", "minimum": 0, "maximum": 1},
                        "independence": {"type": "number", "minimum": 0, "maximum": 1},
                        "initiative": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "additionalProperties": False,
                },
                "persona_context_intensity": {
                    "type": "object",
                    "properties": {
                        "chat": {"type": "number", "minimum": 0, "maximum": 1},
                        "task": {"type": "number", "minimum": 0, "maximum": 1},
                        "risk": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "additionalProperties": False,
                },
                "persona_learn_from_self_share": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "companion_remember",
        "description": (
            "Persist an explicit persona, quirk or user fact through Codex Live memory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["persona", "quirk", "user_fact"],
                },
                "value": {"type": "string"},
            },
            "required": ["category", "value"],
            "additionalProperties": False,
        },
    },
    {
        "name": "companion_recall",
        "description": (
            "Search Codex Live memory without modifying it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": ["persona", "quirk", "user_fact"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "companion_user_active",
        "description": "Reset the proactive backoff after real user activity.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "companion_reset",
        "description": "Reset Codex Live proactive sequence, streak and due time.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "companion_pause",
        "description": "Pause or resume proactive due checks.",
        "inputSchema": {
            "type": "object",
            "properties": {"paused": {"type": "boolean"}},
            "required": ["paused"],
            "additionalProperties": False,
        },
    },
]


def call_tool(
    bridge: CodexLiveBridge,
    name: str,
    arguments: dict[str, Any],
) -> Any:
    if name == "companion_status":
        return bridge.status()
    if name == "companion_next_brief":
        return bridge.next_brief(
            force=bool(arguments.get("force", False)),
            foreground_app=str(arguments.get("foreground_app", "")),
            activity=str(arguments.get("activity", "")),
        )
    if name == "companion_ack":
        return bridge.ack(
            str(arguments["text"]),
            int(arguments["topic_index"]),
            token=str(arguments.get("token", "")),
        )
    if name == "companion_configure":
        return bridge.configure(arguments)
    if name == "companion_remember":
        return bridge.remember(
            str(arguments["category"]),
            str(arguments["value"]),
        )
    if name == "companion_recall":
        return bridge.recall(
            str(arguments["query"]),
            limit=int(arguments.get("limit", 20)),
        )
    if name == "companion_user_active":
        return bridge.user_active()
    if name == "companion_reset":
        return bridge.reset()
    if name == "companion_pause":
        return bridge.pause(bool(arguments["paused"]))
    raise ValueError(f"unknown tool: {name}")


def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def serve(bridge: CodexLiveBridge) -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request: dict[str, Any] = {}
        try:
            request = json.loads(line)
            request_id = request.get("id")
            method = str(request.get("method") or "")
            if method == "notifications/initialized":
                continue
            if method == "initialize":
                payload = response(
                    request_id,
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {
                            "name": "lisa-companion",
                            "version": "0.2.0",
                        },
                    },
                )
            elif method == "ping":
                payload = response(request_id, {})
            elif method == "tools/list":
                payload = response(request_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params") or {}
                result = call_tool(
                    bridge,
                    str(params.get("name") or ""),
                    dict(params.get("arguments") or {}),
                )
                payload = response(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    result,
                                    ensure_ascii=False,
                                    indent=2,
                                ),
                            }
                        ],
                        "isError": False,
                    },
                )
            else:
                payload = error(request_id, -32601, f"method not found: {method}")
        except Exception as exc:
            payload = error(
                request.get("id"),
                -32603,
                f"{type(exc).__name__}: {exc}",
            )
        print(json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args()
    bridge = CodexLiveBridge(args.workspace)
    try:
        return serve(bridge)
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
