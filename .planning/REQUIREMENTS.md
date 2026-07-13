# Requirements: Dexter ("Dex") — v1.4 "Open House"

**Defined:** 2026-07-10
**Core Value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.

**Milestone goal:** Turn Dexter from a single-community bot into a publicly-invitable, multi-tenant-robust portfolio piece — a recruiter can invite it to any server and it just works — without changing the on-demand, owner-run hosting model.

**Scale target:** Invitable & robust at modest scale (single-digit to low-dozens of guilds). Explicitly NOT pursuing Discord's 100-guild verification wall this milestone.

---

## v1.4 Requirements

### Per-Guild Configuration (CONFIG)

The foundational seam. Every other category reads from it.

- [x] **CONFIG-01**: A `guild_config` table (`guild_id` PK, `ambient_channel_id`, `configured`, `silenced`, `is_blocked`, `joined_at`, `updated_at`) exists in `SCHEMA_SQL`, following the existing `guild_jams`/`resolution_cache` idiom
- [x] **CONFIG-02**: One consolidated ambient-channel resolver replaces the duplicated `bot.py::_resolve_dexter_channel` and `cogs/events.py::_get_ambient_channel`, AND the two bare-equality `message.channel.id == config.DEXTER_CHANNEL_ID` gates in `events.py::on_message` (proactive-callback + vision-roast dispatch) route through it
- [x] **CONFIG-03**: A `GuildConfigService` serves per-guild config from an in-memory cache loaded at boot, push-invalidated on change — never a per-event DB round-trip against Neon
- [x] **CONFIG-04**: Ambient/unprompted surfaces (roasts, proactive callbacks, vision roasts, idle + startup messages) stay silent in a guild until `/setup` runs; core commands (`/play`, `/ask`, …) work immediately on join
- [x] **CONFIG-05**: The owner's home guild is seeded from the existing `config.DEXTER_CHANNEL_ID` so current behavior is unchanged after the refactor

> `OWNER_ID` and `ERROR_LOG_CHANNEL_ID` remain **global** (owner identity + private cross-guild ops channel) and must not be folded into `guild_config`.

### Onboarding & Admin Setup (ONBOARD)

- [x] **ONBOARD-01**: When Dexter joins a server it posts a welcome/setup-nudge message in a safely-resolved channel, wrapped so a permission failure never crashes the join
- [x] **ONBOARD-02**: A server admin can run `/setup` to designate the ambient channel, enforced by an inline `manage_guild` permission check (`default_permissions` is a UI hint only, never the gate)
- [x] **ONBOARD-03**: `/setup` presents a channel dropdown picker rather than a raw channel argument
- [x] **ONBOARD-04**: A server admin can toggle ambient roasting and vision roasting independently for their guild
- [x] **ONBOARD-05**: The owner is notified in `ERROR_LOG_CHANNEL_ID` when Dexter joins or is removed from a server

### Owner Control Plane / Kill-Switch (OWNER)

The stated abuse mitigation. Table stakes, not polish.

- [x] **OWNER-01**: The owner can list every server Dexter is in, with per-guild AI usage visible
- [x] **OWNER-02**: The owner can silence a guild — Dexter stays joined but suppresses ambient behavior and commands
- [x] **OWNER-03**: The owner can force-leave a guild, with teardown mirroring the `clear_persisted()` discipline (bump `_play_generation`, clear queue + voice state) so no ghost state resurrects on re-invite
- [x] **OWNER-04**: Blocked guilds persist in a blacklist; a re-invite is refused via a block-check-first in the guild-join handler
- [x] **OWNER-05**: A single choke point enforces the block for slash commands (`CommandTree.interaction_check`) and a single seam enforces it for ambient behavior (the CONFIG-02 resolver) — no per-cog checks to remember
- [x] **OWNER-06**: Every owner command enforces an inline `is_owner()` check, and the block check is TOCTOU-safe — evaluated before any `await` in an ambient entry point and re-checked immediately before the final send

### Memory Scoping & Guild Data Lifecycle (MEM)

Hybrid scoping: contain third-party exposure, keep self-recall global.

- [ ] **MEM-01**: `/roast @user`, ambient roasts, and proactive callbacks recall only memories scoped to the current guild — a third party's memories never travel between servers
- [x] **MEM-02**: `/ask` continues to recall the **invoker's own** memory globally (self-scoped — no cross-user exposure is possible)
- [x] **MEM-03**: Legacy memories written with `guild_id = NULL` (e.g. `daily_batch`) are handled by an explicit, tested backward-compat rule — the existing memory corpus is not silently made unrecallable
- [ ] **MEM-04**: When Dexter leaves or is removed from a guild, that guild's data is purged (`guild_config`, `guild_queues`, `guild_jams`, guild-scoped `user_memories`) so stale context cannot resurface
- [x] **MEM-05**: Guild-scoped search does not corrupt cross-kind dedup or `expires_at` semantics — the Phase 13 CR-01 scar is locked by regression test

> **Needs research at plan time.** This category touches `services/memory.py::search_memories`/`recall()` — the subsystem whose `user_id`-only scoping caused the Phase 13 CR-01 blocker. The `guild_id = NULL` backward-compat rule, dedup-search scoping, and `MEMORY_MAX_PER_USER` eviction semantics must all be resolved before implementation.

### Rate-Limit Observability (RATE)

- [x] **RATE-01**: Every Gemini call is tagged with its originating `guild_id`, and per-guild usage counters are surfaced in the owner's server-list view — so a budget hog is visible and actionable via the kill-switch

### Invite Plumbing (INVITE)

- [ ] **INVITE-01**: A least-privilege OAuth2 invite URL exists (explicit `Permissions()` bitfield — no Administrator, no Manage Server/Roles) with `bot` + `applications.commands` scopes
- [ ] **INVITE-02**: An in-bot `/invite` command returns the live invite URL as the single source of truth

### Portfolio Surface (PORT)

- [ ] **PORT-01**: A static landing page in `/site` presents Dexter (hero, feature showcase, "Add to Discord" button)
- [ ] **PORT-02**: A short demo GIF showing the personality landing is embedded in the landing page
- [ ] **PORT-03**: The README is rewritten as an architecture case study (tagline, feature list, tech-stack badges, architecture summary, working invite link)
- [ ] **PORT-04**: Scope boundaries are documented honestly rather than hidden: the 100-guild verification wall, the on-demand hosting caveat (the bot is offline unless the owner runs it), the full-savage-personality + reactive-kill-switch tradeoff, and the hybrid memory-scoping decision

### CI/CD (CICD)

- [x] **CICD-01**: GitHub Actions runs the pytest suite + lint on every push and PR, with a build-status badge in the README
- [ ] **CICD-02**: The `/site` landing page auto-deploys to GitHub Pages on merge to `main`
- [ ] **CICD-03**: The bot's Docker image builds and publishes to GHCR on tag/release, so a future always-on host is a `docker pull` away

---

## Future Requirements

Deferred to a later milestone. Tracked but not in this roadmap.

### Memory

- **MEM-F1**: Salience reinforcement — memories that get surfaced/hit gain durability (deferred out of v1.3)
- **MEM-F2**: Vision → RAG memory — persist a distilled fact from a vision roast (deferred out of v1.3)
- **MEM-F3**: Full guild-scoped recall including `/ask`, or per-user opt-in cross-guild sharing — revisit if Dexter outgrows modest scale

### Deploy

- **DEPLOY-F1**: Resume the parked 24/7 live deploy once an always-on residential host exists → closes DEPLOY-02/03/05/08 and the entire live-UAT tail (Phases 03–06, 09, 11, 14–17)

### Scale

- **SCALE-F1**: Soft per-guild rate ceiling on priority-2 (background) Gemini calls — only if observability (RATE-01) proves starvation is real
- **SCALE-F2**: Discord bot verification + privileged-intent approval (required past 100 guilds / 10k unique users)

---

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Auto-deploy the bot to a live prod host | There is no prod host — the 24/7 deploy is parked behind the YouTube datacenter-IP block. CICD-03 (image → GHCR) makes it a config step later |
| Web-based per-guild settings dashboard | Conflicts with the no-always-on-host constraint; parked since Phase 4. `/setup` in-Discord covers the need |
| Per-guild persona intensity dial | Directly conflicts with the locked "full-savage everywhere" decision |
| Per-guild Gemini quota system | Priority-2 already self-rejects at >10s wait; per-user cooldowns bound priority-1. Observability (RATE-01) + the kill-switch is the chosen remedy |
| Discord bot verification / 100+ guild readiness | Scale target is modest; documented as an honest boundary in PORT-04 instead |
| Per-channel (vs per-guild) ambient config | Over-engineering for the stated scale |
| Automated abuse-detection heuristics | The owner kill-switch is the stated mitigation — reactive by design, disclosed in PORT-04 |
| Multi-owner RBAC, i18n, premium tiers, bot-list submissions | Over-engineering for a single-owner portfolio bot |

---

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONFIG-01 | Phase 18 | Complete |
| CONFIG-02 | Phase 18 | Complete |
| CONFIG-03 | Phase 18 | Complete |
| CONFIG-04 | Phase 18 | Complete |
| CONFIG-05 | Phase 18 | Complete |
| ONBOARD-01 | Phase 19 | Complete |
| ONBOARD-02 | Phase 19 | Complete |
| ONBOARD-03 | Phase 19 | Complete |
| ONBOARD-04 | Phase 19 | Complete |
| ONBOARD-05 | Phase 19 | Complete |
| OWNER-01 | Phase 20 | Complete |
| OWNER-02 | Phase 20 | Complete |
| OWNER-03 | Phase 20 | Complete |
| OWNER-04 | Phase 20 | Complete |
| OWNER-05 | Phase 20 | Complete |
| OWNER-06 | Phase 20 | Complete |
| MEM-01 | Phase 21 | Pending |
| MEM-02 | Phase 21 | Complete |
| MEM-03 | Phase 21 | Complete |
| MEM-04 | Phase 21 | Pending |
| MEM-05 | Phase 21 | Complete |
| RATE-01 | Phase 20 | Complete |
| INVITE-01 | Phase 22 | Pending |
| INVITE-02 | Phase 22 | Pending |
| PORT-01 | Phase 23 | Pending |
| PORT-02 | Phase 23 | Pending |
| PORT-03 | Phase 23 | Pending |
| PORT-04 | Phase 23 | Pending |
| CICD-01 | Phase 18 | Complete |
| CICD-02 | Phase 23 | Pending |
| CICD-03 | Phase 23 | Pending |

**Coverage:**

- v1.4 requirements: 31 total
- Mapped to phases: 31/31 ✓
- Unmapped: 0

---

## Descope Rule (standing, user-directed)

**If research during `/gsd:plan-phase` concludes a requirement isn't feasible, or the cost/risk clearly outweighs the value — do not force it. Descope it.**

Move the requirement to **Future Requirements** or **Out of Scope** with the reason recorded, surface the call to the user, and continue with the rest of the phase. A requirement written here is a hypothesis, not a contract.

This applies with particular force to the **MEM** category, which touches `services/memory.py::search_memories` — the subsystem whose `user_id`-only scoping produced the Phase 13 CR-01 blocker. Specific tripwires that should trigger a descope conversation rather than a heroic workaround:

- The `guild_id = NULL` backward-compat rule (MEM-03) has no clean answer that preserves the existing memory corpus
- Guild-scoped search cannot be made safe against cross-kind dedup / `expires_at` corruption (MEM-05)
- The guild-data purge (MEM-04) cannot cleanly separate guild-scoped memories from user-scoped ones

If MEM-01/03/05 prove infeasible, the documented fallback is **"keep memory global + disclose"** (the Option A already analyzed) — which costs zero code and is honestly defensible in PORT-04. MEM-04 (purge on removal) and MEM-02 (`/ask` stays global) are independently shippable regardless.

---

## Key Decisions (this milestone)

| Decision | Rationale |
|----------|-----------|
| **Hybrid memory scoping** — guild-scope `/roast @user` + ambient + proactive; `/ask` stays global | `/ask` recalls the invoker's *own* memory (self-scoped, no cross-user leak possible). The leak vector is third-party + unprompted surfaces. Targets the real exposure without blinding self-recall |
| **Purge guild data on removal** | With guild-scoping, retained memories from a departed guild are orphaned — unreachable by the filter, yet still consuming `MEMORY_MAX_PER_USER` and visible in `/memory view`. Purging is correct *and* the right-to-be-forgotten story |
| **Rate-limit observability, not a quota system** | The soft per-guild ceiling would constrain priority-2 traffic that *already* self-rejects at >10s wait, while the likely hog (priority-1 `/ask` spam) is untouched by it and already bounded by per-user cooldowns. Observability composes with the kill-switch instead of duplicating it |
| **Ambient default-OFF until `/setup`** | The existing fallback chain (system channel → first writable) would fire roasts/vision-roasts at strangers within minutes of an invite — the exact abuse surface the kill-switch mitigates only reactively |
| **No prod auto-deploy; ship CI + Pages CD + GHCR image instead** | There is no prod host (24/7 deploy parked behind the YouTube datacenter-IP block). CI green-badge is the highest recruiter signal per unit of effort; GHCR makes the future host a config step |
| **Hosting model unchanged** | Dexter runs on the owner's PC (residential IP) on demand. Recruiters invite it; it serves when the owner runs it. Sidesteps the datacenter-IP block entirely — music keeps working |

---
*Requirements defined: 2026-07-10*
*Last updated: 2026-07-10 after v1.4 roadmap creation (Phases 18–23, 31/31 requirements mapped)*
