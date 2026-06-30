"""Pure skip-rate decision logic extracted from OpsCog (UX-02).

All functions in this module are deterministic and side-effect-free: no Discord imports,
no asyncio, no database calls, no random, no datetime.now(), no time.monotonic().

Any nondeterministic value (DB row, guild state) is fetched by the calling cog glue and
passed in as a primitive — following the established seam pattern from logic/playback.py.
"""

from __future__ import annotations


def compute_skip_rate(
    total_plays: int,
    total_skips: int,
    min_plays: int,
) -> float | None:
    """Return 0.0-1.0 skip rate, or None if below min_plays floor (D-08).

    Args:
        total_plays:  Total plays (from song_history COUNT(*)) for this user/guild.
        total_skips:  Total skips (was_skipped=true) within total_plays.
        min_plays:    Minimum play count before a rate is considered meaningful.
                      Pass config.SKIP_STATS_MIN_PLAYS from the calling cog.

    Returns:
        None   — if total_plays < min_plays (floor gate, D-08: suppresses 1/1=100%)
        0.0    — if total_plays == 0 but floor is satisfied (no division-by-zero)
        float  — total_skips / total_plays in [0.0, 1.0] otherwise
    """
    if total_plays < min_plays:
        return None
    if total_plays == 0:
        return 0.0
    return total_skips / total_plays
