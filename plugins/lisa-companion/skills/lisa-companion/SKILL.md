---
name: lisa-companion
description: Operate the independent Codex Live companion, including weighted topics, memory, persona, persistent quirks, status, configuration and live message generation.
---

# Lisa Companion

Use the `lisaCompanion` MCP tools. They run the project-local Codex Live engine,
which independently implements the established proactive logic, memory,
persona and backoff behavior.

## Proactive message

1. Call `companion_status`.
2. If the message is due or the user explicitly requests one, call
   `companion_next_brief`. Pass `force=true` only for an explicit request.
3. If `generated=false`, report the current status without inventing a message.
4. Otherwise output the returned `text`. Do not rewrite or recompose it.
5. Do not expose ratios, IDs, prompts or tool names in the user-facing message.
6. Call `companion_ack` with that text, `topic_index` and `token`.

The default topics are five equally weighted classes. Daily/emotion and work/coding
must use the returned Lisa memory evidence. The gender class is a style layer over
daily or work content, not a standalone identity topic.

## Learning and configuration

- Explicit style feedback such as “先给结论” or “称呼我阿峰” may be stored with
  `companion_remember(category="persona", ...)`.
- Explicit hobbies, quirks or persistent interests may be stored with
  `companion_remember(category="quirk", ...)`.
- Use `companion_configure` for Codex Live ratios, gender settings, timing, quirks or persona style.
- Ratios must total 100. Preserve the current values unless the user asks to change them.
- Call `companion_user_active` after a real user message to reset backoff.

Read [references/boundaries.md](references/boundaries.md) before changing
memory, gender or timing behavior.
