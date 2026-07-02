# Dexter ("Dex")

## What This Is

Dexter is a sarcastic, personality-driven Discord bot. It plays music from YouTube (yt-dlp + FFmpeg), chats via Google Gemini (gemini-2.5-flash), and generates images, while tracking user behavior to roast them. The persona is lowercase, dry, accurate-first-sarcastic-second, and uses at most one emoji per message. It is built for a single Discord community as a solo-developer project, with Claude as the implementer. As of v1.0 it is a complete, code-finished bot — music + AI + an "alive" unprompted-behavior layer — hardened and scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot`.

## Core Value

A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.

## Current State

**Shipped: v1.0 MVP (2026-06-12)** — Phases 1, 2, 2.5, 3, 4. All 45 v1 requirements satisfied at the code/structural level.

**Shipped (code): v1.1 "Live & Lethal" (2026-06-26)** — Phases 5–8, 14 plans, 27 tasks. All 28 v1.1 requirements met at the code level; 24/28 also live-validated. Delivered:
- **Phase 5 (Ship It Live):** deploy substrate re-targeted Oracle A1 → **Koyeb WEB + Neon serverless Postgres** — Neon-tuned asyncpg pool, `sanitize_database_url`, aiohttp `/health`, de-Oracle'd Dockerfile, stdout logging, `docs/DEPLOY-KOYEB.md`, 22-check live-UAT runbook.
- **Phase 6 (Speed & Caching):** generation-guarded next-track prefetch (zero inter-song gap), opus-copy codec-path logging + SponsorBlock, a Postgres `resolution_cache` (survives restart, URL-bypass), download-timeout→stream fallback, LFU eviction protecting in-use tracks, `PerfMetrics` in `/stats`.
- **Phase 7 (Player UX & Filters):** persistent 5-button now-playing view, `/seek` `/previous` `/jump`, four `/filter` presets (opus-passthrough preserved for non-filtered tracks), `user_favorites` + JSONB `user_playlists`.
- **Phase 8 (Social & Ops):** `/roast @user`, per-guild `/leaderboard`, owner-only `/stats`, degraded-but-always-200 `/health`, central `total_errors` tracking.

**The 24/7 live deploy is PARKED.** YouTube blocks datacenter IPs → free cloud hosting is non-viable, and there is no always-on residential host yet. The bot runs on the **user's PC (residential IP) on demand against Neon Singapore**; Phases 6/7/8 were live-verified that way. The 4 open DEPLOY requirements + remaining live-UAT/verification items (9 total) are deferred until a Pi / always-on residential host is acquired — see STATE.md Deferred Items.

**Shipped (code): v1.2 "Sharper & Smarter" (2026-06-30)** — Phases 9–12, 19 plans, 43 tasks. All 21 v1.2 requirements met at the code level. Delivered:
- **Phase 9 (Reliability & Ops Hardening):** truthful `/health` (degraded-503 on MusicCog load failure, `_ready_done`-guarded), fire-and-forget failure surfacing via `utils/tasks.py` `make_task`, un-wedgeable `on_ready` watchdog + `_sync_retry_active`-guarded startup-sync recovery, config-driven DB query timeouts, bounded YouTube search/extract self-heal.
- **Phase 10 (Critical-Path Test Coverage):** extracted the untested decision logic into pure `logic/` modules (`playback.py` TrackEndAction + five fns, `health.py`, `roasts.py`, later `autoqueue.py`) locked by ~83 mock-free unit tests with three named scar regressions; full-suite-green + clean-boot regression gate.
- **Phase 11 (RAG Long-Term Memory):** `pgvector` on Neon + `gemini-embedding-001` @ 768d behind a separate 60 RPM limiter; full read (recall/rerank/floor) + write (remember/dedup/cap-evict) halves, sensitivity/PII + numbers-from-SQL accuracy firewall, callback roasts at four surfaces, daily decay sweep — **zero new infrastructure**.
- **Phase 12 (Richer Music/UX):** per-server `/jam` shared playlists, `/skips` analytics, LRCLIB third lyrics fallback, token-set auto-queue hallucination validation.

The Phase 09/11 live-runtime UAT/verification tail (4 items) is deferred behind the same parked host — see STATE.md Deferred Items.

**In progress (code): v1.3 "Taste Brain"** — Phases 13–16 executed & code-verified. Phase 15 (RAG Reach) complete 2026-07-03: `/roast` and `/ask` grounded in real recalled history (D-01 cadence gate removed from both, ambient surfaces keep it), plus a new `/memory view` (verbatim, ephemeral, paginated) and irreversible `/memory forget` (RAG-01..04, all code-verified; suite 781 green). Its live-runtime tail (live-DB `remember→forget→recall==[]` proof + 3 Discord UX checks) is parked behind the same residential host — see `15-HUMAN-UAT.md`.
- **Phase 16 (Proactive Memory Callbacks) complete 2026-07-03:** a third, rarest ambient cadence — Dexter now *volunteers* a remembered detail unprompted at an active moment (`on_message` in the designated channel → pure `should_fire_proactive_callback` gate at `PROACTIVE_CALLBACK_CHANCE=0.10` + `DAILY_CAP=1`, rarer than ambient roasts), reply-anchored with `AllowedMentions.none()` and recall anchored on the triggering message so it reads as relevant, not surveillance. Per-user opt-out via `/memory callbacks on|off` (self-scoped, ephemeral, `proactive_opt_out` boolean on `user_profiles`, zero `user_memories` touched). Pitfall-1 `pre_recalled_memories` bypass keeps the ambient 0.30/0.35 cadence byte-identical. PROACT-01/02 code-verified 10/10; suite 814 green. All 3 code-review warnings fixed pre-close (WR-03 content-free recall anchor → `message.content`, WR-01 daily-cap TOCTOU, WR-02 unguarded opt-out DB read). Live-runtime tail (proactive "feel" + `/memory callbacks off` UX) parked behind the residential host — see `16-HUMAN-UAT.md`.

## Current Milestone: v1.3 "Taste Brain" (planning)

**Goal:** Turn Dexter's listening history into semantic long-term memory that powers a genuinely good DJ (smarter auto-queue, discovery, generative jams), memory-aware `/roast` + `/ask`, and proactive callbacks — plus vision/multimodal roasting — deepening the v1.2 RAG foundation on existing infra (`pgvector` + the separate 60 RPM embed limiter), at zero new cost. Continues phase numbering at Phase 13.

**Target features:**
- **Semantic music memory** *(foundation)* — a new taste/listening memory kind; the retrievable substrate the music brain and callbacks feed off.
- **Smarter music brain** — taste-aware auto-queue that learns from `was_skipped`, artist/genre taste-graph discovery surfaced via a command, and generative "continue this jam" / suggest-additions.
- **RAG reach** — wire `recall()` into `/roast` and `/ask` (dormant there today; ambient roasts already use it), plus a `/memory` inspect/forget command (trust + recall-quality observability).
- **Proactive callbacks** — a background surface that volunteers a memory (roast or music) at a well-chosen moment, beyond the existing cadence-gated ambient roasts.
- **Vision / multimodal roasting** — Dex reacts to images posted in chat via `gemini-2.5-flash` (free-tier vision confirmed via Context7; native model capability, draws on the shared 15 RPM budget), cadence-gated + content-safety guardrails (VIS-01/02).

**Explicitly out of v1.3:** salience reinforcement (→ v1.4), `/setavatar` (avatar set manually via the Developer Portal), and the parked 24/7 deploy (host-gated).

<details>
<summary>Previous: v1.2 "Sharper & Smarter" milestone framing (archived — shipped 2026-06-30)</summary>

**Goal:** Harden Dexter into a trustworthy 24/7-ready bot and give it a real memory — fix the reliability gaps, cover the untested critical paths, then make it smarter (long-term RAG memory) and richer (music/UX polish). Continued phase numbering at Phase 9.

**Target features:**
- **Reliability & ops hardening** — health endpoint can no longer report "ok" while degraded, fire-and-forget tasks log failures, `first_run`/`on_ready` sync no longer hangs silently, DB query timeouts, search/extract retry/self-heal.
- **Critical-path test coverage** — the untested MusicCog playback flow, OpsCog/health metrics, and EventsCog ambient-roast logic get real tests.
- **RAG long-term memory** — `pgvector` on the existing Neon Postgres + Gemini `gemini-embedding-001` @ 768d, so Dex remembers across restarts and lands callback roasts referencing real history. **Zero new infrastructure or monthly cost.** Includes a research spike.
- **Richer music/UX** — per-server playlists, skip-rate analytics command, third lyrics fallback, auto-queue hallucination validation.

</details>

<details>
<summary>Previous: v1.1 "Live & Lethal" milestone framing (archived)</summary>

**Goal:** Take Dexter from code-complete-on-a-laptop to running 24/7 — fast, polished, and genuinely fun — by deploying it for real, killing playback latency, and surfacing the control, filter, and roast features that make it a joy to use.

Sequenced deploy-first so every speed gain is measured against live numbers. The one tradeoff resolved in the roadmap: `/filter` forces a re-encode, mutually exclusive with opus-copy → opus-copy by default, transcode only when a filter is active per-track. **Reality check:** the deploy-first sequencing was inverted in practice — the live deploy parked behind the YouTube IP block, so speed/UX/social phases shipped and were verified against the on-demand PC run env instead.

</details>

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Music playback: `/play` (search + URL + playlist), `/skip`, `/pause`, `/resume`, `/stop`, `/queue`, `/shuffle`, `/loop`, `/nowplaying`, `/replay`, `/help` — v1.0 (Phase 1)
- ✓ Per-server queue model with loop modes, generation-counter race prevention, cache-first audio with stream fallback — v1.0 (Phase 1)
- ✓ `/ask` with Gemini, 10-message context buffer, mood system, user-taste injection, seasonal awareness — v1.0 (Phase 2)
- ✓ `/imagine` with daily cap, AI auto-queue, "ignored" memory, global Gemini rate limiter, Discord error-log channel — v1.0 (Phase 2)
- ✓ Production-honest hardening: unsilenced exception handlers, WAL + busy_timeout, robust auto-queue JSON parse, FFmpeg orphan cleanup, yt-dlp self-heal — v1.0 (Phase 2.5)
- ✓ Unprompted "alive" behavior: voice-join/leave roasts, late-night roasts, repeat-song roasts, emoji reactions, expanded seasonal awareness — v1.0 (Phase 3)
- ✓ Status rotation, startup message, idle-loneliness, streak tracking + milestone roasts, `/lyrics` (Genius + AZLyrics), `/history` — v1.0 (Phase 3)
- ✓ Scale: multi-server hardening, SQLite→PostgreSQL, `AutoShardedBot`, queue persistence, Oracle Cloud A1 hosting decision — v1.0 (Phase 4)
- ✓ Deploy substrate re-targeted Oracle A1 → Koyeb WEB + Neon serverless Postgres: Neon-tuned asyncpg pool, `sanitize_database_url`, aiohttp `/health`, de-Oracle'd Dockerfile, stdout logging, `docs/DEPLOY-KOYEB.md`, 22-check runbook — v1.1 (Phase 5, code; 24/7 deploy parked)
- ✓ Speed & caching: next-track prefetch (zero gap), opus-copy codec path + SponsorBlock, Postgres resolution cache, download-timeout→stream fallback, LFU eviction, `PerfMetrics` in `/stats` — v1.1 (Phase 6)
- ✓ Player UX & filters: persistent control-button view, `/seek` `/previous` `/jump`, four `/filter` presets (opus-passthrough preserved), favorites + named playlists — v1.1 (Phase 7)
- ✓ Social & ops: `/roast @user`, per-guild `/leaderboard`, owner-only `/stats`, `/health` endpoint, Gemini RPM headroom + `total_errors` visibility — v1.1 (Phase 8)
- ✓ Reliability & ops hardening: truthful `/health` (degraded-503, `_ready_done`-guarded), fire-and-forget failure surfacing via `make_task`, un-wedgeable `on_ready` watchdog + startup-sync recovery, config-driven DB query timeouts, bounded YouTube search/extract self-heal — v1.2 (Phase 9; live-runtime UAT in 09-HUMAN-UAT.md)
- ✓ Critical-path test coverage: playback/health/roast/auto-queue decision logic extracted to pure `logic/` modules with ~83 mock-free unit tests + three named scar regressions; full-suite-green + clean-boot regression gate — v1.2 (Phase 10)
- ✓ RAG long-term memory: `pgvector` on Neon + `gemini-embedding-001` @ 768d, scoped cosine recall with rerank/dedup, constrained distillation with sensitivity/number safety gates, prompt injection at four roast surfaces, per-user cap + daily decay sweep — v1.2 (Phase 11; 3 live-runtime UAT items tracked in 11-HUMAN-UAT.md)
- ✓ Richer music/UX: per-server `/jam` shared playlists (distinct from global favorites), `/skips` analytics, LRCLIB third lyrics fallback, token-set auto-queue hallucination validation — v1.2 (Phase 12)

> Phase 3 & 4 items (v1.0) and Phase 5–6 live checks (v1.1), plus the Phase 09/11 live-runtime checks (v1.2), are code-complete and statically/locally verified; their live-deploy/live-Discord UAT is carried forward as the deployment checklist (STATE.md Deferred Items), not as open scope. Phases 6/7/8 were live-verified on the user's PC + Neon.

### Active

<!-- Current scope: v1.3 "Taste Brain". See .planning/REQUIREMENTS.md for REQ-IDs + traceability. -->

- [ ] Semantic music memory — listening/taste episodes become a retrievable memory kind (foundation)
- [ ] Smarter music brain — taste-aware auto-queue (learns from `was_skipped`), taste-graph discovery command, generative jams
- [ ] RAG into `/roast` + `/ask`, plus a `/memory` inspect/forget command
- [ ] Proactive memory callbacks — background surface that volunteers a memory unprompted
- [ ] Vision / multimodal roasting via `gemini-2.5-flash` — cadence-gated + content-safety guardrails (VIS-01/02)

Carried forward (host-gated / deferred, not scoped to v1.3):
- [ ] Resume the parked 24/7 live deploy once an always-on residential host exists → closes DEPLOY-02/03/05/08 + the live-UAT tail (incl. the Phase 09/11 v1.2 live-runtime checks)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- `/volume` command / `PCMVolumeTransformer` — Discord's per-user volume slider covers it; opus passthrough keeps CPU low
- Prefix commands / hybrid commands — pure `app_commands` slash commands only, by design
- Spotify/Apple Music as audio sources — YouTube via yt-dlp is the single source of truth
- Web config dashboard — "maybe" since Phase 4, never committed; `/stats` in-Discord covers the owner need. Deferred to a future milestone, not killed.
- Datacenter/cloud hosting for the 24/7 deploy — YouTube blocks datacenter IPs, so free cloud is non-viable. Resolution is a residential always-on host (Pi), not a cloud provider.

## Context

- **v1.0 + v1.1 are code-complete and shipped to `main`** (tags `v1.0`, `v1.1`). Layered cog → service → model architecture. Services wired in `bot.py`, attached as bot attributes; cogs access via `self.bot`. CLAUDE.md is the north-star feature spec; `.planning/codebase/` reflects the built state. v1.1 added ~23k LOC of diff across 126 files (incl. `.planning/` docs).
- **The bot runs on the user's PC (residential IP) on demand against Neon Singapore.** Phases 6/7/8 were live-verified that way. A true 24/7 deploy is parked: YouTube blocks datacenter IPs (free cloud non-viable) and there is no always-on residential host yet. The remaining live-UAT/verification tail (9 items) is deferred to that future host — see STATE.md Deferred Items.
- **Personality is the product.** Lowercase, dry, one-emoji-max. Accuracy first, sarcasm second; sarcasm dials back for serious/emotional questions. Mood shifts with daily command count; seasonal context injected into the Gemini system prompt. All personality output is Gemini-first with a guaranteed template fallback.
- **Testing convention:** pure logic gets TDD (`tests/`); Discord/process code (cogs, `bot.py`) is untested-by-design, verified by structural review + clean local boot. Regression gate: full suite green + clean boot with no new silent failures in `dexter.log`.
- **Git convention:** the user handles all git operations (commits, merges, pushes). Do not auto-commit or push.

## Constraints

- **Tech stack**: Python 3.11+, discord.py (+ davey for DAVE voice encryption), yt-dlp + FFmpeg (opus 192kbps), **PostgreSQL via asyncpg** (migrated from SQLite/aiosqlite in Phase 4), Google Gemini via the `google-genai` SDK (NOT the deprecated `google-generativeai`) — fixed per CLAUDE.md, do not deviate
- **AI model**: `GEMINI_MODEL = "gemini-2.5-flash"` for chat; all AI features share a single global 15 RPM rate limiter (`GEMINI_RPM_LIMIT = 15`), priority 1 = user commands (wait ≤60s), priority 2 = background/auto-queue (reject if wait >10s)
- **Image model**: `gemini-2.5-flash-image` with `response_modalities=["IMAGE"]`; `MAX_IMAGES_PER_USER_PER_DAY = 10`
- **Music limits**: `MAX_SONG_DURATION_SECONDS = 900` (reject longer), reject livestreams, `MAX_PLAYLIST_IMPORT = 50` (truncate + inform), `IDLE_TIMEOUT_SECONDS = 600` auto-leave, `AUDIO_CACHE_MAX_MB = 2048` (evict oldest by atime, hourly cleanup), `MAX_QUEUE_SIZE_PER_GUILD = 500` (cap enforced in `MusicQueue.add()`)
- **Reliability**: explicit FFmpeg/voice cleanup on skip/stop/error/leave to avoid orphans; yt-dlp self-heals (daily 04:00 update + on-failure update→retry throttled ≤once/hour→stream fallback→error)
- **Discord interaction timeout**: must `defer()` or respond within 3s, then do async work via `asyncio.create_task()` / `interaction.followup`
- **Hosting**: re-targeted Oracle A1 → **Koyeb WEB + Neon serverless Postgres** (v1.1, Phase 5) → **24/7 deploy PARKED** (YouTube blocks datacenter IPs; free cloud non-viable). Current run env: **user's PC (residential IP) on demand → Neon Singapore**. Resume the 24/7 deploy on an always-on residential host (Pi). Code is substrate-agnostic (Dockerfile + `DATABASE_URL`), so the host swap is config-only.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Image-gen model = `gemini-2.5-flash-image` (resolved during ingest, not ADR-locked) | Two equal-precedence SPECs diverged; tie broken by ground truth — shipped `config.py:36` | ✓ Good (matches shipped code) |
| Layered cog → service → model architecture, services wired in `bot.py` | Decoupling, testability of pure logic, "grow into the spec" | ✓ Good |
| `current_index` queue (no popping) instead of pop-on-play | Enables `/replay`, `/previous`, loop wrap, `/history` | ✓ Good |
| Global Gemini rate limiter with priority tiers (sliding-window deque) | All AI features share one 15 RPM budget; user commands must not starve | ✓ Good |
| Phase 2.5 parks live-concurrency bugs rather than fixing blind | Bot booted locally only; fixes must be verifiable by inspection + local boot | ✓ Good |
| Hosting → Oracle Cloud Always Free A1 ARM (Phase 4) | Always-free ARM capacity fits a single-community bot; Docker Compose keeps Hetzner portability open | ✓ Resolved — ⚠ monitor reclamation/termination risk in production |
| Persistence → PostgreSQL via asyncpg 0.31.0 (Phase 4) | SQLite sufficient for v1–v3; multi-server scale needs real concurrency + durable queue persistence; raw `CREATE TABLE IF NOT EXISTS` over Alembic for a start-fresh schema | ✓ Resolved (static); live round-trip pending deploy |
| Queue cap enforced in `MusicQueue.add()` (Phase 4) | Guard at the source covers the playlist loop and every add path automatically | ✓ Good |
| Gemini-first personality output with guaranteed template fallback (Phase 3) | Never let rate limits or API errors block a roast/response | ✓ Good |
| Re-target deploy Oracle A1 → Koyeb WEB + Neon serverless Postgres (Phase 5) | Oracle reclamation risk + no card; Koyeb free WEB + Neon free fit a single-community bot | ⚠️ Revisit — superseded by the parked-deploy decision below |
| **Park the 24/7 live deploy; run on the user's PC (residential IP) → Neon on demand (v1.1)** | YouTube blocks datacenter IPs, breaking yt-dlp from any free cloud host; no card, no Pi yet | — Pending — resume on an always-on residential host |
| Neon-tuned asyncpg pool: `ssl='require'`, `statement_cache_size=0`, 240s lifetime (Phase 5) | Survive Neon's scale-to-zero without SSL-EOF / prepared-statement crashes through PgBouncer | ✓ Good |
| Generation-guarded fire-and-forget next-track prefetch (Phase 6) | Kill the inter-song silence gap without racing skip/stop teardown | ✓ Good |
| opus-copy by default, transcode only when a `/filter` is active per-track (Phase 6/7) | Resolve the filter-vs-opus-copy tradeoff — keep the fast path for the common case | ✓ Good |
| LFU cache eviction keyed on `song_history` play counts, with `protected_video_ids` (Phase 6) | `atime` is unreliable on `noatime` mounts; never evict an in-use track | ✓ Good |
| Persistent views via `timeout=None` + stable `custom_id`s registered in `setup_hook` (Phase 7) | Correct discord.py pattern so buttons survive restarts | ✓ Good |
| Shared `_do_*` helpers route slash command + button through one path (Phase 7) | Eliminate divergence between the two invocation surfaces | ✓ Good |
| Truthful `/health` returns degraded-503, guarded by `_ready_done` (Phase 9) | A health endpoint that reports "ok" while broken is worse than none; the guard prevents false-degraded during legitimate startup (Pitfall 3) | ✓ Good |
| Fire-and-forget tasks attach a `make_task` done-callback (Phase 9) | Background-task exceptions must surface to logs/error channel instead of vanishing silently (REL-02) | ✓ Good |
| Extract decision logic into pure `logic/` modules; Discord/process glue stays untested-by-design (Phase 10) | Test the branches that matter without mocking Discord; ~83 mock-free tests + named scar regressions lock the critical paths | ✓ Good |
| RAG memory = `pgvector` on the existing Neon DB, not Redis/knowledge-graph (Phase 11) | A new table on infra already in use → zero new cost/infra; top-k + heuristic rerank suffices for a single-community bot | ✓ Good |
| Embeddings on a **separate** 60 RPM limiter, never the shared 15 RPM chat budget (Phase 11) | Memory writes are background work that must not starve user-facing `/ask`/`/imagine` | ✓ Good |
| Accuracy firewall: never embed SQL-known numbers; hard numbers in output come from live SQL (Phase 11) | Stale embedded counts/streaks would violate Critical Rule 5 (accuracy-first); memory is roast *ammo*, not a number source | ✓ Good |
| Numeric retrieval defaults validated by a live-Neon spike before retrieval landed (Phase 11) | MEDIUM-confidence priors (floor/dedup/dims) tuned empirically (dedup 0.90→0.92, floor 0.70, keep-768) rather than shipped on assumption | ✓ Good |
| Token-set-containment over difflib for auto-queue validation (Phase 12) | YouTube titles are longer than clean names; subset check is the semantically correct rejection test for hallucinated tracks | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-03 after Phase 16 (Proactive Memory Callbacks) execution*
