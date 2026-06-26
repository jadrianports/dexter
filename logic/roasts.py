"""Pure ambient-roast decision logic extracted from EventsCog (TEST-03).

All functions in this module are deterministic and side-effect-free: no ``random``,
no ``asyncio``, no ``datetime``, no ``discord``.

Any nondeterministic value (random rolls, monotonic clock delta, local hour) is computed
by the calling cog glue and passed in as a primitive — following the established seam
pattern from ``personality/roasts.py`` ``is_late_night(hour)`` (D-06).

Decision functions here are the single source of truth for the following live code paths
(D-01/D-02):
  - ``cogs/events.py`` ``on_voice_state_update``  — chance/cooldown/late-night/event dispatch
  - ``cogs/events.py`` ``_check_ambient_cooldown`` — delegates to ``cooldown_elapsed``

Phase 10 coverage locked by tests/test_roast_logic.py (D-03/TEST-03).
"""

from __future__ import annotations

import enum

import config
from personality.roasts import is_late_night


# ---------------------------------------------------------------------------
# Enum: possible outcomes of decide_ambient_roast
# ---------------------------------------------------------------------------


class RoastScenario(enum.Enum):
    """What ambient-roast scenario the ``on_voice_state_update`` glue should fire."""

    NONE = "none"
    """No roast — a gate (chance, cooldown, or late-night second roll) failed."""

    JOIN = "join"
    """Normal voice-join roast (not late-night)."""

    LATE_NIGHT = "late_night"
    """Late-night join roast (hour within config.LATE_NIGHT_HOURS, second roll passed)."""

    LEAVE = "leave"
    """Voice-leave roast (no late-night branch for leave events)."""


# ---------------------------------------------------------------------------
# 1. cooldown_elapsed
# ---------------------------------------------------------------------------


def cooldown_elapsed(seconds_since_last: float, ceiling_seconds: float) -> bool:
    """Return True if enough time has elapsed since the last ambient roast.

    Mirrors the comparison in ``EventsCog._check_ambient_cooldown`` exactly:
    ``>=`` means exactly-at-ceiling is allowed (a roast fired exactly 300 s ago
    is eligible again immediately).

    Args:
        seconds_since_last: Monotonic seconds since the last roast for this user.
            Compute as ``asyncio.get_event_loop().time() - last`` in the cog glue.
        ceiling_seconds:    Minimum interval required between roasts for the same user.

    Returns:
        True if a roast is allowed (enough time has passed or no prior roast recorded).
    """
    return seconds_since_last >= ceiling_seconds


# ---------------------------------------------------------------------------
# 2. decide_ambient_roast
# ---------------------------------------------------------------------------


def decide_ambient_roast(
    *,
    event: str,
    chance_roll: float,
    late_night_roll: float,
    local_hour: int,
    seconds_since_last_roast: float,
    chance: float = config.UNPROMPTED_ROAST_CHANCE,
    late_night_chance: float = config.LATE_NIGHT_ROAST_CHANCE,
    ceiling_seconds: float = config.AMBIENT_ROAST_CEILING_SECONDS,
) -> RoastScenario:
    """Decide which ambient-roast scenario to fire for a voice-state event.

    Mirrors the trigger/gating nest in ``cogs/events.py`` ``on_voice_state_update``
    (D-02 true extraction). Evaluation order is preserved exactly:

    1. Chance gate: ``chance_roll >= chance`` → NONE (roll missed; live code uses
       ``random.random() < chance`` to proceed, so the inverse is NONE).
    2. Cooldown gate: ``not cooldown_elapsed(seconds_since_last_roast, ceiling_seconds)``
       → NONE (not enough time has passed since the last roast for this user).
    3. Event dispatch:
       - ``"join"`` + late night (``is_late_night(local_hour)``) → second roll:
           ``late_night_roll < late_night_chance`` → LATE_NIGHT; else → NONE.
       - ``"join"`` + not late night → JOIN.
       - ``"leave"`` → LEAVE (no late-night branch for leave events).
       - Any other event → NONE.

    Args:
        event:                 ``"join"``, ``"leave"``, or any other string.
        chance_roll:           Pre-rolled float in [0, 1). Pass ``random.random()`` from glue.
        late_night_roll:       Second pre-rolled float for the late-night branch (join only).
                               Pass ``random.random()`` from glue; pass ``0.0`` for leave.
        local_hour:            Hour of day in the guild's local timezone (0–23). Compute via
                               ``datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour``
                               in the cog glue (D-06 / CLAUDE.md community-time gotcha).
        seconds_since_last_roast: Monotonic seconds since the last roast for this user.
                               Compute as ``asyncio.get_event_loop().time() - last`` in glue.
        chance:                Probability threshold for the initial chance gate
                               (default ``config.UNPROMPTED_ROAST_CHANCE`` = 0.30).
        late_night_chance:     Probability threshold for the late-night second roll
                               (default ``config.LATE_NIGHT_ROAST_CHANCE`` = 0.50).
        ceiling_seconds:       Minimum cooldown interval in seconds
                               (default ``config.AMBIENT_ROAST_CEILING_SECONDS`` = 300).

    Returns:
        A ``RoastScenario`` the cog glue dispatches on. NONE means no roast.
    """
    # Gate 1: initial chance roll (must be strictly less than chance to proceed)
    if chance_roll >= chance:
        return RoastScenario.NONE

    # Gate 2: per-user cooldown (ceiling_seconds must have elapsed)
    if not cooldown_elapsed(seconds_since_last_roast, ceiling_seconds):
        return RoastScenario.NONE

    # Gate 3: event-specific dispatch
    if event == "join":
        if is_late_night(local_hour):
            # Second roll for the late-night branch
            if late_night_roll < late_night_chance:
                return RoastScenario.LATE_NIGHT
            else:
                return RoastScenario.NONE  # Late-night roll failed — no roast
        else:
            return RoastScenario.JOIN

    if event == "leave":
        return RoastScenario.LEAVE  # No late-night branch for leave

    # Unknown event (e.g. channel-switch "move" — not a roast trigger)
    return RoastScenario.NONE
