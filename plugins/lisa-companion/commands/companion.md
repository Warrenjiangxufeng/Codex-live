---
description: Check or generate Lisa's next memory-backed proactive companion message.
---

# Lisa Companion

## Preflight

1. Call `companion_status`.
2. If proactive is paused, report that and stop unless the user explicitly asks to resume.
3. If the user asks about current settings, call `companion_status` and summarize ratios,
   custom quirks, gender settings, persona style and topic progress.

## Compose

If a message is due, or the user explicitly asks for a proactive message:

1. Call `companion_next_brief`; use `force=true` for an explicit `/companion` request.
   When the host already exposes a trusted foreground-app label or brief activity hint,
   pass it through `foreground_app` or `activity`; never capture the screen implicitly.
2. If `generated=false`, summarize the status and stop.
3. Otherwise output the returned `text` exactly; Codex Live already generated it.
4. Do not expose memory implementation details, IDs, ratios or internal metadata.
5. Call `companion_ack` with `text`, `topic_index` and `token`.

## Boundaries

- Use the project-local Codex Live engine as the source of truth.
- Do not install background schedulers or queue synthetic turns.
- `remember` only stores explicit user statements or explicit feedback.
- Gender is never inferred from name, occupation or tone.
- If the user sends a real message, call `companion_user_active`.
- If the user changes ratios, pass all five values to `companion_configure`; they must total 100.
- Persona style values are normalized to the 0-1 range. Self-share learning stays off unless
  the user explicitly enables `persona_learn_from_self_share`.

## Summary

When composing a proactive message, output only the final message.
For status/configuration requests, output a compact summary of the requested fields.
