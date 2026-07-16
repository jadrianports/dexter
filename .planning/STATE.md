---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Deep Cuts
status: executing
stopped_at: Phase 27 context gathered
last_updated: "2026-07-16T20:54:02.548Z"
last_activity: 2026-07-16 -- Phase 27 planning complete
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 10
  completed_plans: 10
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-14 after v1.4 milestone)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** Phase 26 — radio-mode-skip-democracy

## Current Position

Phase: 27
Plan: Not started
Status: Ready to execute
Last activity: 2026-07-16 -- Phase 27 planning complete

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed (v1.4): 32/32 (Phases 18–23) — milestone shipped 2026-07-14
- Total plans completed (v1.3): 18/18 (Phases 13–17) — milestone shipped 2026-07-03
- v1.0 + v1.1 + v1.2: 52 plans shipped across Phases 1-12 — full per-plan timings archived in milestones/v1.1-ROADMAP.md and milestones/v1.2-ROADMAP.md
- v1.5 (Phases 24–28): not yet planned — no timings yet

**By Phase (v1.4) — shipped, see milestones/v1.4-ROADMAP.md for full per-plan timings:**

| Phase | Plans |
|-------|-------|
| 18. Per-Guild Config Foundation | 7/7 |
| 19. Onboarding & Admin Setup | 4/4 |
| 20. Owner Control Plane & Rate Observability | 7/7 |
| 21. Memory Scoping & Guild Data Lifecycle | 4/4 |
| 22. Invite Plumbing | 3/3 |
| 23. Portfolio Surface & CI/CD | 7/7 |

**By Phase (v1.5) — roadmap only, plans TBD:**

| Phase | Plans |
|-------|-------|
| 24. Hosting Honesty & Docker | 0/TBD |
| 25. Smarter Memory | 0/TBD |
| 26. Radio Mode & Skip Democracy | 0/TBD |
| 27. Crossfade Playback (spike-gated) | 0/TBD |
| 28. Portfolio Finish & Release | 0/TBD |

**v1.4 per-plan timing detail (archived from execution):**

| Phase 18 P01 | 40min | 3 tasks | 82 files |
| Phase 18 P02 | 25min | 3 tasks | 4 files |
| Phase 18 P03 | 15min | 2 tasks | 2 files |
| Phase 18 P04 | 16min | 3 tasks | 2 files |
| Phase 18 P05 | 25min | 2 tasks | 1 files |
| Phase 18-per-guild-config-foundation-ci-gate P06 | 20min | 2 tasks | 2 files |
| Phase 18 P07 | 12min | 1 tasks | 1 files |
| Phase 19 P01 | 25min | 3 tasks | 3 files |
| Phase 19 P02 | 20min | 3 tasks | 6 files |
| Phase 19 P03 | 20min | 3 tasks | 3 files |
| Phase 19 P04 | 15min | 3 tasks | 2 files |
| Phase 20 P01 | 15min | 2 tasks | 4 files |
| Phase 20 P02 | 12min | 2 tasks | 2 files |
| Phase 20 P03 | 15min | 3 tasks | 6 files |
| Phase 20 P04 | 20min | 2 tasks | 2 files |
| Phase 20 P05 | 21min | 3 tasks | 3 files |
| Phase 20 P06 | 18min | 2 tasks | 1 files |
| Phase 20 P07 | 25min | 3 tasks | 3 files |
| Phase 21 P01 | 20min | 3 tasks | 3 files |
| Phase 21 P02 | 18min | 2 tasks | 2 files |
| Phase 21 P03 | 18min | 3 tasks | 5 files |
| Phase 21 P04 | 19min | 2 tasks | 3 files |
| Phase 22 P01 | 12min | 2 tasks | 4 files |
| Phase 22 P02 | 12min | 2 tasks | 4 files |
| Phase 22 P03 | 25min | 2 tasks | 3 files |
| Phase 23 P01 | 12min | 2 tasks | 4 files |
| Phase 23 P03 | 25min | 3 tasks | 12 files |
| Phase 23 P04 | 15min | 3 tasks | 3 files |
| Phase 23 P05 | 25min | 3 tasks | 9 files |
| Phase 23-portfolio-surface-ci-cd P07 | 35min | 3 tasks | 4 files |
| Phase 24 P01 | 12min | 3 tasks | 7 files |
| Phase 24 P02 | 15min | 3 tasks | 4 files |
| Phase 24 P03 | 30min | 2 tasks | 2 files |
| Phase 25 P01 | 25min | 3 tasks | 4 files |
| Phase 25 P02 | 35min | 2 tasks | 4 files |
| Phase 26 P01 | 45min | 3 tasks | 6 files |
| Phase 26 P02 | 30min | 3 tasks | 5 files |
| Phase 26 P03 | 40min | 3 tasks | 3 files |
| Phase 26 P04 | 35min | 3 tasks | 3 files |
| Phase 26 P05 | 38min | 3 tasks | 3 files |

## Accumulated Context

### Decisions

The full pre-v1.4 decision log (architecture, per-phase highlights, every prior-milestone implementation decision) is preserved in **PROJECT.md Key Decisions** and `milestones/v1.1/v1.2/v1.3/v1.4-ROADMAP.md`. This milestone's own decisions live in **REQUIREMENTS.md Key Decisions (this milestone)**. Enduring cross-milestone invariants worth carrying forward:

- `MemoryService.recall/remember/distill` is kind-agnostic — new memory kinds/scoping dimensions should be additive where possible (Phase 11/13; tested again in Phase 21's guild-scoping work). MEM-07's vision-sourced fact should follow the Phase 13 `taste_episode` precedent (new kind, not a new table).
- Accuracy firewall: qualitative narrative flows through vector memory; any number that drives a ranking decision comes from live SQL, never embedded text (Phase 11). Applies to MEM-07's distilled fact same as every other kind.
- Rate budgets: shared 15 RPM chat limiter (priority tiers) vs a separate ~60 RPM embed limiter — background work never starves user commands.
- Gemini 2.5 defaults `safety_settings` OFF — set them explicitly on every user-content `generate_content` call (Phase 17).
- Pure-logic TDD seam (`logic/*.py`): all decision logic mock-free-tested before Discord wiring; glue stays untested-by-design.
- **Standing Descope Rule (REQUIREMENTS.md):** if plan-time research proves a requirement infeasible, descope rather than force it — governs DJ-03's crossfade spike gate this milestone (descopes to DJ-F2 on a failed spike).
- **v1.5 sequencing lock (from roadmap creation):** Phase 24 (hosting/Docker cleanup) first — independent, low-risk, comments+docs+one verify; Phase 25 (smarter memory) additive over existing RAG infra, no dependency on 24; Phase 26 (radio + skip-voting) before Phase 27 (crossfade) so the playback-engine spike risk is contained to its own phase rather than compounding with the other music-engine work; Phase 28 (portfolio finish) last as milestone close-out — mostly blocked-on-human, PORT-05 already shipped (`c7fd22e`).
- [Phase 18]: Ruff adopted as the single lint+format tool (D-14); config files committed separately from the mechanical cleanup pass so the repo-wide reformat stays its own atomic commit (D-16).
- [Phase 18]: seed_guild_config_if_absent uses ON CONFLICT DO NOTHING (never DO UPDATE) so a stale DEXTER_CHANNEL_ID never overrides a later /setup write (D-09)
- [Phase 20-01]: guild_blocklist lands as its own table (D-01) with load_blocklist/insert_blocklist/delete_blocklist + set_silenced helpers in database.py; guild_config.is_blocked left in place but dead (D-03), documented in CLAUDE.md
- [Phase 21-02]: purge_guild_data's four-table list is four hardcoded SQL literals, never a loop / never information_schema — reviewability of the literal list IS the T-21-03 control that keeps guild_blocklist structurally out of reach (OWNER-04)
- [Phase 22-01]: Ten-permission bitfield (309240908864, D-09 amendment) locked with negative-assertion test; logic/invite.py is the one documented exception to the logic/ no-discord-import convention
- [Phase 23-portfolio-surface-ci-cd]: [Phase 23-07]: README.md rewritten as an architecture case study; drift guard proven NON-VACUOUS (README.md now in tracked-doc scan, canonical URL found, zero offenders) — PORT-03/PORT-04 delivered; the moment a tracked doc carries the invite URL, tests/test_invite_drift_guard.py stops passing vacuously and starts enforcing something real

> Full v1.4 per-phase decision log (30+ entries) preserved in milestones/v1.4-ROADMAP.md and prior STATE.md git history — trimmed here to keep this digest under the size guideline.

- [Phase 24-01]: deleted tests/test_seed_restore.py alongside scripts/seed_restore_test.py (sole importer) as the necessary completion of D-11, not new scope
- [Phase ?]: [Phase 24-02] Dropped (not repointed) the UptimeRobot inbound-keep-alive note from .env.example per D-07 -- no scale-to-zero concept applies to a residential Docker run
- [Phase ?]: [Phase 24-02] docs/DEPLOY-DOCKER.md deliberately omits the old doc's Neon-account walkthrough, UptimeRobot setup, Koyeb secrets-UI steps, and HeavenCloud/Wispbyte contingency -- none apply to the real docker compose up -> Neon flow
- [Phase 24]: [Phase 24-03] RENDER_ALLOWLIST derived fresh from git grep against the post-scrub repo (29 entries/18 files), not copied from 24-PATTERNS.md's pre-scrub line-number guesses
- [Phase 24]: [Phase 24-03] milestones/ sealed prefix kept as defensive/currently-vacuous (milestone docs nest under .planning/milestones/, already covered) rather than dropped or faked
- [Phase 25-01]: recall() reinforces expiry via a new GREATEST-guarded batched helper, grouped by kind, at the single step-7 chokepoint; salience/hit_count/last_seen_at stay byte-identical (D-01/D-02)
- [Phase 25]: MEM-07: vision_roast is a new memory kind (0.4 salience, TASTE_DECAY_DAYS decay); write is fire-and-forget after a successful roast reply, distilling the roast line (not the image) through the full accuracy/PII firewall (exempt_numbers=False since kind != taste_episode).
- [Phase 26-01]: radio armed-state lives on MusicQueue (not a service/DB) and clear() disarms it -- covers all four existing teardown sites for free, zero bot.py changes — D-11 makes radio and loop_mode mutually exclusive, same category of state as loop_mode which clear() already resets
- [Phase 26-01]: reconciled a prior executor's uncommitted mid-task-1 crash artifacts (logic/radio.py, config.py knobs) -- verified correct against plan spec, no rewrite needed, only added the missing test file
- [Phase ?]: [Phase 26-02]: floor(listener_count * majority_ratio) + 1 clamped to listener_count (never n // 2 + 1) so config.SKIP_VOTE_MAJORITY_RATIO is an honoured knob, not a lie -- reproduces D-09c's table at ratio=0.5
- [Phase ?]: [Phase 26-02]: decide_skip counts len(new_votes) never an intersection with listener_ids -- D-17 departed voters stay counted; locked by both a source-grep test and a behavioral test
- [Phase ?]: [Phase 26-02]: MusicQueue skip-vote state is a single-slot cache keyed to (current_index, video_id), reset lazily on read -- structural D-17 reset with zero per-mutation-site hooks; a revisited track's earlier votes are not resurrected
- [Phase 26-03]: try_auto_queue(guild, *, radio: bool = False) is the radio refill entry point (D-01) -- round cap lifted, prompt anchored on the armed seed, session repeats hard-rejected after YouTube resolution via an independent post-filter, ignored-signal announce/memory-write suppressed while armed (D-05); byte-identical when radio=False, locked by a source-scan regression guard
- [Phase 26]: [Phase 26-04]: _try_skip is a new gate-wraps-mechanics wrapper; _do_skip stays completely unmodified and is called ONLY on SKIP_NOW, preserving D-20 and Critical Rule 3 for free
- [Phase 26]: [Phase 26-04]: closed a second, plan-undocumented vote-bypass surface -- /seek's past-end auto-skip called _do_skip directly, letting any single user force an unvoted skip; routed through _try_skip too since the plan's own acceptance criteria (exactly one _do_skip call site) required it
- [Phase 26-05]: radio start kicks its first refill through the same should_refill_radio gate the lookahead uses, giving D-12 non-destructive takeover with no special starting case; both /radio start and /radio stop call reset_auto_queue() so radio-era play/skip counts never leak into the next auto-queue session's ignored-signal check

### Pending Todos

None.

### Blockers/Concerns

- [Parked] The 24/7 live deploy remains parked behind the YouTube datacenter-IP block. Not scoped to v1.5 — hosting model is intentionally unchanged this milestone (Docker becomes the honest local run path, not a 24/7 standup).
- [Watch] DJ-03 crossfade (Phase 27) is spike-gated — plan-time research must prove `/skip`-mid-crossfade + generation-counter safety before implementation proceeds; descope to DJ-F2 per the standing Descope Rule if the spike shows engine instability.
- [Watch] MEM-06/MEM-07 (Phase 25) touch the same `user_memories`/decay-sweep subsystem that carried the Phase 13 CR-01 scar and the Phase 21 guild-scoping surgery — verify salience-reinforcement math and the new vision-kind write path don't regress existing kinds' decay behavior.

## Deferred Items

Acknowledged and deferred at **v1.4 milestone close (2026-07-14)** — 36 open items from the pre-close artifact audit (17 UAT gaps, 16 `human_needed` verification, 3 stale CONTEXT markers) **plus 3 blocked-on-human v1.4 requirements** (PORT-02, CICD-02, CICD-03 — all carried forward into v1.5 as the same requirement IDs, now mapped to Phase 28). All are `human_needed` live-Discord checks, manual GitHub-UI toggles, or stale planning markers — **zero code gaps** (code-complete, CI green at HEAD `006da2a`). The live-Discord tail resumes when a Pi / always-on residential host exists (DEPLOY-F1); the blocked-on-human reqs resume when the owner performs the manual GitHub-UI / live-bot steps.

### Blocked-on-human v1.5 requirements (4, incl. 3 carried from v1.4)

| Req | Item | Status |
|-----|------|--------|
| HOST-04 | Delete the dashboard-side Render service so the repo stops auto-deploying and CI/CD failure emails stop | Blocked on owner Render-UI step |
| PORT-02 | Demo GIF needs two verbatim real Dexter personality lines (placeholder tokens intact; no invented lines) | Blocked on live bot capture |
| CICD-02 | Enable GitHub Pages (Settings→Pages→Source=GitHub Actions) + first `pages.yml` run | Blocked on owner GitHub-UI toggle |
| CICD-03 | GHCR package-visibility flip + first `v*` tag `release.yml` run | Blocked on owner GitHub-UI toggle |

### Live-Discord / verification tail (33, carried from v1.4 close)

| Category | Item | Status |
|----------|------|--------|
| uat | Phases 18/19/20/21/22 — `*-HUMAN-UAT.md` (v1.4: `/setup`, kill-switch, guild-scoped recall, `/invite`, join/leave notifications feel) | Blocked on live Discord/host |
| verification | Phases 18/19/20/21/22 — `*-VERIFICATION.md` (`human_needed`) | Blocked on live Discord/host |
| uat | Phases 14/15/16/17 — `*-HUMAN-UAT.md` (v1.3: taste auto-queue, `/memory`, proactive feel, vision) | Blocked on live Discord/host |
| verification | Phases 14/15/16/17 — `*-VERIFICATION.md` (`human_needed`) | Blocked on live Discord/host |
| uat/verification | Phases 09/11 — `*-HUMAN-UAT`/`*-VERIFICATION` (v1.2: truthful `/health`, task surfacing, live RAG recall) | Blocked on live Discord/host |
| uat/verification | Phases 03-06 — `*-HUMAN-UAT`/`*-VERIFICATION`/`05-UAT-RUNBOOK.md` (v1.1 live-deploy checks) | Blocked on 24/7 host |
| requirement | DEPLOY-02/03/05/08 — standing live-UAT, restart persistence, keepalive cron (carried v1.1) | Blocked on 24/7 host |
| planning | Phases 13/14/15 — 3 stale `*-CONTEXT.md` open-question markers (all resolved during research/planning; code shipped + verified) | Doc-only, no action |

> Phases 08 & 23 `*-HUMAN-UAT.md` show `partial` with 0 pending scenarios (marker-only, nothing actually open). Prior-milestone detail in MILESTONES.md v1.2/v1.3/v1.4 "Known Gaps" entries.

## Session Continuity

Last session: 2026-07-16T19:38:47.437Z
Stopped at: Phase 27 context gathered
Resume file: .planning/phases/27-crossfade-playback-spike-gated/27-CONTEXT.md

## Operator Next Steps

- Review the roadmap draft (`.planning/ROADMAP.md`) and approve, or provide feedback for revision.
- Once approved: `/gsd-plan-phase 24` to start planning Hosting Honesty & Docker.
