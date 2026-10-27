# Isolation and Data Boundaries

## Codex Live Runtime

The plugin ships the independent Codex Live engine and reads:

- `~/.codex-live/config.json` for proactive settings
- `~/.codex-live/memory.db` for memory, persona and proactive state

`CODEX_LIVE_DATA_DIR` may override the data directory. The plugin never reads or
writes `~/.sunus` and never imports the Sunus package.

## Delivery

The plugin generates messages inside an active Codex interaction. It does not
install a timer, queue a synthetic user prompt, or claim background delivery.
The generated Codex Live message becomes interactive immediately after it is shown.

## Gender

`codex_live_gender` is the user's explicit gender-style setting. `user_gender`
is the user's explicit gender. If either is absent, do not infer it.
