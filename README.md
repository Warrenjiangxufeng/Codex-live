# Codex Live

Codex Live is an independent local companion and coding agent, packaged both as
a standalone CLI and as the `lisa-companion` Codex plugin.

The project contains its own copy of the companion engine. It has no runtime
dependency on Sunus, does not import the Sunus package, and does not read or
write `~/.sunus`.

## Features

- Five weighted proactive topics with adjustable ratios
- Persistent local memory, persona and quirky preferences
- Memory-backed proactive message generation
- Exponential backoff and persisted message delivery state
- Interactive Codex plugin tools and a `/companion` command
- Standalone `codex-live` CLI with the same core logic

## Standalone CLI

```bash
cd ~/voice-lisa/plugins/codex-live
./bin/codex-live doctor
./bin/codex-live
```

Install the global entrypoint:

```bash
./scripts/install_cli.sh
codex-live --version
```

The current directory is the workspace. Use `codex-live -C /path/to/project` to
start elsewhere.

## Codex plugin

```bash
codex plugin marketplace add .
codex plugin add lisa-companion@codex-live
```

Start a new Codex session after installation. Then run:

```text
/companion
```

The plugin generates a live companion message inside the current Codex
interaction. The returned message can be answered immediately. It does not
install a timer, queue a synthetic user prompt, or claim idle background
delivery.

## Independent state

Codex Live uses its own data directory:

```text
~/.codex-live/config.json
~/.codex-live/memory.db
```

Set `CODEX_LIVE_DATA_DIR` to override it. The `codex-live` session rows are
stored in this database and are independent from any other project.

## Persona growth

`~/.codex-live/config.json` can define a stable persona kernel:

```json
{
  "persona": {
    "name": "Lisa",
    "prompt": "温和、敏锐、尊重边界。",
    "examples": [
      "慢慢来，不催你。",
      "这一步做得很稳呀。"
    ],
    "style": {
      "sweetness": 0.7,
      "playfulness": 0.6,
      "warmth": 0.8,
      "independence": 0.8,
      "initiative": 0.5
    },
    "context_intensity": {
      "chat": 1.0,
      "task": 0.65,
      "risk": 0.3
    },
    "learn_from_self_share": false
  }
}
```

The configured persona has priority over older identity traits. Core identity
traits are protected from the six-trait distillation cap. Proactive messages are
stored as expression history by default and do not become persona evidence;
enabling `learn_from_self_share` is an explicit opt-in.

Proactive messages select a context-appropriate reaction intent (care, curiosity,
sharing, or playfulness), use shorter factual prompts less randomly, and derive a
daypart from local time. `min_idle_sec` and `max_idle_sec` define the quiet window;
messages generated outside it are deferred. `typing_chars_per_second` and
`bubble_seconds` are presentation hints for a host UI or voice adapter.

## Delivery in an active Codex host

Proactive content must be delivered by a native host interface that can append
an assistant-only message or notification. Do not queue a synthetic
`/companion` user prompt: Codex will treat it as real user input and start a new
assistant turn.

The Lisa Voice GUI is such a host: it calls the local Companion bridge directly,
acknowledges the generated message, and publishes it as a `Lisa` message in the
conversation stream. The pending proactive text is carried into the next user
turn as assistant context so the exchange remains coherent. In a bare Codex TUI
without native assistant-message delivery, proactive messages remain manual.

The compatibility trigger in `scripts/codex_proactive_trigger.py` is intentionally
disabled and refuses to inject prompts even if it is accidentally re-enabled.

## Development

The implementation uses only the Python standard library and targets
Python 3.10+.

```bash
PYTHONPATH=plugins/lisa-companion/vendor \
  python3 -m unittest discover -s plugins/lisa-companion/tests/codex_live -v

PYTHONPATH=plugins/lisa-companion/vendor \
  python3 -m unittest discover -s plugins/lisa-companion/tests -v
```

## Repository layout

```text
bin/codex-live
plugins/lisa-companion/
  .codex-plugin/plugin.json
  .mcp.json
  companion_core.py
  commands/
  mcp/
  skills/
  tests/
  vendor/codex_live/
pyproject.toml
scripts/install_cli.sh
```
