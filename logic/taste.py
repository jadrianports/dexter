"""Pure taste-episode banding, classification, and decay-resolution logic (TASTE-01/TASTE-02).

All functions in this module are deterministic and side-effect-free: no Discord imports,
no asyncio, no database calls, no random, no datetime.now(), no time.monotonic().

Any nondeterministic value (DB row, config knob) is fetched by the calling task glue
(bot.py::taste_distill_batch, plan 13-04) and passed in as a primitive — following the
established seam pattern from logic/playback.py / logic/skip_stats.py / logic/autoqueue.py.

Accuracy firewall (Critical Rule 12 / D-02): summarize_taste emits ONLY fixed, number-free
template phrases. Raw counts (plays_in_window, plays_before_window, skips_in_window) are read
for classification purposes but are NEVER interpolated into an output string. This keeps
numbers structurally out of the distillation pipe, rather than relying solely on the
downstream contains_number() backstop in services/memory.py.
"""

from __future__ import annotations

import enum


class TastePattern(enum.Enum):
    """A detected listening-behavior pattern for one artist in the lookback window (D-01)."""

    OBSESSION = "obsession"
    NEW_ARRIVAL = "new_arrival"
    STEADY = "steady"
    DROPPED_OFF = "dropped_off"
    NONE = "none"


def has_min_activity(tracks_in_window: int, *, min_tracks: int) -> bool:
    """Return True when tracks_in_window meets or exceeds min_tracks (D-08 gate).

    Mirrors the skip_stats floor pattern: below the floor, distillation is skipped
    entirely for this user (avoids noise facts + wasted embed-limiter/chat-priority
    calls for light/inactive users).

    Args:
        tracks_in_window: Total tracks played by the user in the lookback window.
        min_tracks: Minimum tracks required before distillation is worthwhile.
                    Pass config.TASTE_MIN_ACTIVITY_TRACKS from the calling task.

    Returns:
        False — if tracks_in_window < min_tracks.
        True  — at or above the floor.
    """
    return tracks_in_window >= min_tracks


def classify_artist(
    plays_in_window: int,
    plays_before_window: int,
    skips_in_window: int,
    *,
    obsession_min: int,
    new_arrival_min: int,
    steady_min_baseline: int,
) -> TastePattern:
    """Classify one artist's listening behavior into a TastePattern (D-01).

    Precedence (first match wins):
        1. OBSESSION     — plays_in_window >= obsession_min.
        2. NEW_ARRIVAL   — plays_before_window == 0 and plays_in_window >= new_arrival_min.
        3. STEADY        — plays_before_window >= steady_min_baseline and plays_in_window > 0.
        4. DROPPED_OFF   — plays_before_window >= steady_min_baseline and plays_in_window == 0.
        5. NONE          — none of the above (not a notable pattern this cycle).

    Args:
        plays_in_window: Plays of this artist within the recent lookback window
                          (config.TASTE_LOOKBACK_DAYS).
        plays_before_window: Plays of this artist in the baseline period preceding
                              the lookback window (config.TASTE_BASELINE_DAYS).
        skips_in_window: Skips of this artist within the lookback window. Accepted
                          for future-proofing (e.g. skip-adjusted confidence) but not
                          consulted by the current precedence rules.
        obsession_min: config.TASTE_OBSESSION_MIN_PLAYS.
        new_arrival_min: config.TASTE_NEW_ARRIVAL_MIN_PLAYS.
        steady_min_baseline: config.TASTE_STEADY_MIN_BASELINE.

    Returns:
        A TastePattern member.
    """
    del skips_in_window  # accepted for signature stability; unused by current precedence rules

    if plays_in_window >= obsession_min:
        return TastePattern.OBSESSION
    if plays_before_window == 0 and plays_in_window >= new_arrival_min:
        return TastePattern.NEW_ARRIVAL
    if plays_before_window >= steady_min_baseline and plays_in_window > 0:
        return TastePattern.STEADY
    if plays_before_window >= steady_min_baseline and plays_in_window == 0:
        return TastePattern.DROPPED_OFF
    return TastePattern.NONE


_PHRASE_TEMPLATES: dict[TastePattern, str] = {
    TastePattern.OBSESSION: "played {artist} heavily this week",
    TastePattern.NEW_ARRIVAL: "{artist} is new for them this week",
    TastePattern.STEADY: "keeps coming back to {artist}",
    TastePattern.DROPPED_OFF: "dropped off from {artist} this week",
}


def summarize_taste(
    artist_rows,
    *,
    obsession_min: int,
    new_arrival_min: int,
    steady_min_baseline: int,
) -> list[str]:
    """Turn raw per-artist play/skip counts into number-free descriptor phrases (D-02).

    Reads plays_in_window / plays_before_window / skips_in_window off each row via
    item access (row["..."]) — works with plain dicts or asyncpg.Record alike.
    Classifies each row via classify_artist and emits one fixed template phrase per
    non-NONE pattern. NONE-classified artists are omitted from the output.

    FIREWALL (D-02 / Critical Rule 12): no returned phrase ever interpolates a count —
    only the artist name and a fixed qualitative template. Never raises for any list
    of dict/Record rows carrying the expected integer count fields + an "artist" field.

    Args:
        artist_rows: Iterable of dict-like rows, each with keys "artist",
                     "plays_in_window", "plays_before_window", "skips_in_window".
        obsession_min: config.TASTE_OBSESSION_MIN_PLAYS.
        new_arrival_min: config.TASTE_NEW_ARRIVAL_MIN_PLAYS.
        steady_min_baseline: config.TASTE_STEADY_MIN_BASELINE.

    Returns:
        list[str] — number-free phrases, one per notable (non-NONE) artist. Empty
        list when artist_rows is empty or no artist is notable.
    """
    phrases: list[str] = []
    for row in artist_rows:
        pattern = classify_artist(
            row["plays_in_window"],
            row["plays_before_window"],
            row["skips_in_window"],
            obsession_min=obsession_min,
            new_arrival_min=new_arrival_min,
            steady_min_baseline=steady_min_baseline,
        )
        template = _PHRASE_TEMPLATES.get(pattern)
        if template is None:
            continue
        phrases.append(template.format(artist=row["artist"]))
    return phrases


def resolve_decay_days(
    kind: str,
    *,
    default_days: int,
    kind_overrides: dict[str, int],
) -> int:
    """Resolve the decay horizon (in days) for a memory kind (D-03).

    Args:
        kind: The memory "kind" string (e.g. "taste_episode", "milestone").
        default_days: config.MEMORY_DECAY_DAYS — fallback for kinds absent from
                      kind_overrides (preserves Phase 11 semantics unchanged).
        kind_overrides: config.MEMORY_DECAY_DAYS_BY_KIND — per-kind overrides.

    Returns:
        kind_overrides.get(kind, default_days).
    """
    return kind_overrides.get(kind, default_days)
