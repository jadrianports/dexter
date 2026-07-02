"""Pure vision-roast firing-decision gate (Phase 17 / VIS-01 / D-04).

All functions in this module are deterministic and side-effect-free: no ``random``,
no ``asyncio``, no ``datetime``, no ``discord``.

Any nondeterministic value (the chance roll, the per-user cooldown state, the
opt-out flag read from the database) is computed by the calling cog glue and
passed in as a primitive — following the established seam pattern from
``logic/roasts.py`` and ``logic/proactive.py`` (Phase 10 / 16 convention).

The per-user cooldown is NOT recomputed here: the glue calls the existing
``logic.roasts.cooldown_elapsed(seconds_since_last, config.VISION_ROAST_COOLDOWN_SECONDS)``
helper and passes the resulting bool in as ``cooldown_elapsed``.

Locked by tests/test_vision_logic.py (mock-free boundary coverage).
"""

from __future__ import annotations

import config


# ---------------------------------------------------------------------------
# should_fire_vision_roast
# ---------------------------------------------------------------------------


def should_fire_vision_roast(
    *,
    opted_out: bool,
    cooldown_elapsed: bool,
    chance_roll: float,
    chance: float = config.VISION_ROAST_CHANCE,
) -> bool:
    """Decide whether a posted image should trigger an unprompted vision roast.

    Mirrors the short-circuit, cheapest-gate-first ordering of
    ``logic/proactive.py::should_fire_proactive_callback`` (Phase 16 convention),
    applied to D-04's three synchronous gates in order:

    1. Opt-out gate: ``opted_out`` -> False immediately (cheapest check, and the
       user's explicit preference — reusing Phase 16's ``proactive_opt_out``,
       D-03 step 4 — always wins).
    2. Cooldown gate: ``not cooldown_elapsed`` -> False (the per-user cooldown
       ceiling has not yet elapsed; the glue computes this via the existing
       ``logic.roasts.cooldown_elapsed`` helper — do NOT reimplement cooldown math here).
    3. Chance gate: ``chance_roll >= chance`` -> False (roll missed; live glue
       uses ``random.random() < chance`` to proceed, so the inverse fails here —
       identical boundary convention to ``decide_ambient_roast`` /
       ``should_fire_proactive_callback``: exactly-at-threshold fails, one-under passes).
    4. All three gates passed -> True.

    Args:
        opted_out:        Whether the message author has paused unprompted callbacks
                          (``database.get_proactive_opt_out(pool, user_id)`` in glue).
        cooldown_elapsed: Whether the per-user vision-roast cooldown has elapsed.
                          Compute in glue via
                          ``logic.roasts.cooldown_elapsed(seconds_since_last,
                          config.VISION_ROAST_COOLDOWN_SECONDS)``.
        chance_roll:      Pre-rolled float in [0, 1). Pass ``random.random()`` from glue.
        chance:           Probability threshold for the chance gate (default
                          ``config.VISION_ROAST_CHANCE`` = 0.12 — strictly below both
                          ``config.UNPROMPTED_ROAST_CHANCE`` (0.30) and
                          ``config.MEMORY_CALLBACK_CHANCE`` (0.35)).

    Returns:
        True only if the user is not opted out, the cooldown has elapsed, and the
        chance roll passed. The caller still performs the actual image read,
        Gemini call, and silent-skip-vs-fallback dispatch (VIS-02, plan 17-02).
    """
    # Gate 1: opt-out (cheapest check, and the user's explicit preference wins)
    if opted_out:
        return False

    # Gate 2: per-user cooldown (must have elapsed — computed by glue via cooldown_elapsed)
    if not cooldown_elapsed:
        return False

    # Gate 3: chance roll (must be strictly less than chance to proceed)
    if chance_roll >= chance:
        return False

    return True
