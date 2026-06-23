# Requirements: Dexter ("Dex") — Milestone v1.1 "Live & Lethal"

**Defined:** 2026-06-12
**Core Value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.

**Milestone goal:** Take Dexter from code-complete-on-a-laptop to running 24/7 — fast, polished, and genuinely fun — by deploying it for real, killing playback latency, and surfacing the control, filter, and roast features that make it a joy to use. Sequenced **deploy-first** so every speed gain is measured against live numbers.

## v1.1 Requirements

### Ship It Live (`DEPLOY`)

- [x] **DEPLOY-01**: Dexter runs 24/7 on Oracle A1 via Docker Compose (bot + Postgres), surviving a host reboot
- [ ] **DEPLOY-02**: The standing live-UAT checklist (9 Phase-3 behavioral + 6 Phase-4 deploy checks) is executed and passing
- [ ] **DEPLOY-03**: The 6 human-UAT scenarios (`04-HUMAN-UAT.md`) are executed and passing
- [x] **DEPLOY-04**: Voice playback survives a reconnect under live concurrency (the parked race at `cogs/music.py:~609` is fixed)
- [ ] **DEPLOY-05**: Queue + playback position survive a bot restart (persistence + smart-rejoin validated live)
- [x] **DEPLOY-06**: `clear_persisted()` fires correctly on idle-leave and reconnect-failure paths (IN-02 resolved)
- [x] **DEPLOY-07**: Scheduled `pg_dump` backup runs and a restore is validated end-to-end
- [ ] **DEPLOY-08**: Keepalive / dead-man cron is confirmed firing in production

### Speed & Caching (`PERF`)

- [ ] **PERF-01**: The next track is prefetched into cache during current playback (no inter-song download gap)
- [ ] **PERF-02**: Cached audio uses native-opus copy (no opus→opus re-encode) when the source is already opus
- [x] **PERF-03**: A resolution cache maps repeat queries → `video_id` without re-searching YouTube
- [ ] **PERF-04**: Download attempts honor `DOWNLOAD_TIMEOUT_SECONDS`, falling back to stream on timeout
- [ ] **PERF-05**: Cache eviction is play-frequency based and does not depend on filesystem `atime`
- [x] **PERF-06**: Pipeline timing is instrumented (search, download, transcode, time-to-first-audio, cache-hit rate) and observable
- [ ] **PERF-07**: SponsorBlock segments (sponsor / intro / non-music) are skipped on YouTube-video playback

### Player UX & Filters (`PLAYER`)

- [ ] **PLAYER-01**: The now-playing embed has interactive control buttons (play/pause, skip, loop, shuffle, stop)
- [x] **PLAYER-02**: User can `/seek <time>` within the current track
- [ ] **PLAYER-03**: User can `/previous` to replay the prior track
- [x] **PLAYER-04**: User can `/jump <position>` to a specific queue slot
- [x] **PLAYER-05**: User can save and replay personal favorite songs
- [x] **PLAYER-06**: User can save and load named playlists (queue snapshots)
- [x] **PLAYER-07**: User can apply audio filters via `/filter <preset>` (bassboost / nightcore / slowed+reverb / 8d)
- [x] **PLAYER-08**: User can clear filters back to normal playback

### Social & Personality (`SOCIAL`)

- [x] **SOCIAL-01**: User can `/roast @user` — a personalized roast generated from that user's tracked history
- [x] **SOCIAL-02**: User can view a `/leaderboard` for the server (most songs queued, longest streak, most skipped)

### Ops & Observability (`OPS`)

- [x] **OPS-01**: Owner can view a `/stats` dashboard in Discord (commands, songs, AI queries, images, errors)
- [x] **OPS-02**: A health endpoint exposes bot liveness for the dead-man switch
- [x] **OPS-03**: Gemini and Oracle quota/usage is observable before limits are hit

## Future Requirements

Deferred to a later milestone (v1.2 / v2.0). Tracked, not in this roadmap.

### Memory & Multimodal

- **RAG-01**: Long-term semantic memory over conversation/song/roast history (pgvector + Gemini embeddings) for callback roasts
- **RAG-02**: Taste-RAG for semantically-grounded auto-queue / `/recommend`
- **VISION-01**: Dexter sees and reacts to images posted in chat (multimodal `gemini-2.5-flash`)

### Ops

- **OPS-F1**: Web config dashboard (per-server settings, browser UI) — deferred; `/stats` covers the v1.1 owner need

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Web config dashboard (this milestone) | Whole frontend + auth + hosting surface; `/stats` in-Discord (OPS-01) covers the owner need. Deferred to Future, not killed. |
| `/volume` / `PCMVolumeTransformer` | Discord's per-user volume slider covers it; opus passthrough keeps CPU low (carried from v1.0) |
| Prefix / hybrid commands | Pure `app_commands` slash commands only, by design (carried from v1.0) |
| Spotify / Apple Music as audio sources | YouTube via yt-dlp is the single source of truth (carried from v1.0) |
| RAG long-term memory / Vision | Deliberately deferred to a future milestone — high value, but wants live data volume + a research spike first |

## Traceability

Which phases cover which requirements. Phase numbering continues from v1.0 (last phase = 4), so v1.1 starts at **Phase 5**.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEPLOY-01 | Phase 5 | Pending |
| DEPLOY-02 | Phase 5 | Pending |
| DEPLOY-03 | Phase 5 | Pending |
| DEPLOY-04 | Phase 5 | Complete |
| DEPLOY-05 | Phase 5 | Pending |
| DEPLOY-06 | Phase 5 | Complete |
| DEPLOY-07 | Phase 5 | Pending |
| DEPLOY-08 | Phase 5 | Pending |
| PERF-01 | Phase 6 | Pending |
| PERF-02 | Phase 6 | Pending |
| PERF-03 | Phase 6 | Complete |
| PERF-04 | Phase 6 | Pending |
| PERF-05 | Phase 6 | Pending |
| PERF-06 | Phase 6 | Complete |
| PERF-07 | Phase 6 | Pending |
| PLAYER-01 | Phase 7 | Pending |
| PLAYER-02 | Phase 7 | Complete |
| PLAYER-03 | Phase 7 | Pending |
| PLAYER-04 | Phase 7 | Complete |
| PLAYER-05 | Phase 7 | Complete |
| PLAYER-06 | Phase 7 | Complete |
| PLAYER-07 | Phase 7 | Complete |
| PLAYER-08 | Phase 7 | Complete |
| SOCIAL-01 | Phase 8 | Complete |
| SOCIAL-02 | Phase 8 | Complete |
| OPS-01 | Phase 8 | Complete |
| OPS-02 | Phase 8 | Complete |
| OPS-03 | Phase 8 | Complete |

**Coverage:**

- v1.1 requirements: 28 total
- Mapped to phases: 28
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-12*
*Last updated: 2026-06-12 — traceability filled by roadmapper*
