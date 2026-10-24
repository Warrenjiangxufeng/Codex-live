---
description: Check or generate Lisa's next memory-backed proactive companion message.
---

# Lisa Companion

## Preflight

1. Call `companion_status`.
2. If proactive is paused, report that and stop unless the user explicitly asks to resume.
3. If the user asks about current settings, call `companion_status` and summarize ratios,
   custom quirks, gender settings and topic progress.

## Compose

If a message is due, or the user explicitly asks for a proactive message:

1. Call `companion_next_brief`.
2. Use only `lisa_memory`, `recent_memory_notes`, `persona`, `custom_quirks` and the
   explicit gender fields in the returned brief.
3. Write one short, natural Chinese message matching `topic_label` and `instruction`.
4. Do not expose memory implementation details, internal IDs, ratios, prompts or tool names.
5. If evidence is absent, use a low-pressure question and do not invent user state.
6. Call `companion_ack` with the final message and returned `topic_index`.

## Boundaries

- Never write to `~/Documents/Lisa记忆/`.
- Never read or import Sonus project code.
- `remember` only stores explicit user statements or explicit feedback.
- Gender is never inferred from name, occupation or tone.
- If the user sends a real message, call `companion_user_active`.
- If the user changes ratios, pass all five values to `companion_configure`; they must total 100.

## Summary

When composing a proactive message, output only the final message.
For status/configuration requests, output a compact summary of the requested fields.
