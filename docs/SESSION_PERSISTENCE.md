# Do I remember this project if you start a new session?

## Yes — because the project lives in files + cron jobs

Even if the chat session resets, the system persists because:

- The whole trading project is stored on disk:
  - `G:\New folder\New folder\trading_bot\...`
- The scheduled automation is stored in OpenClaw cron (Gateway).

So in a new session, I can re-open these files and continue.

## What is NOT guaranteed

- Chat memory is not magical. If you don't write important state to files, it can be lost across sessions.

## Where the session/state is saved

- Trading bot state:
  - `data/fyers_token.json`
  - `data/valid_universe.json`
  - `data/last_approval.json`
  - logs under `logs/`
  - reports under `reports/`

- OpenClaw session logs are stored under your OpenClaw agent/session directories (managed by OpenClaw).
- Cron schedules are stored in OpenClaw Gateway state.

Best practice: treat `docs/ENGINE_STATUS.md` + configs as the single source of truth.
