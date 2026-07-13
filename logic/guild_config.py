"""Pure per-guild ambient-channel decision seam (Phase 18 / CONFIG-02 / D-01 / D-05).

All functions in this module are deterministic and side-effect-free: no ``random``,
no ``asyncio``, no ``datetime``, no ``discord``.

The cached config row (an ``asyncpg.Record`` or a plain mapping) is read by the
calling service/glue and passed in here as a primitive — following the established
seam pattern from ``logic/proactive.py`` and ``logic/vision.py`` (Phase 10 D-01/D-02).

D-01 (strict resolution): ambient surfaces resolve *only* the guild's own
``guild_config.ambient_channel_id`` when ``configured`` is true. A missing row, an
unconfigured row, or a configured row with no channel id all resolve to silence
(``None``). This makes "silent until `/setup`" (CONFIG-04) a structural property of
the decision function rather than a behavior every ambient caller must remember to
enforce.

No discord I/O (``guild.get_channel``, permission checks, channel-existence checks)
belongs here — that is service-tier work (``services/guild_config.py``'s
``resolve_ambient_channel`` / ``resolve_announce_channel``), which dispatches on the
value this module returns and never re-derives the branch (Phase 10 D-02 convention).

Locked by tests/test_guild_config_logic.py (mock-free boundary coverage).
"""

from __future__ import annotations

import enum
from typing import Mapping

# ---------------------------------------------------------------------------
# AmbientSurface
# ---------------------------------------------------------------------------


class AmbientSurface(enum.Enum):
    """Which ambient behavior category a call site belongs to (D-22).

    Required keyword-only on every function below (no default) — a future
    ambient surface cannot resolve a channel or pass the predicate without
    declaring its intent. This extends the Phase 18 D-02 structural-safety
    principle surface-wise: a call site that forgets to pass ``surface=``
    fails loudly (``TypeError``) rather than silently defaulting to a gate
    it doesn't actually belong to.
    """

    ROAST = "roast"
    """Gated by ``ambient_roasts_enabled``: voice-join/leave/move roasts,
    proactive callbacks, repeat-song + milestone roasts, emoji reactions."""

    VISION = "vision"
    """Gated by ``vision_roasts_enabled``: image roasts only."""

    PRESENCE = "presence"
    """Gated by ``ambient_roasts_enabled`` (same column as ROAST, D-18) — a
    distinct member for the startup message (home-guild-only, D-23) and the
    idle-loneliness message."""


# ---------------------------------------------------------------------------
# decide_ambient_channel
# ---------------------------------------------------------------------------


def decide_ambient_channel(*, config_row: Mapping | None, surface: AmbientSurface) -> int | None:
    """Decide the ambient channel id for a guild from its cached config row.

    D-01: strict resolution — the config row or silence. No fallback chain.
    D-22: surface-keyed — ``surface`` picks which toggle column gates
    resolution, in addition to the pre-existing ``configured``/channel checks.

    Args:
        config_row: The guild's cached ``guild_config`` row (an ``asyncpg.Record``
            or any ``Mapping`` with ``configured`` and ``ambient_channel_id`` keys),
            or ``None`` when the guild has no row at all (never configured).
        surface: Which ambient behavior category is asking. Required keyword-only,
            no default — see :class:`AmbientSurface`.

    Returns:
        The ambient channel id as an ``int`` only when ``config_row`` is not
        ``None``, ``configured`` is truthy, the surface's toggle column is not
        explicitly ``False``, and ``ambient_channel_id`` is not ``None``.
        Otherwise ``None`` (structural silence):

        - No row at all (guild never configured) -> ``None``.
        - Row present but ``configured`` is ``False`` -> ``None``, even if
          ``ambient_channel_id`` happens to be set (e.g. a `/setup` that was
          started then explicitly disabled).
        - Row present, ``configured`` is ``True``, but ``silenced`` is
          ``True`` -> ``None`` (D-14: the owner kill-switch silences a guild
          structurally, at the same choke point as the toggle columns). A
          missing ``silenced`` key defaults to ``False`` (fail-open, matching
          the column ``DEFAULT false`` and keeping every pre-Phase-20
          test/mock that omits ``silenced`` byte-identical).
        - Row present, ``configured`` is ``True``, but the surface's toggle
          column (``vision_roasts_enabled`` for VISION, else
          ``ambient_roasts_enabled``) is ``False`` -> ``None``. A missing
          toggle key defaults to ``True`` (fail-open, matching the column
          ``DEFAULT true``).
        - Row present, ``configured`` is ``True``, toggle not ``False``, but
          ``ambient_channel_id`` is ``None`` -> ``None`` (should not normally
          happen, but fails closed).
        - Row present, ``configured`` is ``True``, toggle not ``False``,
          ``ambient_channel_id`` set -> the channel id, coerced with
          ``int(...)`` since the column is stored as TEXT. A non-coercible
          value (e.g. ``""`` or ``"abc"``) also fails closed to ``None``
          (WR-01) rather than raising ``ValueError`` — the column has no
          ``CHECK`` constraint, so a corrupted row must degrade to silence
          like every other uncertain-state branch in this module.
    """
    if config_row is None:
        return None

    if not config_row.get("configured", False):
        return None

    if config_row.get("silenced", False):  # D-14: silenced guild -> structural silence
        return None

    toggle_column = "vision_roasts_enabled" if surface is AmbientSurface.VISION else "ambient_roasts_enabled"
    if not config_row.get(toggle_column, True):
        return None

    channel_id = config_row.get("ambient_channel_id")
    if channel_id is None:
        return None
    try:
        return int(channel_id)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# is_ambient_channel
# ---------------------------------------------------------------------------


def is_ambient_channel(*, config_row: Mapping | None, channel_id: int, surface: AmbientSurface) -> bool:
    """Decide whether ``channel_id`` is this guild's configured ambient channel.

    Replaces the two bare-equality gates
    (``message.channel.id == config.DEXTER_CHANNEL_ID``) in
    ``cogs/events.py::on_message`` (CONFIG-02) with a single predicate that
    delegates the row decision to :func:`decide_ambient_channel` instead of
    re-deriving the branch.

    Args:
        config_row: The guild's cached ``guild_config`` row, or ``None``.
        channel_id: The channel id to test (e.g. ``message.channel.id``).
        surface: Which ambient behavior category is asking. Required
            keyword-only, threaded straight through to
            :func:`decide_ambient_channel` — see :class:`AmbientSurface`.

    Returns:
        ``True`` only if :func:`decide_ambient_channel` resolves a channel id for
        this guild AND it equals ``channel_id``. ``False`` for an unconfigured
        guild (including a ``None`` row), a toggled-off surface, and any
        non-matching channel.
    """
    decided = decide_ambient_channel(config_row=config_row, surface=surface)
    return decided is not None and decided == channel_id


# ---------------------------------------------------------------------------
# should_welcome_guild
# ---------------------------------------------------------------------------


def should_welcome_guild(*, inserted_row: object | None) -> bool:
    """Pure wrapper naming the D-14 rule: welcome iff the INSERT actually inserted.

    Deliberately trivial — the substance is the anti-pattern it encodes: never
    derive this from a cache-miss check (e.g. ``bot.guild_config.get(guild_id)
    is None``), which conflates "never configured" with "this event handler
    happened to run before the cache was populated" and would replay the
    welcome message on every restart/cache-miss race (the D-14 scar, see
    Pitfall 3). The one true signal is whether
    ``database.insert_guild_config_if_absent``'s own ``RETURNING`` clause
    actually produced a row (a genuine first-time insert) versus ``None``
    (the row already existed — ``ON CONFLICT DO NOTHING`` fired instead).

    Args:
        inserted_row: The return value of
            ``database.insert_guild_config_if_absent`` — a fresh
            ``asyncpg.Record`` on a genuine insert, or ``None`` on conflict.

    Returns:
        ``True`` only when ``inserted_row`` is not ``None``.
    """
    return inserted_row is not None


# ---------------------------------------------------------------------------
# decide_interaction_allowed
# ---------------------------------------------------------------------------


def decide_interaction_allowed(
    *,
    is_owner: bool,
    has_guild: bool,
    blocked: bool,
    silenced: bool,
) -> bool:
    """The pure OWNER-05 slash-command choke-point predicate (D-13).

    This is the single authorization decision `DexterCommandTree.interaction_check`
    (the slash-command choke point OWNER-05 names) dispatches on — the glue
    computes ``is_owner``/``has_guild``/``blocked``/``silenced`` and never
    re-derives the branch order here (Phase 10 D-02).

    Deliberately NOT modeled here: the boot-race "service absent -> fail open"
    case (``bot.guild_config`` not yet constructed). That is a GLUE concern
    (Phase 10 D-02 / Pitfall 5) distinct from this predicate's steady-state
    authorization logic — callers must resolve the boot race before calling
    this function.

    Args:
        is_owner: Whether the invoking user is the bot owner. Checked FIRST —
            the owner is never locked out, even by self-silencing/blocking the
            home guild (D-13; T-20-06 owner-DoS-of-self mitigation).
        has_guild: Whether the interaction has a guild at all
            (``interaction.guild is not None``). ``False`` means a DM or other
            guild-less interaction, which is always allowed (D-13 DM
            exemption).
        blocked: Whether the guild is on the blocklist. Checked defensively
            even though a blocked guild is normally already left (D-11
            block-implies-leave) — covers the block-written-while-leave-in-
            flight window (T-20-03).
        silenced: Whether the guild has been silenced via ``/guilds silence``.

    Returns:
        ``True`` to allow the interaction to proceed; ``False`` to refuse it
        (the glue in `DexterCommandTree.interaction_check` sends the D-12
        in-persona ephemeral refusal and returns this value).

        - ``is_owner`` is ``True`` -> ``True``, regardless of every other flag.
        - ``has_guild`` is ``False`` (DM/guild-less) -> ``True``.
        - ``blocked`` or ``silenced`` is ``True`` -> ``False``.
        - Otherwise -> ``True`` (allow).
    """
    if is_owner:
        return True
    if not has_guild:
        return True
    if blocked or silenced:
        return False
    return True
