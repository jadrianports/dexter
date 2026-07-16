# Phase 26: Radio Mode & Skip Democracy - Research

**Researched:** 2026-07-16
**Domain:** Discord voice/music-bot playback engine extension (Python 3.11, discord.py 2.3) — endless auto-queue radio mode + vote-gated skip, built entirely on existing in-repo infrastructure (Gemini auto-queue brain, pure `logic/` seam, voice-state enumeration idiom).
**Confidence:** HIGH

## Summary

This phase is almost entirely a **wiring and decision-logic** exercise, not a new-technology
exercise. Every capability DJ-01 and DJ-02 need already exists in the codebase: an auto-queue
Gemini brain (`cogs/ai.py::try_auto_queue`) that just needs its round cap lifted and a seed
anchor added, a voice-member enumeration idiom (`[m for m in vc.channel.members if not m.bot]`)
already used in four places, a pure `logic/` seam convention with three living examples
(`logic/playback.py`, `logic/proactive.py`, `logic/vision.py`) to clone for the two new gates,
and a templated-response-pool pattern (`personality/responses.py` + `pick_random`) for the vote
tally copy. No new dependencies, no new database tables, no new per-guild config surface — this
matches every phase since 11 and is explicitly locked by CONTEXT.md D-21.

The one genuinely new architectural finding from reading the code (not just CONTEXT.md's
canonical refs) is that **`/skip` and the `⏭ Skip` button are NOT currently unified** — CONTEXT.md's
D-15 canonical-refs section describes `_do_skip` as shared, but the actual `/skip` slash command
(`cogs/music.py:1663`) has its **own fully-duplicated inline skip body** that never calls
`_do_skip`; only `NowPlayingView.skip_button` (`:377`) calls `_do_skip`. This means D-15's "ONE
choke point" requires the planner to either (a) refactor `/skip` to call `_do_skip` for the first
time (deleting ~15 lines of duplicated logic), or (b) build the vote-gate as a wrapper that both
callers route through before either path's existing logic runs. Either way, this is a real code
change, not just "add a check before the button calls `_do_skip`" — the research surfaced a stale
assumption baked into CONTEXT.md's own canonical-refs summary.

**Primary recommendation:** Build two new pure `logic/` modules (`logic/radio.py`,
`logic/skip_vote.py`) following the exact `logic/proactive.py` / `logic/vision.py` template
(keyword-only params, no Discord/asyncio/random/datetime imports, cheapest-gate-first ordering).
Wire radio as an `is_radio: bool` (or seed-bearing) branch inside `try_auto_queue` reusing every
existing pipeline stage. Unify `/skip` and the button behind a new `_try_skip` (or similarly named)
shared async helper in `cogs/music.py` that both call, with the vote decision computed by
`logic/skip_vote.py::decide_skip` and dispatched on (never re-branched in glue, per the Phase 10
D-02 rule).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Radio armed-state tracking | API/Backend (in-process bot state) | — | Lives on `MusicQueue` or `ServerState` (in-memory, per-guild, per Discord.py process) — not a browser/DB tier; this is a single-process Discord bot |
| Radio refill decision (lookahead gate, played-set filter) | Pure `logic/` seam | API/Backend (glue dispatches) | Deterministic branching belongs in the pure seam per Phase 10 D-02; the async Gemini/YouTube I/O stays in `cogs/ai.py` glue |
| Radio's Gemini recommendation call | API/Backend (`services/gemini.py`) | External API (Gemini) | Reuses the existing priority-2 rate-limited chat() call — no new external dependency |
| Skip-vote tally + threshold arithmetic | Pure `logic/` seam | API/Backend (glue dispatches) | Same Phase 10 D-02 rule — majority-ratio math, requester-bypass, and solo-case detection must be mock-free-testable, not buried in Discord callback code |
| Skip-vote state (per-track vote set) | API/Backend (in-process, on `MusicQueue`) | — | Track-scoped, reset on track change (D-17) — in-memory, not persisted (mirrors radio's D-08 in-memory precedent) |
| Voice-member enumeration ("who's listening") | API/Backend (`discord.VoiceChannel.members`) | — | Discord gateway state, read live at vote/refill time — never cached/duplicated (the existing `for m in vc.channel.members if not m.bot` idiom, reused not reinvented) |
| Tally/radio narration copy | API/Backend (`personality/responses.py` template pools) | — | Templated, numbers interpolated by code — never a Gemini call (D-18, Critical Rule 12) |
| `/radio` command surface + skip vote-gate | API/Backend (`cogs/music.py` or new `cogs/radio.py`) | — | Discord slash-command glue layer; governed by the existing Phase 20 `DexterCommandTree.interaction_check` choke point (block/silence) — no new gate needed |

## Project Constraints (from CLAUDE.md)

- **Critical Rule 1:** All AI features share the 15 RPM Gemini limiter — radio refills are
  priority-2 (rejected outright when wait > 10s), exactly like today's auto-queue. No new limiter.
- **Critical Rule 3:** Kill FFmpeg processes explicitly on skip/stop/error — the skip path (now
  vote-gated) must still call `voice_client.stop()` / `_play_track` cleanup on an actual skip
  exactly as today; only the *decision to skip* changes, not the skip mechanics.
- **Critical Rule 5/12 (accuracy firewall):** Hard numbers in output must come from live state,
  never a model. The vote tally is the clearest instance of this rule outside the memory
  subsystem — D-18 locks templated-with-code-interpolated-numbers for exactly this reason.
- **Critical Rule 7/8:** ≤1 emoji, all lowercase — applies to every new personality string (radio
  start/stop/disarm lines, tally lines, mutual-exclusion notices).
- **Critical Rule 9:** Designated channel only — radio/vote narration posts through the existing
  `_get_text_channel` resolution, not a new channel-picking mechanism.
- **Critical Rule 19:** Block/silence enforced at ONE choke point
  (`DexterCommandTree.interaction_check`), never per-cog — confirmed still true by reading
  `bot.py`; `/radio` and vote-gated `/skip` need no new gate, they inherit this automatically.
- **Phase 1 gotcha:** Never `voice_client.stop()` before `_play_track()` — a radio refill that
  races `_on_track_end` must not violate this. The lookahead trigger (D-10) fires while a track is
  still playing, so the refill call itself (`try_auto_queue`) must never touch `voice_client.stop()`;
  it only appends to `queue.tracks` (exactly like today's auto-queue on empty-queue exhaustion).
- **Phases 6-8 gotcha (scar #2):** Gate playback-start on `voice_client.is_playing()`, never
  `queue.is_playing`. Radio's refill reuses `should_start_playback` unchanged — verified present
  at `cogs/ai.py:474`.
- **Phases 9-12 gotcha:** `logic/` is the pure seam; glue dispatches on the returned
  enum/verdict, never mirrors the branch logic back (Phase 10 D-02) — this is the explicit
  convention D-19 in CONTEXT.md invokes for both new seams.
- **Phases 13-17 gotchas:** Optional-param/omitted-clause/byte-identical-when-unset discipline
  (Phase 14 `recently_skipped`/`positive_taste`, Phase 16 `pre_recalled_memories`) is the exact
  shape D-02's seed-anchor param and D-05's ignored-signal suppression must follow.

## Standard Stack

### Core

No new libraries. This phase is 100% additive Python over the existing stack: `discord.py`
≥2.3 (`app_commands.Group` for `/radio`), the existing `google-genai` client via
`services/gemini.py`, `asyncpg` (no new tables — in-memory state only), `pytest`/`pytest-asyncio`
for the two new pure-logic test files.

### Supporting

No new supporting libraries required. Reused in-repo modules:

| Module | Purpose | Reused For |
|--------|---------|------------|
| `cogs/ai.py::try_auto_queue` | Gemini-backed recommendation pipeline | Radio's engine (round-cap lifted + seed) |
| `logic/autoqueue.py` | `validate_youtube_match` + `is_recently_skipped_artist` | Radio's hallucination guard + the D-03 hard-post-filter pattern |
| `logic/taste.py::select_positive_taste_context` | Room-taste blend | Radio's positive-taste context (unchanged) |
| `personality/prompts.py::build_recommendation_prompt` | Prompt assembly | D-02's seed-anchor optional param |
| `personality/responses.py` + `pick_random` | Templated response pools | D-18's tally copy + radio lifecycle copy |
| `services/gemini.py::chat` (priority=2) | Rate-limited Gemini call | Radio refill call (unchanged signature) |
| `database.py::mark_song_skipped`/`get_recent_songs`/`get_recently_skipped` | History reads/writes | D-20's unchanged skip-recording path |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Reusing `try_auto_queue` for radio | A second, dedicated radio recommender | Rejected by CONTEXT.md D-01 — duplicates the hallucination guard, taste blend, and rate-limit handling for no benefit |
| Templated skip-vote tally | Gemini-generated tally line | Rejected by CONTEXT.md D-18 — costs shared 15 RPM budget on a high-frequency surface and violates the accuracy firewall (Critical Rule 12) |
| Fixed skip-vote count | Listener-majority ratio | Rejected by CONTEXT.md D-09 — a fixed count is wrong at both ends of Dexter's actual room-size range |
| New `guild_config` columns for vote ratio/lookahead | Global `config.py` knobs | Rejected by CONTEXT.md D-21 — neither feature is an unprompted ambient surface, so the `AmbientSurface`/`GuildConfigService` machinery doesn't apply |

**Installation:**

```bash
# No new packages — additive Python only.
```

**Version verification:** N/A — no new third-party packages introduced by this phase.

## Package Legitimacy Audit

**Not applicable.** This phase installs zero new external packages (confirmed by reading
`config.py`, `cogs/ai.py`, `cogs/music.py`, `personality/prompts.py`, `personality/responses.py`,
`services/gemini.py` — every dependency needed already exists in `requirements.txt`). The
Package Legitimacy Gate is skipped per its own scope condition ("whenever this phase installs
external packages").

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────────────────┐
                         │              /radio start [seed]         │
                         │              /radio stop                 │
                         └───────────────┬───────────────────────────┘
                                          │
                                          ▼
                         ┌─────────────────────────────────────────┐
                         │  Radio armed-state (MusicQueue/ServerState)│
                         │  in-memory, per-guild, dies on restart     │
                         └───────────────┬───────────────────────────┘
                                          │  consulted at
                                          ▼
┌──────────────┐   track ends    ┌───────────────────────┐   below lookahead N    ┌─────────────────────────┐
│ Voice Client  │───naturally───▶│ cogs/music.py          │───threshold (D-10)────▶│ logic/radio.py           │
│ (audio flow)  │                │ _on_track_end          │                        │ should_refill_radio()    │
└──────────────┘                 │ (existing choke point) │◀───returns verdict─────│ (pure: armed? below N?   │
                                  └───────────┬─────────────┘                        │  session played-set?)   │
                                              │ dispatches on TrackEndAction         └─────────────────────────┘
                                              │ (existing enum, unchanged)
                                              ▼
                                  ┌─────────────────────────┐
                                  │ cogs/ai.py::try_auto_queue│  ← radio branch: round-cap lifted, seed
                                  │ (existing brain, D-01)    │    anchor injected, ignored-signal
                                  │  - recent history          │    suppressed while armed (D-05)
                                  │  - negative skip hint       │
                                  │  - positive taste blend     │
                                  │  - Gemini chat (priority=2) │───▶ Gemini API (existing 15 RPM limiter)
                                  │  - validate_youtube_match   │
                                  │  - session played-set filter│  ← NEW independent hard gate (D-03)
                                  │  - queue.add(track)         │
                                  └─────────────────────────┘


┌──────────────┐   /skip cmd    ┌───────────────────────┐
│ User          │──OR────────────│ ONE shared choke point │
│ (slash cmd or │   ⏭ button     │ (new _try_skip helper,  │
│  NP button)   │────────────────│  D-15 unification)      │
└──────────────┘                └───────────┬───────────────┘
                                             │  gathers: voice members (existing
                                             │  `not m.bot` idiom), requester,
                                             │  current votes, track requester_by
                                             ▼
                                 ┌─────────────────────────┐
                                 │ logic/skip_vote.py        │
                                 │ decide_skip()              │  (pure: solo? requester bypass?
                                 │                             │   majority reached? tally state)
                                 └───────────┬───────────────┘
                                             │ returns verdict (SKIP_NOW / VOTE_RECORDED / ALREADY_VOTED)
                                             ▼
                     ┌───────────────────────┴────────────────────────┐
                     ▼                                                 ▼
        ┌─────────────────────────┐                    ┌─────────────────────────────┐
        │ Existing skip mechanics   │                    │ Templated tally narration     │
        │ (queue.skip(), _play_track,│                    │ personality/responses.py       │
        │  mark_song_skipped,        │                    │ pick_random + count-interpolate │
        │  _persist_queue — unchanged)│                    │ (D-18, never Gemini)            │
        └─────────────────────────┘                    └─────────────────────────────┘
```

### Recommended Project Structure

```
logic/
├── radio.py            # NEW — pure radio refill-gate seam (D-19)
└── skip_vote.py         # NEW — pure skip-vote decision seam (D-19)

cogs/
├── music.py             # MODIFIED — /radio group (or new cogs/radio.py), unified skip choke
│                         #   point, _on_track_end lookahead hook, loop/radio mutual exclusion
└── ai.py                # MODIFIED — try_auto_queue radio branch (cap lift + seed + D-05 suppress)

personality/
├── prompts.py            # MODIFIED — build_recommendation_prompt seed-anchor optional param
└── responses.py          # MODIFIED — new tally pool + radio lifecycle copy pools

models/
├── queue.py              # MODIFIED (likely) — radio armed-state field(s), session played-set,
│                          #   per-track vote-state fields (planner's call vs ServerState)
└── server_state.py        # MODIFIED (alternative home for radio state — planner's call)

config.py                 # MODIFIED — new global knobs (D-21): majority ratio, lookahead depth,
                           #   refill batch size, session played-set cap

tests/
├── test_radio_logic.py    # NEW — mock-free tests for logic/radio.py
├── test_skip_vote_logic.py# NEW — mock-free tests for logic/skip_vote.py, esp. D-09c arithmetic
└── test_autoqueue_wiring.py # EXTENDED (likely) — regression guard: auto-queue path unchanged
                              #   when radio is disarmed
```

### Pattern 1: Pure decision seam with keyword-only params (D-19)

**What:** Both new `logic/` modules must follow the exact shape of `logic/proactive.py` /
`logic/vision.py`: module docstring stating "no Discord imports, no asyncio, no database calls,
no random, no datetime.now()", every public function `*`-keyword-only, cheapest-gate-first
ordering, one function per decision, an explicit "what the glue still must do after True" note.

**When to use:** Every branch of radio-refill and skip-vote logic that involves comparison/
threshold/boolean-combination arithmetic.

**Example:**
```python
# Source: logic/vision.py (existing, Phase 17) — the template to clone
def should_fire_vision_roast(
    *,
    opted_out: bool,
    cooldown_elapsed: bool,
    chance_roll: float,
    chance: float = config.VISION_ROAST_CHANCE,
) -> bool:
    if opted_out:
        return False
    if not cooldown_elapsed:
        return False
    if chance_roll >= chance:
        return False
    return True
```

A `logic/skip_vote.py::decide_skip` following this shape (illustrative signature — exact name/
shape is planner's discretion per CONTEXT.md):

```python
import enum

class SkipVerdict(enum.Enum):
    SKIP_NOW = "skip_now"          # solo listener OR requester bypass OR threshold just reached
    VOTE_RECORDED = "vote_recorded" # valid new vote, threshold not yet reached
    ALREADY_VOTED = "already_voted" # idempotent re-vote from the same user, no-op

def decide_skip(
    *,
    voter_id: int,
    is_requester: bool,
    listener_ids: frozenset[int],   # non-bot voice members RIGHT NOW (live, computed by glue)
    existing_votes: frozenset[int], # votes already recorded for the current track
    majority_ratio: float = config.SKIP_VOTE_MAJORITY_RATIO,
) -> tuple[SkipVerdict, frozenset[int]]:
    """Returns (verdict, updated_votes_set)."""
    if is_requester:
        return SkipVerdict.SKIP_NOW, existing_votes
    if len(listener_ids) <= 1:
        return SkipVerdict.SKIP_NOW, existing_votes
    if voter_id in existing_votes:
        return SkipVerdict.ALREADY_VOTED, existing_votes
    new_votes = existing_votes | {voter_id}
    required = len(listener_ids) // 2 + 1  # strict majority (D-09c)
    if len(new_votes & listener_ids) >= required:
        return SkipVerdict.SKIP_NOW, new_votes
    return SkipVerdict.VOTE_RECORDED, new_votes
```

Note the strict-majority arithmetic `len // 2 + 1`: for 2 listeners → 2, for 3 → 2, for 4 → 3
(D-09c's exact table). This is the single line of arithmetic CONTEXT.md flags as needing
mock-free tests at 1/2/3/4 listeners.

### Pattern 2: Optional-param, omitted-clause, byte-identical-when-unset (D-02, D-05)

**What:** New optional behavior is threaded through an existing function via a keyword-only
param that defaults to `None`/`False` and renders byte-identical output when omitted.

**When to use:** The D-02 seed anchor on `build_recommendation_prompt`, and the radio-branch cap
lift inside `try_auto_queue`.

**Example — existing precedent (Phase 14), verified in `personality/prompts.py:181-223`:**
```python
def build_recommendation_prompt(
    recent_songs: list[dict],
    *,
    recently_skipped: list[dict] | None = None,
    positive_taste: list[str] | None = None,
) -> str:
    ...
    skip_block = ""
    if recently_skipped:
        skip_block = "\n\nAVOID these...\n" + ...
    taste_block = ""
    if positive_taste:
        taste_block = "\n\nTHE ROOM TENDS TO LIKE:\n" + ...
    return MUSIC_RECOMMENDATION_PROMPT.format(...) + skip_block + taste_block
```

The D-02 seed anchor is a third optional kwarg (`seed: str | None = None`) following this exact
shape — omitted when `None`, byte-identical prompt when radio is disarmed.

### Pattern 3: Templated response pool with code-interpolated numbers (D-18)

**What:** A `list[str]` pool in `personality/responses.py` with `{placeholder}` slots filled by
`.format(**kwargs)` in the calling cog — never sent through Gemini.

**Example — existing precedent, verified in `personality/responses.py:178-183`:**
```python
SKIPS_RATE_ROASTS: list[str] = [
    "you skip {pct}% of what you queue. bold of you to keep going.",
    ...
]
```
Called via `pick_random(SKIPS_RATE_ROASTS).format(pct=pct)` at the cog layer (mirrors
`cogs/music.py::_build_roast_line`'s `fallback_kwargs` handling). The D-18 tally pool follows
this exactly:
```python
SKIP_VOTE_TALLY: list[str] = [
    "{votes} of {required}. one more and this track's gone.",
    "{votes}/{required} votes to skip. make your case or make your move.",
]
```

### Anti-Patterns to Avoid

- **Recomputing a second voice-member enumeration inside `try_auto_queue`:** the existing
  `voice_members = [m for m in vc.channel.members if not m.bot]` at `cogs/ai.py:335` is asserted
  to appear **exactly once** in that function's source by
  `tests/test_autoqueue_wiring.py::test_voice_member_enumeration_is_a_single_reused_comprehension`
  (a literal `src.count(...)` assertion scoped to `try_auto_queue`'s own source). Any radio-branch
  code added inside `try_auto_queue` must reuse this same list, not recompute a second one — doing
  so would both violate D-03's stated design and fail that existing test.
- **Building the skip-vote gate as a per-cog check instead of one shared choke point:** directly
  contradicts D-15 and the Phase 20 OWNER-05 precedent (Critical Rule 19). See Pitfall 1 below for
  the concrete discovery that `/skip` and the button are not currently unified.
- **Persisting radio armed-state to `guild_queues` JSONB:** explicitly rejected by D-08. A restart
  must drop radio to disarmed — no schema change, no new persistence payload key.
- **A vote-message/button UI, or Gemini-generated tally text:** both explicitly rejected (D-14,
  D-18) in favor of `/skip`-is-the-vote + templated copy.
- **Round-down majority (2→1, 3→2, 4→2) for the vote threshold:** explicitly rejected (D-09c) in
  favor of strict majority (`n // 2 + 1`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Music recommendation / hallucination guarding | A second Gemini recommender for radio | `cogs/ai.py::try_auto_queue` + `logic/autoqueue.py::validate_youtube_match` | Already handles duration guards, YouTube-title validation, and priority-2 rate-limit rejection; a second engine doubles the surface with no quality gain (D-01) |
| "Who's currently listening" | A new voice-state cache or a `discord.VoiceState`-derived member list computed differently per call site | `[m for m in vc.channel.members if not m.bot]` (existing idiom, 4 call sites) | One definition of "who's in the room" across the whole codebase (D-09b); a second definition risks drift and duplicate-test friction |
| Templated copy with number interpolation | A new formatting helper | `pick_random()` + `.format(**kwargs)` (existing pattern from `SKIPS_RATE_ROASTS`, `AUTO_QUEUE_ANNOUNCE`, `REPEAT_SONG_ROAST_TEMPLATES`) | Already the established idiom; a new helper would be a parallel, untested path |
| Gapless refill trigger | A time-based background loop | The existing `_on_track_end` choke point + `queue.upcoming()` lookahead read | `_on_track_end` already dispatches on `TrackEndAction`; a parallel background loop would race the generation counter for no benefit (D-10 rejected this explicitly) |

**Key insight:** Every "don't hand-roll" item in this phase is really "don't build a second copy
of something that already exists in this exact repo" — this is the defining character of Phase 26:
radio and skip-voting are compositions of existing primitives, not new subsystems.

## Common Pitfalls

### Pitfall 1: `/skip` and the `⏭ Skip` button are NOT currently unified (contradicts a CONTEXT.md canonical-refs claim)

**What goes wrong:** CONTEXT.md's canonical-refs section describes `_do_skip` (`cogs/music.py:1006`)
as the code both the `/skip` slash command and the button call, and frames D-15 as "unify these
two callers behind one gate." Reading the actual code shows the `/skip` slash command
(`cogs/music.py:1663-1695`) has its own **fully duplicated inline skip body** — it never calls
`_do_skip`. Only `NowPlayingView.skip_button` (`:377-393`) calls `cog._do_skip(...)`. If a planner
takes CONTEXT.md's canonical-refs section at face value and just "adds a vote check before the
`_do_skip` call," the `/skip` slash command's separate inline body sails through completely
unvoted — the exact D-15 bypass hole the phase exists to close, just on the other command.

**Why it happens:** `_do_skip` was extracted in Phase 7 ("SHARED CONTROL HELPERS" comment at
`cogs/music.py:1002-1004`) explicitly so slash commands AND button callbacks share logic — but the
`/skip` command itself was apparently never migrated to call it, unlike `/pause`... (actually
`/pause`/`/resume`/`/stop` also have their own inline bodies distinct from `_do_pause_toggle`/
`_do_stop`; this is a broader, pre-existing pattern in this file, not unique to skip).

**How to avoid:** The plan must explicitly route BOTH the `/skip` slash command body and the
button callback through the SAME new shared async helper (e.g. `_try_skip`), which then calls the
vote gate first and only falls through to the existing `_do_skip`-style mechanics
(`queue.skip()`, `_persist_queue`, `make_task(_play_track...)`, `_refresh_now_playing`,
`mark_song_skipped`) on an actual `SKIP_NOW` verdict. This likely means refactoring `/skip`'s
inline body to finally call through `_do_skip` (or a renamed/generalized version of it) for the
first time — not just adding a check in front of the existing `_do_skip` call.

**Warning signs:** A plan/PR that touches only `NowPlayingView.skip_button` or only `_do_skip`
without also touching the `skip` slash command body at `cogs/music.py:1663` has NOT closed D-15.

### Pitfall 2: `try_auto_queue`'s round-cap check happens BEFORE the recent-history bail

**What goes wrong:** `try_auto_queue` checks `server_state.auto_queue_rounds >= AUTO_QUEUE_MAX_ROUNDS`
first (line 283) and sends `AUTO_QUEUE_CAP_REACHED` if so — a message that says "someone else pick
something or I'm leaving." If radio simply "lifts the cap" by never incrementing
`auto_queue_rounds` while armed, this is safe. But if the planner instead special-cases the
comparison (`rounds >= cap and not radio_armed`), a person who starts radio mid-way through an
existing 3-round auto-queue session inherits a stale `auto_queue_rounds` count that then behaves
inconsistently across the radio/non-radio boundary. **Recommendation surfaced by this research:**
have `/radio start` reset `server_state.reset_auto_queue()` (same call `/play` already makes) so
radio always starts from a clean round counter, independent of how the cap-lift is implemented.

**Why it happens:** `auto_queue_rounds` is shared mutable state (`ServerState`) that both the
existing auto-queue feature and the new radio feature read/increment. Radio's "cap lift" is easy
to implement as "skip the check when radio_armed" but that still leaves `auto_queue_rounds`
incrementing during radio (probably desired for `/skips` analytics parity, but worth an explicit
decision) — or NOT incrementing (also plausible if radio uses a separate counter). The planner
must pick one and be explicit; CONTEXT.md leaves "how the round cap is lifted" as discretion.

**How to avoid:** Decide explicitly whether radio increments `auto_queue_rounds` (affecting the
`AUTO_QUEUE_IGNORED` signal calculation at line 490-493, which reads `auto_queue_results`) or uses
independent tracking. Given D-05 already suppresses the ignored-signal announce/write while radio
is armed, the safest choice is: radio does NOT touch `auto_queue_rounds`/`auto_queue_results` at
all (they stay exactly as pre-radio, so post-radio auto-queue resumes with a clean slate) —
document this explicitly in the plan.

**Warning signs:** A test asserting `auto_queue_rounds` state after a radio session with no
explicit statement of what the "right" value should be.

### Pitfall 3: The session played-set (D-03) must not leak across radio sessions or guilds

**What goes wrong:** If the session played-set is a module-level or bot-level dict keyed only by
`guild_id` (not reset on `/radio start`/`/radio stop`), a second radio session in the same guild
inherits the first session's played history, defeating the purpose of "fresh station, fresh
rotation" and potentially causing false-positive rejections on tracks that would otherwise be fine
to replay in a new session.

**Why it happens:** Natural to store this as a `set[str]` (video_ids) on `MusicQueue` (guild-scoped,
long-lived object) without clearing it in the `/radio start` handler.

**How to avoid:** Explicitly clear/reinitialize the played-set at `/radio start` (not just at
`clear()`/`/stop`), and clear it again at disarm (D-07's three disarm sites: `/radio stop`,
`/stop`, idle-leave). CONTEXT.md's discretion section explicitly flags this ("it dies with radio
per D-08") — the plan must include an explicit reset-on-start line, not just reset-on-stop.

### Pitfall 4: A departed voter's vote stays counted (D-17) — but a departed non-voter must NOT be double-counted against the shrinking threshold

**What goes wrong:** D-17 locks "a departed voter's vote stays counted" (so a walkout can't
strand a vote below a threshold that just dropped). But the *threshold itself* is "recomputed
live at each vote" from `listener_ids` — the live voice-channel member set at THAT vote's moment.
If the pure `decide_skip` function is handed a stale `listener_ids` snapshot (e.g. captured once
when the vote "opened" rather than freshly read from `vc.channel.members` on every `/skip`/button
press), the threshold silently goes wrong the moment anyone joins or leaves voice mid-vote.

**Why it happens:** It's tempting to cache `listener_ids` once per track (e.g. compute it in
`_refresh_now_playing` and stash it) for efficiency, since it looks like "who's listening to this
track." D-17 explicitly requires re-reading it at every single vote.

**How to avoid:** The glue must call `[m for m in voice_client.channel.members if not m.bot]`
FRESH inside the skip-vote choke point on every invocation (cheap — it's a synchronous property
read on cached gateway state, not a network call), never memoized per-track.

### Pitfall 5: Radio + auto-queue both set `requested_by = self.bot.user.id` — D-13a's requester bypass naturally excludes them, but "requester bypass" must resolve `interaction.user.id`, not `track.requested_by`, for the VOTER

**What goes wrong:** D-13a bypass logic is "the track's requester votes → instant skip." The
*voter* is `interaction.user.id` (or the button-presser's id); the check is
`interaction.user.id == track.requested_by`. If radio/auto-queue tracks have
`requested_by = self.bot.user.id`, no human interaction.user.id will ever equal that — D-13b's
"bot-queued tracks always vote" falls out for free, exactly as CONTEXT.md states, PROVIDED the
comparison is implemented as a plain equality check and nobody adds a special-case "if
`requested_by == bot.user.id`, treat as no-bypass" branch (which would be redundant but harmless)
or, worse, "if `requested_by == bot.user.id`, bypass for everyone" (which would be a real bug,
re-opening the exact hole D-13b closes).

**How to avoid:** Implement the requester-bypass check as a single equality
(`voter_id == track.requested_by`) with no special-casing for the bot's own id. Add an explicit
test: a vote from a non-requester on a bot-queued track (radio or auto-queue) must NOT bypass.

## Code Examples

### Existing voice-member enumeration idiom (reuse, don't reinvent)

```python
# Source: cogs/ai.py:335 (existing, Phase 14)
vc = guild.voice_client
voice_members = [m for m in vc.channel.members if not m.bot] if vc and vc.channel else []
```

```python
# Source: cogs/music.py:864 (existing, _on_track_end)
humans_present = any(not m.bot for m in voice_client.channel.members) if connected else False
```

### Existing "shared control helper" pattern (Phase 7) — the template `_try_skip` should follow

```python
# Source: cogs/music.py:1006-1033 (existing _do_skip, called today ONLY by the button)
async def _do_skip(
    self, guild: discord.Guild, queue: MusicQueue, voice_client: discord.VoiceClient
) -> Track | None:
    """Skip to the next track. Returns the new track, or None if queue exhausted."""
    current = queue.get_current()
    if current and current.was_auto_queued:
        await mark_song_skipped(self.pool, guild_id=str(guild.id), url=current.url)
        ...
    next_track = queue.skip()
    await self._persist_queue(guild, queue)
    if next_track:
        make_task(self._play_track(guild, next_track), name="play-after-skip", bot=self.bot)
        await self._refresh_now_playing(guild, queue)
    else:
        queue.is_playing = False
        voice_client.stop()
    return next_track
```

### Existing lookahead read (D-10's refill trigger source)

```python
# Source: models/queue.py:235-237 (existing)
def upcoming(self) -> list[Track]:
    """Return tracks after the current one."""
    return self.tracks[self.current_index + 1 :]
```
`len(queue.upcoming())` at the `_on_track_end` choke point (after `queue.advance()`, before the
`decide_on_track_end` dispatch) is the natural D-10 lookahead-depth read.

### Existing rate-limiter priority-2 rejection (underpins D-04)

```python
# Source: services/gemini.py:103-129 (existing _RateLimiter.acquire)
if priority >= 2 and wait_time > 10:
    raise GeminiRateLimitError(f"Rate limit full, wait would be {wait_time:.0f}s")
```
`try_auto_queue` already catches `GeminiRateLimitError` at its outer `except` (line 536) and
`log.info`s + returns — this is the exact "silent, log and retry next cycle" behavior D-04 wants
radio to inherit unchanged.

## State of the Art

Not applicable in the traditional "library X replaced library Y" sense — this phase is pure
in-repo composition. The one relevant "state of the art" note: nothing changed externally since
Phase 14 (2026-07-02) in how the auto-queue brain, taste blend, or hallucination guard work — this
research found zero drift in Gemini API surface, discord.py version, or yt-dlp behavior relevant
to this phase's scope. `services/gemini.py::chat` still returns `None`-on-empty/-blocked (VIS-02's
contract), still uses the shared `_RateLimiter` with the same priority semantics documented in
Phase 11/14.

**Deprecated/outdated:** Nothing in this phase's scope deprecates prior-phase work. The
`AUTO_QUEUE_IGNORED` announce + `auto_queue_ignored` memory write are not removed — D-05
suppresses them conditionally (while radio is armed), a runtime gate, not a code deletion.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The exact default value for `SKIP_VOTE_MAJORITY_RATIO` (suggested: 0.5, i.e. `n // 2 + 1` strict majority) is planner's discretion per CONTEXT.md — this research does not assert a "correct" default, only documents the D-09c arithmetic table (2→2, 3→2, 4→3) that any chosen ratio must reproduce | Pattern 1 / Standard Stack | Low — CONTEXT.md explicitly delegates this; a wrong pick is a one-line config change, not an architecture change |
| A2 | The exact lookahead depth (how many tracks remaining triggers a D-10 refill) is planner's discretion; this research suggests reading `len(queue.upcoming())` at the existing `_on_track_end` choke point as the mechanism but does not assert a specific N | Architecture Patterns | Low — same as A1, explicitly delegated by CONTEXT.md |
| A3 | Radio's armed-state and session played-set are assumed to live on `MusicQueue` (following the `auto_lyrics` in-memory-preference precedent) rather than `ServerState`; CONTEXT.md explicitly leaves this as discretion with a "strong steer" toward whichever makes D-07/D-11 cleanest — this research did not resolve which is actually cleaner, only that both are viable per existing precedent (`auto_lyrics` on `MusicQueue`, `auto_queue_rounds` on `ServerState`) | Recommended Project Structure | Low — a straightforward refactor either way; does not affect correctness, only code organization |

**If this table is empty:** N/A — all three entries above are pre-flagged CONTEXT.md discretion
items, not unverified factual claims; nothing in this research required external verification that
could not be confirmed directly against the repo.

## Open Questions

1. **How should `/skip`'s existing inline body be reconciled with the new shared choke point?**
   (RESOLVED) — Pitfall 1 above documents the concrete finding: `/skip`'s slash-command body is
   currently NOT calling `_do_skip` at all (contradicting CONTEXT.md's canonical-refs framing).
   The plan must explicitly refactor `/skip` to route through the same new shared helper the
   button uses. This is now a known, scoped code change, not an open question — flagging it here
   so the planner sees the discrepancy from CONTEXT.md's own summary explicitly, in case they
   trust that summary over reading `cogs/music.py` directly.

2. **Does radio's refill touch `server_state.auto_queue_rounds`/`auto_queue_results`, or does it
   stay fully independent?** (RESOLVED, with a recommendation) — Pitfall 2 recommends radio NOT
   touch these fields at all (call `reset_auto_queue()` on `/radio start` and never increment
   during radio), keeping the existing auto-queue counters clean for whenever radio is disarmed.
   This is stated as a recommendation, not a locked decision — CONTEXT.md leaves "how the round
   cap is lifted" as planner's discretion, and this research surfaces the concrete state-sharing
   risk that discretion must resolve.

3. **Exact home for skip-vote per-track state (votes-so-far set)?** (RESOLVED as "MusicQueue,
   reset on track change") — mirrors D-17's requirement that votes reset on track change; since
   `MusicQueue` already tracks `current_index`/`_play_generation` per-guild and is the natural
   place to key state off "the current track," a `dict[str, set[int]]` or similar keyed by
   video_id (or simply a `set[int]` cleared on every `advance()`/`skip()`) is the natural home.
   Not explicitly locked by CONTEXT.md (left to "exact test shape"/discretion), but this research
   found no viable alternative home that doesn't require new cross-object plumbing.

## Environment Availability

Skipped — this phase has no new external dependencies (no new services, CLIs, runtimes, or
databases). Every dependency it touches (Gemini API, Discord gateway, PostgreSQL via existing
pool) is already verified available and in continuous use by the shipped Phase 11-25 code.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (existing, `requirements.txt`) |
| Config | No `pytest.ini`/`setup.cfg` — implicit defaults (unchanged since Phase 1) |
| Quick run command | `pytest tests/test_radio_logic.py tests/test_skip_vote_logic.py -x` |
| Full suite command | `pytest` (currently 848+ tests passing per STATE.md Phase 17 note; Phase 25 added more) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DJ-01 (SC-1) | Radio refills indefinitely off a seed, no manual `/play` needed | unit (pure gate) | `pytest tests/test_radio_logic.py -k should_refill -x` | ❌ Wave 0 |
| DJ-01 (SC-1) | Radio's refill reuses `try_auto_queue`'s pipeline unchanged (byte-identical when disarmed) | unit (wiring/regression) | `pytest tests/test_autoqueue_wiring.py -x` (extended) | ❌ Wave 0 (extend existing file) |
| DJ-01 (SC-1) | Session played-set independently rejects a duplicate after YouTube resolution (D-03) | unit (pure gate + hard filter) | `pytest tests/test_radio_logic.py -k played_set -x` | ❌ Wave 0 |
| DJ-01 (SC-2) | `/radio stop`, `/stop`, idle-leave all disarm radio (no leftover auto-refill) | unit (pure gate: armed-state transitions) | `pytest tests/test_radio_logic.py -k disarm -x` | ❌ Wave 0 |
| DJ-01 (SC-2) | Human `/play` mid-radio injects without disarming | unit (pure gate) | `pytest tests/test_radio_logic.py -k human_play_injects -x` | ❌ Wave 0 |
| DJ-01 | Radio and loop mode are mutually exclusive (D-11) | unit (pure gate or glue structural review) | `pytest tests/test_radio_logic.py -k loop_exclusion -x` | ❌ Wave 0 |
| DJ-02 (SC-3) | Vote threshold = strict majority of non-bot listeners, computed live | unit (pure arithmetic, D-09c table at n=1,2,3,4) | `pytest tests/test_skip_vote_logic.py -k majority -x` | ❌ Wave 0 |
| DJ-02 (SC-3) | Tally narrates the running count via templated copy | unit (response-pool format smoke test, mirrors `test_responses.py`) | `pytest tests/test_responses.py -k skip_vote -x` (extended) | ❌ Wave 0 (extend existing file) |
| DJ-02 (SC-3) | Both `/skip` and the `⏭ Skip` button route through the SAME vote gate | structural/wiring test (source-scan, mirrors `test_autoqueue_wiring.py`'s pattern) | `pytest tests/test_music_wiring.py -k skip_choke_point -x` | ❌ Wave 0 (likely new file, or extend an existing music-wiring test if one exists) |
| DJ-02 (SC-4) | Solo listener's `/skip` skips instantly (regression-locked) | unit (pure gate, `len(listener_ids) <= 1` branch) | `pytest tests/test_skip_vote_logic.py -k solo -x` | ❌ Wave 0 |
| DJ-02 | Track requester bypasses the vote (D-13a); bot-queued tracks never bypass (D-13b) | unit (pure gate) | `pytest tests/test_skip_vote_logic.py -k requester_bypass -x` | ❌ Wave 0 |
| DJ-02 | Vote is idempotent per user; a repeat `/skip` from the same voter is a no-op (D-14) | unit (pure gate) | `pytest tests/test_skip_vote_logic.py -k idempotent -x` | ❌ Wave 0 |
| DJ-02 | Votes reset on track change (D-17) | unit or glue structural review (state lifecycle) | `pytest tests/test_skip_vote_logic.py -k reset_on_track_change -x` | ❌ Wave 0 |
| DJ-02 | A vote-skipped track records via the existing `mark_song_skipped`, nothing more (D-20) | regression/structural (assert no new memory-kind call in the skip path) | `pytest tests/test_music_wiring.py -k no_new_memory_kind -x` or manual code review | ❌ Wave 0 (or reviewer-only, per D-20's "nothing more" framing) |

### Sampling Rate

- **Per task commit:** `pytest tests/test_radio_logic.py tests/test_skip_vote_logic.py -x`
  (fast, mock-free, no DB/network — matches the existing `logic/` test convention's near-instant
  runtime)
- **Per wave merge:** `pytest` (full suite — currently 848+ tests; Discord/process glue stays
  untested-by-design per `TESTING.md`, structural review + clean boot instead)
- **Phase gate:** Full suite green before `/gsd-verify-work`; a clean-boot smoke check
  (`docker compose up` / local run, per Phase 24's established Docker path) confirming `/radio` and
  `/skip` command registration succeeds

### Wave 0 Gaps

- [ ] `tests/test_radio_logic.py` — covers DJ-01 (the radio refill-gate pure seam: armed?
      below-lookahead? played-set filter? loop-mutual-exclusion signal?)
- [ ] `tests/test_skip_vote_logic.py` — covers DJ-02 (the skip-vote pure seam: majority
      arithmetic at n=1/2/3/4, requester bypass, idempotent re-vote, solo instant-skip)
- [ ] A structural/wiring test file (new or extended) asserting `/skip` and the `⏭ Skip` button
      both call the same shared choke-point helper — mirrors `test_autoqueue_wiring.py`'s
      source-scan pattern (`src.count(...)` assertions). This is the concrete regression guard for
      Pitfall 1's finding.
- [ ] Extend `tests/test_autoqueue_wiring.py` (or add a sibling) with a regression guard proving
      the auto-queue path (`try_auto_queue` called with radio disarmed) is byte-identical to
      pre-Phase-26 behavior — mirrors the Phase 14/16 "byte-identical when unset" test convention.
- [ ] Extend `tests/test_responses.py` (or wherever response pools are tested) with a smoke test
      that the new tally pool's `{votes}`/`{required}` placeholders format without `KeyError` —
      mirrors the existing `SKIPS_RATE_ROASTS` `{pct}` test pattern.

*(No test-framework install gap — pytest/pytest-asyncio already fully wired.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No new auth surface — this phase is entirely within Discord's existing interaction/gateway auth |
| V3 Session Management | No | No new session concept beyond existing Discord interaction lifecycle |
| V4 Access Control | Yes | Governed entirely by the EXISTING Phase 20 `DexterCommandTree.interaction_check` choke point (block/silence) — no new access-control code needed, but the plan must NOT accidentally add a second, redundant check that could diverge from it (Critical Rule 19) |
| V5 Input Validation | Yes | The `/radio start [seed]` free-text seed string (D-06a) flows only into a Gemini prompt slot, never SQL/shell/file-path — no injection surface beyond what `build_recommendation_prompt` already handles for `recent_songs`/`recently_skipped` text. The hallucination validator (`validate_youtube_match`) still gates every actual queued track regardless of what the seed says (D-06a's own stated mitigation) |
| V6 Cryptography | No | Not applicable — no new secrets, tokens, or crypto operations |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Vote brigading — one user re-voting many times (e.g. by re-issuing `/skip` repeatedly) | Elevation of Privilege / Repudiation | D-14 locks `/skip` as idempotent per user (`voter_id in existing_votes` check) — a repeat vote from the same user is a no-op, not an additional tally increment. The existing `SKIP_COOLDOWN_SECONDS=2` cooldown remains as the secondary anti-spam guard at the command-invocation layer (separate from the vote-idempotency guard, which prevents a SECOND distinct vote from the same identity even after the cooldown elapses) |
| A departed voice member's vote still counting toward/against the live threshold | Tampering (stale-state) | D-17 explicitly ACCEPTS this for votes-already-cast (a walkout can't strand a vote below a dropped threshold) but requires `listener_ids` (the denominator) to be freshly read on every vote (Pitfall 4) — the accepted risk is scoped and documented, not an oversight |
| Radio mode as a Gemini-budget amplification vector — an armed radio silently consuming the shared 15 RPM budget, starving `/ask`/`/roast` | Denial of Service | Radio refills stay priority-2 (D-04) — the SAME rejection-when-wait>10s behavior that already protects priority-1 (`/ask`, `/roast`) traffic from today's auto-queue. No new escalation path; D-04 explicitly rejects escalating radio to priority 1 for exactly this reason |
| Radio/vote state leaking across guilds | Information Disclosure | Both live entirely on per-guild objects (`MusicQueue`/`ServerState`, keyed by `guild_id`) — the SAME per-guild-instance pattern every existing queue/auto-queue state already uses. No cross-guild read path exists in either new module (both are pure functions over caller-supplied primitives, per the D-19 seam convention) |
| An admin/owner attempting to bypass the vote gate to unilaterally force a skip | Elevation of Privilege | D-13a explicitly REJECTS any admin/owner bypass — "an admin/owner override would quietly reinstate exactly the unilateral power DJ-02 removes." The only bypass is the track's own requester. This is a locked decision, not discretion — a plan/PR that adds a `manage_guild`- or `is_owner()`-gated skip bypass would be a scope violation, not a security fix |
| A malicious/malformed seed string attempting prompt injection against the recommendation prompt | Tampering | Low severity — the seed only steers prompt TEXT; `validate_youtube_match` still gates every candidate track against real YouTube search results before it's ever queued (D-06a's stated mitigation: "a misread costs nothing"). No file/shell/SQL surface is reachable from the seed string |

## Sources

### Primary (HIGH confidence — direct repository reads)

- `.planning/phases/26-radio-mode-skip-democracy/26-CONTEXT.md` — all locked decisions D-01…D-21,
  canonical refs, discretion items
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/ROADMAP.md` — phase scope,
  success criteria, milestone decisions
- `CLAUDE.md` — Critical Rules, Implementation Gotchas, project structure
- `cogs/music.py` (full read, both halves) — `_on_track_end`, `_do_skip`, `NowPlayingView.skip_button`,
  the `/skip`/`/pause`/`/resume`/`/stop`/`/loop` slash commands, `_play_track`, `_prefetch_next_track`,
  `_persist_queue`
- `cogs/ai.py` (full read) — `try_auto_queue` end to end, `/ask`, `/roast`, `parse_suggestions`
- `logic/playback.py`, `logic/autoqueue.py`, `logic/taste.py`, `logic/proactive.py`, `logic/vision.py`
  (full reads) — the pure-seam convention and three living precedent modules
- `models/queue.py`, `models/server_state.py` (full reads) — `MusicQueue`, `Track`, `ServerState`,
  the `auto_lyrics` in-memory precedent
- `personality/prompts.py`, `personality/responses.py` (full reads) — `build_recommendation_prompt`,
  the templated response-pool pattern
- `services/gemini.py`, `services/queue_persistence.py` (full reads) — the priority-2 rate-limiter
  rejection behavior, the smart-rejoin/clamp-index precedent
- `database.py` (targeted reads) — `mark_song_skipped`, `get_recent_songs`, `get_recently_skipped`,
  `get_artist_cooccurrence`
- `bot.py` (targeted read) — `DexterCommandTree.interaction_check`, the voice-member idiom at line 951
- `cogs/library.py` (targeted read) — `app_commands.Group` pattern for `/playlist`/`/jam`, the
  precedent for `/radio`'s subcommand-group shape
- `.planning/codebase/TESTING.md` — test framework, conventions, mocking patterns
- `tests/test_autoqueue_wiring.py` (targeted read) — the source-scan wiring-test pattern and the
  exact single-occurrence assertion on the voice-member comprehension

### Secondary (MEDIUM confidence)

None — this research required no external web verification; the entire domain is in-repo code
already read directly.

### Tertiary (LOW confidence)

None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, entirely reused in-repo modules verified by direct read
- Architecture: HIGH — every pattern cited is a verified, currently-shipping precedent in this exact codebase (not inferred from training data)
- Pitfalls: HIGH — Pitfall 1 (the `/skip`/button non-unification) is a first-hand discovery from reading the actual current code, not carried over from CONTEXT.md's own summary; the other four pitfalls follow directly from documented CLAUDE.md scars and CONTEXT.md's own stated risk acceptances

**Research date:** 2026-07-16
**Valid until:** 30 days (stable, in-repo-only domain; no external API/library drift risk in scope)
