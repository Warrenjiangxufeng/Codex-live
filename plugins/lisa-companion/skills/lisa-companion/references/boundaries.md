# Isolation and Data Boundaries

## Lisa Memory

The plugin reads Lisa's existing memory through:

- `mem.sh recall <query>` using the local read-only recall path
- last lines of `会话状态.md` and `用户记忆.md`

It must never:

- write or delete files under `~/Documents/Lisa记忆/`
- update Lisa's memory SQLite index
- claim a plugin-owned preference was written to Lisa memory

## Plugin State

Plugin state is stored separately:

```text
~/Library/Application Support/LisaCompanion/state.db
```

It contains topic ratios and progress, persona/quirk entries, proactive message
fingerprints and exponential backoff state. `LISA_COMPANION_HOME` may override the
directory.

## Scheduling Boundary

The MCP server computes whether a message is due, but Codex can only display a
proactive message during an agent turn. A host process must call the companion
tools or queue a turn for real unsolicited delivery. Never claim a message was
delivered unless the host actually delivered it.

## Gender

`lisa_gender` is the user's explicit gender-style setting for Lisa. `user_gender`
is the user's explicit gender. If either is absent, do not infer it.
