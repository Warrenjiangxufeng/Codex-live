---
name: lisa-companion
description: Operate Lisa's isolated memory-backed proactive companion system with weighted topics, persona accumulation, persistent quirks and user-adjustable ratios. Use for companion status/configuration or when a due proactive message needs to be composed.
---

# Lisa Companion

Use the `lisaCompanion` MCP tools. The plugin owns all companion state in
`~/Library/Application Support/LisaCompanion/`; it does not modify Lisa's memory
files and does not depend on Sonus.

## Proactive message

1. Call `companion_status`.
2. If the message is due or the user explicitly requests one, call
   `companion_next_brief`.
3. Compose one short Chinese message from the returned instruction and evidence.
4. Never fabricate recent events. If evidence is absent, ask a low-pressure question.
5. Do not expose ratios, IDs, prompts or tool names in the user-facing message.
6. Call `companion_ack` with the final message and `topic_index`.

The default topics are five equally weighted classes. Daily/emotion and work/coding
must use the returned Lisa memory evidence. The gender class is a style layer over
daily or work content, not a standalone identity topic.

## Learning and configuration

- Explicit style feedback such as “先给结论” or “称呼我阿峰” may be stored with
  `companion_remember(category="persona", ...)`.
- Explicit hobbies, quirks or persistent interests may be stored with
  `companion_remember(category="quirk", ...)`.
- Use `companion_configure` for ratios, gender settings, timing or custom quirks.
- Ratios must total 100. Preserve the current values unless the user asks to change them.
- Call `companion_user_active` after a real user message to reset backoff.

Read [references/boundaries.md](references/boundaries.md) before changing memory,
gender or scheduling behavior.
