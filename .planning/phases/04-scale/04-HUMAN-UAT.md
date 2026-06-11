---
status: partial
phase: 04-scale
source: [04-VERIFICATION.md]
started: 2026-06-12
updated: 2026-06-12
---

## Current Test

[awaiting human testing]

## Tests

These items passed all static/structural verification but require a live deploy
(Postgres + Discord + Oracle A1) that the dev machine cannot provide.

### 1. Postgres integration tests
expected: With a live `dexter_test` Postgres reachable via `TEST_DATABASE_URL`, `pytest tests/test_database_phase4.py` runs green (18 tests — schema, batch transaction, helpers). Collectible today; not executed (no local Postgres).
result: [pending]

### 2. Docker Compose clean boot on Oracle A1 ARM
expected: On a fresh Oracle Ampere A1 (arm64) VM, `docker compose up` brings up postgres + bot; the bot reaches `on_ready`, creates the pool, runs `init_db`, and connects to Discord. Persistent volumes survive `docker compose down && up`.
result: [pending]

### 3. Queue persistence round-trip across a real restart
expected: Queue songs in a guild, restart the bot (`docker compose restart bot`), and the queue is restored from `guild_queues`; smart-rejoin reconnects voice + resumes only when a non-bot human is still in the channel.
result: [pending]

### 4. Over-cap /play rejection live in Discord
expected: Queuing past `MAX_QUEUE_SIZE_PER_GUILD` (500) — including via a large playlist import — yields the lowercase personality rejection, and the bot does not exceed the cap.
result: [pending]

### 5. Keepalive cron + Healthchecks.io
expected: The `*/5 * * * *` `keepalive.sh` cron pings `HEALTHCHECK_URL`; the Healthchecks.io check shows green/"up" and would alert if the VM goes idle/down.
result: [pending]

### 6. Backup cron + Oracle Object Storage
expected: The `*/30 * * * *` `backup.sh` cron `pg_dump`s and uploads to the Oracle Object Storage bucket; a recent object is present and restorable.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
