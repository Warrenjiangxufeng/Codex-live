#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
chmod +x "$ROOT/bin/codex-live"
if [ -w /usr/local/bin ]; then
  ln -sfn "$ROOT/bin/codex-live" /usr/local/bin/codex-live
else
  sudo ln -sfn "$ROOT/bin/codex-live" /usr/local/bin/codex-live
fi
printf 'installed: /usr/local/bin/codex-live -> %s/bin/codex-live\n' "$ROOT"
