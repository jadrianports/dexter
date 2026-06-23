"""Rolling in-memory performance metrics aggregate (Phase 6, PERF-06).

A single PerfMetrics instance is attached to the bot at startup
(bot.perf_metrics) and fed timing deltas from the audio/youtube pipeline.
Its summary() dict is surfaced in the /stats owner embed (D-18).

No external dependencies — uses only Python stdlib (collections.deque).
Thread-safe for single-writer / multiple-reader access (deque append is GIL-safe).
"""

from __future__ import annotations

import collections


class PerfMetrics:
    """Rolling in-memory aggregate for pipeline timing (D-17/D-18).

    Each metric uses a collections.deque with a fixed maxlen so only the last
    `window` samples are retained — older observations are automatically
    discarded. summary() is O(n) where n <= window.

    Attributes:
        cache_hits: deque[bool] — True = resolution-cache hit, False = miss.
        download_times: deque[float] — seconds spent in async_download.
        search_times: deque[float] — seconds spent in async_search.
        ttfa_times: deque[float] — time-to-first-audio (queue → voice.play).
    """

    def __init__(self, window: int = 50) -> None:
        self.cache_hits: collections.deque[bool] = collections.deque(maxlen=window)
        self.download_times: collections.deque[float] = collections.deque(maxlen=window)
        self.search_times: collections.deque[float] = collections.deque(maxlen=window)
        self.ttfa_times: collections.deque[float] = collections.deque(maxlen=window)

    # ------------------------------------------------------------------
    # Record methods — called from audio/youtube pipeline
    # ------------------------------------------------------------------

    def record_cache_result(self, hit: bool) -> None:
        """Record a resolution-cache hit (True) or miss (False)."""
        self.cache_hits.append(hit)

    def record_download(self, elapsed: float) -> None:
        """Record time (seconds) spent downloading a track to cache."""
        self.download_times.append(elapsed)

    def record_search(self, elapsed: float) -> None:
        """Record time (seconds) spent in a YouTube search."""
        self.search_times.append(elapsed)

    def record_ttfa(self, elapsed: float) -> None:
        """Record time-to-first-audio: from /play invocation to voice.play()."""
        self.ttfa_times.append(elapsed)

    # ------------------------------------------------------------------
    # Summary — fed to /stats embed
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Return a snapshot dict for the /stats perf section.

        Returns:
            {
                "cache_hit_rate": float,  # 0.0–100.0 percentage
                "avg_download_s": float,  # average download time in seconds
                "avg_ttfa_s":     float,  # average time-to-first-audio in seconds
                "avg_search_s":   float,  # average search time in seconds
                "samples":        int,    # number of cache-hit observations
            }

        All averages return 0.0 when the corresponding deque is empty (no
        ZeroDivisionError).
        """
        hit_rate = (
            sum(self.cache_hits) / len(self.cache_hits) * 100
            if self.cache_hits else 0.0
        )
        avg_dl = (
            sum(self.download_times) / len(self.download_times)
            if self.download_times else 0.0
        )
        avg_ttfa = (
            sum(self.ttfa_times) / len(self.ttfa_times)
            if self.ttfa_times else 0.0
        )
        avg_search = (
            sum(self.search_times) / len(self.search_times)
            if self.search_times else 0.0
        )
        return {
            "cache_hit_rate": hit_rate,
            "avg_download_s": avg_dl,
            "avg_ttfa_s": avg_ttfa,
            "avg_search_s": avg_search,
            "samples": len(self.cache_hits),
        }
