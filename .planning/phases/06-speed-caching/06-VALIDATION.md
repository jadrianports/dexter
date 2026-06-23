---
phase: 6
slug: speed-caching
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-24
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (already installed) |
| **Config file** | `pytest.ini` / `pyproject.toml` (existing) |
| **Quick run command** | `pytest tests/test_phase6_perf.py tests/test_audio.py tests/test_youtube.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~30 seconds (quick); full suite includes live-DB integration tests |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_phase6_perf.py tests/test_audio.py tests/test_youtube.py -x`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 1 | PERF-01 | — | Prefetch task spawned when next track exists | unit | `pytest tests/test_phase6_perf.py::test_prefetch_task_spawned -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-01 | — | Prefetch skips already-cached tracks | unit | `pytest tests/test_phase6_perf.py::test_prefetch_skips_cached -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-01 | — | Stale prefetch task (generation guard) discards result | unit | `pytest tests/test_phase6_perf.py::test_prefetch_stale_gen -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-02 | — | Copy path logged for opus source | unit | `pytest tests/test_youtube.py::TestCodecLogging -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-02 | — | Transcode path logged for non-opus source | unit | `pytest tests/test_youtube.py::TestCodecLogging::test_transcode_logged -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-03 | T (V5) | `normalize_search_query` casing/whitespace normalization | unit | `pytest tests/test_phase6_perf.py::TestNormalizeQuery -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-03 | T (V5) | Resolution cache returns hit on known key | integration (live DB) | `pytest tests/test_phase6_perf.py::TestResolutionCache -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-03 | — | Resolution cache miss on expired TTL | integration (live DB) | `pytest tests/test_phase6_perf.py::TestResolutionCache::test_expired_ttl_miss -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-03 | — | URL queries bypass the resolution cache | unit | `pytest tests/test_phase6_perf.py::test_url_bypasses_cache -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-04 | DoS | `get_source` TimeoutError → falls back to stream | unit | `pytest tests/test_audio.py::TestDownloadTimeout -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-05 | — | `cleanup_cache` evicts lowest-play-count file first | unit | `pytest tests/test_audio.py::TestLFUEviction -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-05 | — | `cleanup_cache` never evicts protected video_ids | unit | `pytest tests/test_audio.py::TestLFUEviction::test_protected_not_evicted -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-05 | — | `cleanup_cache` tie-breaks by oldest mtime | unit | `pytest tests/test_audio.py::TestLFUEviction::test_tiebreak_oldest -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-06 | — | `PerfMetrics.summary()` returns correct hit rate | unit | `pytest tests/test_phase6_perf.py::TestPerfMetrics -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-06 | — | Timing logged per download event | unit (log capture) | `pytest tests/test_phase6_perf.py::test_timing_logged -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-07 | DoS | `DOWNLOAD_OPTS` contains SponsorBlock + ModifyChapters keys | unit | `pytest tests/test_youtube.py::TestDownloadOpts -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | PERF-07 | — | SponsorBlock PP has `when='after_filter'` | unit | `pytest tests/test_youtube.py::TestDownloadOpts::test_sponsorblock_when -x` | ❌ W0 | ⬜ pending |

*Task IDs are TBD until plans are written; the planner maps each row to a concrete `{N}-{plan}-{task}` ID.*
*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase6_perf.py` — new file covering PERF-01 (prefetch), PERF-03 (resolution cache + normalization), PERF-05 (LFU), PERF-06 (metrics)
- [ ] `tests/test_audio.py` — update `TestCacheCleanup` for LFU; add `TestDownloadTimeout`
- [ ] `tests/test_youtube.py` — add `TestDownloadOpts`, `TestCodecLogging`
- [ ] `database.py` helpers under test: `get_resolution_cache`, `set_resolution_cache`, `normalize_search_query`
- [ ] `tests/conftest.py` — extend `DROP TABLE` teardown to include `resolution_cache`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real YouTube opus stream actually takes the copy path | PERF-02 | Requires live yt-dlp run against YouTube | Play a known opus-source track; confirm logs show copy path, not transcode |
| End-to-end gapless playback between songs | PERF-01 | Requires a live Discord voice channel | Queue ≥2 tracks; confirm no audible gap when track ends |
| SponsorBlock segment actually removed from a known-segmented video | PERF-07 | Requires live yt-dlp + SponsorBlock API | Play a video with known sponsor segment; confirm segment is absent |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
