---
status: partial
phase: 24-hosting-honesty-docker
source: [24-RESEARCH.md]
started: 2026-07-15T00:00:00Z
updated: 2026-07-15T00:00:00Z
---

## Current Test

[awaiting human testing]

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
result: [pending]

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
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 1

## Gaps

- HOST-03 requires real secrets that must not live in this session (D-08) — deferred to the
  owner's next local run.
- HOST-04 requires owner-only Render dashboard access (D-09) — no repo-side action exists.
