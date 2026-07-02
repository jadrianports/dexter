# Phase 16: Proactive Memory Callbacks - Research

**Researched:** 2026-07-03
**Domain:** Discord bot ambient/unprompted-surface engineering (discord.py `on_message` gate) +
pure-logic decision seam (Phase 10 convention) + additive Postgres column (Phase 8 convention).
No new libraries, no new infra — this is 100% internal-codebase research.
**Confidence:** HIGH (every claim below was verified by reading the actual current source files
in this repo, not from training-data recall; the two external-library claims — `discord.py`
`Message.reply(allowed_mentions=...)` and `asyncpg` `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
idempotency — are CITED against Context7-fetched discord.py docs and the codebase's own Phase 8
precedent respectively).

## Summary

Phase 16 adds a third, rarest ambient cadence to `cogs/events.py`'s already-existing
`on_message` listener. All four design decisions (D-01…D-04) are locked in CONTEXT.md; this
research confirms the exact current line numbers, signatures, and reuse seams the planner needs,
and finds them **unchanged from what CONTEXT.md's `canonical_refs` block claims** — no
line-number corrections needed anywhere.

The implementation is small and almost entirely additive: one new pure-logic module
(`logic/proactive.py`, mirroring `logic/roasts.py::decide_ambient_roast` almost exactly), one
new boolean column on `user_profiles` (mirroring the Phase 8 `total_errors` additive-column
precedent), one new `/memory callbacks` subcommand (mirroring the existing `view`/`forget`
subcommands' self-scoping and ephemeral-response conventions), a handful of new `config.py`
knobs, and a new gate evaluated inside `EventsCog.on_message` right after the existing bot-author
guard, dispatching into the **already-existing** `_generate_ambient_roast` helper — reused
wholesale, not duplicated — followed by a `message.reply(..., allowed_mentions=discord.
AllowedMentions.none())` instead of a plain `channel.send(...)`.

**Primary recommendation:** Add `logic/proactive.py::should_fire_proactive_callback(*, opted_out,
chance_roll, chance, daily_count, daily_cap) -> bool` (pure, keyword-only, mirrors
`decide_ambient_roast`'s gate-ordering convention exactly: opt-out → chance → cap, cheapest gate
first). Evaluate it in `EventsCog.on_message` after the existing bot-guard and message-buffer
feed, gated on `_get_ambient_channel`-equivalent designated-channel confirmation, then on success
call the existing `_generate_ambient_roast(member, scenario, fallback_pool)` with the message
author as `member` and reply-anchor the result. Store the opt-out as
`user_profiles.proactive_opt_out BOOLEAN DEFAULT false` via an additive `ALTER TABLE` in
`SCHEMA_SQL`, with a getter/setter pair in `database.py`. Add a `callbacks` subcommand to the
existing `cogs/memory.py` `app_commands.Group`. Keep the daily-cap counter as an in-memory
per-cog `dict[str, tuple[str, int]]` keyed by `(user_id -> (iso_date_in_STREAK_TIMEZONE,
count))`, reset implicitly by date comparison (no separate rollover task needed — durability
is explicitly not required per D-02).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 (Active-moment anchor): Chat message only.** A proactive callback is evaluated in the
`on_message` path (`cogs/events.py:348`) when a non-bot user posts in the designated channel —
the cleanest "they are actively here right now" signal. The recall target is the message author
(their own memory, scoped to `str(author.id)`), and the callback is anchored to that message
(D-04). Voice-join is deliberately NOT a trigger — it already fires ambient roasts via the 0.30
gate, and stacking a second surface there would double-fire. *(Rejected: chat+voice —
overlap/double-fire risk; chat-only-after-absence — needs per-user last-seen tracking, over-
engineering for v1.3.)*

**D-02 (Rarity & daily cap): probability roll strictly below ambient, AND an additive PER-USER
daily cap; both must pass.** Firing logic on a qualifying message, in order (short-circuit,
cheapest gate first):
1. **Opt-out check** (D-03) — skip immediately if the author paused callbacks.
2. **Chance roll** — a new `PROACTIVE_CALLBACK_CHANCE` knob strictly less than
   `MEMORY_CALLBACK_CHANCE` (0.35) / `UNPROMPTED_ROAST_CHANCE` (0.30). Suggested starting value
   ≈ 0.08–0.12 (planner/numeric discretion, tunable).
3. **Per-user daily cap** — the additive bound PROACT-01 requires, keyed per user per calendar
   day. Suggested cap 1/day per user (tunable, `PROACTIVE_CALLBACK_DAILY_CAP`).
4. **Recall floor** — only fire if `recall()` actually returns a memory clearing
   `MEMORY_SIMILARITY_FLOOR` (0.70). No memory → silently skip (Pitfall 8: "no memory beats a
   wrong memory").
Cap scope is PER-USER, not per-guild. Counter storage is planner discretion — an in-memory
`{user_id: (date, count)}` dict reset at day rollover is sufficient (a cap reset across a
restart is harmless). Reuse the day-rollover convention already in `bot.py` daily loops if
convenient. *(Rejected: per-guild cap — wrong bound; cap-before-roll — the roll should gate
first so the cap is a ceiling on an already-rare event.)*

**D-03 (Opt-out control): a `/memory callbacks` toggle subcommand, indefinite on/off, stored as
a boolean column on `user_profiles`, default opted-IN.** Add `callbacks` (or `pause`) as a third
subcommand under the existing `/memory` `app_commands.Group` (`cogs/memory.py`, Phase 15).
Semantics: an indefinite toggle ("pause callbacks for me" until turned back on), not a timed
snooze. Default = opted-in (callbacks ON). Storage: a new boolean column on `user_profiles`
(e.g. `proactive_opt_out BOOLEAN DEFAULT false`) via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
in `SCHEMA_SQL` — mirrors the Phase 8 `total_errors` additive-column pattern; no new table.
Crucially distinct from `/memory forget`: the opt-out flips a flag and touches zero memory
rows. Ephemeral confirmation, in-character. *(Rejected: timed snooze — unnecessary complexity;
separate `/callbacks` top-level command — worse discoverability; new table — overkill for one
boolean.)*

**D-04 (Callback voice & shape): a Gemini-framed sarcastic callback reusing the ambient
recall→prompt→priority-2 path, posted as a REPLY to the triggering message, with
`AllowedMentions.none()` and a guaranteed template fallback.**
- Gemini-framed, not verbatim. Reuse the existing `_generate_ambient_roast` machinery
  (`cogs/events.py:87-172`): recall the author's memory → feed `build_chat_prompt(...,
  memories=...)` → priority-2 Gemini → enforce lowercase/length → template fallback on
  rate-limit/error. Do NOT invent a second recall path.
- Reply to the triggering message (not a standalone drive-by post) so the callback is visibly
  anchored to the active moment. Planner discretion on `message.reply` vs
  channel-send-with-context.
- `AllowedMentions.none()` — reference the user by display name, never ping.
- Accuracy firewall preserved — the callback references the episodic memory; any hard number
  still comes from live SQL, never embedded text.

### Claude's / Planner's Discretion (do NOT re-ask the user)

- Pure-logic gate seam — strongly indicated: a new `logic/proactive.py` with a keyword-only,
  `random`/`datetime`/`discord`-free gate function (e.g. `should_fire_proactive_callback(*,
  opted_out, chance_roll, chance, daily_count, daily_cap) -> bool`) mirroring
  `logic/roasts.py::decide_ambient_roast`. The `on_message` glue computes the rolls/counts and
  dispatches on the result; the recall-floor check stays in glue (it's async I/O). Lock it under
  mock-free tests.
- Exact numeric knob values — `PROACTIVE_CALLBACK_CHANCE`, `PROACTIVE_CALLBACK_DAILY_CAP` (and
  any per-user cooldown if the planner wants belt-and-suspenders on top of the daily cap).
- Daily-counter storage mechanism — in-memory dict vs reusing an existing daily-stats structure;
  either is fine (durability not required, D-02).
- Cog placement of the trigger glue — fold into `EventsCog.on_message` (alongside
  `_handle_message_reactions`) vs a small dedicated method; lean toward reusing `EventsCog`.
- Opt-out flag read path — a small `database.py` getter/setter for `proactive_opt_out`
  (mirroring existing `user_profiles` helpers); wire the read into the `on_message` gate.

### Deferred Ideas (OUT OF SCOPE)

- Voice-join / return-from-absence as an additional proactive anchor — could be revisited if
  the chat anchor proves too rare in practice.
- Timed snooze ("pause for 24h") instead of an indefinite toggle.
- Per-guild proactive budget / rate shaping.
- Salience reinforcement so frequently-recalled memories surface differently → v1.4 (MEM-R1).
- Vision / multimodal roasting → Phase 17.
- Any polling loop or DM delivery for callbacks — **permanently out** (the "bot is watching me"
  failure mode).
- Embedding any SQL-known number — accuracy firewall, permanent.
- New memory `kind`, write path, table beyond the one opt-out flag, dependency, or limiter.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROACT-01 | A background surface occasionally volunteers a recalled memory at an active moment (anchored, never a poll, never a DM), gated behind `/memory forget` existing, firing rarer than 0.30–0.35 ambient rates, with an additive daily cap. | Confirmed `on_message` (cogs/events.py:347-364) as the D-01 anchor point; confirmed `_generate_ambient_roast` (cogs/events.py:87-172) as the reusable recall→Gemini→fallback pipeline; designed `logic/proactive.py::should_fire_proactive_callback` mirroring `decide_ambient_roast`'s gate-ordering; confirmed `config.UNPROMPTED_ROAST_CHANCE`=0.30 and `config.MEMORY_CALLBACK_CHANCE`=0.35 as the two rates the new chance must undercut; confirmed `services/memory.py::recall` silently returns `[]` below `MEMORY_SIMILARITY_FLOOR` (the D-02 step-4 silent-skip). |
| PROACT-02 | A user can opt out of proactive callbacks, distinct from full memory deletion. | Confirmed `user_profiles` schema + Phase 8 additive-column precedent (`ALTER TABLE bot_daily_stats ADD COLUMN IF NOT EXISTS total_errors`, database.py:171) as the pattern for `proactive_opt_out`; confirmed `cogs/memory.py`'s `/memory` `app_commands.Group` structure, self-scoping convention (`str(interaction.user.id)` only, no target param), and ephemeral-response pattern as the drop-in home for a `callbacks` subcommand; confirmed `database.delete_all_user_memories` only ever touches `user_memories`, never `user_profiles` — structurally proving the opt-out and forget are independent stores. |
</phase_requirements>

## Architectural Responsibility Map

This is a Discord bot (cog → service → pure-logic → database layering, not a web-tier
architecture), so the standard Browser/SSR/API/CDN/DB tiers are adapted to this codebase's
actual layers (see `CLAUDE.md` Project Structure).

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Trigger detection (is this message a qualifying active moment?) | Cog / Event Layer (`cogs/events.py::on_message`) | — | `on_message` is the only Discord Gateway event that fires per-chat-message; must live where the event arrives. |
| Gate math (opt-out / chance / daily-cap decision) | Pure Logic Layer (`logic/proactive.py`) | Cog Layer (computes the nondeterministic inputs) | Phase 10 convention: nondeterminism (random rolls, clock reads, DB-sourced opt-out flag, in-memory counter) computed in glue, passed as primitives to a pure, mock-free-testable function. |
| Memory recall (does a real memory clear the floor?) | Service Layer (`services/memory.py::recall`) | Database Layer (`database.search_memories`, pgvector ANN) | Recall is inherently async I/O (Gemini embed call + Postgres ANN query) — cannot be pure; already exists, reused as-is. |
| Callback text generation (Gemini-framed sarcasm + template fallback) | Cog Layer (`cogs/events.py::_generate_ambient_roast`, reused) | Service Layer (`services/gemini.py::GeminiService.chat`) | Already-built pipeline; D-04 mandates reuse, not a new generator. |
| Opt-out flag storage | Database Layer (`user_profiles.proactive_opt_out`) | — | One boolean column, additive `ALTER TABLE`, mirrors Phase 8's `total_errors` precedent exactly. |
| Opt-out flag read/write | Database Layer (`database.py` getter/setter) | Cog Layer (`cogs/memory.py` command, `cogs/events.py` gate read) | New thin `database.py` functions mirroring the existing `user_profiles` helper shape (e.g. `update_user_profile`). |
| Daily-cap counter | Cog Layer (in-memory `dict` on `EventsCog`, e.g. `self._proactive_daily_counts`) | — | Explicitly not durable per D-02; mirrors the existing `self._ambient_roast_times` per-cog dict pattern already on `EventsCog` (cogs/events.py:33). |
| Opt-out command surface | Cog Layer (`cogs/memory.py` `/memory callbacks` subcommand) | — | Existing `app_commands.Group`, existing self-scoping/ephemeral conventions — pure additive subcommand. |
| Message delivery (reply, mention suppression) | Cog Layer (`discord.Message.reply(..., allowed_mentions=...)`) | Discord Gateway/REST (discord.py) | `Message.reply` is the discord.py-provided reply-anchor primitive; `AllowedMentions.none()` mirrors every other ambient send in this codebase. |

## Standard Stack

No new libraries. This phase is 100% internal-codebase composition of already-shipped
dependencies (`discord.py`, `asyncpg`, `google-genai` via the existing `GeminiService`). Per
`.planning/REQUIREMENTS.md` Out of Scope table: *"Any new pip dependency ... is a smell"* — this
phase adds zero.

### Core (already installed, reused as-is)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `discord.py` | ≥2.3 (already pinned per CLAUDE.md) | `Message.reply()`, `AllowedMentions.none()`, `commands.Cog.listener()` on `on_message` | Already the bot's Discord layer; no alternative considered. |
| `asyncpg` | 0.31.0 (already pinned) | Additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` on `user_profiles`; boolean getter/setter | Already the bot's only DB driver. |
| `google-genai` (via `services/gemini.py::GeminiService`) | already wired | Priority-2 `chat()` call inside the reused `_generate_ambient_roast` | Zero new code path — this phase makes zero direct Gemini calls of its own. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-memory per-cog daily-cap dict | A new `bot_daily_stats`-style Postgres table keyed by `(user_id, date)` | Rejected by D-02 explicitly — durability is not required, and a DB round-trip on every qualifying message adds latency + Neon-pool pressure for a value that resets harmlessly on restart. |
| New boolean column on `user_profiles` | A separate `user_preferences` table | Rejected by D-03 explicitly — "overkill for one boolean"; mirrors the proven Phase 8 additive-column pattern. |

**Installation:** None — no new packages.

## Package Legitimacy Audit

**Not applicable.** This phase installs zero external packages (confirmed against
`.planning/REQUIREMENTS.md` Out of Scope: *"Any new pip dependency ... a new dep is a smell"*).
The Package Legitimacy Gate protocol is skipped per its own trigger condition ("whenever this
phase installs external packages").

## Architecture Patterns

### System Architecture Diagram

```
Discord Gateway
      │
      ▼
on_message(message)                                    [cogs/events.py:347]
      │
      ├─ author.bot? ──yes──► return (existing guard, unchanged)
      │
      ├─ feed message_buffer (existing, unchanged)
      │
      ├─ _handle_message_reactions(message) (existing, unchanged)
      │
      └─ NEW: proactive-callback gate
            │
            ├─ in designated channel? (config.DEXTER_CHANNEL_ID) ──no──► skip
            │
            ├─ read proactive_opt_out for author.id  ──► database.get_proactive_opt_out(pool, user_id)
            │
            ├─ chance_roll = random.random()
            ├─ daily_count = self._proactive_daily_counts.get(user_id, (today, 0))
            │
            ├─ logic.proactive.should_fire_proactive_callback(     [PURE — no I/O]
            │       opted_out=..., chance_roll=..., chance=config.PROACTIVE_CALLBACK_CHANCE,
            │       daily_count=..., daily_cap=config.PROACTIVE_CALLBACK_DAILY_CAP,
            │   ) ──False──► skip
            │
            ├─ True ──► amb_memories = await memory_service.recall(author_id, guild_id, anchor_text)
            │              │
            │              └─ [] (below floor) ──► skip, no fire (D-02 step 4 / Pitfall 8)
            │
            ├─ non-empty ──► line = await self._generate_ambient_roast(author, scenario, fallback_pool)
            │                       [REUSED WHOLESALE — cogs/events.py:87-172, unchanged]
            │
            ├─ increment daily counter for author.id
            │
            └─ await message.reply(line, allowed_mentions=discord.AllowedMentions.none(),
                                    mention_author=False)
```

A reader can trace the primary path top-to-bottom: a chat message in the designated channel
either exits early at any gate (opt-out, chance, cap, channel, recall floor) or produces exactly
one reply, using the same Gemini-first/template-fallback machinery every other ambient surface
already uses.

### Recommended Project Structure

```
logic/
├── roasts.py            # existing — decide_ambient_roast (the template this mirrors)
└── proactive.py          # NEW — should_fire_proactive_callback (pure, keyword-only)

cogs/
├── events.py             # MODIFIED — on_message gains the proactive gate; NO changes to
│                          #   _generate_ambient_roast itself (reused as-is)
└── memory.py              # MODIFIED — /memory group gains a `callbacks` subcommand

database.py                # MODIFIED — SCHEMA_SQL gains one ALTER TABLE; two new small
                           #   helpers (get/set proactive_opt_out)

config.py                  # MODIFIED — new "--- Phase 16: Proactive Memory Callbacks ---"
                           #   section, inserted after the Phase 14 block (before line 227
                           #   sanitize_database_url), holding PROACTIVE_CALLBACK_CHANCE,
                           #   PROACTIVE_CALLBACK_DAILY_CAP

tests/
├── test_proactive_logic.py       # NEW — mirrors test_roast_logic.py exactly
├── test_database_phase16.py      # NEW — mirrors test_database_phase15.py (static +
│                                  #   optional live-DB opt-out round-trip)
├── test_memory_command.py         # MODIFIED — add callbacks-toggle test cases
└── test_ambient_recall_cadence.py # MODIFIED — extend with a new proactive-rarer-than-
                                    #   ambient source-inspection assertion; existing tests
                                    #   stay green untouched (regression lock)
```

### Pattern 1: Pure-logic gate mirroring `decide_ambient_roast`

**What:** A keyword-only, side-effect-free function that takes pre-computed primitives (a chance
roll, an opt-out bool, a daily count) and returns a boolean fire/no-fire decision. No `random`,
`datetime`, or `discord` imports — the calling cog computes those and passes them in.

**When to use:** Any new ambient/ subject-to-random-firing decision in this codebase — this is
the Phase 10 convention (`logic/roasts.py`, `logic/health.py`, `logic/taste.py` all follow it).

**Example (recommended shape for `logic/proactive.py`):**
```python
# Source: mirrors logic/roasts.py::decide_ambient_roast (cogs/events.py caller pattern),
# read directly from this repo — HIGH confidence, verbatim internal convention.
from __future__ import annotations

import config


def should_fire_proactive_callback(
    *,
    opted_out: bool,
    chance_roll: float,
    daily_count: int,
    chance: float = config.PROACTIVE_CALLBACK_CHANCE,
    daily_cap: int = config.PROACTIVE_CALLBACK_DAILY_CAP,
) -> bool:
    """Decide whether a qualifying chat message should fire a proactive callback.

    Gate order (cheapest first, short-circuit — mirrors D-02's numbered steps):
      1. opted_out          -> False immediately (D-03 opt-out is absolute)
      2. chance_roll >= chance -> False (roll missed; `<` to proceed, same convention
         as decide_ambient_roast's chance gate)
      3. daily_count >= daily_cap -> False (additive per-user daily ceiling)
      4. else -> True (glue then attempts recall(); a [] recall is a SEPARATE silent-skip
         handled in the async cog layer, not here — recall requires I/O and cannot be pure)

    Args:
        opted_out:    Whether the author has run `/memory callbacks off`.
        chance_roll:  Pre-rolled float in [0, 1). Pass random.random() from glue.
        daily_count:  How many proactive callbacks have already fired for this user
                      today (in-memory counter, reset by date comparison in glue).
        chance:       Probability threshold (default config.PROACTIVE_CALLBACK_CHANCE).
        daily_cap:    Max callbacks per user per calendar day (default
                      config.PROACTIVE_CALLBACK_DAILY_CAP).

    Returns:
        True if the gate passes (glue should then attempt recall()); False otherwise.
    """
    if opted_out:
        return False
    if chance_roll >= chance:
        return False
    if daily_count >= daily_cap:
        return False
    return True
```

### Pattern 2: Reusing `_generate_ambient_roast` for a new caller

**What:** `_generate_ambient_roast(member, scenario, fallback_pool)` already does
recall→`build_chat_prompt`→priority-2 Gemini→lowercase/length-enforce→template-fallback. It is
called today from `on_voice_state_update` with `member` = the joining/leaving voice user. D-04
requires the proactive surface call the exact same method with `member` = the chat message's
author.

**When to use:** Exactly this phase — do not fork or duplicate the method.

**Example (verified against the live `cogs/events.py` signature, cogs/events.py:87-92):**
```python
# Source: cogs/events.py:87-172 (read directly, this session) — HIGH confidence.
line = await self._generate_ambient_roast(
    message.author,                                   # discord.Member, not discord.User —
                                                         # on_message in a guild text channel
                                                         # gives a Member (has .guild)
    "{name} is here and dexter has a thought",          # new scenario string — recall anchor
    roasts.PROACTIVE_CALLBACK_FALLBACKS,                 # NEW fallback pool (personality/roasts.py)
)
```

Note: `_generate_ambient_roast` internally re-rolls its OWN independent
`MEMORY_CALLBACK_CHANCE` recall gate (cogs/events.py:128,
`if random.random() < config.MEMORY_CALLBACK_CHANCE:`) — for the proactive surface this SECOND
roll must NOT gate the recall (the whole point of D-02 step 4 is "recall floor, not another
chance roll"). **This means the proactive caller cannot call `_generate_ambient_roast` completely
unmodified if the recall step inside it is itself chance-gated** — see Pitfall 1 below for the
resolution.

### Pattern 3: Additive boolean column + getter/setter (Phase 8 precedent)

**What:** `ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS proactive_opt_out BOOLEAN DEFAULT
false;` appended to `SCHEMA_SQL` (idempotent, safe to re-run — the whole file already relies on
this for every existing table/column).

**Example (verified against database.py:88-97, 171 — HIGH confidence, direct read):**
```sql
-- Source: database.py SCHEMA_SQL, mirrors line 171's exact precedent
-- (ALTER TABLE bot_daily_stats ADD COLUMN IF NOT EXISTS total_errors INTEGER DEFAULT 0;)
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS proactive_opt_out BOOLEAN DEFAULT false;
```

```python
# Source: mirrors database.py::update_user_profile shape (database.py:297-310) — HIGH confidence.
async def set_proactive_opt_out(pool: asyncpg.Pool, *, user_id: str, opted_out: bool) -> None:
    """Set or clear the proactive-callback opt-out flag for a user (PROACT-02).

    Touches ONLY user_profiles — never user_memories. This is the structural guarantee
    that opting out is distinct from /memory forget (D-03).
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_profiles (user_id, username, proactive_opt_out)"
            " VALUES ($1, $2, $3)"
            " ON CONFLICT (user_id) DO UPDATE SET proactive_opt_out = EXCLUDED.proactive_opt_out",
            user_id, "unknown", opted_out,
        )
        # NOTE: see Pitfall 3 below re: the username column's NOT NULL constraint on
        # first-insert for a user who has never triggered update_user_profile() before.


async def get_proactive_opt_out(pool: asyncpg.Pool, user_id: str) -> bool:
    """Return True if the user has paused proactive callbacks. Defaults to False (opted-in)
    when the user has no profile row at all — matches D-03's "default opted-in" semantics."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT proactive_opt_out FROM user_profiles WHERE user_id = $1", user_id
        )
    return bool(row["proactive_opt_out"]) if row else False
```

### Pattern 4: `/memory callbacks` subcommand (mirrors existing `/memory` group shape)

**Example (verified against cogs/memory.py:224-289 — HIGH confidence, direct read):**
```python
# Source: mirrors cogs/memory.py's existing view/forget subcommand shape.
@memory.command(name="callbacks", description="Pause or resume Dexter's occasional unprompted callbacks")
@app_commands.describe(setting="on to resume, off to pause")
@app_commands.choices(setting=[
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
])
async def memory_callbacks(
    self, interaction: discord.Interaction, setting: app_commands.Choice[str]
) -> None:
    """/memory callbacks on|off — self-scoped only (str(interaction.user.id))."""
    user_id = str(interaction.user.id)
    opted_out = setting.value == "off"
    await database.set_proactive_opt_out(self.bot.pool, user_id=user_id, opted_out=opted_out)
    if opted_out:
        msg = "fine, i'll keep my mouth shut. your memories are still here though."
    else:
        msg = "back on. don't say i didn't warn you."
    await interaction.response.send_message(msg, ephemeral=True)
```

### Anti-Patterns to Avoid

- **Writing a second recall/Gemini pipeline for the proactive surface** — D-04 explicitly
  forbids this; reuse `_generate_ambient_roast`.
- **Gating the daily-cap counter behind a Postgres write** — D-02 explicitly allows (and the
  research recommends) an in-memory dict; a DB round-trip on every qualifying chat message in
  the designated channel is unnecessary load for a value with no durability requirement.
- **Checking `message.author.bot` AFTER the proactive gate instead of before** — the existing
  `on_message` guard at the very top (`if message.author.bot: return`) already covers this; the
  new gate must be added AFTER that guard, never duplicate the check.
- **Using `channel.send()` instead of `message.reply()`** — D-04 requires the reply-anchor
  specifically for the "responding to you being here" framing; a bare `channel.send()` loses
  that visible anchor.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Sarcastic-but-safe callback generation | A new prompt template + Gemini call path | `EventsCog._generate_ambient_roast` (existing) | Already handles priority-2 rate limiting, lowercase/length enforcement, and guaranteed template fallback — a second implementation would drift and double the surface area to keep in sync with personality rules. |
| Recall relevance thresholding | A custom similarity cutoff for the proactive surface | `services/memory.py::recall()` + `config.MEMORY_SIMILARITY_FLOOR` (existing, 0.70) | Already the single source of truth for "no memory beats a wrong memory" (Pitfall 8, 11-RESEARCH.md); a separate proactive-only floor would create two Pitfall-8 policies to maintain. |
| Day-boundary detection for the daily cap | Manual UTC midnight math | `datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).date().isoformat()` (existing pattern, cogs/events.py:206-208) | The codebase has a documented, scar-tested gotcha (CLAUDE.md Phases 4-5 gotchas, D-06/D-17) that naive `datetime.now()` fires community-time logic on the wrong calendar day on a UTC host — the `ZoneInfo(config.STREAK_TIMEZONE)` pattern is already used for exactly this in `on_voice_state_update`. |

**Key insight:** Every piece of machinery this phase needs already exists in the codebase from
Phases 3, 8, 10, 11, and 15. The entire implementation surface is new *composition*, not new
*capability* — which is exactly what an "anti-creepy discipline is the deliverable" phase should
look like: the risk is in getting the gate ORDER and the reuse-not-duplicate discipline right,
not in building anything novel.

## Common Pitfalls

### Pitfall 1: `_generate_ambient_roast`'s internal recall roll double-gates the recall

**What goes wrong:** `_generate_ambient_roast` (cogs/events.py:127-138) contains its OWN
`if random.random() < config.MEMORY_CALLBACK_CHANCE:` gate around the recall call. If the
proactive glue calls `_generate_ambient_roast` unmodified, the D-02 step-4 "recall floor" gate
becomes a THIRD, undocumented probability gate (in addition to `PROACTIVE_CALLBACK_CHANCE` and
the daily cap) — most proactive-eligible messages would silently produce a **memory-less**
template-fallback line instead of skipping entirely, which is the opposite of D-02's intent
("only fire if recall() actually returns a memory clearing the floor... No memory → silently
skip").

**Why it happens:** `_generate_ambient_roast` was designed as a *self-contained* roast generator
for voice events, where "no memory" is an acceptable fallback (the roast still makes sense
without a callback). The proactive surface's entire premise is different: no memory means no
fire at all, not a memory-less roast.

**How to avoid:** The planner has two clean options, both compatible with D-04's "reuse
wholesale, no second recall path":
  - **Option A (recommended):** Perform recall in the `on_message` glue FIRST (calling
    `memory_service.recall(...)` directly, exactly as `_generate_ambient_roast` does
    internally), check for `[]` there (D-02 step 4), and only THEN call
    `_generate_ambient_roast` — but this still hits the internal `MEMORY_CALLBACK_CHANCE` gate a
    second time inside the helper, which may skip re-recalling (fine, wasted call) OR — if the
    roll fails — build the prompt with `memories=None` even though a real memory was found,
    silently dropping it. This still isn't right.
  - **Option B (cleaner):** Extract a **new small parameter** on `_generate_ambient_roast`, e.g.
    `pre_recalled_memories: list[str] | None = None`, that when provided (non-`None`) skips the
    internal `MEMORY_CALLBACK_CHANCE` roll and internal recall call entirely, using the passed-in
    memories directly. This is a minimal, backward-compatible signature change (default `None`
    preserves the exact existing behavior for the two voice-event call sites — byte-identical,
    zero regression risk) and lets the proactive glue do its own D-02-step-4 recall+floor check
    once, then hand the result straight through. **This is the recommended fix** — it keeps
    "one recall path, one Gemini pipeline" (D-04's letter and spirit) while giving the proactive
    surface the exact gate semantics D-02 specifies.

**Warning signs:** If `tests/test_ambient_recall_cadence.py`'s existing
`test_ambient_surfaces_retain_gate` (asserting `"MEMORY_CALLBACK_CHANCE" in events_src` for
`_generate_ambient_roast`) starts failing after the Phase 16 edit, the internal gate was removed
entirely instead of made conditionally-bypassable — that test must stay green (the voice-event
call sites still need the internal gate).

### Pitfall 2: `message.author` in `on_message` is a `discord.Member`, but only inside a guild

**What goes wrong:** `_generate_ambient_roast`'s type hint is `member: discord.Member` and it
calls `member.guild.id` internally (cogs/events.py:134, `str(member.guild.id)`). If the
designated channel check is skipped or DMs somehow reach `on_message`, `message.author` could be
a `discord.User` (no `.guild` attribute) and the call would raise `AttributeError`.

**Why it happens:** discord.py's `on_message` fires for both guild messages and DMs; the
existing bot-author guard doesn't distinguish.

**How to avoid:** The designated-channel gate (`config.DEXTER_CHANNEL_ID`, always a guild text
channel) inherently filters out DMs before the proactive logic ever runs — as long as the new
gate is placed AFTER a `message.guild is not None` / channel-ID-match check (which it must be,
since `_get_ambient_channel` resolution requires a `discord.Guild`), this is a non-issue. Just
don't reorder the gate before the channel check.

**Warning signs:** A crash log showing `AttributeError: 'User' object has no attribute 'guild'`
from inside `_generate_ambient_roast`.

### Pitfall 3: First-ever `set_proactive_opt_out` call for a brand-new user hits `username NOT
NULL`

**What goes wrong:** `user_profiles.username` is `NOT NULL` (database.py:90). If a user runs
`/memory callbacks off` before ever queuing a song (i.e., before `update_user_profile()` has
ever run an `INSERT`), a naive `UPDATE user_profiles SET proactive_opt_out = $1 WHERE user_id =
$2` is a no-op (0 rows affected, silently "succeeds" but doesn't persist) unless the setter uses
an `INSERT ... ON CONFLICT DO UPDATE` shape like `update_user_profile` does.

**Why it happens:** `user_profiles` rows are lazily created on first song-queue, not on first
bot interaction — a user could plausibly run `/memory` commands (which have no such
prerequisite, per `cogs/memory.py`'s design) before ever playing music.

**How to avoid:** Use the `INSERT ... ON CONFLICT (user_id) DO UPDATE SET proactive_opt_out =
EXCLUDED.proactive_opt_out` shape shown in Pattern 3 above (mirrors `update_user_profile`'s own
upsert shape at database.py:297-310), providing a placeholder `username` (e.g.
`interaction.user.display_name`, readily available from the command context — better than a
literal `"unknown"` placeholder) for the insert branch.

**Warning signs:** A live-DB integration test asserting "opt-out persists for a user with zero
prior `song_history`" is the direct regression guard for this.

### Pitfall 4: The daily-cap dict grows unbounded across a long-running process

**What goes wrong:** `self._proactive_daily_counts: dict[str, tuple[str, int]]` never evicts old
entries — every distinct user who ever triggers the gate check gets a permanent dict entry for
the process lifetime (bot restarts periodically per CLAUDE.md's on-demand-PC hosting model, so
this is bounded in practice, but worth noting).

**Why it happens:** Mirrors the existing `self._ambient_roast_times: dict[int, float]`
(cogs/events.py:33) which has the same characteristic and has shipped since Phase 3 without
issue — the existing precedent already accepts this tradeoff.

**How to avoid:** Not a blocking concern given the existing precedent and the bot's actual
uptime profile (residential-PC, restarts common); the planner does not need to add eviction
logic — but the value stored per user is `(date_str, int)`, trivially small, so even an
unbounded dict poses negligible memory risk at this server's scale (single/few guilds).

**Warning signs:** None expected; documented for completeness per the "honest reporting"
research discipline, not because it's an actual blocker.

## Code Examples

### Full `on_message` gate glue (recommended shape, composing Patterns 1-4 + Pitfall 1's Option B fix)

```python
# Source: composed from cogs/events.py (existing on_message, _generate_ambient_roast,
# _get_ambient_channel — all read directly this session) + logic/proactive.py (new, Pattern 1).
# HIGH confidence — every referenced symbol/line verified against the live file.

@commands.Cog.listener()
async def on_message(self, message: discord.Message) -> None:
    if message.author.bot:
        return

    if hasattr(self.bot, "message_buffer"):
        self.bot.message_buffer.add(
            channel_id=message.channel.id,
            role="user",
            author=message.author.display_name,
            author_id=str(message.author.id),
            content=message.content,
        )

    await self._handle_message_reactions(message)

    # NEW: D-01 proactive-callback anchor point
    if message.guild is not None and config.DEXTER_CHANNEL_ID and message.channel.id == config.DEXTER_CHANNEL_ID:
        await self._maybe_fire_proactive_callback(message)


async def _maybe_fire_proactive_callback(self, message: discord.Message) -> None:
    """D-01/D-02/D-04: the rarest cadence — a chat-anchored, opt-out-able memory callback."""
    user_id = str(message.author.id)

    opted_out = await database.get_proactive_opt_out(self.bot.pool, user_id)

    import datetime as _dt
    from zoneinfo import ZoneInfo as _ZoneInfo
    today = _dt.datetime.now(tz=_ZoneInfo(config.STREAK_TIMEZONE)).date().isoformat()
    last_date, count = self._proactive_daily_counts.get(user_id, (today, 0))
    daily_count = count if last_date == today else 0

    should_attempt = should_fire_proactive_callback(
        opted_out=opted_out,
        chance_roll=random.random(),
        daily_count=daily_count,
    )
    if not should_attempt:
        return

    memory_service = getattr(self.bot, "memory_service", None)
    if memory_service is None:
        return
    memories = await memory_service.recall(
        user_id, str(message.guild.id), "a proactive callback moment"
    )
    if not memories:
        return  # D-02 step 4 / Pitfall 8 — no memory beats a wrong memory

    line = await self._generate_ambient_roast(
        message.author,
        "{name} is here and dexter has a thought",
        roasts.PROACTIVE_CALLBACK_FALLBACKS,
        pre_recalled_memories=memories,   # Pitfall 1 Option B — bypasses the internal gate
    )

    try:
        await message.reply(
            line, allowed_mentions=discord.AllowedMentions.none(), mention_author=False
        )
        self._proactive_daily_counts[user_id] = (today, daily_count + 1)
    except discord.HTTPException:
        pass
```

## State of the Art

Not applicable in the "external ecosystem changed" sense — this is 100% internal-codebase
composition. The only relevant "state of the art" note is that this phase is the **third**
ambient cadence layered on top of two proven ones (voice-join/leave at 0.30, notable-event
memory-callback at 0.35), and the codebase's own Phase 10/11/15 history is the evolution to
track: Phase 10 established the pure-`logic/` seam, Phase 11 established the recall/Gemini
pipeline this phase reuses, Phase 15 established the `/memory` command home and the
"forget-must-ship-first" trust ordering this phase's hard dependency satisfies.

**Deprecated/outdated:** N/A — no prior proactive-callback implementation exists to deprecate.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `PROACTIVE_CALLBACK_CHANCE` ≈ 0.08–0.12 and `PROACTIVE_CALLBACK_DAILY_CAP` = 1 are reasonable starting values | Standard Stack / Pattern 1 | Low — CONTEXT.md explicitly marks these as Claude's-suggested, planner/numeric discretion, tunable; not a factual claim requiring verification, just a starting point. |
| A2 | Option B (a new `pre_recalled_memories` param on `_generate_ambient_roast`) is the cleanest fix for Pitfall 1, vs. Option A or a third alternative | Pitfall 1 | Medium — this is a genuine design call the planner must confirm/adjust; if the planner picks a different resolution, the exact diff shape to `_generate_ambient_roast`'s signature changes, but the underlying gate-ordering requirement (D-02 step 4) does not. |

**If this table is empty:** N/A — see above; both entries are recommendations/starting values
explicitly invited by CONTEXT.md's discretion language, not unverified factual claims about
external systems.

## Open Questions

1. **How exactly should `_generate_ambient_roast` be modified to avoid double-gating the recall
   (Pitfall 1)?**
   - What we know: the internal `MEMORY_CALLBACK_CHANCE` gate must stay untouched for the two
     existing voice-event call sites (locked by `tests/test_ambient_recall_cadence.py`'s
     `test_ambient_surfaces_retain_gate`); the proactive surface needs a way to hand in an
     already-recalled, already-floor-checked memory list without re-rolling or re-querying.
   - What's unclear: whether the planner prefers a new optional parameter (Option B, this
     research's recommendation) or a small helper extraction (e.g. splitting
     `_generate_ambient_roast` into `_recall_for_roast` + `_generate_roast_text`, with the
     proactive glue calling only the latter).
   - Recommendation: Option B (new `pre_recalled_memories: list[str] | None = None` parameter,
     default preserves existing behavior byte-identical) — smallest diff, lowest regression
     risk, keeps the single-function "reuse wholesale" spirit of D-04 while giving the caller
     control over whether internal recall runs.

2. **Should the daily-cap counter be a plain dict or should it reuse `self._ambient_roast_times`'s
   existing dict-of-cooldowns shape for consistency?**
   - What we know: `EventsCog` already has one per-cog in-memory dict
     (`self._ambient_roast_times: dict[int, float]`, cogs/events.py:33) for a conceptually
     similar per-user ambient-timing concern.
   - What's unclear: whether the planner wants a second, differently-shaped dict
     (`dict[str, tuple[str, int]]` for date+count) or would prefer folding the daily-cap concern
     into a single richer per-user state dict.
   - Recommendation: a second, purpose-specific dict is simpler to read and test in isolation;
     the existing `_ambient_roast_times` dict is keyed by `int` (Discord snowflake as int) while
     `recall()`/`database` calls use `str(user.id)` everywhere else in the codebase — a new dict
     keyed by `str` for consistency with the rest of the memory-surface code is preferable to
     reusing the `int`-keyed dict's convention.

## Environment Availability

No new external dependencies. This phase composes only already-available, already-verified
infrastructure:

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (Neon) | `user_profiles.proactive_opt_out` column + getter/setter | ✓ (already wired, Phase 4/5) | 16 (Neon) | — |
| `discord.py` `Message.reply` | D-04 reply-anchor | ✓ (already pinned ≥2.3) | — | — |
| `GeminiService.chat` (priority-2) | Reused inside `_generate_ambient_roast` | ✓ (already wired, Phase 2/9) | — | Template fallback pool already guaranteed by the existing helper. |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None — everything this phase needs already ships in the
codebase.

## Validation Architecture

`.planning/config.json` has no `workflow.nyquist_validation` key set — absent means enabled per
the mandatory-initial-read convention, so this section is included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` + `pytest-asyncio` (already in `requirements.txt`; no version pin visible, matches Phase 9-15 convention of `@pytest.mark.asyncio` explicit decoration — strict mode, not `asyncio_mode = auto`) |
| Config file | none — no `pytest.ini`/`pyproject.toml` found; tests self-mark with `@pytest.mark.asyncio` |
| Quick run command | `pytest tests/test_proactive_logic.py tests/test_database_phase16.py tests/test_memory_command.py tests/test_ambient_recall_cadence.py -x` |
| Full suite command | `pytest -x` (mirrors STATE.md's "suite 781 pass/0 fail" full-run convention from Phase 15) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|-------------|
| PROACT-01 | `should_fire_proactive_callback` gate math: opt-out short-circuits, chance-roll boundary (`<` not `<=`, mirrors `decide_ambient_roast`'s convention), daily-cap boundary (`>=` fails, mirrors `cooldown_elapsed`'s inclusive-boundary style but inverted for a ceiling) | unit (pure, mock-free) | `pytest tests/test_proactive_logic.py -x` | ❌ Wave 0 |
| PROACT-01 | New chance strictly below `MEMORY_CALLBACK_CHANCE` (0.35) and `UNPROMPTED_ROAST_CHANCE` (0.30) — a config-level invariant, not a runtime behavior | unit (source/value inspection) | `pytest tests/test_proactive_logic.py -k rarer_than_ambient -x` | ❌ Wave 0 |
| PROACT-01 | Ambient 0.35 `MEMORY_CALLBACK_CHANCE` gate inside `_generate_ambient_roast` stays intact for the two existing voice-event call sites (regression lock — the byte-identical invariant Phase 15 established) | unit (source-inspection, existing test extended) | `pytest tests/test_ambient_recall_cadence.py -x` | ✅ (extend existing `test_ambient_surfaces_retain_gate`) |
| PROACT-01 | Recall-floor silent-skip: `recall()` returning `[]` produces zero Discord send, no exception | unit (behavioral, mocked `memory_service.recall`) | `pytest tests/test_proactive_events.py -k recall_floor -x` | ❌ Wave 0 |
| PROACT-01 | Reply is anchored (`message.reply`, not `channel.send`) with `allowed_mentions=discord.AllowedMentions.none()` | unit (behavioral, mocked `discord.Message`) | `pytest tests/test_proactive_events.py -k reply_anchor -x` | ❌ Wave 0 |
| PROACT-01 | Accuracy firewall: the proactive glue never calls a live-SQL numeric-stat helper (e.g. `get_user_summary`'s count fields) directly into the reply text outside the already-firewalled `_generate_ambient_roast` path | unit (source-inspection) | `pytest tests/test_proactive_events.py -k accuracy_firewall -x` | ❌ Wave 0 |
| PROACT-02 | Opt-out getter/setter touches ONLY `user_profiles`, never `user_memories` (structural proof of independence from `/memory forget`) | unit (source-inspection) | `pytest tests/test_database_phase16.py -k opt_out_scope -x` | ❌ Wave 0 |
| PROACT-02 | `/memory callbacks off` then `on` round-trips the flag; default (no prior row) reads as opted-in (`False`) | live-DB integration (optional, skips without `TEST_DATABASE_URL`) | `pytest tests/test_database_phase16.py -k opt_out_roundtrip -x` | ❌ Wave 0 |
| PROACT-02 | `/memory callbacks` subcommand is self-scoped (no `target` param), ephemeral response, in-character copy | unit (behavioral, mocked interaction, mirrors `test_memory_command.py`) | `pytest tests/test_memory_command.py -k callbacks -x` | ❌ Wave 0 (extend existing file) |
| PROACT-02 | Opting out does NOT delete/alter any `user_memories` row (zero-row-touched proof, distinct from `/memory forget`) | live-DB integration (optional) | `pytest tests/test_database_phase16.py -k zero_memories_touched -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_proactive_logic.py tests/test_database_phase16.py -x` (fast, pure + static-inspection only, no live DB needed)
- **Per wave merge:** `pytest -x` (full suite — mirrors Phase 13-15's gate discipline)
- **Phase gate:** Full suite green before `/gsd-verify-work`; live-DB opt-out round-trip test
  runs when `TEST_DATABASE_URL` is configured (mirrors `test_database_phase15.py`'s
  skip-without-live-DB convention — autonomous gate is `pytest --collect-only` exits 0).

### Wave 0 Gaps
- [ ] `tests/test_proactive_logic.py` — new file, mirrors `tests/test_roast_logic.py` exactly:
      full branch/boundary coverage for `should_fire_proactive_callback` (opt-out, chance
      boundary, daily-cap boundary, custom-threshold overrides) plus one config-value assertion
      that `config.PROACTIVE_CALLBACK_CHANCE < config.UNPROMPTED_ROAST_CHANCE` and `<
      config.MEMORY_CALLBACK_CHANCE`.
- [ ] `tests/test_database_phase16.py` — new file, mirrors `tests/test_database_phase15.py`'s
      two-tier shape (static source-inspection always-run + optional live-DB round-trip):
      structural signature guard on `set_proactive_opt_out`/`get_proactive_opt_out` (scoped to
      `user_profiles` only, single-identity + one boolean parameter, never touches
      `user_memories`), plus a live-DB test proving `off` → `get_proactive_opt_out == True` →
      `on` → `get_proactive_opt_out == False`, and a live-DB test proving `delete_all_user_memories`
      (Phase 15) never flips `proactive_opt_out` and vice versa.
- [ ] `tests/test_proactive_events.py` — new file, mirrors `tests/test_ambient_recall_cadence.py`'s
      mock style (`_make_bot`, mocked `discord.Message`/`discord.Member`): behavioral proof that
      the `on_message` glue (a) respects the designated-channel gate, (b) silently no-ops on an
      empty `recall()`, (c) calls `message.reply` (not `channel.send`) with
      `AllowedMentions.none()` when it does fire, (d) increments the daily counter only on an
      actual fire, not on a gate-skip.
- [ ] `tests/test_ambient_recall_cadence.py` — MODIFIED (not new): add one assertion that
      `_generate_ambient_roast`'s existing `MEMORY_CALLBACK_CHANCE` gate is still present
      (already covered by the existing `test_ambient_surfaces_retain_gate` — verify it still
      passes unmodified after the Pitfall-1 signature change) plus one new assertion locking
      that the new `pre_recalled_memories` parameter, when provided, bypasses the internal
      chance roll (proves Pitfall 1's fix is real, not cosmetic).
- [ ] `tests/test_memory_command.py` — MODIFIED (not new): add
      `test_memory_callbacks_off_then_on`, `test_memory_callbacks_is_self_scoped` (no `target`
      param, mirrors `test_memory_subcommands_have_no_target_param`'s existing structural-guard
      style), `test_memory_callbacks_response_ephemeral`.
- Framework install: none — `pytest`/`pytest-asyncio` already in `requirements.txt`.

## Security Domain

`.planning/config.json` has no `security_enforcement` key — absent means enabled per the
mandatory-initial-read convention, so this section is included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Delegated entirely to Discord's own OAuth/gateway auth; this phase adds no new auth surface. |
| V3 Session Management | No | No session concept in this codebase beyond Discord's own interaction tokens. |
| V4 Access Control | **Yes** | Self-scoping via `str(interaction.user.id)` only, no `target`/`user` parameter on `/memory callbacks` — mirrors the exact `T-15-08`/`T-15-09` structural pattern already proven in `cogs/memory.py`'s `view`/`forget` subcommands. The planner should add the same structural signature guard test (`test_memory_subcommands_have_no_target_param`-style) extended to cover `callbacks`. |
| V5 Input Validation | **Yes** | The `/memory callbacks` subcommand should use `app_commands.Choice`-constrained input (`"on"`/`"off"`, not free text) — see Pattern 4 — so there is no string-parsing surface to get wrong. The `on_message` gate itself takes no direct user input beyond message presence (recall's query text is a fixed literal, not user-message content, avoiding any prompt-injection-via-message-content concern for the recall query itself). |
| V6 Cryptography | No | No new secrets, tokens, or cryptographic material introduced. |

### Known Threat Patterns for this phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| A future edit accidentally adds a `target_id` parameter to `set_proactive_opt_out`/`get_proactive_opt_out`, letting one user toggle another's opt-out flag | Tampering / Elevation of Privilege | Structural signature guard test (mirrors `test_delete_all_user_memories_has_single_identity_param`, tests/test_database_phase15.py:95-107) asserting the parameter list is exactly `["pool", "user_id", "opted_out"]` (setter) / `["pool", "user_id"]` (getter) — fails immediately on any accidental second-identity-parameter addition. |
| A proactive callback surfaces a genuinely sensitive/PII-adjacent memory fact in a semi-public designated channel (not a DM, but still visible to everyone in that channel) | Information Disclosure | Already mitigated upstream at distill-time by `models/memory.py::is_sensitive()` (Phase 11's stop-ship backstop, unconditional — never exempted, unlike `contains_number()`) — every fact reaching `recall()` already passed this gate at write time. No new control needed in Phase 16; worth a one-line note in the plan so the reviewer knows this is inherited, not re-verified here. |
| Opt-out flag silently fails to persist for a user with no prior `user_profiles` row (Pitfall 3), giving a false sense of having paused callbacks | Tampering (silent data-integrity failure, not malicious but security-relevant since it's a trust control) | Use the `INSERT ... ON CONFLICT DO UPDATE` upsert shape (Pattern 3), not a bare `UPDATE`; cover with the live-DB round-trip test for a zero-prior-history user. |
| A malformed/edge-case message (e.g. from a webhook or an app-integration "user" that has `.bot == False` but no real `.guild`) reaches the proactive gate and crashes `on_message` | Denial of Service (crash of the event handler affects all subsequent Gateway event processing on that dispatch) | Guard on `message.guild is not None` before any proactive logic runs (Pitfall 2); the existing `_get_ambient_channel`/`config.DEXTER_CHANNEL_ID` channel-ID equality check already structurally requires a guild channel. |

## Sources

### Primary (HIGH confidence — direct repository reads, this session)
- `cogs/events.py` (full file, 368 lines) — `_generate_ambient_roast`, `on_message`,
  `_get_ambient_channel`, `on_voice_state_update`, all line numbers confirmed exactly matching
  CONTEXT.md's `canonical_refs` claims.
- `logic/roasts.py` (full file) — `decide_ambient_roast`, `cooldown_elapsed`, `RoastScenario`
  enum — the template `logic/proactive.py` mirrors.
- `tests/test_roast_logic.py` (full file) — mock-free test convention.
- `tests/test_ambient_recall_cadence.py` (full file) — regression-lock convention, mock style.
- `services/memory.py` (full file) — `recall`, `remember`, `distill`, `distill_and_remember`,
  `sweep` — confirmed `recall()`'s exact floor/degrade-to-`[]` behavior.
- `cogs/memory.py` (full file) — `/memory` group, `MemoryPageView`, `ForgetConfirmView`,
  self-scoping/ephemeral conventions.
- `database.py` (targeted reads: SCHEMA_SQL lines 80-193, `update_user_profile`/
  `increment_daily_stat` lines 280-334, `update_user_streak` lines 531-574, `list_user_memories`/
  `delete_all_user_memories` lines 1145-1210, `get_user_top_artist` lines 1460+).
- `models/user_profile.py` (full file) — `get_user_summary`.
- `config.py` (targeted reads: lines 1-70, 155-239) — exact `MEMORY_*`, `UNPROMPTED_ROAST_CHANCE`,
  `LATE_NIGHT_ROAST_CHANCE`, `AMBIENT_ROAST_CEILING_SECONDS`, `STREAK_TIMEZONE` values and the
  file's end-of-config insertion point (line 226, before `sanitize_database_url` at 227).
- `tests/test_database_phase15.py`, `tests/test_memory_command.py` (full/partial reads) — the
  two closest structural precedents for the new Phase 16 test files.
- `tests/conftest.py` — the `pool` fixture (asyncpg + `init_db`, skip-without-live-DB
  convention) the new live-DB tests will reuse.
- `.planning/phases/16-proactive-memory-callbacks/16-CONTEXT.md`,
  `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `CLAUDE.md`,
  `.planning/config.json` — all read in full this session.

### Secondary (CITED — Context7-fetched official docs)
- `discord.py` official docs (Context7 `/websites/discordpy_readthedocs_io_en`) — confirmed
  `allowed_mentions` is an accepted parameter on message-send/reply/edit paths across the
  library's `abc.Messageable`-derived surface; `Message.reply()` is the documented reply-anchor
  primitive (inherits the same `allowed_mentions`/`mention_author` kwargs as `channel.send`).

### Tertiary (LOW confidence)
- None — every claim in this document traces to either a direct repository read or a Context7
  documentation fetch this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, 100% internal composition, every referenced
  symbol read directly from the live repo.
- Architecture: HIGH — the diagram and patterns are built entirely from confirmed existing code
  paths; the one open design question (Pitfall 1's exact fix shape) is flagged honestly as an
  Open Question rather than asserted as settled.
- Pitfalls: HIGH — all four pitfalls derive from direct inspection of the actual
  `_generate_ambient_roast` source and the actual `user_profiles` schema constraints, not
  speculation.

**Research date:** 2026-07-03
**Valid until:** 30 days (stable internal codebase, no fast-moving external dependency in this
phase's scope) — but effectively valid until the next edit to `cogs/events.py`,
`services/memory.py`, or `database.py`'s `user_profiles` schema, whichever comes first.
