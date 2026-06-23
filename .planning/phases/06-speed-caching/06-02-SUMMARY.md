---
phase: "06-speed-caching"
plan: "02"
subsystem: "download pipeline"
tags: [phase6, perf, sponsorblock, codec-logging, tdd]
dependency_graph:
  requires:
    - "06-01 (config.SPONSORBLOCK_CATEGORIES, test infrastructure)"
  provides:
    - "DOWNLOAD_OPTS 3-PP chain: SponsorBlock(when=after_filter) → FFmpegExtractAudio → ModifyChapters"
    - "download() codec-path logging: codec_path=copy|transcode + elapsed=Xs via postprocessor_hooks"
    - "tests/test_youtube.py: TestDownloadOpts (PP shape/order) + TestCodecLogging (copy vs transcode)"
  affects:
    - "services/youtube.py DOWNLOAD_OPTS (extended from 1-PP to 3-PP list)"
    - "services/youtube.py download() (gains _pp_hook closure + timing)"
tech_stack:
  added: []
  patterns:
    - "postprocessor_hooks mutable-closure pattern for codec-path detection without live yt-dlp"
    - "Mock YoutubeDL side_effect=fake_init + fake_download creates opus file to simulate post-download existence"
key_files:
  created: []
  modified:
    - services/youtube.py
    - tests/test_youtube.py
decisions:
  - "DOWNLOAD_OPTS 3-PP order: SponsorBlock(when=after_filter) first, FFmpegExtractAudio second, ModifyChapters last — required ordering per Pitfall 1 and Anti-Pattern in 06-RESEARCH.md"
  - "copy-when-opus NOT rewritten — FFmpegExtractAudioPP already does it natively; only logging added (RESEARCH critical finding)"
  - "Test mock creates opus file inside fake_download (not before) so cache-hit early return is not triggered"
metrics:
  duration: "~4 min"
  completed_date: "2026-06-24"
  tasks_completed: 2
  files_created: 0
  files_modified: 2
---

# Phase 06 Plan 02: SponsorBlock + Codec-Path Logging Summary

**One-liner:** Extended DOWNLOAD_OPTS to a 3-PP SponsorBlock→FFmpegExtractAudio→ModifyChapters chain with when=after_filter, and added postprocessor_hooks closure to download() logging codec_path=copy|transcode + elapsed for every download (PERF-02/PERF-07).

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| TDD RED | Failing TestDownloadOpts + TestCodecLogging | 027cee9 | tests/test_youtube.py |
| 1+2 (GREEN) | SponsorBlock 3-PP + codec logging + complete tests | 176b4fb | services/youtube.py, tests/test_youtube.py |

## What Was Built

### services/youtube.py

**DOWNLOAD_OPTS postprocessors** — replaced single-PP list with ordered 3-element list:
1. `{"key": "SponsorBlock", "categories": config.SPONSORBLOCK_CATEGORIES, "when": "after_filter"}` — fetches SponsorBlock chapter data before `post_process` stage (Pitfall 1: `when` key is mandatory or no segments get cut)
2. `{"key": "FFmpegExtractAudio", "preferredcodec": "opus", "preferredquality": config.AUDIO_QUALITY}` — UNCHANGED; copy-when-opus is already native to FFmpegExtractAudioPP (RESEARCH critical finding)
3. `{"key": "ModifyChapters", "remove_sponsor_segments": config.SPONSORBLOCK_CATEGORIES, "remove_chapters_patterns": [], "remove_ranges": [], "force_keyframes": False}` — performs actual cuts post FFmpegExtractAudio; tracks with cuts re-encode even if opus source (D-16, expected)

**download() updates:**
- `_codec_path = {"value": "unknown"}` mutable closure captures PP hook result
- `_pp_hook(d)` fires when `d["postprocessor"]=="FFmpegExtractAudio"` and `d["status"]=="finished"`, sets value to `"copy"` (acodec==opus) or `"transcode"` (anything else)
- `opts = {**DOWNLOAD_OPTS, "postprocessor_hooks": [_pp_hook]}` passed to YoutubeDL instead of bare DOWNLOAD_OPTS
- `t0 = time.monotonic()` / `elapsed = time.monotonic() - t0` wraps `ydl.download([url])`
- On success: `log.info("download complete video_id=%s codec_path=%s elapsed=%.2fs", ...)` (D-03 + D-17)
- Retry path after yt-dlp self-update also uses `opts` and logs with the same format

### tests/test_youtube.py

**TestDownloadOpts** (4 pure unit tests, no network):
- `test_has_sponsorblock_and_modifychapters`: all 3 PP keys present in list
- `test_sponsorblock_when`: SponsorBlock PP has `when=="after_filter"`
- `test_pp_order`: FFmpegExtractAudio index < ModifyChapters index
- `test_categories_wired`: SponsorBlock categories == config.SPONSORBLOCK_CATEGORIES

**TestCodecLogging** (2 unit tests with mocked YoutubeDL):
- `test_copy_logged`: hook fires with `acodec="opus"` → `"codec_path=copy"` in log
- `test_transcode_logged`: hook fires with `acodec="aac"` → `"codec_path=transcode"` in log
- Mock pattern: `fake_init` captures opts dict; `fake_download` creates the `.opus` file then fires hooks from `opts["postprocessor_hooks"]` — ensures file doesn't exist pre-download (avoids cache-hit early return) but exists post-download (so the success log fires)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mock created opus file before download, triggering cache-hit early return**
- **Found during:** TDD GREEN verification
- **Issue:** First test implementation pre-created the opus file with `opus_file.touch()` before calling `yt.download()`. The `download()` method has an early return `if cached.exists(): return cached` so the hook code path was never reached, producing empty caplog.
- **Fix:** Moved opus file creation into `fake_download()` (the mock's download method), so the file only exists after the simulated download, matching real yt-dlp behavior. Added `opus_file_to_create` param to `_make_ydl_mock`.
- **Files modified:** `tests/test_youtube.py`
- **Commit:** 176b4fb (same GREEN commit)

## Verification Results

```
python -m pytest tests/test_youtube.py -x -q
# 17 passed, 1 warning

grep -v '^#' services/youtube.py | grep -c 'codec_path='
# 2 (>= 1 required)

python -c "from services.youtube import DOWNLOAD_OPTS; pps=DOWNLOAD_OPTS['postprocessors']; keys=[p['key'] for p in pps]; assert 'SponsorBlock' in keys and 'ModifyChapters' in keys; sb=next(p for p in pps if p['key']=='SponsorBlock'); assert sb['when']=='after_filter'; assert keys.index('FFmpegExtractAudio')<keys.index('ModifyChapters'); print('OK')"
# OK
```

## TDD Gate Compliance

| Gate | Commit | Message |
|------|--------|---------|
| RED | 027cee9 | `test(06-02): add failing TestDownloadOpts + TestCodecLogging (TDD RED)` |
| GREEN | 176b4fb | `feat(06-02): SponsorBlock 3-PP chain + codec-path logging in download()` |

RED gate: 1 failure confirmed (`SponsorBlock` not in single-PP DOWNLOAD_OPTS list). GREEN gate: all 17 tests pass after implementation.

## Threat Surface Scan

No new network endpoints, auth paths, or DB schema changes. The SponsorBlock PP makes an external call to `sponsor.ajay.app` during download (T-06-03 in plan threat model) — yt-dlp handles its own API timeout and proceeds with zero segments on failure. No new threat surface beyond what was already in the plan's threat register.

## Known Stubs

None — the codec-path logging is fully wired; `SPONSORBLOCK_CATEGORIES` pulls from config (set in Plan 01). The postprocessor_hooks are production-ready.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| services/youtube.py DOWNLOAD_OPTS has SponsorBlock PP | FOUND |
| services/youtube.py download() has postprocessor_hooks | FOUND |
| tests/test_youtube.py has class TestDownloadOpts | FOUND |
| tests/test_youtube.py has class TestCodecLogging | FOUND |
| Commit 027cee9 (TDD RED) | FOUND |
| Commit 176b4fb (GREEN) | FOUND |
