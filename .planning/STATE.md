---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: Open House
status: executing
stopped_at: Completed 23-03-PLAN.md
last_updated: "2026-07-14T10:48:43.219Z"
last_activity: 2026-07-14 -- Phase 23 execution started
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 32
  completed_plans: 28
  percent: 83
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-10)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** Phase 23 — portfolio-surface-ci-cd

## Current Position

Phase: 23 (portfolio-surface-ci-cd) — EXECUTING
Plan: 3 of 7
Status: Ready to execute
Last activity: 2026-07-14 -- Phase 23 execution started

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed (v1.3): 18/18 (Phases 13–17) — milestone shipped 2026-07-03
- v1.0 + v1.1 + v1.2: 52 plans shipped across Phases 1-12 — full per-plan timings archived in milestones/v1.1-ROADMAP.md and milestones/v1.2-ROADMAP.md
- v1.4 (Phases 18–23): not yet planned — no timings yet

**By Phase (v1.4) — roadmap only, plans TBD:**

| Phase | Plans |
|-------|-------|
| 18. Per-Guild Config Foundation | 0/TBD |
| 19. Onboarding & Admin Setup | 0/TBD |
| 20. Owner Control Plane & Rate Observability | 0/TBD |
| 21. Memory Scoping & Guild Data Lifecycle | 0/TBD |
| 22. Invite Plumbing | 0/TBD |
| 23. Portfolio Surface & CI/CD | 0/TBD |
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

## Accumulated Context

### Decisions

The full pre-v1.4 decision log (architecture, per-phase highlights, every prior-milestone implementation decision) is preserved in **PROJECT.md Key Decisions** and `milestones/v1.1/v1.2/v1.3-ROADMAP.md`. This milestone's own decisions live in **REQUIREMENTS.md Key Decisions (this milestone)**. Enduring cross-milestone invariants worth carrying forward:

- `MemoryService.recall/remember/distill` is kind-agnostic — new memory kinds/scoping dimensions should be additive where possible (Phase 11/13; tested again in Phase 21's guild-scoping work).
- Accuracy firewall: qualitative narrative flows through vector memory; any number that drives a ranking decision comes from live SQL, never embedded text (Phase 11).
- Rate budgets: shared 15 RPM chat limiter (priority tiers) vs a separate ~60 RPM embed limiter — background work never starves user commands. v1.4 adds `guild_id` tagging for observability (RATE-01), not a new limiter.
- Gemini 2.5 defaults `safety_settings` OFF — set them explicitly on every user-content `generate_content` call (Phase 17).
- Pure-logic TDD seam (`logic/*.py`): all decision logic mock-free-tested before Discord wiring; glue stays untested-by-design.
- **v1.4 sequencing lock (from research + roadmap):** Phase 18 (config seam) blocks everything; Phase 19 (onboarding, preventive) before Phase 20 (owner control plane, reactive); Phase 21 (memory scoping) sequenced after Phase 20 because MEM-04's purge hangs off the force-leave/`on_guild_remove` hook; Phase 22 (invite) sequenced after Phase 20 so the abuse mitigation is real before promoting invites; Phase 23 (portfolio) is strictly last — it needs a real second-guild walkthrough to be honest.
- **Standing Descope Rule (REQUIREMENTS.md):** if plan-time research proves a requirement infeasible, descope rather than force it — applies with particular force to MEM-01/03/05, whose documented zero-code fallback is "keep memory global + disclose."
- [Phase 18]: Ruff adopted as the single lint+format tool (D-14); config files committed separately from the mechanical cleanup pass so the repo-wide reformat stays its own atomic commit (D-16).
- [Phase 18]: seed_guild_config_if_absent uses ON CONFLICT DO NOTHING (never DO UPDATE) so a stale DEXTER_CHANNEL_ID never overrides a later /setup write (D-09)
- [Phase 18]: Extracted pure logic/guild_config.py decision seam (decide_ambient_channel + is_ambient_channel) mirroring logic/proactive.py; mock-free tested, no discord/asyncio/datetime/random imports — Locks the silent-until-configured invariant structurally so no future ambient surface can forget to guard itself (D-01/D-05)
- [Phase 18]: GuildConfigService constructed unconditionally (no gemini-key guard) and both resolve_ambient_channel + resolve_announce_channel are synchronous (cache-only / no-await bodies) (18-04)
- [Phase 18]: [Phase 18] bot.py boot wiring (18-05): GuildConfigService constructed + load_all()'d right after log_to_discord is wired, before Gemini-gated services; home-guild seed reads config.DEXTER_CHANNEL_ID via bot.get_channel, silent INFO skip on unset/unresolvable (D-10); _resolve_dexter_channel deleted, both bot.py ambient sites now call resolve_ambient_channel synchronously — Keeps the home guild's behavior unchanged while making every other guild ambient-silent by construction; cogs/events.py's remaining call sites are a sibling plan (18-06)
- [Phase 18-06]: cogs/events.py ambient surfaces (3 voice sites + 2 on_message gates) consolidated onto the Phase 18 guild_config seam; DEXTER_CHANNEL_ID fully removed from cogs/ — Completes CONFIG-02/04 wiring for the events.py surface; tests updated to mock bot.guild_config.get() instead of patching the retired env var
- [Phase 18-07]: Single combined GitHub Actions lint+test job (not split) with pgvector/pgvector:pg16 service container; pull_request (never pull_request_target) + top-level permissions: contents: read + zero secrets.* as the standing CI least-privilege posture
- [Phase 19]: [Phase 19-01]: insert_guild_config_if_absent (D-14) never sets configured=true; configure_guild_first_time is the separate upsert that turns vision off on first /setup channel write
- [Phase 19]: [Phase 19-01]: redesignate_guild_channel is a plain UPDATE touching only ambient_channel_id, never resets configured or either toggle an admin has since changed (D-03/D-20)
- [Phase 19-02]: AmbientSurface required keyword-only (no default) on decide_ambient_channel/is_ambient_channel/resolve_ambient_channel -- a future ambient surface cannot resolve a channel without naming itself, TypeError on omission (D-22)
- [Phase 19-02]: on_message's shared in_ambient_channel boolean retired for two independent surface-keyed booleans (roast_channel_ok/vision_channel_ok) since ambient_roasts_enabled and vision_roasts_enabled can now disagree per guild; the CONFIG-04 reaction-gating hole is closed
- [Phase 19-02]: GuildConfigService.home_guild_id set unconditionally at the end of seed_home_guild, even on ON CONFLICT DO NOTHING -- the seed still resolves which guild is home regardless of insert-vs-conflict (D-24)
- [Phase 19]: [Phase 19-03]: should_welcome_guild(inserted_row=) is the ONLY welcome-decision signal for on_guild_join and the boot backfill loop -- never bot.guild_config.get(), which would welcome-spam on a cache-miss race
- [Phase 19]: [Phase 19-03]: boot backfill runs strictly after seed_home_guild and before queue-persistence wiring in _initialize_once -- reversing this order would backfill-and-welcome the home guild itself as configured=false (D-14 constraint 1)
- [Phase 19]: [Phase 19-04]: setup_channel reads the cached row once before branching, driving both the first-configure/re-designate decision and (for re-designate) the old->new channel phrasing in the reply
- [Phase 19]: [Phase 19-04]: cogs/admin.py is a dedicated guild-admin (manage_guild) surface, structurally separate from cogs/ops.py's owner (is_owner) surface (D-04)
- [Phase 20-01]: guild_blocklist lands as its own table (D-01) with load_blocklist/insert_blocklist/delete_blocklist + set_silenced helpers in database.py; guild_config.is_blocked left in place but dead (D-03), documented in CLAUDE.md
- [Phase 20-02]: silenced defaults to False via config_row.get('silenced', False) in decide_ambient_channel -- every pre-Phase-20 row/mock stays byte-identical
- [Phase 20-02]: decide_interaction_allowed checks is_owner, then has_guild, then blocked-or-silenced (exact D-13 order); all four args required keyword-only, no defaults
- [Phase 20]: [Phase 20-03]: guild_id kwarg on GeminiService.chat/generate_image is per-session usage tagging only (never a gate/quota); embed() stays untagged (separate 60 RPM limiter, D-09); increment guarded by guild_id is not None, placed right after rate_limiter.acquire() succeeds
- [Phase 20-04]: GuildConfigService.load_all() restructured (try/except/else) so the blocklist load and config-cache load are fully independent -- neither failure blanks the other
- [Phase 20]: [Phase 20-05]: Pre-send re-check re-invokes the same silence-aware is_ambient_channel predicate immediately before message.reply in _maybe_fire_proactive_callback and _maybe_fire_vision_roast (D-14 / SC-2) -- a second read of the same cache, not a new mechanism
- [Phase 20]: [Phase 20-05]: guild_id threaded through the last 2 events.py Gemini call sites (ambient roast, vision roast) completes RATE-01 for this file
- [Phase 20-06]: interaction_check computes is_owner/has_guild/blocked/silenced and dispatches on decide_interaction_allowed; refusal is sent from INSIDE interaction_check before return False (D-12), never via app_commands.CheckFailure -- returning False alone never reaches on_app_command_error (verified discord.py 2.7.1 mechanic)
- [Phase 20-06]: on_guild_join block-check-first runs after the boot-race guard and before insert_guild_config_if_absent -- a blocklisted re-invite is left immediately via guild.leave(), no config insert, no welcome, no owner joined notice
- [Phase 20-07]: Guild names render as plain text with backtick-wrapped ids in /guilds list rows (anti-injection, mirrors bot.py::_build_guild_notice_embed); silence/leave/block echoes use AllowedMentions.none() as defense-in-depth
- [Phase 20-07]: /guilds block runs the shared teardown THEN the blacklist insert (D-11 order); a guild already absent still gets blacklisted, teardown skipped
- [Phase 21-01]: kind appended before guild_id in search_memories so the pre-existing kind-only SQL shape keeps binding at literal $3 (dynamic $N numbering, order-preserving)
- [Phase 21-01]: recall() forwards guild_id via a conditionally-built kwargs dict splatted into search_memories, not an unconditional guild_id=X-if-Y-else-None kwarg -- the latter breaks every hand-written fake_search test double on the recall path lacking a guild_id param
- [Phase 21-02]: purge_guild_data's docstring deliberately omits the literal identifier guild_blocklist -- the T-21-03 invariant check greps inspect.getsource(), which includes the docstring, so even a prose mention fails it; the docstring names the sibling helpers instead and says why
- [Phase 21-02]: purge_guild_data raises on failure (no internal try/except) -- the best-effort swallow belongs at the bot.py::on_guild_remove call site (21-04), keeping the helper honestly testable
- [Phase 21-02]: the purge's four-table list is four hardcoded SQL literals, never a loop / never information_schema -- reviewability of the literal list IS the T-21-03 control that keeps guild_blocklist structurally out of reach (OWNER-04)
- [Phase 21-03]: guild_scoped=bool(guild_id) (not a bare True) on the music-command callback, because _build_roast_line's guild_id param defaults to None -- a bare True with an empty-string guild_id would silently narrow recall to the NULL corpus
- [Phase 21-03]: /ask's inline comment explaining why it stays un-scoped deliberately avoids the literal substring guild_scoped -- inspect.getsource() includes comments, so a comment containing that literal would fail the MEM-02 source-inspection regression test it protects
- [Phase 21]: [Phase 21-04]: on_guild_remove docstring rewritten to avoid the literal substring purge_guild_data in prose — Keeps grep -c purge_guild_data bot.py at exactly 1 (the single call), mirroring plan 21-02's identical guild_blocklist-avoidance discipline for its own docstring.
- [Phase 21]: [Phase 21-04]: PROJECT.md's scoping row explicitly names /ask as staying global and self-scoped — Phase 23's PORT-04 publishes this row verbatim -- an imprecise row omitting /ask would make Dexter's public privacy disclosure false.
- [Phase 22-01]: Ten-permission bitfield (309240908864, D-09 amendment) locked with negative-assertion test; logic/invite.py is the one documented exception to the logic/ no-discord-import convention
- [Phase 22-02]: cogs/invite.py comments avoid the literal substrings ephemeral/guild_only/checks.cooldown so the plan's grep -c == 0 acceptance checks stay exact while still documenting the deliberate omissions in prose — Mirrors the Phase 21 guild_blocklist/purge_guild_data docstring-avoidance discipline
- [Phase 22-02]: /invite command carries no @app_commands.checks.cooldown and no DM-restriction decorator — zero I/O, static output, DM support is a hard requirement (D-06)
- [Phase 22]: [Phase 22-03]: Reworded two pre-existing prose comments (config.py INVITE_SCOPES comment, logic/__init__.py package docstring) that legitimately mentioned oauth_url( in documentation so the new single-invite-URL-constructor scan (T-22-03) doesn't false-positive on prose
- [Phase 23-01]: D-13 discharged clean on first CI run — 1160 DB-inclusive tests pass against real pgvector container, no repair needed
- [Phase 23]: [Phase 23-03]: Astro entity-escapes & in interpolated href attributes -- confirmed empirically, fixed with set:html on a raw HTML fragment for the invite CTA anchors (UI-SPEC HARD VERIFICATION GATE)
- [Phase 23]: [Phase 23-03]: tests/test_site_drift_guard.py rebuilds the D-02 guard to scan built site/dist/**/*.html via filesystem rglob (never git ls-files) -- closes the vacuous-pass hole Astro's SSG choice opened; reuses _canonical_url/_collect_offenders from tests/test_invite_drift_guard.py, no second regex
- [Phase 23]: [Phase 23-03]: site/package.json engines field (>=22.12.0, Astro's own scaffold output) is the CI Node version source of truth for plan 23-04, not a hardcoded guess from research

### Pending Todos

None.

### Blockers/Concerns

- [Parked] The 24/7 live deploy remains parked behind the YouTube datacenter-IP block. Not scoped to v1.4 — hosting model is intentionally unchanged this milestone (owner's PC, on demand).
- [Watch] MEM category (Phase 21) touches `services/memory.py::search_memories`/`recall()` — the exact subsystem whose `user_id`-only scoping caused the Phase 13 CR-01 blocker. Needs research at plan time; may descope per the standing Descope Rule.
- [Watch] `tree_cls`/`CommandTree.interaction_check` exact constructor kwarg (Phase 20) is MEDIUM confidence per research — verify against the installed discord.py version before implementation.

## Deferred Items

Acknowledged and deferred at v1.3 milestone close (2026-07-03) — 24 open items from the pre-close artifact audit, all `human_needed` live-Discord checks or stale planning markers, **zero code gaps**. All resume when a Pi / always-on residential host exists. (Unrelated to and not blocking v1.4 scope.)

| Category | Item | Status |
|----------|------|--------|
| uat | Phase 14 — `14-HUMAN-UAT.md` (4 pending: taste-aware auto-queue, `/discover`, `/jam suggest` feel) | Blocked on live Discord/host |
| uat | Phase 15 — `15-HUMAN-UAT.md` (4 pending: live-DB `remember→forget→recall==[]` proof + 3 `/memory` UX) | Blocked on live Discord/host |
| uat | Phase 16 — `16-HUMAN-UAT.md` (2 pending: proactive "feel" + `/memory callbacks off` UX) | Blocked on live Discord/host |
| uat | Phase 17 — `17-HUMAN-UAT.md` (3 pending: vision cadence feel, real safety-block leaves no trace, `/ask`+`/imagine` unregressed) | Blocked on live Discord/host |
| verification | Phases 14/15/16/17 — `*-VERIFICATION.md` (`human_needed`) | Blocked on live Discord/host |
| uat/verification | Phase 09/11 — `*-HUMAN-UAT`/`*-VERIFICATION` (carried v1.2: truthful `/health`, task surfacing, live RAG recall/callback roasts) | Blocked on live Discord/host |
| requirement | DEPLOY-02/03/05/08 — standing live-UAT, restart persistence, keepalive cron (carried v1.1) | Blocked on 24/7 host |
| uat/verification | Phases 03-06 `*-HUMAN-UAT`/`*-VERIFICATION`/`05-UAT-RUNBOOK.md` — carried v1.1 live-deploy checks | Blocked on 24/7 host |
| planning | Phases 13/14/15 — 3 stale `*-CONTEXT.md` open-question markers (all resolved during research/planning; code shipped + verified) | Doc-only, no action |

Prior-milestone detail also in MILESTONES.md v1.2 "Known Gaps"; v1.3 accomplishments + close in MILESTONES.md v1.3 entry.

## Session Continuity

Last session: 2026-07-14T10:48:43.211Z
Stopped at: Completed 23-03-PLAN.md
Resume file: 
None
