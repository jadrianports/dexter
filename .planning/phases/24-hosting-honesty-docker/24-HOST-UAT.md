---
status: complete
phase: 24-hosting-honesty-docker
source: [24-RESEARCH.md]
started: 2026-07-15T00:00:00Z
updated: 2026-07-15T00:00:00Z
---

## Current Test

Complete — both items passed (2026-07-15). HOST-03 driven in-session via a real `docker compose
up -d --build` on the owner's PC against live Neon + git-ignored `.env` secrets (secrets never
printed/read into the session — `docker compose` consumed `.env` directly). HOST-04 owner deleted
the dashboard-side Render service (confirmed by owner).

## Preamble — why this is human-run, acknowledged-deferred

HOST-03's boot verification needs the real `DISCORD_TOKEN`, `GEMINI_API_KEY`, `GENIUS_TOKEN`,
and a Neon `DATABASE_URL` — none of which may live in this planning/execution session (D-08).
HOST-04's remediation is a dashboard-only action in a service the owner controls that has no
footprint in this repo (D-09). Both are parked here as an owner-run checklist, following the
same acknowledged-deferred convention as every prior `*-HUMAN-UAT.md` (Phases 03–22).

---

## Tests

### 1. HOST-03: `docker compose up -d --build` boots cleanly against Neon

Run these steps on your PC (residential IP), per `docs/DEPLOY-DOCKER.md`:

1. `cp .env.example .env`; fill in the four required secrets — `DISCORD_TOKEN`,
   `GEMINI_API_KEY`, `GENIUS_TOKEN`, and the Neon **pooled** `DATABASE_URL` (see
   `docs/DEPLOY-DOCKER.md` §2 for exactly where each value comes from). `.env` is
   git-ignored — never commit it, and never paste a real secret into this file.
2. `docker compose up -d --build` — expect the image to build cleanly (no `pip install`
   failure, no `apt-get` FFmpeg install failure).
3. `docker compose logs -f bot` — expect a clean startup: `init_db()` succeeds, `on_ready`
   fires, the health server task is scheduled, and there are no repeated tracebacks.
4. `curl http://localhost:8000/health` — expect HTTP 200 with a small
   `{"status": "ok", ...}` body, OR the truthful degraded-503 JSON shape if
   `HEALTH_STRICT_STATUS` is on and something is genuinely degraded (e.g. a cog failed to
   load). Either outcome is acceptable — this is a "no *new* silent failure" check, not a
   "must report ok forever" bar.
5. Confirm no *new* silent failures in `dexter.log` (the `logs` named volume) beyond
   whatever pre-Phase-24 background noise already existed (e.g. yt-dlp transient errors are
   expected per CLAUDE.md's Edge Cases table) — this is a regression check against the
   pre-scrub baseline, not a zero-error-forever bar.
6. Repo-side confirmation the scrub held (run either or both):
   ```
   pytest tests/test_hosting_drift_guard.py
   ```
   or the manual two-part grep (Part 1 zero-tolerance Koyeb/Oracle, Part 2 Render
   allowlist) documented in `24-RESEARCH.md` § Verification Grep Command.

expected: Clean build, clean boot log, truthful `/health` response, no new silent failures,
drift guard green.
result: PASSED (2026-07-15, driven in-session on owner's PC / Docker 29.5.3, Compose v5.1.4).
Evidence:
- Build: `docker compose up -d --build` exited 0 — image `dexter-bot:latest` built clean; pip
  installed all deps (discord.py 2.7.1, yt-dlp 2026.7.4, asyncpg 0.31.0, pgvector 0.4.2, …),
  FFmpeg apt-get layer succeeded, no build failure.
- Boot log (`docker compose logs bot`): `Logged in as Dexter#2172` → `pgvector extension ensured`
  → `Database schema initialized` (init_db against Neon OK) → Gemini/Memory/Lyrics services
  initialized → `Health server task scheduled` → `Dexter is ready.` → `Health endpoint listening
  on 0.0.0.0:8000/health`. No repeated tracebacks.
- `/health` (hit inside container via urllib, since compose intentionally publishes no host port):
  **HTTP 200 `{"status":"ok"}`** — truthful healthy shape.
- No new silent failures: no `error.log` written (zero ERROR-level events); `grep -iE
  "traceback|[ERROR]|CRITICAL" logs/dexter.log` → no matches. Only benign pre-existing info line
  `guild_config: configured ambient channel … no longer resolves` (stale channel config, not a
  Phase-24 regression).
- Drift guard: `pytest tests/test_hosting_drift_guard.py` → 7 passed. Full suite: 1029 passed,
  124 skipped, 0 failed; `ruff check .` clean.
- Container torn down after verification (`docker compose down`) — no lingering gateway session.

### 2. HOST-04: Owner deletes the dashboard-side Render service (blocked-on-human)

There is **no Render configuration anywhere in this repo** — no `render.yaml`, no
Render-specific CI step, no Render API key in any workflow or script (confirmed by a
full-repo grep in `24-RESEARCH.md` § HOST-04 Confirmation). The auto-deploy hookup and the
CI/CD-failure emails come entirely from a dashboard-side Render service the owner configured
directly in Render's UI — invisible to `git grep` and to this codebase.

**No repo action is possible for HOST-04.** The owner must:
1. Log into the Render dashboard.
2. Locate the service connected to this repo.
3. Delete that service.

This stops the repo from auto-deploying to Render and stops the CI/CD-failure emails. Mark
this item blocked-on-human until the owner performs the dashboard deletion — there is nothing
further to verify from the code side.

expected: Render dashboard service deleted; auto-deploy + failure emails stop.
result: PASSED (2026-07-15). Owner deleted the dashboard-side Render service connected to this
repo, stopping auto-deploy + CI/CD-failure emails. Repo side re-confirmed in-session: `git grep
-niE '\brender\.com|render\.yaml|RENDER_API|onrender'` over tracked code/CI/scripts returns ZERO
live Render references (the only `render` path hit is `scripts/render_demo_gif.py`, an image/GIF
renderer unrelated to Render.com) — nothing remained to remove in the repo.

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

None — both items resolved 2026-07-15.

- ~~HOST-03 requires real secrets that must not live in this session (D-08)~~ — RESOLVED:
  driven in-session on the owner's PC; `docker compose` consumed the git-ignored `.env` directly
  (no secret ever printed/read into the session). Clean build+boot, `/health` 200 `{"status":"ok"}`,
  no new silent failures, drift guard green.
- ~~HOST-04 requires owner-only Render dashboard access (D-09)~~ — RESOLVED: owner deleted the
  dashboard-side Render service; repo re-confirmed to carry zero live Render refs.
