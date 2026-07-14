# Requirements: Dexter ("Dex") — v1.5 "Deep Cuts"

**Defined:** 2026-07-15
**Core Value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.

## v1.5 Requirements

Requirements for the "Deep Cuts" milestone. Each maps to a roadmap phase (Phase 24+).

### Hosting & Docker

- [ ] **HOST-01**: All dead cloud-host references (Render, Koyeb, Oracle) are removed from code comments, `config.py`, `Dockerfile`, `docker-compose.yml`, and `.env.example` — only the host-agnostic `$PORT` read and Docker / residential-host framing remain.
- [ ] **HOST-02**: `docs/DEPLOY-KOYEB.md` is replaced by a Docker run guide documenting `docker compose up` on a local/residential machine (env setup, Neon `DATABASE_URL`, how to verify the bot is alive).
- [ ] **HOST-03**: `docker compose up` is verified to build the image and boot Dexter locally against Neon — clean startup, `/health` responds, no new silent failures in `dexter.log`.
- [ ] **HOST-04** *(blocked-on-human)*: The dashboard-side Render service is deleted so the repo no longer auto-deploys and the CI/CD failure emails stop. *(Owner Render-UI step — there is no Render config in the repo; the connection is dashboard-side.)*

### Smarter Memory

- [ ] **MEM-06**: Memories that get surfaced/hit gain durability (salience reinforcement) — a surfaced memory's salience/expiry is reinforced so frequently-relevant facts outlive one-off ones under the daily decay sweep. Additive on the existing `user_memories` pgvector store.
- [ ] **MEM-07**: A vision roast persists a distilled, number-free fact into long-term memory (vision→RAG memory), subject to the same sensitivity / accuracy firewall as every other memory kind (no embedded SQL-known numbers).

### New Music Muscle

- [ ] **DJ-01**: Radio / endless mode — a user seeds a track or artist and Dexter keeps the queue flowing indefinitely off the taste brain (no manual queueing) until stopped.
- [ ] **DJ-02**: Skip-voting / queue democracy — a skip requires a configurable vote threshold (or listener majority) so one user can't unilaterally hijack the queue; Dexter narrates the tally.
- [ ] **DJ-03** *(spike-gated)*: Crossfade between tracks — the tail of the outgoing track blends into the head of the incoming track. Gated on a plan-time spike proving `/skip`-mid-crossfade + generation-counter safety on the existing playback engine; **descope to a fast-follow if the spike shows engine instability** (standing Descope Rule).

### Portfolio Finish

- [x] **PORT-05**: The `/site` landing page is redesigned — proper case throughout the site's own voice, a working (non-broken) staged demo animation, and a distinct "after hours" visual identity. *(Done, `c7fd22e`.)*
- [ ] **PORT-02** *(carried from v1.4, blocked-on-human)*: The demo mock shows two verbatim real Dexter personality lines (the `{{DEXTER_DEMO_LINE}}` placeholder tokens replaced). *(Needs a live bot; preview samples in place until then.)*
- [ ] **CICD-02** *(carried from v1.4, blocked-on-human)*: GitHub Pages is enabled and the landing page is live at the public URL (`Settings → Pages → Source = GitHub Actions` + first `pages.yml` run).
- [ ] **CICD-03** *(carried from v1.4, blocked-on-human)*: GHCR package visibility is set and the first `v*`-tag `release.yml` run publishes the image.

## Future Requirements

Deferred — tracked, not in this roadmap.

### Deploy

- **DEPLOY-F1**: 24/7 residential deploy on an always-on host (Pi / spare machine) — closes the parked live-Discord/UAT tail. Host-gated.

### Memory

- **MEM-F3**: Full guild-scoped recall / opt-in cross-guild memory sharing — revisit only if Dexter outgrows modest scale.

### Music

- **DJ-F1**: Synced-scrolling `/lyrics` (LRCLIB timestamps) — deferred; timestamp coverage/accuracy inconsistent.
- **DJ-F2**: Crossfade (if DJ-03's spike descopes it) — carried as a fast-follow.

### Scale

- **SCALE-F2**: Discord bot verification + privileged-intent approval — required only past 100 guilds / 10k unique users.

## Out of Scope

Explicitly excluded.

| Feature | Reason |
|---------|--------|
| Per-guild personality tone dial | Full-savage sarcasm is core identity; the owner kill-switch is the stated mitigation (v1.4 decision). |
| Datacenter / cloud hosting for a 24/7 deploy | YouTube blocks datacenter IPs → free cloud is non-viable. Resolution is a residential always-on host, not a provider. |
| Spotify / Apple Music as audio sources | YouTube via yt-dlp is the single source of truth. |

## Traceability

Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| HOST-01 | Phase [N] | Pending |
| HOST-02 | Phase [N] | Pending |
| HOST-03 | Phase [N] | Pending |
| HOST-04 | Phase [N] | Pending (blocked-on-human) |
| MEM-06 | Phase [N] | Pending |
| MEM-07 | Phase [N] | Pending |
| DJ-01 | Phase [N] | Pending |
| DJ-02 | Phase [N] | Pending |
| DJ-03 | Phase [N] | Pending (spike-gated) |
| PORT-05 | Phase [N] | Complete (`c7fd22e`) |
| PORT-02 | Phase [N] | Pending (blocked-on-human) |
| CICD-02 | Phase [N] | Pending (blocked-on-human) |
| CICD-03 | Phase [N] | Pending (blocked-on-human) |

**Coverage:**
- v1.5 requirements: 13 total (1 already complete, 4 blocked-on-human)
- Mapped to phases: filled by roadmap
- Unmapped: filled by roadmap

---
*Requirements defined: 2026-07-15*
*Last updated: 2026-07-15 at milestone start*
