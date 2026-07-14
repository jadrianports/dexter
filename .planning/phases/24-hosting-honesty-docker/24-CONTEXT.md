# Phase 24: Hosting Honesty & Docker - Context

**Gathered:** 2026-07-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Dexter's deploy story becomes **one honest, working Docker path**. Every dead cloud-host
reference (Render, Koyeb, Oracle) is purged from tracked code + docs, `docs/DEPLOY-KOYEB.md` is
replaced by a verified `docker compose up` guide against Neon, and a documented local boot is
confirmed to come up clean. Hosting model is **unchanged** — the 24/7 deploy stays parked; this
phase makes Docker the clean run path, **not** a 24/7 standup.

**Requirements:** HOST-01, HOST-02, HOST-03, HOST-04 (HOST-04 is blocked-on-human).

**In scope:** comment/config/docs cleanup, host-honest narrative rewrite, new Docker doc, a boot
verification (parked to human), `.env.example` reframe.
**Out of scope:** any new hosting target, a real 24/7 standup, CI/CD changes, touching the
memory/music/portfolio threads (Phases 25–28).
</domain>

<decisions>
## Implementation Decisions

### Scrub scope / blast radius (tracked repo only)
- **D-01:** Scrub **live + operative** references AND rewrite the **host-honest narrative** in
  tracked files — but only tracked files. Targets confirmed by scout:
  - `config.py:22` (`# Koyeb 2GB ephemeral disk (K-07)`)
  - `bot.py` health-endpoint comments (lines ~216–264, 578–589) + the `Render injects $PORT`
    comment (lines ~252–254) — **keep the `$PORT` read itself** (host-agnostic), strip the
    Render/Koyeb naming.
  - `Dockerfile` header (lines 1–2, "Koyeb builds this…")
  - `docker-compose.yml` ("the colocated-Postgres override was Oracle-era legacy" comment)
  - `.env.example` (see D-07)
  - `CLAUDE.md` — the Tech Stack "Hosting" bullet, the Phase-5 build-log ("Oracle A1 → Koyeb"),
    and any `logs/…Docker/Koyeb` phrasing → reword to Docker/residential-honest framing.
- **D-02:** **Delete** the dead Oracle-era scripts in `scripts/archive/` (`backup.sh`,
  `deploy.sh`, `keepalive.sh`, `lifecycle-policy.json`) — they were retired by Neon PITR +
  UptimeRobot and are only kept alive by the Koyeb doc that is being removed.
- **D-03:** **Leave `.planning/` and `milestones/` archives untouched** — they are the sealed
  historical record. **Skip the gitignored `dexter-architecture.md`** — it is untracked, so it is
  not "the repo" for the grep success criterion.

### K-## traceability tags
- **D-04:** **Keep the `(K-##)` tags intact; rewrite only the surrounding prose.** Rationale:
  `K-##` is the opaque Phase-5 ("Ship It Live") scar-ID namespace, cross-referenced by `.planning/`
  + `milestones/` archives by ID, and a grep for `"Koyeb"` never matches `(K-07)`. Where a comment
  literally spells it out — e.g. `# Koyeb 2GB ephemeral disk (K-07)` — rewrite the prose
  host-honest but keep the tag: `# 512MB cap on ephemeral disk (K-07)`. 12 distinct tags across
  `bot.py`(9), `config.py`(5), `CLAUDE.md`(5), `.env.example`(3), `Dockerfile`(2),
  `tests/test_config.py`, `utils/logger.py`, `scripts/memory_spike.py` — none get renamed/removed.

### Replacement Docker doc (HOST-02)
- **D-05:** New file **`docs/DEPLOY-DOCKER.md`** (mirrors the `docs/DEPLOY-*.md` naming
  convention). **`git rm docs/DEPLOY-KOYEB.md`** (179 lines) — do not leave it behind.
- **D-06:** **Lean-but-complete** shape: prereqs (Docker + Docker Compose), copy `.env.example`
  → `.env` and fill `DISCORD_TOKEN`/`GEMINI_API_KEY`/`GENIUS_TOKEN`/Neon `DATABASE_URL`,
  `docker compose up -d --build`, and how to verify the bot is alive (`/health` on `:8000` +
  clean `dexter.log`). **Keep the parked-24-7 / residential-host framing honest** — state plainly
  that this is an on-demand run on a residential IP, not a 24/7 cloud standup, and carry the
  single-Discord-token warning forward. Not a full 179-line runbook.

### `.env.example` reframe (part of HOST-01)
- **D-07:** **Reframe local-vs-Docker, keep the split.** Relabel the "Koyeb / production" guidance
  as "**Docker on your PC + Neon**"; drop Koyeb Secrets / scale-to-zero / UptimeRobot-inbound
  language. **Keep** the local-Postgres-vs-Neon `DATABASE_URL` distinction (the break-glass local
  Postgres path stays) and **keep** the Healthchecks.io outbound dead-man note (K-09 — still valid,
  host-agnostic). `DATABASE_URL` remains "the only value that differs" framing, just retargeted.

### HOST-03 verification ownership
- **D-08:** **Park HOST-03 as human-run UAT.** The boot needs the real `DISCORD_TOKEN` + Neon
  `DATABASE_URL`, which must not live in this session. Ship a documented `24-HOST-UAT.md` checklist
  (build image, `docker compose up`, confirm clean startup log + `/health` responds + no new
  silent failures in `dexter.log`); the owner runs it on their PC. Matches every prior
  live-verification precedent (Phases 03–22 parked UATs). Scout confirms `docker-compose.yml` is
  already bot-only → Neon, so the boot is genuinely runnable — no compose changes needed for it.

### Claude's Discretion
- Exact host-honest wording of rewritten comments/narrative (must satisfy: grep for
  `Render`/`Koyeb`/`Oracle` in tracked non-archive files returns zero, `$PORT` read + Docker /
  residential framing remain).
- Section ordering and exact prose of `docs/DEPLOY-DOCKER.md` within the D-06 shape.

### HOST-04 (blocked-on-human)
- **D-09:** No repo action possible — there is **no Render config in the repo**. The Render CI/CD
  auto-deploy + failure emails come from a **dashboard-side Render service**; the owner deletes it
  in the Render dashboard. Document this as the standing blocked-on-human item; do not attempt a
  repo-side fix.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` §Hosting — HOST-01…HOST-04 exact wording.
- `.planning/ROADMAP.md` §"Phase 24: Hosting Honesty & Docker" — goal + 4 success criteria.

### Files to scrub / rewrite (tracked, non-archive)
- `.env.example` — Koyeb-heavy template to reframe (D-07).
- `bot.py` §health endpoint (~216–264, 578–589) — Koyeb/Render comments; keep `$PORT` read.
- `config.py:22` — `# Koyeb 2GB ephemeral disk (K-07)`.
- `Dockerfile` (lines 1–2) — "Koyeb builds this Dockerfile…".
- `docker-compose.yml` — "Oracle-era legacy" comment; **already bot-only → Neon (no changes for boot)**.
- `CLAUDE.md` — Tech Stack "Hosting" bullet + Phase-5 build-log narrative + `logs` Docker/Koyeb note.
- `tests/test_config.py`, `utils/logger.py`, `scripts/memory_spike.py` — carry `(K-##)` tags (tags stay, D-04).

### File to remove / replace
- `docs/DEPLOY-KOYEB.md` — 179-line Koyeb runbook; `git rm` and replace with `docs/DEPLOY-DOCKER.md` (D-05/D-06).

### Delete (dead Oracle-era)
- `scripts/archive/backup.sh`, `scripts/archive/deploy.sh`, `scripts/archive/keepalive.sh`, `scripts/archive/lifecycle-policy.json` (D-02).

### Explicitly NOT touched
- `.planning/**`, `milestones/**` (sealed history), `dexter-architecture.md` (gitignored/untracked).

No external ADRs — decisions fully captured above.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docker-compose.yml` — already the clean host-on-PC + Neon stack (bot-only, `env_file: .env`,
  named `audio_cache`/`logs` volumes, `restart: unless-stopped`). It is the reference the new doc
  documents; no functional change needed for the HOST-03 boot.
- `bot.py` `/health` aiohttp endpoint on `0.0.0.0:8000` — the alive-check the new doc points at.
- `config.sanitize_database_url` — strips Neon `channel_binding`/`sslmode` from the DSN at startup;
  the doc should tell users to paste the raw pooled Neon string.

### Established Patterns
- **`(K-##)` / `(D-##)` scar-ID tags** thread rationale through comments and are cross-referenced by
  planning archives — treat as opaque IDs (D-04), never rename.
- **Parked-UAT precedent** (Phases 03–22): live/runtime verification that needs real secrets ships
  as a human-run `*-HOST-UAT.md` / `*-HUMAN-UAT.md` checklist, acknowledged-deferred (D-08).
- **Additive/host-honest CLAUDE.md discipline** — CLAUDE.md is the authoritative spec and has gone
  a full milestone stale before; this phase's narrative rewrite is the moment to make its hosting
  section honest.

### Integration Points
- The scrub touches only comments/docs/config prose — **no runtime code paths change** (the
  `$PORT` read, pool tuning, cache cap, stdout logging all stay functionally identical).
- Tests: `tests/test_config.py` references `(K-##)` tags; keeping tags means no test churn from D-04.
</code_context>

<specifics>
## Specific Ideas

- Concrete rewrite example the user endorsed: `# Koyeb 2GB ephemeral disk (K-07)` →
  `# 512MB cap on ephemeral disk (K-07)`.
- Success gate is a literal grep: `Render` / `Koyeb` / `Oracle` in tracked, non-archive files must
  return **zero** live hosting-target hits — only the host-agnostic `$PORT` read and
  Docker/residential framing remain.
</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (The gitignored `dexter-architecture.md` was
considered and explicitly excluded per D-03; not a deferred item — it is untracked scratch.)
</deferred>

---

*Phase: 24-hosting-honesty-docker*
*Context gathered: 2026-07-15*
