"""Pure auto-queue suggestion-validation logic extracted from AICog (UX-04).

All functions in this module are deterministic and side-effect-free: no Discord imports,
no asyncio, no database calls, no random, no datetime.now(), no time.monotonic().

Any nondeterministic value is computed by the calling cog glue and passed in as a
primitive — following the established seam pattern from logic/playback.py (D-06).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Token-normalization constants
# ---------------------------------------------------------------------------

_PUNCT = re.compile(r"[^\w\s]")

# Common YouTube title suffixes/decorators that carry no song-identity signal.
_NOISE_TOKENS: frozenset[str] = frozenset({
    "official", "audio", "video", "music", "lyrics", "lyric",
    "hd", "hq", "4k", "8k", "remastered", "remaster", "explicit",
    "clean", "live", "performance", "feat", "featuring", "ft",
    "visualizer", "mv",
})

# Function words that appear in both YouTube titles and song names and carry
# no discriminating signal (e.g. "The Beatles" vs "Never Give You Up").
_STOP_WORDS: frozenset[str] = frozenset({"the", "a", "an", "in", "of", "and", "or"})


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _normalize_for_match(text: str) -> set[str]:
    """Return significant token set (lowercase, no punct, no noise/stop words, len>=2).

    Steps:
    1. Lowercase.
    2. Replace all punctuation characters with spaces (_PUNCT).
    3. Split on whitespace.
    4. Discard tokens in _NOISE_TOKENS or _STOP_WORDS.
    5. Discard tokens shorter than 2 characters (keeps short artists like "SZA"
       while dropping single-char fragments from punctuation splitting, e.g. "t"
       from "don't").
    """
    lowered = text.lower()
    no_punct = _PUNCT.sub(" ", lowered)
    tokens = no_punct.split()
    return {
        t for t in tokens
        if len(t) >= 2 and t not in _NOISE_TOKENS and t not in _STOP_WORDS
    }


# ---------------------------------------------------------------------------
# Public validator
# ---------------------------------------------------------------------------


def validate_youtube_match(
    youtube_title: str,
    suggested_title: str,
    suggested_artist: str,
) -> bool:
    """Return True if the YouTube result title plausibly matches the suggestion.

    Uses token-set containment: all significant tokens from *suggested_title* and
    *suggested_artist* must be present in the normalized token set of
    *youtube_title*.

    Design notes (D-12 / RESEARCH.md Pattern 4):
    - Token-set containment is preferred over ``difflib.SequenceMatcher`` ratio
      because YouTube titles are much longer than clean song names, making ratios
      artificially low (Anti-Pattern from RESEARCH.md).
    - Empty *suggested_artist* → artist check passes vacuously (optional field).
    - 2-char minimum in _normalize_for_match keeps short artists like "SZA" while
      dropping single-char punctuation fragments (Pitfall 4 from RESEARCH.md).
    """
    yt_tokens = _normalize_for_match(youtube_title)
    title_tokens = _normalize_for_match(suggested_title)
    artist_tokens = _normalize_for_match(suggested_artist)

    title_ok = (not title_tokens) or title_tokens.issubset(yt_tokens)
    artist_ok = (not artist_tokens) or artist_tokens.issubset(yt_tokens)
    return title_ok and artist_ok


def is_recently_skipped_artist(candidate_artist: str, skipped_artists: list[str]) -> bool:
    """Return True if candidate_artist's normalized tokens match any recently-skipped artist.

    Belt-and-suspenders hard filter (D-02) alongside the soft prompt instruction that
    tells Gemini to avoid recently-skipped artists — this function runs independently
    of validate_youtube_match (the hallucination guard, unchanged) as a second,
    unrelated gate over the same candidate.

    Pure and side-effect-free: no Discord imports, no asyncio, no database calls, no
    random, no datetime.now(). Reuses the module's existing _normalize_for_match —
    does NOT duplicate the tokenizer and does NOT use difflib (D-12 anti-pattern).

    Empty candidate_artist or empty skipped_artists -> False (vacuous, never blocks).
    """
    candidate_tokens = _normalize_for_match(candidate_artist)
    if not candidate_tokens:
        return False
    for skipped in skipped_artists:
        skipped_tokens = _normalize_for_match(skipped)
        if skipped_tokens and skipped_tokens.issubset(candidate_tokens):
            return True
    return False
