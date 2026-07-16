"""Pure skip-vote decision seam (Phase 26 / DJ-02 / D-19).

All functions in this module are deterministic and side-effect-free: no
``discord``, no ``asyncio``, no ``database``, no ``random``, no ``datetime``.

Live voice membership (``listener_ids``) and the per-track vote set
(``existing_votes``) are computed by the calling cog glue — reading
``MusicQueue.skip_votes_for_current()`` and the voice channel's live
member list — and passed in as primitives, following the established seam
pattern from ``logic/playback.py`` (Phase 10) and ``logic/proactive.py`` /
``logic/radio.py`` (Phase 16/26).

D-09c's locked strict-majority table (at the default ratio 0.5):

    listener_count  required_votes
    1               1   (solo — SC-4 instant skip, no tally)
    2               2
    3               2
    4               3

The arithmetic is ``floor(listener_count * majority_ratio) + 1``, clamped to
``listener_count`` — deliberately NOT ``listener_count // 2 + 1``, which would
hardcode 0.5 and make ``config.SKIP_VOTE_MAJORITY_RATIO`` a lie.

Glue dispatches on the returned ``SkipVerdict`` and must never re-derive this
arithmetic itself (Phase 10 D-02 rule) — always call ``required_votes`` for
the same number that drives the D-18 tally's ``{required}`` slot.

Locked by tests/test_skip_vote_logic.py (mock-free boundary coverage).
"""

from __future__ import annotations

import enum
import math

import config

# ---------------------------------------------------------------------------
# SkipVerdict
# ---------------------------------------------------------------------------


class SkipVerdict(enum.Enum):
    """What the skip-vote glue should do after consulting ``decide_skip``."""

    SKIP_NOW = "skip_now"
    """Solo listener, requester bypass, or the vote just reached the
    threshold — run the skip mechanics immediately."""

    VOTE_RECORDED = "vote_recorded"
    """A new valid vote was recorded but the threshold is not yet reached —
    narrate the updated tally (D-18: code-interpolated numbers only)."""

    ALREADY_VOTED = "already_voted"
    """Idempotent re-vote from the same user (D-14) — no state change,
    re-narrate the unchanged tally."""


# ---------------------------------------------------------------------------
# required_votes
# ---------------------------------------------------------------------------


def required_votes(
    *,
    listener_count: int,
    majority_ratio: float = config.SKIP_VOTE_MAJORITY_RATIO,
) -> int:
    """Return the number of votes needed to skip, per D-09/D-09c.

    ``floor(listener_count * majority_ratio) + 1``, clamped to
    ``listener_count`` and floored at 1.

    D-09c's locked table at the default ratio (0.5):
        listener_count=1 -> 1
        listener_count=2 -> 2
        listener_count=3 -> 2
        listener_count=4 -> 3

    This is deliberately NOT ``listener_count // 2 + 1`` — D-09 makes the
    ratio a ``config.py`` knob, and ``n // 2 + 1`` would silently ignore it
    (setting ``majority_ratio=0.75`` would change nothing). ``floor(n *
    ratio) + 1`` is "strictly more than the ratio" — the honest
    generalisation of D-09c's "strictly more than half" — and it reproduces
    the locked table exactly at ratio=0.5.

    The clamp to ``listener_count`` exists so a misconfigured ratio (e.g.
    1.0, or anything >= 1.0) degrades to unanimity instead of producing a
    threshold ABOVE the listener count, which would make skipping
    mathematically impossible and wedge the queue forever (T-26-08). The
    floor at 1 guards a zero/negative ``listener_count`` from ever returning
    0 — "0 votes required" would mean an unconditional auto-skip.

    Args:
        listener_count: Number of non-bot members currently in the voice
                         channel.
        majority_ratio:  The fraction of listeners that must vote to skip
                         (default ``config.SKIP_VOTE_MAJORITY_RATIO`` = 0.5).

    Returns:
        The number of votes required, always in ``[1, max(listener_count, 1)]``.
    """
    threshold = math.floor(listener_count * majority_ratio) + 1
    clamped = min(threshold, listener_count) if listener_count > 0 else threshold
    return max(clamped, 1)


# ---------------------------------------------------------------------------
# decide_skip
# ---------------------------------------------------------------------------


def decide_skip(
    *,
    voter_id: int,
    is_requester: bool,
    listener_ids: frozenset[int],
    existing_votes: frozenset[int],
    majority_ratio: float = config.SKIP_VOTE_MAJORITY_RATIO,
) -> tuple[SkipVerdict, frozenset[int]]:
    """Decide the outcome of a single skip-vote cast by ``voter_id``.

    Gate order (cheapest-gate-first, mirroring ``logic/proactive.py`` /
    ``logic/radio.py``):

    1. Requester bypass (D-13a): ``is_requester`` -> ``(SKIP_NOW,
       existing_votes)``. This is FIRST so a requester who already voted
       still bypasses (D-13a's escape hatch from the D-09c duo-holdout —
       they can always pull their own pick). The caller computes
       ``is_requester`` as a plain equality ``voter_id ==
       track.requested_by`` — there is NO special-casing of the bot's own
       id anywhere; D-13b (a bot-queued track never bypasses ANY human)
       falls out for free, since radio/auto-queue tracks carry
       ``requested_by = bot.user.id``, which no human voter can equal.
    2. Solo gate (SC-4): ``len(listener_ids) <= 1`` -> ``(SKIP_NOW,
       existing_votes)``. A solo listener skips instantly — no vote, no
       tally. An empty ``listener_ids`` also takes this branch
       (defensive — there is nobody to vote).
    3. Idempotency (D-14): ``voter_id in existing_votes`` -> ``(
       ALREADY_VOTED, existing_votes)``. A repeat vote from the same user
       does not stack — the returned vote set is byte-identical to the
       input.
    4. Tally: ``new_votes = existing_votes | {voter_id}``. If
       ``len(new_votes) >= required_votes(listener_count=len(listener_ids),
       majority_ratio=majority_ratio)`` -> ``(SKIP_NOW, new_votes)``, else
       ``(VOTE_RECORDED, new_votes)``.

    Counting uses ``len(new_votes)`` — the full updated vote set, with NO
    intersection against ``listener_ids`` anywhere in this arithmetic. D-17
    locks that a departed voter's already-cast vote STAYS COUNTED — a
    walkout cannot strand an open vote below a threshold that just dropped.
    ``listener_ids`` is used ONLY as the live denominator passed to
    ``required_votes``, never to filter the numerator. (A prior sketch in
    26-PATTERNS.md intersects the vote set with the live listener set here —
    that is a direct D-17 violation; do not "fix" this back to that form.)

    Glue dispatches on the returned ``SkipVerdict`` and must never re-derive
    this arithmetic (Phase 10 D-02 rule) — always read ``required_votes``
    for the same number that drives the D-18 tally's ``{required}`` slot.

    Args:
        voter_id:       The Discord user id casting this vote.
        is_requester:   Whether ``voter_id`` requested the current track
                         (``voter_id == track.requested_by`` in glue).
        listener_ids:   The live set of non-bot member ids in the voice
                         channel right now.
        existing_votes: The current track's vote set before this call
                         (``queue.skip_votes_for_current()`` in glue).
        majority_ratio: The fraction of listeners required (default
                         ``config.SKIP_VOTE_MAJORITY_RATIO``).

    Returns:
        A ``(SkipVerdict, frozenset[int])`` tuple — the verdict and the
        updated vote set glue should write back via
        ``queue.record_skip_votes(...)``.
    """
    # Gate 1: requester bypass (D-13a) — FIRST, so an already-voted requester
    # still bypasses. No bot-id special-casing anywhere (D-13b falls out free).
    if is_requester:
        return (SkipVerdict.SKIP_NOW, existing_votes)

    # Gate 2: solo listener (SC-4) — instant skip, no vote, no tally.
    if len(listener_ids) <= 1:
        return (SkipVerdict.SKIP_NOW, existing_votes)

    # Gate 3: idempotency (D-14) — a repeat vote from the same user never stacks.
    if voter_id in existing_votes:
        return (SkipVerdict.ALREADY_VOTED, existing_votes)

    # Gate 4: tally. Count the full new_votes set — no intersection against
    # listener_ids anywhere here. D-17: a departed voter's vote stays counted;
    # listener_ids is the live denominator ONLY, never a numerator filter.
    new_votes = existing_votes | {voter_id}
    needed = required_votes(listener_count=len(listener_ids), majority_ratio=majority_ratio)
    if len(new_votes) >= needed:
        return (SkipVerdict.SKIP_NOW, new_votes)
    return (SkipVerdict.VOTE_RECORDED, new_votes)
