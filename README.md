# Codex Live

Codex Live packages **Lisa Companion**, an isolated Codex plugin for
memory-backed proactive companion behavior.

The repository name is `codex-live`. The installed plugin keeps the runtime
identifier `lisa-companion` so existing Codex installations and local state
continue to work.

## Features

- Five weighted proactive topics with adjustable ratios
- Read-only recall through Lisa's existing memory interface
- Isolated persona, preference, and quirk storage
- Exponential backoff and persistent message deduplication
- MCP tools, a Codex skill, and a `/companion` command
- No dependency on the Sonus project

## Install

Add this repository as a Codex marketplace, then install the plugin:

```bash
codex plugin marketplace add https://github.com/Warrenjiangxufeng/Codex-live.git
codex plugin add lisa-companion@codex-live
```

Start a new Codex session after installation.

For local development:

```bash
git clone https://github.com/Warrenjiangxufeng/Codex-live.git
cd Codex-live
codex plugin marketplace add .
codex plugin add lisa-companion@codex-live
```

## Use

Run the companion command:

```text
/companion
```

The MCP surface supports status, message generation, acknowledgement,
configuration, memory recall, persona updates, and activity reset.

## Isolation

Plugin state is stored at:

```text
~/Library/Application Support/LisaCompanion/state.db
```

Set `LISA_COMPANION_HOME` to use a different state directory. The plugin reads
Lisa's memory through the existing read-only recall path and never writes to
the memory source directory.

Codex evaluates proactive messages during an agent turn. A host scheduler or
queued turn is still required for unsolicited delivery.

## Development

The plugin uses only the Python standard library and is tested on Python 3.10+.

```bash
cd plugins/lisa-companion
python3 -m unittest discover -s tests -v
```

Generated state databases and Python caches are intentionally excluded from
version control.

## Repository Layout

```text
.agents/plugins/marketplace.json
plugins/lisa-companion/
  .codex-plugin/plugin.json
  .mcp.json
  companion_core.py
  commands/
  mcp/
  skills/
  tests/
```

