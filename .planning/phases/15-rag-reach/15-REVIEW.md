---
phase: 15-rag-reach
reviewed: 2026-07-03T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - bot.py
  - cogs/ai.py
  - cogs/memory.py
  - config.py
  - database.py
  - tests/test_ambient_recall_cadence.py
  - tests/test_database_phase15.py
  - tests/test_memory_command.py
findings:
  critical: 0
  warning: 3
  info: 1
  total: 4
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-07-03
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Reviewed the Phase 15 RAG Reach diff (`d88192b^..HEAD`): two new `database.py` helpers
(`list_user_memories`, `delete_all_user_memories`), the D-01 cadence-gate removal in
`cogs/ai.py` (`/ask` + `/roast` now recall unconditionally instead of on a 35% dice
roll), and the new `cogs/memory.py` `MemoryCog` (`/memory view` + `/memory forget`,
pagination view, confirm view). `bot.py` and `config.py` changes are minimal and
correctly wire the new cog into both boot paths (`_initialize_once` and `first_run`).

The core security property under scrutiny — user_id scoping on every `user_memories`
query — is solid: `list_user_memories`, `delete_all_user_memories`, and the existing
`search_memories`/`evict_lowest_salience` all filter `WHERE user_id = $1` as the sole
or first clause, there is no `target`/`user` parameter anywhere in `MemoryCog`, and
`delete_all_user_memories`'s signature is structurally locked to `(pool, user_id)` by
its own test. The D-01 gate removal in `cogs/ai.py` is a clean, minimal diff that
matches its test lock exactly (`/roast` recalls the target, `/ask` recalls the
invoker, both unconditionally now). All 20 phase-15 unit tests pass locally (1 live-DB
test correctly skips without `TEST_DATABASE_URL`).

The issues found are all in `cogs/memory.py`'s new UI code: it explicitly describes
itself as a "clone" of two existing sibling views (`LyricsPageView`,
`JamSuggestConfirmView`) but diverges from both patterns in ways that matter — the
irreversible delete path lacks the try/except-and-report-failure discipline its
sibling has, the initial `/memory view` send omits the `allowed_mentions=None`
defense-in-depth every other paginated-embed command in the codebase applies, and the
pagination chunks by fact count rather than by character budget (unlike `LyricsPageView`,
which explicitly chunks by char count to stay under Discord's embed limit).

## Warnings

### WR-01: `/memory forget` confirm path has no failure handling — silent hang on DB error

**File:** `cogs/memory.py:143-170`
**Issue:** `ForgetConfirmView.confirm_button` calls
`await database.delete_all_user_memories(self.bot.pool, self.user_id)` directly, with
no `try/except` around it. Compare to the view this file explicitly says it clones,
`JamSuggestConfirmView.confirm_button` (`cogs/library.py:1216-1276`), which wraps its
entire DB-mutating body in `try/except Exception` and sends a user-visible
`"something broke saving those. the jam wasn't touched."` followup on failure.

Because `interaction.response.defer(ephemeral=True)` has already been called before
the delete, if `delete_all_user_memories` raises (pool exhaustion, Neon
scale-to-zero cold start, dropped connection), no `followup.send` ever fires. This is
a component (button) interaction, not an app command, so `bot.py`'s
`@bot.tree.error` global handler (`on_app_command_error`) never sees it either —
`discord.ui.View`'s default `on_error` just logs to stderr. The user is left with a
permanently "thinking..." ephemeral interaction and no indication of whether their
data was actually wiped.

This is exactly the feature (`RAG-04`, the "trust escape hatch") where a user needs
unambiguous confirmation that the delete either happened or didn't — a silent hang is
the worst possible failure mode for this specific command.

**Fix:**
```python
@discord.ui.button(label="wipe it all", style=discord.ButtonStyle.danger)
async def confirm_button(
    self, interaction: discord.Interaction, button: discord.ui.Button
) -> None:
    if self._used:
        await interaction.response.send_message("already handled that.", ephemeral=True)
        return
    self._used = True
    for child in self.children:
        child.disabled = True

    await interaction.response.defer(ephemeral=True)

    try:
        deleted = await database.delete_all_user_memories(self.bot.pool, self.user_id)
        log.info("Memory forget: user %s wiped %d memories", self.user_id, deleted)
        await interaction.followup.send(
            f"gone. all {deleted} of them. i've got nothing on you now.",
            ephemeral=True,
        )
    except Exception as exc:
        log.error("Memory forget failed for user %s: %s", self.user_id, exc, exc_info=True)
        await interaction.followup.send(
            "something broke wiping that. try again in a bit — nothing was confirmed deleted.",
            ephemeral=True,
        )

    if self.message is not None:
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass
```

### WR-02: `/memory view`'s initial send omits `allowed_mentions=None` — inconsistent with every sibling pagination command

**File:** `cogs/memory.py:236-241`
**Issue:** The module docstring claims (`T-15-11`): *"`MemoryPageView` edits use
`AllowedMentions.none()` as defense-in-depth against mention injection via fact
text"* — and this is true for the `prev_button`/`next_button` edits
(`cogs/memory.py:91-95`, `102-106`). But the **initial** `send_message` call that
first renders page 0 of the same untrusted fact text does not pass
`allowed_mentions`:

```python
await interaction.response.send_message(
    "fine, here's what i've got on you.",
    embed=view._build_embed(),
    view=view,
    ephemeral=True,
)
```

Every other paginated-embed command in this codebase applies `allowed_mentions=None`
(or `discord.AllowedMentions.none()`) on **both** the initial send and every
subsequent edit — see `cogs/music.py:1928-1933` (`/lyrics`), `cogs/music.py:1959-1963`
(`/history`), and `cogs/music.py:1016-1021` (auto-lyrics post). `MemoryCog` is the
outlier: the first page (the one every user actually sees by default) lacks the
control the docstring says is applied, and only page-2-onward gets it.

**Fix:**
```python
await interaction.response.send_message(
    "fine, here's what i've got on you.",
    embed=view._build_embed(),
    view=view,
    ephemeral=True,
    allowed_mentions=discord.AllowedMentions.none(),
)
```

### WR-03: `MemoryPageView` paginates by fact count, not character budget — no defense against embed-length overflow

**File:** `cogs/memory.py:44-56`, `234`
**Issue:** `_chunk_facts_into_pages` groups facts into pages of
`config.MEMORY_VIEW_PAGE_SIZE` (10) facts each, with no cap on total rendered
character length per page. Compare to `LyricsPageView`'s sibling `chunk_lyrics`
helper, which explicitly chunks by `config.LYRICS_PAGE_SIZE` (1500 chars) precisely
to stay under Discord's 4096-character embed `description` limit.

The only thing keeping a memory-view page under 4096 chars today is the
`DISTILL_PROMPT`'s instruction to Gemini that facts be *"under 80 characters"*
(`personality/prompts.py:14`) — this is a soft LLM instruction, not enforced
anywhere in code. Neither `MemoryService.remember()` nor
`database.py::insert_memory` truncates or validates fact length before storing a
row. If Gemini ever produces a longer fact (LLMs are not reliably compliant with
length instructions, especially for prose sentences), 10 such facts concatenated
with `"- "` bullet prefixes can exceed 4096 characters, and the
`interaction.response.send_message(embed=...)` / `edit_message(embed=...)` call will
raise `discord.HTTPException` (400 Bad Request), breaking `/memory view` for that
user's page.

**Fix:** Chunk by character budget the same way `chunk_lyrics` does, e.g.:
```python
def _chunk_facts_into_pages(facts: list[str], char_budget: int = 3800) -> list[str]:
    """Group facts into pages bounded by a character budget (not just count)."""
    if not facts:
        return [""]
    pages: list[str] = []
    current: list[str] = []
    current_len = 0
    for fact in facts:
        line = f"- {fact}"
        if current and current_len + len(line) + 1 > char_budget:
            pages.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        pages.append("\n".join(current))
    return pages
```
(Or, cheaper: keep the count-based chunking but also hard-cap each rendered page to
`char_budget` chars with a truncation marker, and/or enforce a max fact length in
`insert_memory`/`remember()` as a backstop.)

## Info

### IN-01: `ForgetConfirmView.count` is set but never read

**File:** `cogs/memory.py:139`
**Issue:** `self.count = count` is stored in `__init__` but nothing in the class
reads `self.count` afterward — the count is only used by the caller
(`memory_forget`) to build the pre-confirm message text before the view is
constructed. Dead attribute.
**Fix:** Either drop the parameter/attribute, or use it to render the pre-confirm
count consistently from the view itself instead of duplicating it in the caller.

---

_Reviewed: 2026-07-03_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
