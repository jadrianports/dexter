# Phase 15: RAG Reach - Research

**Researched:** 2026-07-03
**Domain:** Wiring an already-shipped RAG memory substrate (Phase 11/13) into two existing
command surfaces (cadence-tune only) plus two genuinely new user-facing surfaces
(`/memory` view + `/memory forget`) on the same Postgres/pgvector store.
**Confidence:** HIGH

## Summary

This is the cheapest phase in the v1.3 milestone, and the research confirms why: RAG-01
and RAG-02 require a one-line deletion (remove the `if random.random() < MEMORY_CALLBACK_CHANCE:`
wrapper) at exactly two call sites in `cogs/ai.py` — the recall plumbing, prompt injection,
and byte-identical-fallback guarantee were all already built and verified in Phase 11. No new
service, no new table, no new dependency. The two ambient/notable-event surfaces
(`cogs/events.py:128`, `cogs/music.py:1272`) that must **keep** their gate are structurally
identical in shape to the two surfaces losing theirs, which makes an accidental over-removal
the single largest execution risk in this phase — mitigated by the fact that all four call
sites are easy to enumerate exhaustively (there are only four `recall()` callers in the whole
codebase today).

RAG-03 (`/memory` view) and RAG-04 (`/memory forget`) are genuinely new, but every piece they
need already exists as a reusable pattern in this codebase: `app_commands.Group` (`cogs/library.py`
`/jam`/`/playlist`), a paginated `discord.ui.View` (`cogs/music.py` `QueuePageView`/`LyricsPageView`),
a one-shot propose/confirm view with a finite timeout (`cogs/library.py` `JamSuggestConfirmView`),
and a scoped-DELETE-with-bound-params template (`database.py` `evict_lowest_salience`,
`delete_expired_memories`). The one real design decision this phase must make — and CONTEXT.md
correctly flags as an open question — is the retrieval shape for the view: `recall()` is an ANN
relevance search against a query anchor, not a "list everything" query, so a **new, dedicated DB
helper** is the right answer (detailed below), not a workaround using `recall()` with a broad anchor.

**Primary recommendation:** Remove the `MEMORY_CALLBACK_CHANCE` gate at exactly two call sites
(`cogs/ai.py:132`, `cogs/ai.py:210`), leave the other two call sites (`cogs/events.py:128`,
`cogs/music.py:1272`) byte-for-byte untouched, add a new `list_user_memories()` DB helper (plain
chronological/salience-ordered SELECT, no ANN) for `/memory view`, and add a new
`delete_all_user_memories()` DB helper (single-param `WHERE user_id = $1` DELETE) for
`/memory forget`, wired behind a `JamSuggestConfirmView`-style confirm button.

## Project Constraints (from CLAUDE.md)

- **Critical Rule 11:** Embeddings use the SEPARATE 60 RPM limiter — never the shared 15 RPM
  chat budget. Not touched by this phase (no new embed calls; `/memory view` and `/memory forget`
  are pure-SQL reads/deletes, zero Gemini calls).
- **Critical Rule 12 / accuracy firewall:** Hard numbers in output come from live SQL, never from
  embedded facts. `/memory view` shows verbatim stored fact *text* (D-02) — it must not compute or
  display any derived number from the facts themselves (e.g. do not say "you have 23 things about
  music taste" computed by grouping fact text — the COUNT for the forget-confirmation preview comes
  from `COUNT(*) FROM user_memories WHERE user_id=$1`, a live SQL call, which is already firewall-compliant).
- **`user_id`-scoped writes/deletes with bound `$N` params (T-11-04c):** every new DB helper in this
  phase must use `WHERE user_id = $1` with positional binding — never string interpolation, never a
  second user_id parameter that could be attacker-controlled from `/memory forget`'s command args
  (there must be no `target` argument on `/memory forget` — see Security Domain).
- **`logic/` is the pure-logic seam (D-02, Phase 9/10 convention):** any new decision logic (e.g.
  "should recall fire" for D-01, though D-01 mostly deletes an `if`) should not require a new pure
  function — the cadence removal is a straight-line deletion, not new branching logic worth
  extracting.
- **Fire-and-forget tasks route through `make_task`** (Critical Rule / Phase 9 convention) — not
  applicable here: `/memory view` and `/memory forget` are synchronous request/response command
  flows (defer → do work → followup.send), not fire-and-forget background writes.
- **Python 3.11+, discord.py >=2.3, asyncpg, pgvector on Neon** — all already in place; zero new
  dependency this phase (confirmed: no new pip package is needed for either RAG-03 or RAG-04).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-02 (LOCKED by user) — `/memory` view content & visibility:**
`/memory` shows the **verbatim stored fact strings** (the real ammo) wrapped in a short
**in-character Dex intro/outro** — NOT a Gemini-rewritten paraphrase. Rationale: this is a
**trust/transparency** surface — the user must see *exactly* what is stored (and therefore
exactly what `/memory forget` will erase). A paraphrase could distort or hide the actual rows,
defeating the escape-hatch purpose. The view is **read-only** and should be **ephemeral**
(visible only to the invoker). Empty state returns an in-character "i don't remember anything
about you yet" rather than an error.

### Claude's Recommendations (adopted on user's behalf — re-decidable)

**D-01 — Recall cadence for explicit `/roast` & `/ask` (RAG-01/RAG-02):**
Always ground the explicit commands. Remove the `MEMORY_CALLBACK_CHANCE` (0.35) random gate
from `/roast` and `/ask` **specifically** — these are deliberate, opted-in invocations. Rely on
`MEMORY_SIMILARITY_FLOOR` (0.70) as the real "when relevant" gate, and injected memories remain
candidate ammo the model may NOOP (Phase 11 D-06). **Keep the 0.35 random gate on the
*ambient/unprompted* surfaces only** — `cogs/events.py:128` and `cogs/music.py:1272`. RAG-02's
byte-identical guarantee is preserved: floor returns nothing → `memories=[] → None` → identical
prompt. *User asked to re-decide; revise if rare-callback feel is preferred even on explicit
commands.*

**D-03 — `/memory forget` granularity & safety (RAG-04):**
Nuke-all + confirm. `/memory forget` wipes **all** of the invoker's stored memories behind an
**ephemeral confirmation** (button) with a **count preview** ("i've got 23 things on you. wipe
them all? no takebacks."). New `delete_all_user_memories(pool, user_id)` DB helper, scoped
`WHERE user_id = $1`. Deleting the row deletes its `embedding` column in the same row (pgvector
stores the vector *in* the row — no separate index cleanup needed), so "rows and embeddings
verifiably gone" is inherent. Forget deletes the *memory vector store*, NOT `song_history` — the
Phase 14 taste-brain re-distills gracefully from untouched SQL on the existing schedule. *User
asked to re-decide; revise if selective/kind-aware forget is wanted in-phase.*

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **Command surface shape** — likely a `/memory` `app_commands.Group` with `view` + `forget`
  subcommands (mirrors `/jam`/`/playlist`). Cog placement (new `cogs/memory.py` vs folding into
  `cogs/ai.py`) is planner's call — lean a small new cog for cohesion. discord.py cannot have both
  a bare group invocation and subcommands, so bare-`/memory`-as-view is a naming nicety only.
- **View rendering detail** — lean minimal (facts + framing). Pagination may be needed for up to
  `MEMORY_MAX_PER_USER` (150) facts — reuse `QueuePageView`/`LyricsPageView`.
- **Confirmation UX specifics** (button labels, timeout) — planner discretion; follow the
  finite-timeout confirm-view pattern established by `/discover` (14-04) and `/jam suggest`
  (14-05), not a `setup_hook`-registered persistent view.

### Deferred Ideas (OUT OF SCOPE)

- Kind-aware / selective `/memory forget` (e.g. "keep my taste, drop the roast ammo," or forget a
  specific listed item) — deliberately deferred in favor of clean nuke-all (D-03). Layers on top
  of nuke-all later without rework.
- Owner/mod ability to forget *another* user's memory — out of scope; `/memory forget` is strictly
  self-scoped.
- Proactive unprompted memory callbacks + per-user opt-out → Phase 16 (hard-blocked on RAG-04
  shipping + being verified first — do not reorder).
- Vision / multimodal roasting → Phase 17.
- Any new memory `kind`, write path, dependency, table, or limiter (milestone tight-scope
  discipline; zero new infra).
- Embedding any SQL-known number (permanent anti-feature — accuracy firewall).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RAG-01 | `/roast @user` pulls the target user's recalled history (scoped to target's `user_id`, never invoker's) to ground the roast alongside the existing live SQL stat. | Already wired correctly at `cogs/ai.py:214` (`recall(str(target.id), ...)`). Only change needed: delete the `MEMORY_CALLBACK_CHANCE` gate at `cogs/ai.py:210`. See "Code Examples" and "Don't Hand-Roll" below. |
| RAG-02 | `/ask` incorporates the invoker's recalled memory via `build_chat_prompt(memories=...)`, byte-identical prompt when no memory clears the floor. | Already wired at `cogs/ai.py:136` (`recall(str(interaction.user.id), ...)`). Byte-identical guarantee already implemented in `personality/prompts.py::build_chat_prompt` (empty/None → `memory_context = ""`). Only change: delete the gate at `cogs/ai.py:132`. Existing `tests/test_prompts.py` (`test_memory_block_rendered_*`) already locks the byte-identical contract at the prompt-builder level. |
| RAG-03 | A `/memory` command lets a user view what Dexter remembers about them (in-character, read-only view). | New surface. Needs a new `list_user_memories()` DB helper (see Open Question 1 resolution below) + a new `cogs/memory.py` command group + reuse of `QueuePageView`/`LyricsPageView` pagination pattern. |
| RAG-04 | `/memory forget` deletes stored memories — rows and embeddings verifiably gone. | New surface. Needs a new `delete_all_user_memories()` DB helper (mirrors `evict_lowest_salience`'s scoped-delete template) + a `JamSuggestConfirmView`-style confirm button. Verified-deletion is proven by a new live-DB integration test (`remember → forget → recall == []`) — see Validation Architecture. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Recall-gate removal (RAG-01/RAG-02) | API / Backend (cog command handler) | — | Pure control-flow edit inside `cogs/ai.py`'s existing command coroutines; no new tier involved. |
| `/memory view` retrieval | Database / Storage (new SQL helper) | API / Backend (cog formats + paginates) | The "list everything" query is a plain scoped SELECT, not a service-layer concern — belongs next to the other `user_memories` helpers in `database.py`, called directly by the cog (mirrors how `cogs/library.py` calls `database.get_playlist` directly, no service layer). |
| `/memory view` pagination/rendering | API / Backend (Discord `discord.ui.View`) | — | Reuses `QueuePageView`/`LyricsPageView` — Discord-embed pagination is inherently a bot-process concern, not a DB or service concern. |
| `/memory forget` confirm + delete | API / Backend (cog + confirm view) | Database / Storage (new SQL helper) | The confirm/cancel UX lives in the cog (Discord interaction state); the actual DELETE is a one-line scoped SQL helper in `database.py`, mirroring `evict_lowest_salience`. |
| Memory embedding storage (unchanged) | Database / Storage (`pgvector` column) | — | Not modified this phase — confirms via the "verifiably gone" integration test that a row-DELETE removes the `embedding` column value inherently (pgvector stores it in-row, not in a separate index the app must clean). |

## Package Legitimacy Audit

Not applicable — this phase introduces zero new pip dependencies (confirmed against
`requirements.txt` and the milestone-wide "zero new dependency" constraint in REQUIREMENTS.md
Out of Scope table). No `slopcheck`/registry verification needed.

## Standard Stack

No new dependencies. This phase is 100% additive code against the already-installed stack:

| Library | Version (installed) | Purpose in this phase | Provenance |
|---------|---------------------|------------------------|------------|
| `discord.py` | >=2.3 (per CLAUDE.md) | `app_commands.Group`, `discord.ui.View`/`discord.ui.button`, ephemeral responses | `[VERIFIED: codebase]` — already imported and used identically in `cogs/library.py` |
| `asyncpg` | 0.31.0 (per CLAUDE.md) | New `list_user_memories`/`delete_all_user_memories` helpers, same pool/param-binding pattern as every existing `database.py` helper | `[VERIFIED: codebase]` |

**Installation:** none required.

## Architecture Patterns

### System Architecture Diagram

```
/roast @user  ─┐
/ask <q>      ─┤  (RAG-01/02: cadence gate REMOVED — recall always attempted)
               │
               ▼
     MemoryService.recall(user_id, guild_id, query_text)
               │
               ▼
     database.search_memories()  ── ANN cosine WHERE user_id=$1 ─┐
               │                                                   │
               ▼                                                   │
     apply_floor (0.70) → rerank → cap (MEMORY_INJECT_CAP)        │
               │                                                   │
               ▼                                                   │
     build_chat_prompt(..., memories=facts or None)  ← byte-identical
               │                                          when facts=[]
               ▼
     Gemini chat() → response to Discord

──────────────────────────────────────────────────────────────────

/memory (view)                          /memory forget
       │                                       │
       ▼                                       ▼
 database.list_user_memories()      count preview (COUNT(*) WHERE user_id=$1)
 (NEW — plain SELECT, no ANN,               │
  ORDER BY salience DESC,                    ▼
  created_at DESC, LIMIT 150)        JamSuggestConfirmView-style
       │                              confirm/cancel button
       ▼                                       │
 verbatim facts + Dex framing          [confirm pressed]
       │                                       ▼
       ▼                          database.delete_all_user_memories()
 QueuePageView/LyricsPageView-        (NEW — DELETE WHERE user_id=$1)
 style pagination if >1 page                   │
       │                                       ▼
       ▼                              ephemeral "wiped it all" response
 ephemeral response (never public)   (row + embedding gone in the same DELETE —
                                       pgvector stores embedding in-row)
```

### Recommended Project Structure

No new top-level modules beyond one new cog (planner's discretion whether `cogs/memory.py` or
folded into `cogs/ai.py`; this research recommends the new cog for cohesion + testability):

```
cogs/
├── ai.py            # RAG-01/RAG-02: delete two `if random.random() < ...` gates
├── events.py         # UNCHANGED — keeps gate at :128
├── music.py           # UNCHANGED — keeps gate at :1272
└── memory.py          # NEW (recommended) — /memory view + /memory forget
database.py            # + list_user_memories(), + delete_all_user_memories()
```

### Pattern 1: Cadence-gate removal (RAG-01/RAG-02)

**What:** Delete the `if random.random() < config.MEMORY_CALLBACK_CHANCE:` wrapper around the
existing `recall()` call, un-indenting the body by one level. Leave everything else — the
`_memory_svc = getattr(self.bot, "memory_service", None)` guard, the `try/except`, the
`memories or None` fallback into `build_chat_prompt` — completely untouched.

**When to use:** `cogs/ai.py:132` (`/ask`) and `cogs/ai.py:210` (`/roast`) ONLY.

**Example (current code, `/ask` at `cogs/ai.py:128-142`):**
```python
# Source: cogs/ai.py (this repo, current state)
memories: list[str] = []
if random.random() < config.MEMORY_CALLBACK_CHANCE:
    _memory_svc = getattr(self.bot, "memory_service", None)
    if _memory_svc is not None:
        try:
            memories = await _memory_svc.recall(
                str(interaction.user.id),
                str(interaction.guild_id),
                question,
            )
        except Exception as _mem_err:
            log.debug("memory.recall failed (non-fatal): %s", _mem_err)
```

**After (D-01 applied — gate deleted, body un-indented):**
```python
memories: list[str] = []
_memory_svc = getattr(self.bot, "memory_service", None)
if _memory_svc is not None:
    try:
        memories = await _memory_svc.recall(
            str(interaction.user.id),
            str(interaction.guild_id),
            question,
        )
    except Exception as _mem_err:
        log.debug("memory.recall failed (non-fatal): %s", _mem_err)
```

Apply the identical transformation at `cogs/ai.py:206-220` (`/roast`, recalling `str(target.id)`
— **not** `str(interaction.user.id)`; RAG-01 requires target-scoping, already correct today).

**Anti-pattern to avoid:** Do NOT touch `cogs/events.py:124-138` (`_generate_ambient_roast`) or
`cogs/music.py:1267-1282` (`_build_roast_line`) — these must retain the exact gate structure. A
find-and-replace across all four call sites (they are textually near-identical) is the most
likely accidental-scope-creep failure mode in this phase — treat this as an explicit code-review
checklist item, not an assumption.

### Pattern 2: `/memory view` retrieval — new dedicated "list all" helper, NOT `recall()`

**What:** `recall()` is fundamentally the wrong tool for `/memory view` — it embeds a query
anchor via a live Gemini call (an unnecessary API call for a pure "show me my rows" request),
applies a *relevance* floor that would silently hide low-similarity-to-anchor-but-real facts (the
opposite of the transparency goal — D-02 explicitly wants "exactly what is stored"), and caps at
`MEMORY_INJECT_CAP` (1-3), not the full `MEMORY_MAX_PER_USER` (150) a view needs to honestly
represent everything erasable by `/memory forget`.

**Recommendation:** Add a new `database.list_user_memories(pool, *, user_id, limit)` helper —
a plain SELECT, no ANN, no embedding call, no floor, ordered for a *display* purpose (most
notable/most recent first) rather than an *eviction* purpose (worst-first, which is what the
existing `get_user_memories_for_eviction` helper does — do not repurpose it; its ordering is
inverted for this use case and reusing it would either require re-sorting in Python or presenting
a confusing "worst memories first" view).

**Concrete SQL (bound `$N`, `WHERE user_id = $1`, matches the T-11-04c template):**
```python
# New helper in database.py, placed near get_user_memories_for_eviction (Phase 11 section)
async def list_user_memories(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    limit: int,
) -> list[asyncpg.Record]:
    """Return up to `limit` of a user's memory rows for the /memory view (RAG-03).

    Unlike search_memories (ANN relevance recall) this is a plain listing query:
    no embedding call, no similarity floor, no per-request cap tied to prompt
    injection budget. Ordered salience DESC, created_at DESC so the most
    notable / most recent facts surface first across pagination pages.

    Security (T-11-04c pattern): WHERE user_id = $1 — same cross-user guard as
    every other user_memories query. No caller may pass a different user's id
    (the /memory command never accepts a target-user argument).

    Args:
        pool:    asyncpg connection pool.
        user_id: Discord user ID — sole scope, always interaction.user.id.
        limit:   Row cap — use config.MEMORY_MAX_PER_USER (150) so a full view
                 can never silently truncate below what forget would erase.

    Returns:
        Rows with: id, fact, kind, salience, created_at. May be empty.
    """
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, fact, kind, salience, created_at"
            " FROM user_memories"
            " WHERE user_id = $1"
            " ORDER BY salience DESC, created_at DESC"
            " LIMIT $2",
            user_id, limit,
        )
```

**Pagination:** Chunk the returned rows client-side (e.g. 10 facts/page, mirroring
`LyricsPageView`'s `pages: list[str]` shape — pre-chunk into page strings before constructing
the view) and reuse the `LyricsPageView` Previous/Next button pattern rather than inventing a
new paginator. `LyricsPageView` is the closer template than `QueuePageView` because it already
takes pre-chunked `pages: list[str]` + a `title` rather than being coupled to a `MusicQueue`
object (`cogs/music.py:148-154` docstring explicitly notes this decoupling was intentional —
"avoids the QueuePageView coupling issue").

**Read-only + ephemeral (D-02):** `interaction.response.send_message(..., ephemeral=True)` for
the initial page; all button-driven page turns use `interaction.response.edit_message(...)`
(same pattern as `LyricsPageView.prev_button`/`next_button`) — no `allowed_mentions` concern here
since fact text is bot-distilled, not raw scraped lyrics, but consider `AllowedMentions.none()`
defense-in-depth anyway since fact text ultimately derives from banter that could theoretically
echo an `@mention`-shaped substring (low risk, cheap to add, matches `LyricsPageView`'s existing
posture).

### Pattern 3: `/memory forget` — count-preview confirm, then scoped nuke-all delete

**What:** A two-step interaction: (1) command handler fetches `COUNT(*) WHERE user_id=$1` (reuse
the existing `count_user_memories(pool, user_id)` helper — already built and tested in Phase 11,
no new helper needed for the count), builds the confirm message ("i've got {n} things on you.
wipe them all? no takebacks."), and sends an ephemeral message with a `discord.ui.View` carrying
Confirm/Cancel buttons (mirror `JamSuggestConfirmView`'s shape exactly: `_used` guard against
double-press, `on_timeout` disables buttons, buttons disabled immediately on press before the
async work runs). (2) The Confirm button's callback calls the new `delete_all_user_memories`
helper and edits the ephemeral message to the final "wiped" line.

**Concrete SQL for the new helper (mirrors `evict_lowest_salience`'s WHERE-only-user_id shape,
simpler since there's no `ids` array — the whole user's row set is the target):**
```python
# New helper in database.py, placed near evict_lowest_salience (Phase 11 section)
async def delete_all_user_memories(pool: asyncpg.Pool, user_id: str) -> int:
    """Hard-delete every user_memories row for user_id. Returns rows deleted.

    RAG-04 escape hatch (D-03 nuke-all). Scoped WHERE user_id = $1 — the ONLY
    filter, by design (T-11-04c pattern): a bug here can never touch another
    user's rows because there is no second parameter to get wrong. Deleting
    the row deletes its embedding column value in the same operation (pgvector
    stores the vector in-row, not in a separate structure the app must also
    clean) — "rows AND embeddings gone" is inherent to a single DELETE.

    Args:
        pool:    asyncpg connection pool.
        user_id: Discord user ID — sole scope. Always interaction.user.id;
                 /memory forget must never accept a target-user argument.

    Returns:
        Number of rows deleted (0 if the user had no stored memories).
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_memories WHERE user_id = $1",
            user_id,
        )
    # asyncpg returns "DELETE N"; mirrors delete_expired_memories's parsing idiom
    return int(result.split()[-1])
```

**Confirm-view skeleton (mirrors `cogs/library.py::JamSuggestConfirmView`, `:1179-1310`):**
```python
# New view in cogs/memory.py, following JamSuggestConfirmView's shape
class ForgetConfirmView(discord.ui.View):
    def __init__(self, bot, user_id: str, count: int, timeout: float = 60.0) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.user_id = user_id
        self.count = count
        self.message: discord.Message | None = None
        self._used = False

    @discord.ui.button(label="wipe it all", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction, button) -> None:
        if self._used:
            await interaction.response.send_message("already handled that.", ephemeral=True)
            return
        self._used = True
        for child in self.children:
            child.disabled = True
        await interaction.response.defer(ephemeral=True)
        deleted = await database.delete_all_user_memories(self.bot.pool, self.user_id)
        await interaction.followup.send(
            f"gone. all {deleted} of them. i've got nothing on you now.",
            ephemeral=True,
        )
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="never mind", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction, button) -> None:
        # mirrors JamSuggestConfirmView.cancel_button exactly
        ...

    async def on_timeout(self) -> None:
        # mirrors JamSuggestConfirmView.on_timeout exactly
        ...
```

Note the button style: `discord.ButtonStyle.danger` (red) for the destructive confirm action —
`JamSuggestConfirmView` uses `success` (green) for its confirm because adding tracks is
non-destructive; `/memory forget`'s confirm is the one irreversible action in this codebase's
confirm-view family and should look different.

**Empty-store edge case:** If `count_user_memories` returns 0, skip the confirm view entirely and
respond directly with an in-character "already got nothing on you" line — no point confirming a
no-op delete (mirrors D-02's empty-state handling for `/memory view`).

### Anti-Patterns to Avoid

- **Do NOT drive `/memory view` through `recall()` with a broad/generic anchor string.** This was
  explicitly flagged as an option in CONTEXT.md's Open Question 1 and researched here — it is the
  wrong choice. It burns an unnecessary embedding call (Critical Rule 11's separate limiter still
  costs quota), applies a similarity floor that can *hide real stored facts* from the one command
  whose entire purpose is showing them all, and caps at `MEMORY_INJECT_CAP` (1-3) instead of the
  full store. A relevance search is architecturally the wrong primitive for "list everything."
- **Do NOT reuse `get_user_memories_for_eviction`'s ordering for the view.** It is correctly
  worst-first for eviction decisions; presenting that ordering to a user as "here's what I
  remember" would show the least significant/most likely-to-be-forgotten facts first — the
  opposite of D-02's "here's the real dirt" framing.
- **Do NOT give `/memory forget` a `target` parameter, ever, even owner-only.** REQUIREMENTS.md
  and CONTEXT.md's Deferred Ideas both explicitly rule out mod/owner cross-user forget as
  out-of-scope; the DB helper's single-parameter signature (`user_id` only, no second ID) makes
  this structurally impossible to add by accident later without a deliberate signature change —
  preserve that shape.
- **Do NOT touch `cogs/events.py:128` or `cogs/music.py:1272`.** These are explicit regression
  targets (D-01) — CONTEXT.md and this research both call this out because the four `recall()`
  call sites are visually near-identical (copy-pasted originally from the same Phase 11 pattern),
  making an accidental blanket edit the most likely execution mistake in this phase.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Paginated Discord embed with Previous/Next | A new paginator class | `LyricsPageView` (`cogs/music.py:148`) — take `pages: list[str]` + `title`, same button/`on_timeout` shape | Already handles the coupling issue (pre-chunked pages, not tied to a domain object), already has the `AllowedMentions.none()` defense-in-depth precedent |
| Propose-then-confirm destructive action | A custom modal/confirmation flow | `JamSuggestConfirmView` (`cogs/library.py:1179`) — `_used` guard, disable-on-press, `on_timeout` disable, finite timeout, never `setup_hook`-registered | Already proven pattern for exactly this shape (propose → confirm/cancel → mutate state only inside Confirm) |
| Slash command group with subcommands | Manual subcommand routing inside one `@app_commands.command` | `app_commands.Group` (`cogs/library.py:460` `/playlist`, `:700` `/jam`) | discord.py's native mechanism; already used twice in this codebase for exactly this "verb group" shape |
| Scoped user-data DELETE | A raw `conn.execute` with string-formatted `user_id` | The `evict_lowest_salience`/`delete_expired_memories` template: bound `$N`, `WHERE user_id = $1`, no interpolation | T-11-04c cross-user guard convention; deviating risks reintroducing a cross-user delete bug class already closed out in Phase 11 |
| "Does this user have memories" count | A separate new COUNT helper | `count_user_memories(pool, user_id)` — already exists, already tested (`tests/test_database_phase11.py`) | Zero reason to duplicate an existing, correctly-scoped helper |

**Key insight:** Every piece of RAG-03/RAG-04 is a recombination of patterns this codebase
already has proven exactly once each (pagination, confirm-view, group command, scoped delete).
The risk in this phase is not "does the pattern exist" — it's "did you pick the right existing
pattern to clone" (e.g. `LyricsPageView` not `QueuePageView`; a new list-helper not `recall()`;
`evict_lowest_salience`'s shape not a hand-rolled DELETE).

## Common Pitfalls

### Pitfall 1: Accidentally removing the cadence gate from an ambient surface too

**What goes wrong:** `cogs/events.py:128` and `cogs/music.py:1272` are textually
near-identical to the two call sites that ARE supposed to lose their gate
(`cogs/ai.py:132`/`:210`) — same `if random.random() < config.MEMORY_CALLBACK_CHANCE:` line,
same `_memory_svc = getattr(...)` pattern, same `try/except` shape. An editor find-and-replace
across the codebase, or a well-intentioned "make this consistent everywhere" pass, silently
removes rarity from ambient roasts too — reintroducing Pitfall 3 from `.planning/research/PITFALLS.md`
(memory feels like it's "watching," not occasional).

**Why it happens:** All four call sites were written in the same Phase 11 plan and share a
copy-pasted shape; nothing in the code itself visually distinguishes "explicit command" from
"ambient trigger" at the point of the `if` statement.

**How to avoid:** Treat the 4-call-site enumeration as a checklist, not a search-and-replace:
edit `cogs/ai.py:132` and `cogs/ai.py:210` only; run a final grep for
`MEMORY_CALLBACK_CHANCE` across the repo after the change and confirm exactly two remaining
matches (`cogs/events.py` and `cogs/music.py`), not zero and not four.

**Warning signs:** `grep -rn MEMORY_CALLBACK_CHANCE cogs/` returns 0 or 4 matches instead of 2
after the edit.

### Pitfall 2: `/memory view` silently truncated below what `/memory forget` will erase

**What goes wrong:** If the view helper caps at a small number (e.g. accidentally reusing
`MEMORY_INJECT_CAP=3` instead of `MEMORY_MAX_PER_USER=150`), a user sees "3 things" but forget
deletes potentially 150 — the transparency promise (D-02: "the user must see exactly what is
stored ... and therefore exactly what `/memory forget` will erase") is broken by a config
constant mismatch, not a logic bug.

**How to avoid:** The new `list_user_memories` helper's `limit` argument must be called with
`config.MEMORY_MAX_PER_USER`, never `config.MEMORY_INJECT_CAP`. Add a one-line comment at the
call site cross-referencing this constraint so a future refactor doesn't quietly swap it.

**Warning signs:** A user with more than `MEMORY_INJECT_CAP` (3) stored memories sees fewer
facts in `/memory view` than actually exist in the table.

### Pitfall 3: Treating the DELETE as "soft" or forgetting to verify the embedding column is gone

**What goes wrong:** PITFALLS.md's Pitfall 6 (from the flagship v1.3 research) flags this
generally: a naive implementation might add a `deleted_at` tombstone column instead of a hard
DELETE, silently leaving the embedding (and therefore the memory's semantic content) still
present in the table and still theoretically recallable if any query forgot to filter tombstones.

**How to avoid:** `delete_all_user_memories` must be a real `DELETE FROM user_memories WHERE
user_id = $1` — no soft-delete flag, no `deleted_at` column (none exists in the schema; do not
add one). Confirm via the Success-Criterion-4 integration test (see Validation Architecture)
that runs an actual `recall()` afterward and asserts `[]`, not just that the DELETE statement ran.

**Warning signs:** A follow-up `/memory view` after `/memory forget` still shows old facts; a
follow-up `/ask`/`/roast` still surfaces old memory content.

### Pitfall 4: `/memory forget`'s stated scope overpromising ("erases everything Dexter knows")

**What goes wrong:** PITFALLS.md's Pitfall 6 also flags that a "forgotten" fact's substance can
resurface via a *derivative* memory — e.g., if Dex previously roasted the user about a fact and
that roast interaction itself got distilled into a new `daily_batch` memory, deleting the
original source fact doesn't touch the derivative one (both are just rows in the same table
today, so D-03's nuke-all actually DOES clear derivatives too — since it deletes every row for
the user, not a single targeted row). Confirm this is true for nuke-all specifically: unlike a
single-id `forget <id>` (explicitly deferred, not built this phase), nuke-all's blanket
`WHERE user_id = $1` has no derivative-memory gap, because it deletes the *entire* row set, not
one row.

**How to avoid:** State the command's scope accurately in the response/help text: "wipes
everything I've got on you — including anything I picked up from your listening history" (do NOT
promise it also stops future roasts from talking about you again — a fresh `daily_batch`/ambient
roast interaction next week will re-accumulate new memories, which is expected and by design,
mirroring how Phase 13's taste-brain "re-distills gracefully from untouched SQL"). Do not word the
confirmation message as if this is a permanent "never mention me again" toggle — that's
`PROACT-02`'s job in Phase 16, a distinct control.

**Warning signs:** User feedback interprets `/memory forget` as "stop roasting me forever" and is
surprised when new roasts eventually reference newly-formed memories weeks later.

### Pitfall 5: Forgetting the empty-store edge case shows a broken/awkward confirm view

**What goes wrong:** If `count_user_memories` returns 0 and the code still builds a confirm view
("i've got 0 things on you. wipe them all?"), the interaction feels broken/comedic-in-a-bad-way
rather than in-character.

**How to avoid:** Branch explicitly: `count == 0` → skip the confirm view, respond directly with
an in-character "already got nothing on you" line (mirrors D-02's empty-state handling for the
view command — both empty states should feel like the same voice).

**Warning signs:** A brand-new user (zero memories) runs `/memory forget` and gets a confirm
button for wiping zero rows.

## Code Examples

### `/memory view` command handler skeleton

```python
# Source: pattern derived from cogs/library.py::playlist_load + cogs/music.py::LyricsPageView
@memory.command(name="view", description="See what Dexter remembers about you")
async def memory_view(self, interaction: discord.Interaction) -> None:
    user_id = str(interaction.user.id)
    rows = await database.list_user_memories(
        self.bot.pool, user_id=user_id, limit=config.MEMORY_MAX_PER_USER
    )
    if not rows:
        await interaction.response.send_message(
            "i don't remember anything about you yet.", ephemeral=True
        )
        return

    facts = [row["fact"] for row in rows]
    # Pre-chunk into pages (e.g. 10 facts/page) before constructing the view —
    # mirrors LyricsPageView's pre-chunked pages: list[str] contract.
    pages = _chunk_facts_into_pages(facts, per_page=10)
    view = MemoryPageView(pages, title=f"{interaction.user.display_name}'s file")
    await interaction.response.send_message(
        "fine, here's what i've got on you.",
        embed=view._build_embed(),
        view=view,
        ephemeral=True,
    )
```

### Byte-identical prompt guarantee (already locked — reference only, no change needed)

```python
# Source: personality/prompts.py:163-172 (existing, unchanged by this phase)
if memories:
    memory_context = (
        "THINGS YOU REMEMBER ABOUT THIS USER (episodes/opinions, not stats):\n"
        + "\n".join(f"- {m}" for m in memories)
        + "\nUse at most one of these, and only if it genuinely lands."
          " Do NOT invent details beyond these lines."
          " All numbers/counts come from USER CONTEXT above — never from these memories.\n\n"
    )
else:
    memory_context = ""
```
This is the RAG-02 byte-identical guarantee. D-01's gate removal changes *how often* `memories`
is non-empty (always attempted instead of 35%-of-the-time attempted) but never changes this
function — `recall()` degrading to `[]` (rate-limit, no facts above floor, any error) still
produces `memory_context = ""` exactly as before.

## State of the Art

Not applicable in the traditional "library version bump" sense — this phase is entirely internal
architecture reuse. The one relevant "current vs. old approach" is intra-project:

| Old Approach (pre-Phase-15) | Current Approach (Phase 15) | When Changed | Impact |
|------------------------------|------------------------------|---------------|--------|
| `/ask`/`/roast` recall gated at 35% (`MEMORY_CALLBACK_CHANCE`) | `/ask`/`/roast` recall always attempted; ambient/notable-event surfaces keep the 35% gate | This phase (D-01) | Explicit commands feel reliably memory-aware; ambient surfaces retain "rarity hits harder" |
| No user-facing way to view or delete stored memories | `/memory view` (read) + `/memory forget` (nuke-all delete) | This phase (RAG-03/RAG-04) | Required trust escape hatch before Phase 16 (proactive callbacks) can ship |

**Deprecated/outdated:** None — no library deprecations relevant to this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A new `list_user_memories` DB helper (rather than driving `recall()` with a broad anchor) is the correct retrieval shape for `/memory view`. | Architecture Patterns / Pattern 2, Open Question 1 resolution | LOW — this is a reasoned recommendation resolving CONTEXT.md's explicitly flagged open question, not a verified external fact. If the planner/user prefers reusing `recall()` for consistency despite the tradeoffs, the view would need a much higher `MEMORY_TOP_K`/no-floor override and would still cost an embedding call per view — a straightforward, low-risk pivot if the recommendation is rejected. |
| A2 | `LyricsPageView` is the better pagination template to clone than `QueuePageView` for `/memory view`. | Architecture Patterns / Pattern 2 | LOW — both patterns exist in the same file with nearly identical button mechanics; picking the "wrong" one costs a small refactor, not a design failure. |
| A3 | `ButtonStyle.danger` (red) is the right visual treatment for the forget-confirm button, distinct from `JamSuggestConfirmView`'s `success` (green). | Architecture Patterns / Pattern 3 | COSMETIC ONLY — no functional risk; purely a UX polish recommendation. |
| A4 | Nuke-all forget's blanket `WHERE user_id = $1` has no derivative-memory gap (unlike a hypothetical single-id `forget <id>`), because it deletes the entire row set for the user. | Common Pitfalls / Pitfall 4 | LOW-MEDIUM — this is a logical deduction from the schema (single flat `user_memories` table, no foreign-key derivative tracking), not something independently verified against a live dataset. If a future kind ever writes memories keyed by *another* user's id while referencing this user (not observed anywhere in the current schema/codebase), the deduction would break. Confirmed correct for the schema as it exists today. |

**If this table is empty:** N/A — see entries above. All four are reasoning-based recommendations
built on verified codebase reads (HIGH confidence on the underlying code facts; the *recommendation*
layered on top is what's flagged ASSUMED-adjacent for planner/user visibility).

## Open Questions

### Open Question 1 (from CONTEXT.md) — RESOLVED

**Question:** `/memory` view retrieval shape + pagination — new "list all facts" DB helper vs.
driving `recall()` with a broad anchor + raised cap?

**Resolution:** New dedicated DB helper — `list_user_memories(pool, *, user_id, limit)`. See
"Architecture Patterns / Pattern 2" above for the full rationale and concrete SQL. Reject the
`recall()`-with-broad-anchor approach: it costs an unnecessary embedding call, applies a
relevance floor that can hide real stored facts (directly undermining D-02's transparency
promise), and caps at `MEMORY_INJECT_CAP` (1-3) rather than the full store. Pagination: reuse
`LyricsPageView`'s pre-chunked-`pages: list[str]` pattern (`cogs/music.py:148`), not
`QueuePageView`.

### Open Question 2 (from CONTEXT.md) — RESOLVED

**Question:** Cadence-change regression coverage (D-01) — confirm existing tests still assert
ambient surfaces keep the gate; specify the new explicit-command test.

**Resolution — the honest finding is there is currently NO existing test locking the
recall-cadence gate at any of the four call sites.** Verified by direct reads:

- `tests/test_roast_logic.py` tests `logic/roasts.py::decide_ambient_roast` — this is the
  *whether-to-roast-at-all* decision (probability + late-night + cooldown), a completely
  different gate from the *recall-cadence* gate (`MEMORY_CALLBACK_CHANCE`) inside
  `_generate_ambient_roast`/`_build_roast_line`. These are two separate `if` statements in two
  separate functions — `decide_ambient_roast` does not call `recall()` at all.
- `tests/test_roast_command.py` (the only existing test file that invokes `/roast`'s coroutine
  directly) mocks `cogs.ai.build_chat_prompt` entirely (`return_value="system prompt"`) and never
  inspects the `memories` kwarg passed to it, so it currently provides **zero** coverage of the
  `MEMORY_CALLBACK_CHANCE` gate's presence or absence.
- No test file greps for `MEMORY_CALLBACK_CHANCE` at all (`grep -rn MEMORY_CALLBACK_CHANCE tests/`
  returns nothing).

**This means Phase 15 must ADD new tests, not just adjust existing ones — there is no
pre-existing regression lock to preserve, only new coverage to write.** See Validation
Architecture below for the concrete test specification (deterministic via `patch("random.random",
return_value=0.99)` rather than statistical sampling, following this codebase's existing
`unittest.mock.patch` convention from `test_roast_command.py`).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`@pytest.mark.asyncio`) |
| Config file | none dedicated — repo-root `pytest.ini`/`pyproject.toml` equivalent not inspected; existing convention is directory-wide `pytest tests/` |
| Quick run command | `pytest tests/test_roast_command.py tests/test_ai_helpers.py tests/test_prompts.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RAG-01 | `/roast @user` recall now fires unconditionally (no 35% gate) and stays target-scoped | unit (mock-free-adjacent, mocks Discord/Gemini per `test_roast_command.py` convention) | `pytest tests/test_roast_command.py::test_roast_recall_always_fires -x` | ❌ Wave 0 |
| RAG-01 | `/roast` recall is scoped to `target.id`, never `interaction.user.id` | unit | `pytest tests/test_roast_command.py::test_roast_recall_scoped_to_target -x` | ❌ Wave 0 |
| RAG-02 | `/ask` recall now fires unconditionally (no 35% gate) | unit | `pytest tests/test_ai_helpers.py::test_ask_recall_always_fires -x` (or a new `tests/test_ask_command.py`, mirroring `test_roast_command.py`'s shape — no direct `/ask` command test file currently exists) | ❌ Wave 0 |
| RAG-02 | Byte-identical prompt when `recall()` returns `[]` | unit (already covered at the prompt-builder level) | `pytest tests/test_prompts.py -k memory_block -x` | ✅ (existing — confirm it still passes unchanged; no new test needed, this is the pre-existing lock D-01 must not break) |
| RAG-01/02 regression | Ambient surfaces (`cogs/events.py:128`, `cogs/music.py:1272`) KEEP their 35% gate | unit | `pytest tests/test_ambient_recall_cadence.py -x` (new file — no existing coverage per Open Question 2 finding) | ❌ Wave 0 |
| RAG-03 | `/memory view` shows verbatim facts, empty state is in-character, ephemeral | unit | `pytest tests/test_memory_command.py::test_memory_view_shows_verbatim_facts -x`, `::test_memory_view_empty_state -x`, `::test_memory_view_is_ephemeral -x` | ❌ Wave 0 |
| RAG-03 | `list_user_memories` scoped to `user_id`, ordered correctly, capped at `MEMORY_MAX_PER_USER` | unit (static source-inspection, mirrors `TestWriteHelpersExist` convention in `test_database_phase11.py`) + live-DB integration | `pytest tests/test_database_phase15.py -k list_user_memories -x` | ❌ Wave 0 |
| RAG-04 | `/memory forget` shows count preview, confirm/cancel/timeout all behave per `JamSuggestConfirmView` shape | unit | `pytest tests/test_memory_command.py::test_forget_confirm_flow -x` | ❌ Wave 0 |
| RAG-04 | **"Verifiably gone" — rows AND embeddings** (Success Criterion 4) | **live-DB integration** (requires `TEST_DATABASE_URL`, pgvector-enabled) | `pytest tests/test_database_phase15.py::test_remember_forget_recall_empty -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_memory_command.py tests/test_ambient_recall_cadence.py tests/test_prompts.py -x` (fast, mock-only, no live DB)
- **Per wave merge:** `pytest tests/ -x` (full suite; live-DB tests auto-skip if `TEST_DATABASE_URL` unset, matching every prior phase's convention)
- **Phase gate:** Full suite green before `/gsd-verify-work`; the Success Criterion 4 integration
  test MUST be run at least once against a real pgvector-enabled Postgres (Neon or local) before
  phase close — it is the load-bearing proof for RAG-04 and cannot be considered verified from
  the skipped-static-only run alone.

### Wave 0 Gaps

- [ ] `tests/test_ambient_recall_cadence.py` — NEW file. Covers the Open Question 2 finding: no
  existing test locks the `MEMORY_CALLBACK_CHANCE` gate anywhere. Recommended shape (deterministic,
  no statistical flakiness):
  ```python
  # Pattern: patch random.random to a fixed value ABOVE the 0.35 threshold.
  # Old-gate call sites (ambient) must NOT call recall(); new-gate-removed call
  # sites (/ask, /roast) MUST call recall() regardless of the patched value.
  with patch("cogs.events.random.random", return_value=0.99):
      # ... invoke _generate_ambient_roast(...) via its cog ...
      memory_service.recall.assert_not_called()

  with patch("cogs.music.random.random", return_value=0.99):
      # ... invoke _build_roast_line(...) ...
      memory_service.recall.assert_not_called()

  with patch("cogs.ai.random.random", return_value=0.99):
      # random is imported in cogs.ai but D-01 removes its use at these two
      # call sites — this test asserts recall() fires even when the (now
      # unused for this purpose) random value would have failed the old gate.
      await _invoke_ask(...)
      memory_service.recall.assert_called_once()
      await _invoke_roast(...)
      memory_service.recall.assert_called_once_with(str(target.id), ANY, ANY)
  ```
  Mirrors the `unittest.mock.patch` + `MagicMock`/`AsyncMock` bot-fixture convention already
  established in `tests/test_roast_command.py`.
- [ ] `tests/test_memory_command.py` — NEW file. Covers `/memory view` + `/memory forget` command
  handlers, following `tests/test_roast_command.py`'s fake-bot/fake-interaction helper convention
  (`_make_bot`, `_make_interaction`).
- [ ] `tests/test_database_phase15.py` — NEW file. Two halves, mirroring
  `tests/test_database_phase11.py`'s structure exactly:
  - `TestWriteHelpersExist`-style static class (no live DB needed): asserts
    `list_user_memories`/`delete_all_user_memories` exist, are `user_id`-scoped
    (`inspect.getsource` + substring assertions on `"user_id"`, `"$1"`), and
    `delete_all_user_memories` has no second ID parameter in its signature
    (`inspect.signature` check — enforces the "never accepts a target" constraint structurally).
  - Live-DB integration class (`@pytest.mark.skipif(_SKIP_LIVE, ...)`, reusing the `pool` fixture
    from `tests/conftest.py`): the Success Criterion 4 test —
    ```python
    @pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
    @pytest.mark.asyncio
    async def test_remember_forget_recall_empty(pool) -> None:
        """remember -> forget -> recall == [] (RAG-04 Success Criterion 4)."""
        user_id = "test-phase15-forget"
        embedding = [0.3] * config.EMBED_DIM
        expires_at = datetime.now(timezone.utc) + timedelta(days=90)

        await database.insert_memory(
            pool, user_id=user_id, guild_id=None, kind="daily_batch",
            fact="user only listens to sad indie at 2am",
            embedding=embedding, salience=0.3, expires_at=expires_at,
        )
        # Sanity: the fact is actually there before forgetting.
        before = await database.search_memories(
            pool, user_id=user_id, query_embedding=embedding, k=5
        )
        assert len(before) == 1

        deleted = await database.delete_all_user_memories(pool, user_id)
        assert deleted == 1

        after = await database.search_memories(
            pool, user_id=user_id, query_embedding=embedding, k=5
        )
        assert after == []   # rows AND embeddings verifiably gone
    ```
  This directly exercises the real DELETE against a real pgvector column and re-queries via the
  real ANN search path — the strongest available proof that "verifiably gone" holds, stronger
  than asserting on row-count alone.
- [ ] Framework install: none — pytest/pytest-asyncio already present and used identically across
  all four cited test-file conventions above.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | Discord interaction identity (`interaction.user.id`) is the trust boundary; no new auth surface introduced. |
| V3 Session Management | No | Not applicable — stateless slash-command interactions. |
| V4 Access Control | **Yes** | `/memory view` and `/memory forget` MUST scope exclusively to `str(interaction.user.id)` — no `target`/`user` command parameter may exist on either subcommand. This is the direct continuation of the T-11-03a/T-11-04c cross-user guard already established in Phase 11; this phase's only genuinely new access-control risk is a command author accidentally adding a convenience "mod can forget for a user" parameter, which REQUIREMENTS.md/CONTEXT.md both explicitly forbid. |
| V5 Input Validation | No new surface | `/memory view` and `/memory forget` take no free-text user input (no query string, no id parameter) — there is nothing to validate/sanitize beyond what discord.py's slash-command type system already guarantees. |
| V6 Cryptography | No | Not touched — embeddings/storage encryption-at-rest is Neon's existing responsibility, unchanged by this phase. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Cross-user memory disclosure via `/memory view` (viewing another user's facts) | Information Disclosure | No `target` parameter on `/memory view`; always `str(interaction.user.id)`; response is `ephemeral=True` so even the invoker's own view isn't visible to others in-channel. |
| Cross-user memory deletion via `/memory forget` (deleting another user's facts) | Tampering | No `target` parameter on `/memory forget`; `delete_all_user_memories`'s signature takes exactly one `user_id` argument with no second identity parameter — structurally prevents a future accidental "forget for someone else" feature from being bolted on without a deliberate signature change. |
| SQL injection via a hand-rolled DELETE/SELECT for the two new helpers | Tampering | Both new helpers use `$N` positional bound parameters exclusively (`WHERE user_id = $1`), following the T-11-04c/T-11-07b template — no string formatting/interpolation anywhere in the query text. |
| Confirm-view double-press causing a double DELETE (harmless here, but a correctness concern) | — (not a security threat per se, but a correctness/UX bug class) | `_used` guard + immediate `child.disabled = True` before the async work runs, exactly mirroring `JamSuggestConfirmView`'s existing pattern — already proven safe in this codebase. |

## Sources

### Primary (HIGH confidence — direct codebase reads, this repo)
- `services/memory.py` — full `MemoryService.recall`/`remember`/`distill`/`sweep` read
- `cogs/ai.py` — full `/ask` and `/roast` command bodies, exact line numbers for the two gates to remove
- `cogs/events.py:1-180` — `_generate_ambient_roast`, confirmed gate location (`:128`) and structure
- `cogs/music.py:100-200, 1230-1310` — `QueuePageView`, `LyricsPageView`, `_build_roast_line` (gate at `:1272`)
- `cogs/library.py:440-560, 1179-1310` — `/playlist` group shape, `JamSuggestConfirmView` full confirm/cancel/timeout implementation
- `database.py:1000-1240` — `bump_memory_hit`, `refresh_memory_expiry`, `count_user_memories`, `get_user_memories_for_eviction`, `evict_lowest_salience`, `bump_surfaced`, `delete_expired_memories`, `search_memories` (full docstring + SQL)
- `models/memory.py` — full pure-logic module (`MemoryFact`, `apply_floor`, `rerank`, `dedup_decision`, `compute_salience`, `choose_eviction`, `is_sensitive`, `contains_number`, `decay_predicate`)
- `personality/prompts.py` — `build_chat_prompt` byte-identical-fallback implementation, all prompt builders
- `config.py:150-209` — Phase 11/13 `MEMORY_*`/`TASTE_*` knobs, exact current values
- `tests/test_roast_command.py`, `tests/test_roast_logic.py`, `tests/test_database_phase11.py`, `tests/conftest.py` — existing test conventions (fake-bot/fake-interaction mocking style, live-DB skip-guard pattern, static-source-inspection pattern)
- `.planning/phases/15-rag-reach/15-CONTEXT.md` — locked/recommended decisions, canonical refs, open questions (this research resolves both flagged open questions)
- `.planning/phases/11-rag-long-term-memory/11-CONTEXT.md` — D-04/D-06 cadence principle, accuracy firewall origin
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` — RAG-01..04 requirement text, 4 success criteria, Out of Scope table (zero new dependency constraint)
- `.planning/research/PITFALLS.md` — Pitfall 4 (cross-user leak), Pitfall 5 (stale memory), Pitfall 6 (`/memory forget` incomplete erasure) — all directly informed this research's Common Pitfalls section
- `CLAUDE.md` — Critical Rules 11/12, project structure, tech stack constraints

### Secondary (MEDIUM confidence)
- None required — this phase's entire scope is verifiable directly against the existing codebase; no external library/API research was needed (zero new dependencies, no new Gemini call shapes, no new Discord API surface beyond patterns already used twice elsewhere in this repo).

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, fully verified against installed `requirements.txt` and CLAUDE.md
- Architecture: HIGH — every pattern recommended is a direct clone of an existing, working pattern in this same codebase (`JamSuggestConfirmView`, `LyricsPageView`, `evict_lowest_salience`, `app_commands.Group`)
- Pitfalls: HIGH on the cross-cutting Phase-11/v1.3-research-derived pitfalls (cross-user leak, stale memory, incomplete erasure — all previously identified by the flagship PITFALLS.md and re-confirmed against this phase's actual code); HIGH on the cadence-gate-removal risk (directly observed exact line numbers and near-identical shape across all four call sites)
- Test coverage gap (Open Question 2): HIGH confidence finding — directly verified by reading every candidate existing test file; there is genuinely no pre-existing lock on the `MEMORY_CALLBACK_CHANCE` gate at any of the four call sites, confirmed by both file inspection and a repo-wide grep

**Research date:** 2026-07-03
**Valid until:** No expiry pressure — this phase's substance is 100% intra-repo architecture reuse with zero external dependencies; stays valid until the underlying `services/memory.py`/`database.py` schema changes (i.e., effectively for the life of this milestone).
