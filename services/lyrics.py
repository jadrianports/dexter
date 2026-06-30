"""Lyrics fetching service: Genius primary, AZLyrics fallback, LRCLIB third fallback.

Exposes LyricsService(genius_token) with async get_lyrics(title, artist).
Pure helpers (build_genius_search_query, build_azlyrics_url, chunk_lyrics,
sanitize_lyrics, extract_azlyrics, strip_lrc_headers) are importable standalone
for unit tests.

Security notes (STRIDE T-03-06 through T-03-09, T-12-03-01 through T-12-03-05):
- build_azlyrics_url strips ALL non-alphanum from artist/song (kills path traversal, @).
- URL host is hard-coded azlyrics.com — no SSRF.
- sanitize_lyrics strips HTML tags and neutralizes @everyone / @here.
- GENIUS_TOKEN is passed only to the Genius() constructor; never logged or echoed.
- _get_azlyrics uses aiohttp.ClientTimeout(total=10) + 500_000-byte cap (DoS guards).
- Genius is wrapped in asyncio.to_thread — never blocks the event loop.
- _LRCLIB_BASE is hard-coded — no user-supplied host reaches the HTTP client (T-12-03-01).
- strip_lrc_headers removes LRC metadata lines before sanitize_lyrics (T-12-03-04).
"""

from __future__ import annotations

import asyncio
import json
import re

import aiohttp
from bs4 import BeautifulSoup
from lyricsgenius import Genius

import config
from utils.logger import log

# Browser User-Agent to avoid AZLyrics bot detection (Pitfall 6)
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Regex to strip feat / remix / version suffixes from track titles (Pattern 9)
_FEAT_RE = re.compile(
    r"\s*[\(\[](?:feat|ft|featuring|remix|edit|version|radio edit)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)

# Strip YouTube/upload noise tags like (Official Audio), [HD], (Lyric Video),
# (Remastered 2009), (Visualizer) — only brackets that CONTAIN a noise keyword,
# so genuine title parentheticals (e.g. "(When September Ends)") are preserved.
_NOISE_RE = re.compile(
    r"\s*[\(\[][^\)\]]*\b(?:"
    r"official|audio|video|music\s*video|m/?v|lyrics?|lyric\s*video|visuali[sz]er|"
    r"hd|hq|4k|8k|remaster(?:ed)?|explicit|clean|live|performance|"
    r"color\s*coded|sub(?:title|bed|s)?|eng\s*sub|full\s*album"
    r")\b[^\)\]]*[\)\]]",
    re.IGNORECASE,
)

# A provided "artist" that is really a YouTube channel name, not the artist
# (e.g. "Trackateering Music", "ArtistVEVO", "Artist - Topic", "XYZ Records").
_JUNK_ARTIST_RE = re.compile(
    r"(?:vevo\b|-\s*topic\b|\bofficial\b|\bmusic\b|\brecords\b|"
    r"\bentertainment\b|\bchannel\b|\bnetwork\b|\bproductions?\b)",
    re.IGNORECASE,
)

# "Artist - Title" separator (hyphen/en-dash/em-dash, space-padded) and trim chars.
_DASH_SPLIT_RE = re.compile(r"\s[-–—]\s")
_DASH_TRIM = " -–—\t"

# LRCLIB API base URL — hard-coded, no user-supplied host reaches the HTTP client (T-12-03-01).
_LRCLIB_BASE = "https://lrclib.net"

# LRC metadata header lines embedded in some LRCLIB plainLyrics records (Pitfall 1 / T-12-03-04).
# Matches a FULL line like "[ti:Title]", "[ar:Artist]", "[offset:0]" etc.
# re.MULTILINE so ^ matches each line start; [^\]]* consumes the tag value safely.
_LRC_HEADER_RE = re.compile(
    r"^\[(ti|ar|al|by|offset|length|re|ve):[^\]]*\]\s*$",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def strip_lrc_headers(text: str) -> str:
    """Strip LRC metadata header lines from LRCLIB plainLyrics text (T-12-03-04).

    Some LRCLIB records embed [ti:...], [ar:...], [al:...], [by:...],
    [offset:0], [length:...], [re:...], [ve:...] lines at the start of
    plainLyrics (verified via live API probe 2026-06-30).

    This helper MUST run BEFORE sanitize_lyrics() — sanitize_lyrics only strips
    HTML and @mentions; it will not remove LRC header lines (Pitfall 1).

    Pure function — no I/O, no async — suitable for unit testing without mocks.
    """
    return _LRC_HEADER_RE.sub("", text).strip()


def build_genius_search_query(title: str, artist: str | None) -> tuple[str, str]:
    """Return a (title, artist) cleaned for a lyricsgenius search_song() call.

    Real YouTube titles are messy and the uploader/"artist" field is unreliable —
    it can be a label, a "- Topic" auto-channel, a VEVO channel, or a random
    re-uploader (e.g. "Rodrigo Lima", "LatinHype"). So:
      - strip feat/remix and noise tags ("(Official Audio)", "[HD]", "(Lyric Video)"),
      - if the title is "Artist - Title", the artist baked into the TITLE wins and
        the uploader field is ignored entirely,
      - otherwise use the uploader only if it isn't an obvious junk channel.

    e.g. ("Arctic Monkeys - Suck It And See", "Rodrigo Lima") -> ("Suck It And See", "Arctic Monkeys")
         ("Billy Joel - Vienna (Audio) (Official Audio)", "Trackateering Music") -> ("Vienna", "Billy Joel")
    Falls back gracefully: empty title -> ("", "").
    """
    t = _NOISE_RE.sub("", _FEAT_RE.sub("", title or ""))
    t = re.sub(r"\s+", " ", t).strip(_DASH_TRIM)
    a = (artist or "").strip()

    parts = _DASH_SPLIT_RE.split(t, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        # "Artist - Title": the embedded artist is canonical; ignore the unreliable
        # uploader field (could be a random re-uploader, not the real artist).
        a, t = parts[0].strip(_DASH_TRIM), parts[1].strip(_DASH_TRIM)
    elif (not a) or _JUNK_ARTIST_RE.search(a):
        # No "Artist - Title" in the title; drop an empty/junk-channel uploader so
        # we search the title alone instead of by a channel name.
        a = ""

    return (t.strip(_DASH_TRIM), a.strip(_DASH_TRIM))


def _artist_matches(wanted: str, got: str) -> bool:
    """Loose artist-equality check for validating a Genius search result.

    Genius can return an unrelated song for a title it doesn't have. When we
    searched with a specific artist, require the matched song's artist to loosely
    match (normalized substring either direction) before trusting the lyrics.
    Returns True when either side is empty (nothing to validate against).
    """
    w = re.sub(r"[^a-z0-9]", "", (wanted or "").lower())
    g = re.sub(r"[^a-z0-9]", "", (got or "").lower())
    if not w or not g:
        return True
    return w in g or g in w


def build_azlyrics_url(artist: str, song: str) -> str:
    """Build AZLyrics URL. Strip ALL non-alphanum from artist and song (T-03-06).

    Kills path-traversal chars (../), @ (SSRF header injection), spaces, and
    any other non-ASCII. Host is hard-coded — no user-supplied host reaches
    the HTTP client.
    """
    a = re.sub(r"[^a-z0-9]", "", artist.lower())
    s = re.sub(r"[^a-z0-9]", "", song.lower())
    return f"https://www.azlyrics.com/lyrics/{a}/{s}.html"


def chunk_lyrics(lyrics: str, page_size: int = config.LYRICS_PAGE_SIZE) -> list[str]:
    """Split lyrics into chunks of at most page_size chars, breaking on newlines.

    Guarantees that no chunk exceeds page_size characters and that all original
    lines appear in the output when rejoined with newlines.
    """
    if not lyrics:
        return []
    lines = lyrics.split("\n")
    pages: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        # +1 for the newline separator that will be added between lines
        if current_len + len(line) + 1 > page_size and current:
            pages.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line) + 1
    if current:
        pages.append("\n".join(current))
    return pages


def sanitize_lyrics(text: str) -> str:
    """Strip HTML tags and neutralize @everyone / @here (T-03-07).

    Defense-in-depth before plan 03-05 sends with allowed_mentions=none().
    Uses BeautifulSoup get_text for robust HTML stripping, then inserts a
    zero-width space (U+200B) after every bare @ to break mention pings.
    """
    # Strip all HTML tags via BeautifulSoup
    soup = BeautifulSoup(text, "html.parser")
    plain = soup.get_text(separator="\n")
    # Neutralize @everyone / @here by inserting zero-width space after @
    # This breaks Discord's mention parsing while keeping text readable
    neutralized = re.sub(r"@(everyone|here)", r"@​\1", plain)
    return neutralized


def extract_azlyrics(html: str) -> str | None:
    """Extract lyrics text from AZLyrics HTML.

    AZLyrics places lyrics in a <div> with no class and no id, between
    HTML comment markers. Returns the longest classless/idless div text
    that is plausibly lyrics (>100 chars). Returns None for alert/bot-detect
    pages (short content) or when no match is found.
    """
    soup = BeautifulSoup(html, "html.parser")
    divs = soup.find_all("div", class_=False, id=False)
    best: str | None = None
    for div in divs:
        text = div.get_text("\n").strip()
        if len(text) > 100:
            # Take the longest candidate (typically the lyrics div)
            if best is None or len(text) > len(best):
                best = text
    return best


# ---------------------------------------------------------------------------
# LyricsService
# ---------------------------------------------------------------------------


class LyricsService:
    """Fetch lyrics with Genius as primary and AZLyrics as fallback.

    Usage:
        service = LyricsService(os.getenv("GENIUS_TOKEN"))
        lyrics = await service.get_lyrics(title, artist)

    If genius_token is None or empty, the Genius path is disabled and only
    AZLyrics is attempted (graceful degradation — Assumption A4).

    Security:
        The genius_token is passed only to the Genius() constructor and stored
        as a private attribute. It is NEVER logged or echoed in any error
        message or embed.
    """

    def __init__(self, genius_token: str | None) -> None:
        if genius_token:
            # NOTE: lyricsgenius 3.x removed the `verbose` kwarg — passing it raises
            # TypeError at init, which (with GENIUS_TOKEN set) aborted on_ready before
            # cogs loaded. Keep only kwargs valid in the installed 3.x signature.
            self._genius = Genius(
                genius_token,
                remove_section_headers=True,  # strip [Verse] / [Chorus] (Pitfall 2)
                retries=1,                    # limit retry amplification (T-03-08)
                timeout=5,                    # Genius() timeout in seconds (T-03-08)
            )
        else:
            self._genius = None
            log.warning("GENIUS_TOKEN not set — Genius lyrics disabled")

    async def get_lyrics(self, title: str, artist: str | None) -> str | None:
        """Fetch lyrics: Genius → AZLyrics → LRCLIB. Returns None if all three fail.

        Cleans the (often messy YouTube) title/artist ONCE here via
        build_genius_search_query, so ALL three sources use the same normalized
        query (previously AZLyrics used the raw title, which produced wrong matches).

        Chain: Genius (search_song via asyncio.to_thread) → AZLyrics (aiohttp scrape)
               → LRCLIB (aiohttp JSON /api/search — third fallback, D-10).
        """
        q_title, q_artist = build_genius_search_query(title, artist)
        if not q_title:
            return None
        lyrics = await self._get_genius(q_title, q_artist)
        if lyrics:
            return lyrics
        lyrics = await self._get_azlyrics(q_title, q_artist)
        if lyrics:
            return lyrics
        return await self._get_lrclib(q_title, q_artist)

    async def _get_genius(self, title: str, artist: str | None) -> str | None:
        """Search Genius for lyrics using asyncio.to_thread (non-blocking).

        Returns sanitized lyrics string or None. The synchronous lyricsgenius
        call is offloaded to a thread so the event loop is never blocked (T-03-08).
        """
        if self._genius is None:
            return None
        try:
            query_title, query_artist = build_genius_search_query(title, artist)
            song = await asyncio.to_thread(
                self._genius.search_song, query_title, query_artist
            )
            if not song or not song.lyrics:
                return None
            # Safety net: Genius can return a confidently-wrong song for a title it
            # doesn't have. If we searched with a specific artist, require the matched
            # artist to loosely match — otherwise treat it as "not found" (a
            # personality "no lyrics" line beats the wrong song's lyrics).
            matched_artist = getattr(song, "artist", "")
            if query_artist and isinstance(matched_artist, str) and matched_artist:
                if not _artist_matches(query_artist, matched_artist):
                    log.info(
                        "Genius returned a non-matching artist (wanted %r, got %r) — rejecting",
                        query_artist,
                        matched_artist,
                    )
                    return None
            # Strip trailing "EmbedXX" / contributor lines (Pitfall 2)
            raw = song.lyrics.split("Embed")[0].strip()
            return sanitize_lyrics(raw) if raw else None
        except Exception as exc:
            log.warning("Genius fetch failed: %s", exc)
            return None

    async def _get_azlyrics(self, title: str, artist: str | None) -> str | None:
        """Fetch lyrics from AZLyrics via aiohttp with timeout and size cap.

        Security (T-03-06 / T-03-08):
        - URL built from sanitized artist/song (no user-supplied URL).
        - aiohttp.ClientTimeout(total=10) caps fetch time.
        - 500_000-byte response cap prevents memory exhaustion.
        - Browser User-Agent to avoid bot detection page (Pitfall 6).
        """
        url = build_azlyrics_url(artist or "", title)
        headers = {"User-Agent": _BROWSER_UA}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        log.warning("AZLyrics returned HTTP %s for %s", resp.status, url)
                        return None
                    html = await resp.text()
                    # DoS guard: cap response size
                    if len(html) > 500_000:
                        log.warning("AZLyrics response too large (%d bytes)", len(html))
                        return None
                    text = extract_azlyrics(html)
                    if not text or len(text) < 50:
                        # Pitfall 6: alert/bot-detection page
                        log.warning("AZLyrics returned suspiciously short content for %s", url)
                        return None
                    return sanitize_lyrics(text)
        except Exception as exc:
            log.warning("AZLyrics fetch failed: %s", exc)
            return None

    async def _get_lrclib(self, title: str, artist: str | None) -> str | None:
        """Fetch plainLyrics from LRCLIB as third lyrics fallback (D-10, UX-03).

        Uses /api/search (NOT /api/get) — more robust because /api/get requires
        a matching duration (±2s) which Dexter may not have; /api/search returns
        an array sorted by relevance, and we pick the first non-instrumental,
        non-null plainLyrics result.

        Security (T-12-03-01 through T-12-03-05):
        - Host hard-coded as _LRCLIB_BASE — no SSRF.
        - title/artist passed via aiohttp params= dict (URL-encoded — no injection).
        - aiohttp.ClientTimeout(total=10) + 500_000-byte cap (DoS guards).
        - strip_lrc_headers() removes LRC metadata lines BEFORE sanitize_lyrics().
        - Non-200 responses (incl. 429) treated as None — no retry storm.
        """
        params: dict[str, str] = {"track_name": title}
        if artist:
            params["artist_name"] = artist
        headers = {"User-Agent": "Dexter/1.2 (Discord music bot)"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{_LRCLIB_BASE}/api/search",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        log.warning("LRCLIB returned HTTP %s for %s / %s", resp.status, title, artist)
                        return None
                    raw = await resp.text()
                    # DoS guard: cap response size (T-12-03-02)
                    if len(raw) > 500_000:
                        log.warning("LRCLIB response too large (%d bytes)", len(raw))
                        return None
                    results = json.loads(raw)
                    # LRCLIB's success shape is an array; a bare object/string/number
                    # (e.g. an error body) would otherwise iterate dict keys / chars and
                    # AttributeError on item.get(...), masked as a silent miss (WR-05).
                    if not isinstance(results, list):
                        log.warning("LRCLIB returned non-list payload for %s / %s", title, artist)
                        return None
                    for item in results:
                        # Skip instrumental tracks (no vocals; plainLyrics is typically null)
                        if item.get("instrumental"):
                            continue
                        plain = item.get("plainLyrics")
                        if not plain:
                            continue
                        # Strip LRC metadata headers before sanitizing (Pitfall 1 / T-12-03-04)
                        cleaned = strip_lrc_headers(plain)
                        if len(cleaned) < 50:
                            continue  # too short to be real lyrics
                        return sanitize_lyrics(cleaned)
                    # All results were instrumental or had no plainLyrics
                    return None
        except Exception as exc:
            log.warning("LRCLIB fetch failed: %s", exc)
            return None
