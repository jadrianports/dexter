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

from typing import Mapping

# ---------------------------------------------------------------------------
# decide_ambient_channel
# ---------------------------------------------------------------------------


def decide_ambient_channel(*, config_row: Mapping | None) -> int | None:
    """Decide the ambient channel id for a guild from its cached config row.

    D-01: strict resolution — the config row or silence. No fallback chain.

    Args:
        config_row: The guild's cached ``guild_config`` row (an ``asyncpg.Record``
            or any ``Mapping`` with ``configured`` and ``ambient_channel_id`` keys),
            or ``None`` when the guild has no row at all (never configured).

    Returns:
        The ambient channel id as an ``int`` only when ``config_row`` is not
        ``None``, ``configured`` is truthy, and ``ambient_channel_id`` is not
        ``None``. Otherwise ``None`` (structural silence):

        - No row at all (guild never configured) -> ``None``.
        - Row present but ``configured`` is ``False`` -> ``None``, even if
          ``ambient_channel_id`` happens to be set (e.g. a `/setup` that was
          started then explicitly disabled).
        - Row present, ``configured`` is ``True``, but ``ambient_channel_id`` is
          ``None`` -> ``None`` (should not normally happen, but fails closed).
        - Row present, ``configured`` is ``True``, ``ambient_channel_id`` set ->
          the channel id, coerced with ``int(...)`` since the column is stored as
          TEXT. A non-coercible value (e.g. ``""`` or ``"abc"``) also fails
          closed to ``None`` (WR-01) rather than raising ``ValueError`` — the
          column has no ``CHECK`` constraint, so a corrupted row must degrade to
          silence like every other uncertain-state branch in this module.
    """
    if config_row is None:
        return None

    if not config_row.get("configured", False):
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


def is_ambient_channel(*, config_row: Mapping | None, channel_id: int) -> bool:
    """Decide whether ``channel_id`` is this guild's configured ambient channel.

    Replaces the two bare-equality gates
    (``message.channel.id == config.DEXTER_CHANNEL_ID``) in
    ``cogs/events.py::on_message`` (CONFIG-02) with a single predicate that
    delegates the row decision to :func:`decide_ambient_channel` instead of
    re-deriving the branch.

    Args:
        config_row: The guild's cached ``guild_config`` row, or ``None``.
        channel_id: The channel id to test (e.g. ``message.channel.id``).

    Returns:
        ``True`` only if :func:`decide_ambient_channel` resolves a channel id for
        this guild AND it equals ``channel_id``. ``False`` for an unconfigured
        guild (including a ``None`` row) and for any non-matching channel.
    """
    decided = decide_ambient_channel(config_row=config_row)
    return decided is not None and decided == channel_id
