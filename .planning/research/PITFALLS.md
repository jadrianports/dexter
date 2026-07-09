# Pitfalls Research

**Domain:** Retrofitting public multi-tenancy + an owner kill-switch onto an existing single-community discord.py bot (Dexter v1.4 "Open House")
**Researched:** 2026-07-10
**Confidence:** HIGH (codebase-verified against `cogs/events.py`, `bot.py`, `services/gemini.py`, `services/memory.py`, `cogs/ops.py`, `config.py`) + MEDIUM/HIGH on Discord platform policy (official docs) + MEDIUM on generic multi-tenant architecture (community sources)

## Critical Pitfalls

### Pitfall 1: The ambient-channel resolver is duplicated verbatim in two files and still has no per-guild config seam

**What goes wrong:**
`cogs/events.py::_get_ambient_channel` and `bot.py::_resolve_dexter_channel` are two byte-identical copies of the same 4-step fallback chain (`config.DEXTER_CHANNEL_ID` → last active music channel → `guild.system_channel` → first writable text channel). This was an accepted duplication in Phase 3-era code because there was only ever one guild and one channel ID. Adding a per-guild config lookup (a new "step 0": look up the guild's configured channel from the database) means editing **two call sites that have no shared source of truth**. It is very easy to update one and forget the other, silently reintroducing the single-channel behavior in half the ambient surfaces (e.g. voice-join roasts pick the new per-guild channel, but the startup message still posts to whatever `DEXTER_CHANNEL_ID`/system-channel fallback resolves to).

**Why it happens:** The duplication was intentional and documented ("kept local to bot.py to preserve file-ownership boundaries") when there was no per-guild dimension to get wrong. Multi-tenancy retrofits are exactly the kind of change that turns an acceptable duplication into a correctness bug, because the new logic (DB lookup) has to be threaded through every copy.

**How to avoid:** Before adding per-guild config, first **consolidate the two resolvers into one shared function** (e.g. `utils/channels.py::resolve_ambient_channel(bot, guild)`), called from both `bot.py` and `cogs/events.py`. Add the per-guild DB lookup as the new step 0 in that single place. Write one test that asserts both call sites route through the same function (import-identity check), so a future edit can't silently re-fork it.

**Warning signs:** Grep for `_resolve_dexter_channel` and `_get_ambient_channel` returning two separate function bodies instead of one being an alias/import of the other. Manual QA where the startup message appears in a different channel than voice-join roasts on the same guild.

**Phase to address:** Config seam phase (per-guild config storage + resolver) — do this consolidation as the FIRST task, before layering guild-config lookup on top.

---

### Pitfall 2: The 15 RPM Gemini limiter has zero per-guild fairness — one noisy guild starves every other guild silently

**What goes wrong:** `services/gemini.py::_RateLimiter` is a single global sliding-window deque shared by every guild, gated only by a 2-level priority (1 = user command, 2 = background). There is no guild dimension anywhere in `acquire()`. On a single community this was fine — only one guild's users compete. Once Dexter is publicly invitable, a single busy guild (heavy `/ask`/`/roast` traffic, auto-queue triggering every empty-queue, ambient roasts firing) can legitimately consume the entire 15 RPM budget in any given 60s window. Every *other* guild's `/ask`, `/roast`, `/imagine`, ambient roasts, proactive callbacks, and vision roasts then silently fall back to their template/fallback paths — the fallback design (Gemini-first, guaranteed template) means this degrades gracefully in isolation, but across guilds it becomes an invisible fairness bug: a recruiter's demo guild goes quiet not because Dexter is broken, but because someone else's guild is chatty.

**Why it happens:** The rate limiter was designed to protect the shared Gemini free-tier budget from bursts, not to allocate it fairly across tenants — a single-community bot has no "tenants" to be unfair to. Multi-tenancy exposes an assumption (one consumer) baked into the concurrency primitive itself, not just the config.

**How to avoid:** Do NOT attempt real per-guild quotas at this scale (adds complexity disproportionate to a "modest scale, not 100+ servers" target). Instead:
1. Add **observability**: log/track which `guild_id` each `acquire()` call is for (a lightweight rolling counter, mirroring the existing `PerfMetrics` pattern), surfaced in the owner control plane (`/servers` or similar) so the owner can *see* which guild is dominating the budget.
2. Consider a **soft per-guild ceiling inside priority 2** (background/ambient work only) — e.g. skip an ambient roast/proactive callback/auto-queue Gemini call for a guild that already used N of the last 15 RPM slots, falling back to template — protects priority-1 user commands in OTHER guilds without touching the existing priority semantics test suite.
3. Explicitly do NOT change priority-1 (user command) behavior per guild — a user in any guild typing `/ask` should still get the existing wait-up-to-60s behavior; starvation here is an acceptable tradeoff at modest scale and rearchitecting it is out of scope.

**Warning signs:** `/stats` (bot-wide only) shows RPM usage near cap while a demo/portfolio guild's roasts/`/ask` are silently falling back to templates. No per-guild breakdown exists today to even notice this without log-diving.

**Phase to address:** Owner control-plane phase (add the per-guild RPM visibility) — the observability half is cheap and directly serves the kill-switch's "see what's happening across guilds" goal. The soft-ceiling mitigation is optional polish, not required for the milestone's modest-scale target — flag as a documented known-limitation if deferred.

---

### Pitfall 3: Cross-guild memory recall is `user_id`-only by design — a feature, until strangers are in the room

**What goes wrong:** `services/memory.py::recall()` scopes ANN search to `user_id` only; `guild_id` is accepted as a parameter but explicitly NOT used in the `WHERE` clause (the docstring calls this out: "reserved for future per-guild memory scoping... cross-server personal facts are desirable: the same user uses the bot on multiple servers"). On a single community, or even across a user's own multiple servers, this is a genuinely good design (why should Dexter forget you switched Discords?). But once Dexter is *publicly* invitable, this becomes a privacy/embarrassment surface: a `/roast @user` or a proactive callback in **Guild B** (a stranger's server, a work Discord, a new friend group) can surface a memory distilled from that user's behavior in **Guild A** (their home server) — late-night listening habits, repeat-song obsessions, taste episodes, milestone counts. The user never consented to that context following them into an unrelated server, and `/memory forget` nukes ALL memories globally, not per-guild, so a user who wants to keep their home-server memory but stop it leaking into a new public server they just joined has no partial escape hatch.

**Why it happens:** This is not a bug — it's a correct implementation of a v1.2/v1.3 design decision made when "guild" meant "which of Dexter's few servers is this user in," never "a stranger's server the user just met the bot in." The multi-tenancy retrofit changes what "another guild" *means* without changing the code.

**How to avoid:** This needs an explicit product decision, not just a code fix, and should be flagged clearly in the roadmap discussion:
- **Option A (minimal):** Leave recall global-per-user (current behavior), but make it discoverable — `/memory view` and the opt-out already exist; ensure onboarding/help text tells new-server users that Dexter's roasts may reference their history from other servers it shares with them, and that `/memory forget` is the escape hatch. Cheapest, ships with existing primitives.
- **Option B (safer default):** Add a per-user "cross-guild memory sharing" opt-in (default OFF for guilds joined after some cutover date, or default OFF entirely with an easy opt-in), reusing the `proactive_opt_out`-style column pattern. Only activate global recall for users who've explicitly allowed it; otherwise `recall()` adds a `guild_id = $N` filter.
- Do NOT silently ship Option B's guild-scoping as a quiet behavior change without deciding — it would also quietly change `/ask`/`/roast` grounding behavior that's been relied on and tested since Phase 15 (D-01).

**Warning signs:** A user roasted in a brand-new public server references a fact only ever true in their home guild ("still playing that song 4 times a day" from a totally different server's history) — reads as surveillance to someone who just met the bot.

**Phase to address:** Config seam / owner control-plane phase should surface this as an explicit decision point (likely resolved in a `discuss-phase`-style checkpoint, not silently coded); whichever option is chosen, implement in the same phase that touches `MemoryService.recall()` call sites, since it changes a security-relevant WHERE clause that 4+ surfaces depend on (`/ask`, `/roast`, ambient roasts, proactive callbacks).

---

### Pitfall 4: `app_commands.default_permissions` is a Discord-side HINT, not an enforced check — don't rely on it for `/setup` or the kill-switch

**What goes wrong:** discord.py's `@app_commands.default_permissions(...)` decorator (verified via Context7 against the discord.py source) explicitly documents: *"This is sent to Discord server side, and is not a check. Therefore, error handlers are not called."* It also states an admin **can reconfigure** who's allowed to run the command via the Discord client's Integrations settings, and that "due to a Discord limitation, this decorator does nothing in subcommands and is ignored." A developer adding `/setup` (admin-designates-ambient-channel) or worse, an owner-only kill-switch command, and gating it ONLY with `default_permissions(administrator=True)` will find: (a) it's a hint a guild admin can weaken/remove, (b) it silently does nothing at all if `/setup` is ever nested as a subcommand, and (c) since error handlers never fire for it, there's no ephemeral "you can't do that" — the command option just doesn't appear for that user, which is confusing UX with zero telemetry.

**Why it happens:** The decorator name and its resemblance to a real permission check make it easy to assume it's enforced like `commands.check`. It isn't.

**How to avoid:** Dexter already has the correct pattern for this in `cogs/ops.py`'s `/stats` command (D-21/T-08-09): an **inline runtime check as the first line of the command body** — `await bot.is_owner(interaction.user)` for bot-owner-only commands, or `interaction.user.guild_permissions.administrator` / `manage_guild` for per-guild admin commands like `/setup` — followed by an ephemeral refusal before any data access. Reuse this exact convention for:
- `/setup` (per-guild): check `interaction.user.guild_permissions.manage_guild` (or `administrator`) inline, not just as a decorator hint.
- Owner control-plane commands (list guilds, silence/force-leave a guild): check `await bot.is_owner(interaction.user)` inline — and critically, this must be **bot-owner**, never conflated with "guild owner" or "guild administrator." A guild admin must never be able to force-leave or silence a DIFFERENT guild.
- Use `default_permissions` only as a cosmetic hint on top of the real check (helps hide the command from non-admins in the UI), never as the sole gate.

**Warning signs:** A command with only a decorator and no inline check; any command whose top-level docstring doesn't mention where the owner/permission check happens; a kill-switch command reachable from a guild that isn't the owner's home guild.

**Phase to address:** Owner control-plane phase (kill-switch commands) and config seam phase (`/setup`) both — this is a cross-cutting convention, verify it in code review for every new command this milestone adds.

---

### Pitfall 5: The owner kill-switch can be bypassed by in-flight ambient tasks and stale in-memory state (TOCTOU, same shape as the Phase 16 daily-cap bug)

**What goes wrong:** Dexter already has a documented, fixed instance of this exact bug class: Phase 16's `_maybe_fire_proactive_callback` originally checked-then-later-incremented a daily counter across `await` boundaries, letting two concurrent messages both pass the gate (fixed via WR-01's "reserve slot before await, release on non-fire"). The kill-switch has the identical shape at guild scope: if "is this guild silenced?" is checked once at the top of `on_message`/`on_voice_state_update` and then the handler proceeds through several `await`s (recall, Gemini call, DB write) before sending, a silence/force-leave issued by the owner *during* that window does not retroactively stop the in-flight roast from posting. Worse, ambient state is cached in-memory per cog instance (`_ambient_roast_times`, `_proactive_daily_counts`, `_vision_roast_cooldowns` in `EventsCog.__init__`) — if the kill-switch's "silenced guilds" set is ALSO an in-memory cache refreshed only periodically (or only on command), a guild silenced via the DB can still fire ambient behavior until that cache refreshes, and a force-leave that doesn't also clear per-guild in-memory state (voice cooldowns, proactive counts, persisted queue) leaves ghost state that could resurrect behavior if the bot later rejoins.

**Why it happens:** Fire-and-forget async handlers with multiple await points are inherently racy against any check-then-act invariant; Dexter's own Phase 16 postmortem is direct precedent for this exact bug shape recurring at guild scope instead of user scope.

**How to avoid:**
- Check "is this guild silenced?" as EARLY as possible (first line, no `await` before it) in every ambient entry point: `on_message`, `on_voice_state_update`, the vision/proactive dispatch, and — critically — the AI cog's `/ask`/`/roast`/auto-queue paths too (the kill-switch should mean "Dexter is off here," not just "no unprompted ambient chatter").
- Re-check the silence flag immediately before the final `send`/`reply` call too (belt-and-suspenders against a silence issued mid-flight) — cheap since it's a cache read, not a new DB round-trip if cached correctly.
- On force-leave: mirror the existing `clear_persisted()` teardown discipline (CLAUDE.md's documented pattern: `_play_generation += 1` → `clear()` → `clear_persisted()` at every teardown site) — a force-leave must invalidate the queue generation counter, clear the persisted `guild_queues` row, and disconnect voice, or a ghost queue/voice session survives the "kill" and can resume on next boot (the exact DEPLOY-06 scar, recurring at kill-switch scope).
- Prefer a short-TTL cache (or a pure DB read per event, since guild-level checks are far less frequent than per-message checks) over a long-lived in-memory set for the silenced-guilds flag, and invalidate/refresh it explicitly the moment the owner runs the silence/force-leave command (push-invalidate, don't wait for a poll interval).

**Warning signs:** A roast/reply posts in a guild seconds after the owner silenced it; a force-left guild's queue/voice state resurrects on the next bot restart; no test exists asserting the silence check happens before the first `await` in each ambient handler (mirror the existing `test_ambient_recall_cadence.py` regression-lock pattern for this).

**Phase to address:** Owner control-plane phase — this is the core correctness requirement of the kill-switch feature itself, not a nice-to-have; write a pure `logic/kill_switch.py`-style gate (mirroring `logic/proactive.py`/`logic/vision.py`) so it's mock-free-testable, and lock the "checked before any await" invariant with a structural test.

---

### Pitfall 6: `on_guild_join` doesn't exist yet — a bare "just works" bot is worse than an explicit onboarding message

**What goes wrong:** There is currently NO `on_guild_join` handler anywhere in the codebase. Today, when Dexter joins a new guild, nothing happens: no welcome message, no onboarding, no indication of how to set the ambient channel, no indication ambient/vision roasting exists or how to opt out. A recruiter who invites the bot for a portfolio demo gets total silence until they manually discover `/help`. Naively fixing this by posting a message via `guild.system_channel` is itself a common pitfall: `system_channel` can be `None` (many servers don't set one), or the bot may lack `send_messages` permission there even though it has it elsewhere, and posting can raise `discord.Forbidden`/`discord.HTTPException` uncaught inside an event listener — Discord swallows exceptions raised in listeners by logging them, but the join message is silently lost with no error-channel visibility unless explicitly caught. There's also a spam-perception risk: an unprompted message the moment the bot joins (before anyone invoked it) can read as a bot advertising itself uninvited in a server the admin is still configuring.

**Why it happens:** The bot was built to be manually added to one known community by its own owner, who already knew the personality/setup — there was never a need for a "first impression" flow. Public invitability makes onboarding a first-class UX requirement, not an afterthought.

**How to avoid:**
- Implement `on_guild_join(guild)` explicitly, wrapped in try/except around the send call (mirror the `discord.HTTPException` guard pattern already used throughout `events.py` for reactions/replies).
- Resolve the target channel via the SAME consolidated resolver as Pitfall 1 (don't write a third copy), falling back gracefully to "post nothing, log a debug line" if no writable channel exists — never let onboarding raise into the gateway.
- Keep the join message short, low-key, and actionable: what Dexter does, the ONE command to run next (`/setup`), and where to learn about `/memory forget`/opt-outs — not the full sarcastic personality blast on arrival, since the admin hasn't opted into ambient behavior yet (see Pitfall 7).
- Register this in the config-seam phase alongside `/setup`, since the join message should tell the admin to run `/setup` (chicken-and-egg: onboarding message existing is what makes `/setup` discoverable).

**Warning signs:** Inviting the bot to a fresh test guild and getting silence; a caught-but-unlogged `discord.Forbidden` on join in a guild with a locked-down `system_channel`.

**Phase to address:** Onboarding phase (paired with the config-seam phase's `/setup` command — they are two halves of the same first-run experience).

---

### Pitfall 7: Ambient behavior (roasts, proactive callbacks, vision) must default OFF in a freshly-joined guild, not silently inherit the fallback-channel guess

**What goes wrong:** Today, `_get_ambient_channel`'s fallback chain (system channel → first writable channel) means ambient roasts, proactive callbacks, and vision roasts will start firing in ANY guild the bot joins the moment a qualifying event occurs (a voice join, a message in whatever channel the fallback picked, an image post) — there is no "configured" gate. For a single trusted community this fallback is a convenience; for an arbitrary public server it means: (a) Dexter may pick a channel the admin never intended for bot chatter (a mod-only channel that happens to be first-writable, an announcements channel), (b) full-savage personality roasts and vision-roasts arbitrary user-uploaded images of STRANGERS before the admin has even seen `/setup` exists, which is the exact ToS/abuse surface this milestone's kill-switch is meant to mitigate — except the kill-switch is reactive (after a complaint), while this pitfall is about the FIRST few minutes after invite, before anyone could possibly have complained yet.

**Why it happens:** The fallback chain was designed for resilience (never fully silent, even if `DEXTER_CHANNEL_ID` misconfigures) on a bot that only ever ran in guilds the owner controlled. Public invite removes the "the owner controls every guild it's in" assumption that made an aggressive fallback safe.

**How to avoid:** Add an explicit **per-guild "configured" flag** (part of the new per-guild config row from Pitfall 1/3), default `False` on join. While unconfigured:
- Slash commands (`/play`, `/ask`, etc.) work normally (guild-scoped, no ambient risk) — don't gate the core music/AI functionality behind setup.
- Ambient/unprompted surfaces (voice-join/leave roasts, idle messages, proactive callbacks, vision roasts, status-rotation posts, startup farewell) are suppressed entirely until `/setup` runs and flips the flag.
- The `on_guild_join` message (Pitfall 6) is the one exception allowed to post via the fallback chain, since it's the mechanism that gets the admin to run `/setup` in the first place.

**Warning signs:** A test invite to a scratch guild produces an unprompted roast or vision-roast before anyone has run any command; an admin reports "I didn't even set this up yet and it roasted someone's photo."

**Phase to address:** Config seam phase — the "configured" gate is the same schema change as per-guild channel storage, so implement together.

---

### Pitfall 8: Bot verification is a hard join-blocking wall at 100 guilds — separate from, and stricter than, the newer 10,000-user privileged-intent threshold

**What goes wrong:** Two different Discord gates exist and are easy to conflate:
1. **App/bot verification** (identity verification via Stripe, submitted through the Developer Portal) is required once a bot is already in **100 servers** — per Discord's own developer support docs, *"if a bot is already in more than 100 servers, it will not be able to join any more until it is verified."* This is a hard block on `bot.add_to_server`, not a warning.
2. **Privileged intent access** (needed for `message_content`, which Dexter uses for the message buffer, reactions, ambient-roast anchors, and vision triggers) was changed in 2026 from a 100-guild-adjacent rule to a **10,000-unique-user threshold**: once an app with a privileged intent crosses 10,000 total unique users across all its guilds, Discord notifies the developer and gives 90 days to apply for continued access; missing that window revokes the intent (the bot keeps running otherwise, it just loses `message_content` etc.).

For THIS project (modest-scale, not pursuing 100+ guilds this milestone), neither is an active blocker, but both should be documented and monitored: the moment a portfolio/demo push causes organic growth past double digits of guilds, the 100-guild join-block is a real, sudden, no-warning wall (a recruiter trying to add Dexter to guild #101 simply fails), while the intent threshold is comparatively forgiving (90-day grace window).

**Why it happens:** Both thresholds are easy to miss because a bot built for one community never approaches either; the moment it's genuinely public and growing, they become live constraints, not hypotheticals.

**How to avoid:** Document both thresholds explicitly in the portfolio README/architecture write-up as a known, intentional scope boundary ("not verified, not intended to scale past 100 servers"). Optionally surface current guild count in the owner control-plane's server list so the owner notices approaching the 100 mark organically. Do not attempt to pursue Discord verification this milestone (identity verification, a public-facing privacy policy/ToS, and a review process are disproportionate to a portfolio piece) — explicitly out of scope, matching the milestone's own stated scale target.

**Warning signs:** None at current scale — this is a "know it exists" documentation item, not a code fix.

**Phase to address:** Portfolio phase (document as an explicit, honest scope boundary in the README/case-study) — no code changes needed this milestone.

Sources: [What are Privileged Intents? – Discord Developers](https://support-dev.discord.com/hc/en-us/articles/6207308062871-What-are-Privileged-Intents), [How Do I Get My App Verified? – Discord Developers](https://support-dev.discord.com/hc/en-us/articles/23926564536471-How-Do-I-Get-My-App-Verified) (MEDIUM confidence — content summarized via web search excerpt of official docs, not directly fetched due to a 403 on direct WebFetch; cross-checked against two independent search results agreeing on both thresholds).

---

### Pitfall 9: Full-savage personality + unprompted vision-roasting of strangers' photos is a real Discord Community Guidelines / Developer Policy harassment surface — the kill-switch is reactive, not preventive

**What goes wrong:** Discord's Community Guidelines and Developer Policy prohibit using bots/apps to "defame, abuse, harass, stalk, threaten others" — this applies to bot-generated content exactly as it applies to a human's. Dexter's stated design (full-savage everywhere, unchanged; vision roasts arbitrary user-uploaded images with no consent mechanism beyond an opt-out most users won't know exists) creates real exposure once strangers — not the owner's known community — can be on the receiving end: an uploaded photo of a real person, roasted by an AI, in a server the bot owner doesn't moderate, is a plausible harassment report vector. The stated mitigation (owner kill-switch: silence/force-leave a guild) is **reactive** — it only helps *after* abuse has already happened and been reported/noticed, and only if the owner is online to act (the bot itself is already only-sometimes-online, so incident response could itself be delayed for real hours).

**Why it happens:** The personality-stays-full-savage decision was made deliberately as a product identity choice (CLAUDE.md: "the owner's decision"), and vision roasting was designed and scoped in Phase 17 for a trusted single community, where the existing per-user `proactive_opt_out` was a reasonable, low-stakes safety valve. Multi-tenancy doesn't change the code path, but it changes who's exposed to it — from "people who chose to be in this Discord and know Dexter" to "anyone in any server that invites the bot."

**How to avoid (mitigations that reduce, not eliminate, the risk — a full acceptance was already made at the product level):**
- **Preventive, not just reactive:** make the vision/ambient opt-out discoverable in the `on_guild_join` message and/or `/setup` output ("Dexter roasts things unprompted, including photos — `/memory callbacks off` opts you out"), not buried in `/help`.
- **Fast-path kill-switch, not just guild-level:** ensure the per-user `proactive_opt_out` flag (already shared by proactive callbacks and vision roasts) is easy to find and self-serve — this is the fastest mitigation a harassed user can apply themselves, faster than waiting on the owner.
- **Owner-facing incident visibility:** the control plane should let the owner quickly see recent vision-roast/ambient-roast activity per guild (a lightweight audit log — even just "last N ambient/vision fires + guild + timestamp") so a reported incident can be investigated and the guild silenced quickly once the owner IS online — reduces mean-time-to-mitigate even though it can't reduce mean-time-to-detect.
- **Be honest in the portfolio write-up:** state explicitly that full-savage personality + public invite is a deliberate, disclosed risk tradeoff with a reactive (not preventive) safety valve — a recruiter reading the case study will read this as engineering maturity (naming a tradeoff) rather than an oversight, whereas silence on it reads as naivety about production bot risk.

**Warning signs:** No audit trail exists today for which guild/user an ambient or vision roast fired for beyond debug-level logs; no in-product surface tells a new user the opt-out exists before they might need it.

**Phase to address:** Owner control-plane phase (audit visibility + fast silence/force-leave) and onboarding phase (surface the opt-out proactively) together; document the residual risk explicitly in the portfolio phase's case study rather than treating it as solved.

---

### Pitfall 10: An often-offline, on-demand bot creates a public-invite UX expectation mismatch, and multi-guild persisted state assumes short offline windows

**What goes wrong:** Two distinct problems compound:
1. **UX expectation mismatch:** A public bot listing/invite implies "always there." Dexter is intentionally owner-run, on-demand, residential-IP-only. A recruiter or random invited server sees an offline bot with no explanation — reads as broken, not as "runs on demand," unless the invite flow and/or bot status/presence communicates this explicitly (e.g. a custom status, a landing-page disclaimer, an `on_guild_join` message that sets expectations).
2. **Multi-guild persisted-state assumptions:** `guild_queues` (JSONB queue snapshots) and smart-rejoin logic were built and UAT'd against short, single-community offline windows (dev restarts, brief outages). Public multi-tenancy means potentially MANY guilds accumulate stale persisted queues over long owner-offline windows (the bot could be off for days between the owner's play sessions). On the next boot, `restore_queues` attempting smart-rejoin across every guild with a stale persisted queue simultaneously is a thundering-herd risk against voice channels whose members left long ago (each attempt should fail gracefully per-guild per the existing `continue`-not-`return` discipline, but that discipline was written for a handful of guilds, not tested at "every public guild that ever queued something, reconnecting at once").

**Why it happens:** The persistence and reconnection code (Phase 4/5) was built and validated for a single owner-controlled guild with predictable short offline gaps; multi-tenancy multiplies the number of independently-stale queues without changing the reconnection assumptions.

**How to avoid:**
- Add a staleness check before attempting smart-rejoin: if a persisted queue's `updated_at` is older than some threshold (e.g. a few hours), skip the rejoin attempt entirely and just clear it — resuming playback in a channel that's been empty for two days is never the right UX regardless of guild count.
- Set the bot's Discord presence/activity or a status-rotation entry to something honest ("owner-run, on-demand — mention when it's up") so a public invite doesn't imply an SLA it doesn't have.
- Communicate the on-demand model explicitly in the portfolio landing page AND the `on_guild_join` message, so it's a disclosed feature ("live demo when the owner's online") rather than a discovered limitation.

**Warning signs:** Bot boot logs showing many simultaneous voice-reconnect attempts to now-empty channels across guilds; a portfolio visitor's first interaction being an unresponsive `/play` with no context.

**Phase to address:** Onboarding phase (expectation-setting copy) and portfolio phase (landing page disclaimer); the staleness-check code change belongs in the config-seam phase since it touches the same queue-persistence code the multi-tenancy work already has to reason about.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|--------------------|-----------------|------------------|
| Global `DEXTER_CHANNEL_ID` env var stays as a fallback/default instead of being fully replaced by per-guild config | Zero-migration path for the owner's existing home guild | New guilds get inconsistent behavior depending on whether they're "the" env-configured guild or not | Acceptable ONLY if it's explicitly the "unconfigured guild fallback," never a silent default for all guilds |
| Reusing `proactive_opt_out` as the shared silence flag for vision roasts (already the v1.3 design) | Zero new schema, proven pattern | One flag now means three different things (proactive callbacks, vision roasts, and potentially "don't roast me at all") with no granularity | Acceptable at modest scale; revisit if users request partial opt-outs (e.g. "roast my music, not my photos") |
| In-memory-only guild silence cache with periodic refresh instead of a DB read per event | Avoids a DB round-trip on every ambient event | Directly reintroduces the Pitfall 5 TOCTOU window | Never acceptable without push-invalidation on the silence/force-leave command itself |
| Skipping per-guild rate-limit fairness entirely (Pitfall 2) at this milestone's scale | Saves real engineering complexity disproportionate to a "modest scale" target | If the portfolio bot ever gets modest organic pickup, one guild's chatter silently degrades every other guild with zero visibility | Acceptable IF the observability half (guild_id logging) ships so the owner can at least detect it |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|------------------|--------------------|
| discord.py `app_commands.default_permissions` | Treating it as an enforced permission check | Use it only as a UI hint; always add the inline `is_owner()`/`guild_permissions` check as the real gate (Pitfall 4) — Dexter already has this convention in `cogs/ops.py`, extend it |
| discord.py `on_guild_join` | Posting to `guild.system_channel` without checking it's non-`None` and writable, or without a try/except around the send | Reuse the consolidated ambient-channel resolver (Pitfall 1) and always wrap the send in `discord.HTTPException`/`discord.Forbidden` handling |
| Discord bot verification (100-guild join wall) | Assuming it only matters "someday" and being surprised when a growth spike hard-blocks new joins with zero warning | Track guild count in the owner control plane; document the ceiling explicitly as an accepted scope boundary in the portfolio write-up |
| Discord privileged intents (10k-unique-user threshold, 2026 policy) | Conflating this with the 100-guild verification wall — they are separate mechanisms with separate consequences | Know both exist and are independent; at this milestone's scale neither is a near-term concern, but don't assume "under 100 guilds" also means "under the intent threshold" if a guild is unusually large |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Global 15 RPM Gemini limiter with no per-guild fairness | One guild's `/ask`/auto-queue traffic silently starves another guild's ambient/roast/chat features into template-fallback mode | Add per-guild RPM usage observability (Pitfall 2); optionally soft-cap priority-2 (background) usage per guild | Noticeable once more than 2-3 guilds are simultaneously active with real usage — not a concern with 1 guild, real risk by single-digit active guilds doing normal usage |
| Persisted `guild_queues` smart-rejoin across many guilds after a long owner-offline window | Boot-time burst of voice-reconnect attempts to channels that have been empty for days | Add a staleness check (Pitfall 10) — skip smart-rejoin and clear the queue if `updated_at` exceeds a threshold | Breaks noticeably once more than a handful of guilds have queued something during an offline stretch of days, not hours |
| In-memory ambient-roast/proactive/vision cooldown dicts (`_ambient_roast_times`, `_proactive_daily_counts`, `_vision_roast_cooldowns`) keyed by user/guild, never pruned | Slow, unbounded memory growth is not a near-term concern at modest scale, but a silenced/force-left guild's entries linger forever, creating stale-state confusion if the guild ever rejoins | Clear a guild's entries from these dicts on force-leave/kick (`on_guild_remove`) | Not a hard failure at modest scale; a correctness/hygiene issue, not a resource issue, until guild count is much larger |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Gating `/setup` or kill-switch commands with only `default_permissions`, no inline check | A guild admin reconfigures command permissions in Discord's Integrations UI and grants a non-admin access; kill-switch commands become guild-permission-controllable instead of bot-owner-only | Inline `is_owner()`/`guild_permissions` check as the actual gate (Pitfall 4), matching the existing `/stats` convention |
| Confusing "guild owner/admin" with "bot owner" on any control-plane command | A guild administrator could force-leave or silence a DIFFERENT guild, or read cross-guild data, if the check is `has_permissions(administrator=True)` instead of `bot.is_owner()` | Owner control-plane commands must check `await bot.is_owner(interaction.user)`, full stop — never a guild-relative permission |
| Checking the kill-switch's silence flag only once, at the top of a multi-await handler | TOCTOU window lets an in-flight ambient/roast/vision task complete after the owner silences the guild (Pitfall 5) | Check immediately before the final send too; push-invalidate any cache the moment the owner issues silence/force-leave |
| Treating the vision-roast/ambient-roast opt-out as sufficiently discoverable via `/help` alone | New users in a newly-invited public guild have no reason to know the opt-out exists before an incident happens | Surface the opt-out proactively in `on_guild_join`/`/setup` output (Pitfall 9) |
| SSRF via message-content image URLs (mentioned as already-mitigated in Phase 17: attachments-only trigger, never a message-content URL) | Public multi-tenancy raises the stakes on any accidental regression of this guard, since untrusted strangers (not just the owner's community) could probe it | Keep the existing Phase 17 attachments-only trigger discipline explicitly locked by a regression test if not already; do not weaken it while retrofitting per-guild config around the same event handlers |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Silence after invite (no `on_guild_join` message) | Admin has no idea `/setup` exists, no idea ambient behavior/vision roasting will start, no idea how to opt out | Explicit, short, actionable join message (Pitfall 6) |
| Ambient behavior firing before `/setup` is run, in whatever channel the fallback chain guesses | Roasts/vision-roasts appear in the wrong channel, feel unsolicited and possibly targeted at the wrong audience (e.g. a mod channel) | Default-OFF "configured" gate per guild until `/setup` runs (Pitfall 7) |
| Bot appears offline with no explanation on a public invite | Reads as broken/abandoned rather than "runs on demand" | Presence/status messaging + explicit expectation-setting copy (Pitfall 10) |
| A user roasted with cross-guild memory in a server where nobody else knows their history | Reads as surveillance/creepy rather than "personalized," especially to someone new to the bot | Explicit decision + disclosure on cross-guild recall scope (Pitfall 3) |
| Kill-switch force-leave doesn't clean up voice/queue state | If the bot is later re-invited to the same guild, ghost queue/voice state could resurrect unexpectedly | Mirror the existing `clear_persisted()` teardown discipline on force-leave (Pitfall 5) |

## "Looks Done But Isn't" Checklist

- [ ] **Per-guild ambient channel:** Looks done once `/setup` writes a DB row — verify BOTH `bot.py::_resolve_dexter_channel` and `cogs/events.py::_get_ambient_channel` (or their consolidated replacement) actually read it, not just one of the two call sites (Pitfall 1).
- [ ] **Owner kill-switch:** Looks done once a `/servers silence` command exists and flips a DB flag — verify the flag is checked BEFORE any `await` in every ambient entry point (`on_message`, `on_voice_state_update`, auto-queue, `/ask`/`/roast`), not just at the top of `on_message` (Pitfall 5).
- [ ] **Force-leave:** Looks done once `guild.leave()` is called — verify voice disconnect, `_play_generation` bump, `clear()`, and `clear_persisted()` all run first, mirroring the existing `/stop` teardown template (Pitfall 5).
- [ ] **`/setup` admin gate:** Looks done once `default_permissions(administrator=True)` decorates the command — verify there's also an inline `guild_permissions` check in the command body (Pitfall 4).
- [ ] **`on_guild_join` onboarding:** Looks done once a message posts on join — verify it's wrapped in try/except for `discord.Forbidden`/`HTTPException`, and that it uses the SAME channel-resolution logic as ambient behavior, not a third hand-rolled lookup (Pitfall 6).
- [ ] **Fresh-guild ambient suppression:** Looks done once `/setup` exists — verify a guild that has NOT run `/setup` truly produces zero ambient/vision/proactive output, tested against a scratch guild, not just code-reviewed (Pitfall 7).
- [ ] **Cross-guild memory decision:** Looks done once `/memory` commands still work — verify the actual product decision (global-per-user vs. per-guild-scoped recall) was made deliberately and is reflected consistently across `/ask`, `/roast`, ambient roasts, AND proactive callbacks — not just one of the four call sites (Pitfall 3).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|------------------|
| Duplicated channel resolver drifts (Pitfall 1) | LOW | Diff the two functions, consolidate into one shared resolver, add the import-identity regression test |
| Cross-guild rate-limit starvation goes unnoticed (Pitfall 2) | LOW | Add guild_id logging retroactively to `_RateLimiter.acquire()`; no schema change needed, purely additive |
| Kill-switch TOCTOU lets a roast slip through after silence (Pitfall 5) | MEDIUM | Delete the offending message if `message.reply` already succeeded (best-effort, may already be read by users); move the check earlier; add the regression test that would have caught it |
| Force-leave leaves ghost voice/queue state (Pitfall 5) | LOW | Run the same manual cleanup the existing `/stop` path does, invoked once from a maintenance script or an owner command, against any previously force-left guild's stale row |
| No `on_guild_join` shipped, discovered post-launch via silent invites | LOW | Additive — implement and deploy; no migration needed, purely a new listener |
| Cross-guild memory leak reported by a user | MEDIUM–HIGH (depends on chosen fix) | If Option B (opt-in scoping) wasn't shipped, retrofitting per-guild `WHERE guild_id = $N` into `recall()` and `search_memories` touches 4+ call sites and needs the existing `/ask`+`/roast` regression tests (`test_ambient_recall_cadence.py`-style) updated in lockstep |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| 1. Duplicated channel resolver | Config seam | Single shared resolver function; both call sites import it; a test asserts identity, not just equal output |
| 2. Cross-guild rate-limit fairness | Owner control-plane (observability) | `/servers`-style command shows per-guild RPM usage in the last window; manual test with two guilds generating load simultaneously |
| 3. Cross-guild memory privacy | Config seam (decision + implementation) | Explicit decision recorded (ADR-style); if scoped, a test proves a memory distilled in Guild A never appears in a Guild B `/roast`/proactive callback for the same user |
| 4. `default_permissions` is a hint | Config seam (`/setup`) + Owner control-plane (kill-switch) | Code review checklist item; every new admin/owner command has an inline check, verified by grep for `is_owner`/`guild_permissions` in each new command body |
| 5. Kill-switch TOCTOU + force-leave cleanup | Owner control-plane | Pure `logic/kill_switch.py` gate with mock-free tests; a structural test asserting the silence check precedes the first `await` in each ambient handler; a test proving force-leave clears persisted queue + voice state |
| 6. Missing `on_guild_join` | Onboarding | Manual test: invite to a scratch guild, confirm a message posts, confirm no exception on a guild with no system channel / no bot permissions anywhere |
| 7. Ambient behavior firing pre-`/setup` | Config seam | Manual test: scratch guild with `/setup` never run produces zero ambient output across a full test pass (voice join/leave, message, image post) |
| 8. 100-guild verification wall / 10k-user intent threshold | Portfolio (documentation only) | README/case-study explicitly states the scope boundary; no code required |
| 9. Savage-personality/vision ToS-abuse surface | Owner control-plane + Onboarding + Portfolio | Opt-out surfaced in onboarding copy; audit-log visibility in control plane; residual risk explicitly documented in the case study |
| 10. Offline-bot UX + stale multi-guild persisted state | Onboarding + Portfolio + Config seam | Staleness check on `restore_queues` (config seam); expectation-setting copy shipped in `on_guild_join` and the landing page (onboarding/portfolio) |

## Sources

- Codebase (HIGH confidence, directly read): `C:\Users\James\desktop\projects\dexter\CLAUDE.md`, `.planning\PROJECT.md`, `cogs\events.py`, `services\memory.py`, `bot.py` (`_resolve_dexter_channel`), `services\gemini.py` (`_RateLimiter`), `cogs\ops.py` (owner-check convention)
- [discord.py — `app_commands.commands.default_permissions` source](https://github.com/rapptz/discord.py/blob/master/discord/app_commands/commands.py) via Context7 `/rapptz/discord.py` (HIGH confidence — direct library source excerpt)
- [What are Privileged Intents? – Discord Developers](https://support-dev.discord.com/hc/en-us/articles/6207308062871-What-are-Privileged-Intents) (MEDIUM confidence — summarized via search snippet, direct fetch returned HTTP 403)
- [How Do I Get My App Verified? – Discord Developers](https://support-dev.discord.com/hc/en-us/articles/23926564536471-How-Do-I-Get-My-App-Verified) (MEDIUM confidence — summarized via search snippet)
- [Discord Developer Policy – Developers](https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy) and [Community Guidelines | Discord](https://discord.com/guidelines) (MEDIUM confidence — general harassment/abuse prohibitions confirmed via search summary, not line-by-line fetched)
- [Discord Privileged Gateway Intents and MESSAGE_CONTENT in 2026 — space-node.net](https://space-node.net/blog/discord-gateway-intents-message-content-2026) (LOW-MEDIUM confidence — third-party summary, cross-checked against official support-dev article for the 10k-user figure)
- [Multi-Server Discord Bots: Architecture — space-node.net](https://space-node.net/blog/discord-multi-server-bot-architecture-2026) (LOW confidence — generic multi-tenant bot architecture advice, used only for the general scale-inflection framing, not for any Dexter-specific claim)
- Phase 16 postmortem (`WR-01` daily-cap TOCTOU fix) and Phase 5 `clear_persisted()`/DEPLOY-06 scar — cited from CLAUDE.md's own documented "Implementation Gotchas," used as direct precedent for Pitfall 5's failure mode recurring at guild scope

---
*Pitfalls research for: single-community → publicly-invitable multi-tenant Discord bot retrofit (Dexter v1.4 "Open House")*
*Researched: 2026-07-10*
