"""Pure proactive-callback firing-decision gate (Phase 16 / PROACT-01 / D-02).

All functions in this module are deterministic and side-effect-free: no ``random``,
no ``asyncio``, no ``datetime``, no ``discord``.

Any nondeterministic value (the chance roll, the per-user daily counter, the
opt-out flag read from the database) is computed by the calling cog glue and
passed in as a primitive — following the established seam pattern from
``logic/roasts.py`` (Phase 10 D-01/D-02/D-03).

This gate implements only D-02 steps 1-3 of the proactive-callback firing logic
(opt-out -> chance roll -> daily cap). D-02 step 4 (the recall-floor silent-skip,
i.e. only fire if ``services.memory.recall`` actually returns a memory clearing
``config.MEMORY_SIMILARITY_FLOOR``) is deliberately NOT implemented here — that
check requires async I/O (a database/vector-search round trip) and therefore
lives in the cog glue (plan 16-03), evaluated only after this gate returns True.

Locked by tests/test_proactive_logic.py (mock-free boundary coverage).
"""

from __future__ import annotations

import config

# ---------------------------------------------------------------------------
# should_fire_proactive_callback
# ---------------------------------------------------------------------------


def should_fire_proactive_callback(
    *,
    opted_out: bool,
    chance_roll: float,
    daily_count: int,
    chance: float = config.PROACTIVE_CALLBACK_CHANCE,
    daily_cap: int = config.PROACTIVE_CALLBACK_DAILY_CAP,
) -> bool:
    """Decide whether a qualifying chat message should fire a proactive callback.

    Mirrors the short-circuit, cheapest-gate-first ordering of
    ``logic/roasts.py::decide_ambient_roast`` (Phase 10 convention), applied to
    D-02's three synchronous gates in order:

    1. Opt-out gate: ``opted_out`` -> False immediately (cheapest check, and the
       user's explicit preference always wins).
    2. Chance gate: ``chance_roll >= chance`` -> False (roll missed; live glue
       uses ``random.random() < chance`` to proceed, so the inverse fails here —
       identical boundary convention to ``decide_ambient_roast``: exactly-at-
       threshold fails, one-under passes).
    3. Daily-cap gate: ``daily_count >= daily_cap`` -> False (the cap is an
       inclusive ceiling: a user already at the cap does not get one more).
    4. All three gates passed -> True.

    D-02 step 4 (the recall-floor silent-skip) is deliberately NOT evaluated
    here — it is async I/O (``services.memory.recall``) and lives in the cog
    glue (plan 16-03), checked only after this function returns True.

    Args:
        opted_out:   Whether the message author has paused proactive callbacks
                     (``database.get_proactive_opt_out(pool, user_id)`` in glue).
        chance_roll: Pre-rolled float in [0, 1). Pass ``random.random()`` from glue.
        daily_count: Number of proactive callbacks already fired for this user
                     on the current calendar day. Compute from the in-memory
                     per-user counter (``EventsCog._proactive_daily_counts``) in
                     glue; reset the counter at day rollover.
        chance:      Probability threshold for the chance gate (default
                     ``config.PROACTIVE_CALLBACK_CHANCE`` = 0.10 — strictly below
                     both ``config.UNPROMPTED_ROAST_CHANCE`` (0.30) and
                     ``config.MEMORY_CALLBACK_CHANCE`` (0.35)).
        daily_cap:   Maximum callbacks allowed per user per calendar day
                     (default ``config.PROACTIVE_CALLBACK_DAILY_CAP`` = 1).

    Returns:
        True only if the user is not opted out, the chance roll passed, and the
        daily cap has not yet been reached. The caller must still check the
        recall floor (D-02 step 4) before actually firing a callback.
    """
    # Gate 1: opt-out (cheapest check, and the user's explicit preference wins)
    if opted_out:
        return False

    # Gate 2: chance roll (must be strictly less than chance to proceed)
    if chance_roll >= chance:
        return False

    # Gate 3: per-user daily cap (inclusive ceiling — at-cap fails)
    if daily_count >= daily_cap:
        return False

    return True
