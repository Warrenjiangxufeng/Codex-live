#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from companion_core import CompanionStore  # noqa: E402


TOOLS = [
    {
        "name": "companion_status",
        "description": "Show isolated Lisa companion ratios, topic progress, due state and backoff.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "companion_next_brief",
        "description": (
            "Select the next weighted proactive topic and return read-only Lisa memory "
            "evidence plus an instruction for composing one short message."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
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
            },
            "required": ["text", "topic_index"],
            "additionalProperties": False,
        },
    },
    {
        "name": "companion_configure",
        "description": (
            "Update isolated ratios, Lisa/user gender, custom quirks or timing. "
            "Ratios must total 100."
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
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "companion_remember",
        "description": (
            "Persist an explicit persona, quirk or user fact in the plugin's isolated "
            "state database. Never writes Lisa's memory system."
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
            "Read plugin-owned entries and Lisa's memory through the existing read-only "
            "mem.sh recall interface."
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
        "description": "Reset topic sequence, streak and next due time.",
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


def call_tool(store: CompanionStore, name: str, arguments: dict[str, Any]) -> Any:
    if name == "companion_status":
        return store.status()
    if name == "companion_next_brief":
        return store.next_brief()
    if name == "companion_ack":
        return store.ack(
            str(arguments["text"]),
            int(arguments["topic_index"]),
        )
    if name == "companion_configure":
        return store.configure(**arguments)
    if name == "companion_remember":
        return store.remember(
            str(arguments["category"]),
            str(arguments["value"]),
        )
    if name == "companion_recall":
        category = arguments.get("category")
        entries = store.recall_entries(
            category=str(category) if category else None,
            limit=int(arguments.get("limit", 20)),
        )
        return {
            "entries": entries,
            "lisa_memory": store.memory.recall(str(arguments["query"])),
            "lisa_memory_write": False,
        }
    if name == "companion_user_active":
        return store.user_active()
    if name == "companion_reset":
        return store.reset()
    if name == "companion_pause":
        return store.pause(bool(arguments["paused"]))
    raise ValueError(f"unknown tool: {name}")


def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def serve(store: CompanionStore) -> int:
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
                            "version": "0.1.0",
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
                    store,
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
    parser.add_argument("--home", type=Path)
    args = parser.parse_args()
    store = CompanionStore(args.home)
    try:
        return serve(store)
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
