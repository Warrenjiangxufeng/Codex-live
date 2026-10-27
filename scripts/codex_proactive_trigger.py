#!/usr/bin/env python3
"""Compatibility guard for the retired synthetic /companion trigger."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


DEFAULT_CONFIG = Path.home() / ".codex-live" / "proactive_trigger.json"
DEFAULT_LOG = Path.home() / ".codex-live" / "proactive_trigger.log"
MESSAGE = (
    "background synthetic prompt injection is disabled; "
    "use /companion in an active Codex interaction"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    enabled = False
    try:
        payload = json.loads(args.config.read_text(encoding="utf-8"))
        enabled = bool(payload.get("enabled", False))
    except (OSError, json.JSONDecodeError):
        pass
    detail = (
        "obsolete trigger enabled but blocked; use native host delivery"
        if enabled
        else MESSAGE
    )
    if args.dry_run:
        print(detail)
        return 0
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a", encoding="utf-8") as handle:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        handle.write(f"{stamp} {detail}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
