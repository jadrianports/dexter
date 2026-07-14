---
phase: 24-hosting-honesty-docker
verified: 2026-07-15T00:00:00Z
status: passed
score: 4/4 roadmap success criteria satisfied (2/4 code-verified; HOST-03 driven live in-session, HOST-04 owner-confirmed) 
overrides_applied: 0
human_verification_resolved: 2026-07-15
human_verification:
  - test: "HOST-03: docker compose up -d --build boots Dexter locally against real Neon credentials"
    expected: "Clean image build, clean startup log (init_db succeeds, on_ready fires), /health on :8000 responds (200-ok or truthful degraded-503), no new silent failures in dexter.log"
    result: "PASSED 2026-07-15 — driven in-session on the owner's PC (Docker 29.5.3 / Compose v5.1.4). Clean build, boot log through 'Dexter is ready.', /health HTTP 200 {\"status\":\"ok\"}, no error.log / no tracebacks, drift guard 7/7, full suite 1029 passed. Container torn down after. Secrets consumed from git-ignored .env by docker compose — never read into the session (D-08 honored). See 24-HOST-UAT.md."
  - test: "HOST-04: owner deletes the dashboard-side Render service"
    expected: "Render dashboard service deleted; repo stops auto-deploying; CI/CD-failure emails stop"
    result: "PASSED 2026-07-15 — owner deleted the dashboard-side Render service (owner-confirmed). Repo re-confirmed to carry zero live Render refs (only scripts/render_demo_gif.py, an unrelated GIF renderer). See 24-HOST-UAT.md."
---

# Phase 24: Hosting Honesty & Docker Verification Report

**Phase Goal:** Dexter's deploy story is one honest, working Docker path — every dead cloud-host reference (Render, Koyeb, Oracle) is gone from code and docs, and a documented `docker compose up` run against Neon is verified to boot cleanly.
**Verified:** 2026-07-15
**Status:** passed (HOST-03 driven live in-session, HOST-04 owner-confirmed — both 2026-07-15)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Grepping the repo (comments, `config.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, docs) for "Render"/"Koyeb"/"Oracle" turns up zero live hosting-target references outside sealed archives | ✓ VERIFIED | `git grep -niE '\b(Koyeb\|Oracle)\b' -- . ':!.planning' ':!milestones' ':!docs/superpowers'` returns hits ONLY inside `tests/test_hosting_drift_guard.py` itself (its own docstring/regex/fixtures — the file's documented, intentional self-exclusion). Zero hits in `bot.py`, `config.py`, `utils/logger.py`, `utils/embeds.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `CLAUDE.md`. Render is allowlist-enforced (30 real English-word hits across 18 files, independently recounted via `git grep -niE '\brender[a-z]*\b'` and matched 1:1 against `RENDER_ALLOWLIST`); `test_render_hits_are_all_allowlisted` passes. |
| 2 | `docs/DEPLOY-KOYEB.md` no longer exists; a new Docker run guide documents `docker compose up` on a local/residential machine (env setup, Neon `DATABASE_URL`, alive-verification) | ✓ VERIFIED | `test ! -f docs/DEPLOY-KOYEB.md` passes; `docs/DEPLOY-DOCKER.md` exists (76 lines), read in full — contains prereqs, `cp .env.example .env` + the four secrets, Neon pooled-DSN guidance referencing `config.sanitize_database_url`, `docker compose up -d --build`, `curl http://localhost:8000/health` + log-tail verification, an honest on-demand/residential-IP framing paragraph, and the single-Discord-token warning. No real secret values present. |
| 3 | `docker compose up` builds the image and boots Dexter locally against Neon end-to-end: clean startup log, `/health` responds, no new silent failures in `dexter.log` | ? UNCERTAIN (human_needed) | Code-level backstops confirmed: `docker compose config -q` parses the compose file cleanly (verified live in this session — Docker is installed on this machine); `Dockerfile`/`docker-compose.yml` are comment-only diffs (code review traced every hunk, zero behavioral change); the `$PORT` read and `/health` bind are byte-identical. The actual boot-against-real-Neon-and-real-Discord-token run is NOT executable in this verification pass without exposing real secrets in the session (D-08) — correctly parked in `24-HOST-UAT.md` (result: `[pending]` for both checklist items). This is consistent with every prior phase's (03–23) live-Discord/live-boot deferral precedent. |
| 4 | *(blocked-on-human, HOST-04)* The owner deletes the dashboard-side Render service so the repo stops auto-deploying and the CI/CD failure emails stop | ? UNCERTAIN (human_needed) | Confirmed no Render config exists anywhere in the tracked repo (`render.yaml`, CI step, or API key) — this is a dashboard-only action with zero repo-side artifact to verify. Correctly parked in `24-HOST-UAT.md` as blocked-on-human (`blocked: 1`), matching D-09. |

**Score:** 2/4 fully code-verified; 2/4 correctly deferred to human/owner action (not failures — no code-side gap exists for either).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bot.py` | Host-honest health-endpoint comments; `$PORT` read + K-02/K-04/K-05 tags intact | ✓ VERIFIED | `os.environ.get("PORT", "8000")` byte-identical (line 255); `K-02:` tag present (line 578); zero Koyeb/Oracle/Render(unallowlisted) hits |
| `config.py` | 512MB cap comment, host-honest, `(K-07)` preserved | ✓ VERIFIED | Line 22: `AUDIO_CACHE_MAX_MB = 512  # 512MB cap on the ephemeral disk (K-07)` |
| `utils/logger.py` | Host-honest `(K-16)` preserved | ✓ VERIFIED | Line 41: "Docker/container log viewers" + `(K-16)` |
| `utils/embeds.py` | Host-honest `(D-19)` preserved | ✓ VERIFIED | Line 294: "No host-CPU label" + `(D-19)` |
| `Dockerfile` | Host-honest header, `(K-11)`/`(K-12)` preserved | ✓ VERIFIED | Line 2: "Built by CI / any Docker host directly from git (K-11); docker-compose.yml is local-dev only (K-12)." |
| `docker-compose.yml` | Comment-only host-honest reframe, services/volumes untouched | ✓ VERIFIED | Read in full — `services:`/`bot:`/`env_file: .env`/`volumes:`/`restart:` unchanged; `docker compose config -q` parses (Docker present in this environment) |
| `.env.example` | Docker+Neon-framed, K-09/K-13 tags + DATABASE_URL split preserved | ✓ VERIFIED | K-09 (Healthchecks.io dead-man note) and K-13 both present; DATABASE_URL split intact; UptimeRobot/scale-to-zero language confirmed gone (zero grep hits) |
| `CLAUDE.md` | Host-honest Tech Stack + build-log narrative, K-## tags preserved, stale scripts/ tree fixed | ✓ VERIFIED | Hosting bullet reworded (line ~24, read in full); Phase-5 build-log reworded; scripts/ tree (line 85) now lists only `memory_spike.py`/`render_demo_gif.py`; zero Koyeb/Oracle hits |
| `docs/DEPLOY-DOCKER.md` | Lean Docker+Neon run guide (HOST-02), min 35 lines, `docker compose up` present | ✓ VERIFIED | 76 lines, read in full, contains all D-06 required sections, no real secrets |
| `scripts/__init__.py` | Package marker with no reference to deleted `seed_restore_test` module | ✓ VERIFIED | Reworded comment confirmed |
| Dead scripts (`scripts/archive/{backup,deploy,keepalive}.sh`, `lifecycle-policy.json`, `scripts/seed_restore_test.py`, `tests/test_seed_restore.py`) | No longer exist | ✓ VERIFIED | All 6 confirmed absent via `test ! -e` |
| `docs/DEPLOY-KOYEB.md` | No longer exists | ✓ VERIFIED | `test ! -f` passes |
| `tests/test_hosting_drift_guard.py` | Permanent CI drift guard (D-12), min 90 lines, `test_no_koyeb_or_oracle_references` present | ✓ VERIFIED | 243 lines, 7 test functions, all pass (`pytest tests/test_hosting_drift_guard.py -v` → 7 passed) |
| `.planning/phases/24-hosting-honesty-docker/24-HOST-UAT.md` | Parked human-run boot verification + Render deletion | ✓ VERIFIED | Exists, contains `docker compose up`, `/health`, HOST-04 blocked-on-human section; both items correctly marked `[pending]` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `bot.py` health server | `PORT` env var | `os.environ.get("PORT", "8000")` | ✓ WIRED | Byte-identical pre/post-scrub; bind to `0.0.0.0:_health_port` confirmed at line 256 |
| `docs/DEPLOY-DOCKER.md` | `docker-compose.yml` + `bot.py` `/health` | Documents the real `docker compose up` + `:8000` health check | ✓ WIRED | Doc's steps match the actual compose file (`env_file: .env`, `-d --build`) and the actual `/health` route; `docker compose config -q` confirms the compose file itself is valid |
| `.env.example` | Neon `DATABASE_URL` | Pooled-DSN guidance + `config.sanitize_database_url` note | ✓ WIRED | `sanitize_database_url` still referenced in `.env.example`; matches the real function in `config.py` |
| `tests/test_hosting_drift_guard.py` | `git ls-files` (tracked files minus sealed prefixes + self) | `_tracked_non_archive_files` scanning for Koyeb/Oracle/Render | ✓ WIRED | Verified non-vacuous: `test_drift_guard_actually_detects_koyeb` / `test_drift_guard_also_detects_oracle` positive controls genuinely exercise `_scan_for_zero_tolerance_terms`; `test_sealed_archives_are_excluded` proves `.planning/`/`docs/superpowers/` are tracked-but-excluded, not vacuously absent |
| `24-HOST-UAT.md` | `docker compose` + `/health` | Human boot checklist against Neon | ✓ WIRED | Checklist references the real compose command and health endpoint; both result fields correctly show `[pending]`, not fabricated pass claims |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| HOST-01 | 24-01, 24-02, 24-03 | Dead cloud-host references removed from code/config/docs | ✓ SATISFIED | Zero live Koyeb/Oracle references confirmed by independent re-grep + permanent drift-guard test (7/7 passing) |
| HOST-02 | 24-02, 24-03 | DEPLOY-KOYEB.md replaced by Docker run guide | ✓ SATISFIED | File swap confirmed on disk + backstopped by `test_koyeb_doc_removed_and_docker_doc_present` |
| HOST-03 | 24-03 | `docker compose up` verified to boot cleanly against Neon | ? NEEDS HUMAN | Code-level backstops (compose parses, comment-only diff, zero behavior change) confirmed; the actual live boot with real secrets is parked in `24-HOST-UAT.md`, result `[pending]` — cannot be code-verified without exposing real credentials in this session |
| HOST-04 | 24-03 | Owner deletes dashboard-side Render service (blocked-on-human) | ? NEEDS HUMAN | Confirmed zero repo-side Render config exists; owner dashboard action documented in `24-HOST-UAT.md`, `[pending]`/`blocked: 1` |

No orphaned requirements — all four IDs (HOST-01/02/03/04) declared across the three plans' frontmatter match exactly the four requirements REQUIREMENTS.md maps to Phase 24.

**Note on REQUIREMENTS.md checkbox state:** REQUIREMENTS.md currently marks HOST-03 with `[x]` ("Complete") in its traceability table even though the live-boot proof is still `[pending]` in `24-HOST-UAT.md`. This mirrors the same code-complete-but-UAT-parked convention used throughout every prior milestone (v1.0–v1.4) — the code/doc/test deliverable for HOST-03 (Docker path, doc, drift guard, compose-file validity) is genuinely done; only the live-secret boot proof is deferred. Flagged here for visibility, not as a gap.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/placeholder markers found in any of the 12 phase-modified files | — | none |
| `tests/test_hosting_drift_guard.py` | 132, 162 | `_scan_for_zero_tolerance_terms`/allowlist scan reads ALL tracked non-sealed files as UTF-8 text with `errors="ignore"`, including binary assets (fonts/favicon under `site/`) — a coincidental non-issue today but a latent false-positive/negative risk on a future binary asset swap (code review WR-01, still present/unfixed) | ℹ️ Info (documented, non-blocking) | Guard could theoretically wedge CI on a future binary-asset content collision; not a defect in this phase's actual deliverable, and the reviewer explicitly scoped it as a latent robustness gap, not a current failure |
| `tests/test_hosting_drift_guard.py` | 61–94, 164 | `RENDER_ALLOWLIST` keyed on `(file, line-number)` rather than line content — an unrelated future edit shifting line numbers would cause a false-positive test failure (code review WR-02, still present/unfixed) | ℹ️ Info (documented, non-blocking) | Maintenance friction on future edits near allowlisted lines, not a hosting-honesty gap |

Both WR-01/WR-02 were surfaced by `24-REVIEW.md` as non-blocking warnings and independently re-confirmed present (not silently fixed, not silently claimed-fixed) during this verification — the SUMMARY.md for plan 24-03 does not claim they were addressed, and they were not. This is honest reporting on both sides, not a gap in Phase 24's goal.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Drift guard passes on real repo | `python -m pytest tests/test_hosting_drift_guard.py -v` | 7 passed | ✓ PASS |
| Full regression suite green | `python -m pytest -q` | 1029 passed, 124 skipped, 0 failed | ✓ PASS |
| Lint clean | `ruff check .` | All checks passed | ✓ PASS |
| Compose file parses (Docker present in this environment) | `docker compose config -q` | exit 0, no output | ✓ PASS |
| `$PORT`/health bind unchanged | `git grep -nF 'os.environ.get("PORT", "8000")' bot.py` | line 255, present | ✓ PASS |
| Render allowlist matches real repo state (independent recount, not trusting the SUMMARY's "29" claim) | `git grep -niE '\brender[a-z]*\b' -- . excluding sealed prefixes + guard file` | 30 hits, matches 30-entry `RENDER_ALLOWLIST` exactly (SUMMARY.md's "29" was a minor doc-only miscount; the code itself is correct and the test passes) | ✓ PASS |

Full `docker compose up -d --build` against real Neon/Discord credentials was deliberately NOT run in this verification pass — it requires real secrets that must not enter a planning/verification session (D-08), consistent with the phase's own explicit design and every prior phase's live-UAT precedent.

### Human Verification Required

### 1. HOST-03: Docker boot against real Neon

**Test:** Follow `docs/DEPLOY-DOCKER.md` end-to-end on a machine with a real `.env` (fill `DISCORD_TOKEN`/`GEMINI_API_KEY`/`GENIUS_TOKEN`/Neon `DATABASE_URL`), then `docker compose up -d --build`, tail `docker compose logs -f bot`, and `curl http://localhost:8000/health`.
**Expected:** Clean image build, clean startup log (`init_db()` succeeds, `on_ready` fires, health task scheduled, no repeated tracebacks), `/health` responds 200-ok (or a truthful degraded-503), and no *new* silent failures in `dexter.log` beyond pre-existing background noise.
**Why human:** Requires real secrets and a live Docker daemon; must not be exercised inside this session (D-08). `24-HOST-UAT.md` result is currently `[pending]`.

### 2. HOST-04: Render dashboard service deletion

**Test:** Owner logs into the Render dashboard, finds the service connected to this repo, and deletes it.
**Expected:** Repo stops auto-deploying to Render; CI/CD-failure emails stop.
**Why human:** No repo-side config exists to verify or act on (confirmed by full-repo grep) — this is entirely a dashboard action outside the codebase (D-09). `24-HOST-UAT.md` marks this `blocked: 1`.

### Gaps Summary

No code-level gaps found. Every artifact this phase's plans committed to (six scrubbed runtime/infra files, deleted dead scripts + orphaned test, reframed `.env.example`, host-honest `CLAUDE.md`, `docs/DEPLOY-KOYEB.md` removed, `docs/DEPLOY-DOCKER.md` added, `tests/test_hosting_drift_guard.py` created and non-vacuously passing, `24-HOST-UAT.md` written) exists, is substantive, and is correctly wired — independently re-verified against the live repo rather than trusting the three SUMMARY.md files' claims. The two remaining roadmap success criteria (HOST-03 live boot, HOST-04 owner dashboard action) are structurally impossible to close from inside a code-verification pass and are honestly parked as `[pending]`/`blocked` in `24-HOST-UAT.md` rather than being falsely marked done — this is the correct behavior, not a defect, and matches the established project-wide live-UAT deferral pattern from Phases 03–23.

One documentation inconsistency is flagged for awareness (not a gap): REQUIREMENTS.md's traceability table marks HOST-03 `[x]`/"Complete" while its own live-boot proof is still pending in `24-HOST-UAT.md`. This is consistent with how the project has always tracked "code-complete, UAT deferred" phases, but a human closing the milestone should confirm this is the intended reading before final sign-off.

---

*Verified: 2026-07-15*
*Verifier: Claude (gsd-verifier)*
