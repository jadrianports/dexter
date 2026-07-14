# Phase 24: Hosting Honesty & Docker - Research

**Researched:** 2026-07-15
**Domain:** Repo-wide comment/docs/config prose scrub (dead cloud-host references) + a replacement Docker deploy doc + a human-run local-boot verification. No new libraries, no runtime code-path changes.
**Confidence:** HIGH — every claim below is [VERIFIED] against this repo's actual tracked file contents via `git grep`/`Read`, not training-data recall. This phase has almost no "ecosystem" surface (no new packages, no framework choice) — the risk is exhaustiveness of the scrub, not technology selection.

## Summary

This phase is a text/prose scrub, not a feature build. The deliverable is: (1) zero live `Render`/`Koyeb`/`Oracle` hosting-target references in tracked, non-`.planning/`/non-`milestones/` files, (2) `docs/DEPLOY-KOYEB.md` deleted and replaced by a lean `docs/DEPLOY-DOCKER.md`, (3) a human-run boot verification (`24-HOST-UAT.md`), and (4) `.env.example`/CLAUDE.md reframed host-honest. All 12 `(K-##)` scar-ID tags across 8 files (D-04's claim) are independently confirmed correct by a full-repo tag census below.

The full enumeration below found the CONTEXT.md file list is **incomplete in two places**: `scripts/seed_restore_test.py` (an "Oracle" mention plus references to the soon-deleted `scripts/archive/backup.sh`) and `utils/embeds.py:294` (an "Oracle" mention in a stats-embed comment) were not listed in 24-CONTEXT.md's canonical refs but **are** tracked, non-archive files carrying live `Oracle` references — both will trip the ROADMAP's literal success-criterion-1 grep if left unscrubbed. Both are flagged prominently below as required additions to the plan's file list (not new decisions — they fall squarely under the already-locked D-01 "scrub live + operative references" mandate; the grep gate the phase is graded against is repo-wide, not limited to the CONTEXT.md file list).

**Primary recommendation:** Treat this as a single scrub pass driven by an enumerated file:line worklist (below) plus one canonical verification grep command, run before and after the pass to prove the delta. Docker is installed and working in this environment (Docker 29.5.3 / Compose v5.1.4), so HOST-03's boot verification is technically runnable — but per D-08 it still requires real `DISCORD_TOKEN`/Neon `DATABASE_URL` secrets that must not live in this session, so it stays a human-run UAT, not something this research or the plan can execute directly.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hosting-reference text scrub (comments/docs/config prose) | Docs/Config (no runtime tier) | — | Pure text edits; zero behavior change. Not a browser/API/DB capability — flagged here only for completeness since the template requires this section. |
| `$PORT` env read (survivor) | API/Backend (`bot.py` health server) | — | Host-agnostic `os.environ.get("PORT", "8000")` — stays functionally identical, only the adjacent comment naming "Render" is reworded. |
| Docker Compose local boot | Runner / Process tier (residential PC) | Database (Neon, external) | `docker-compose.yml` already builds + runs the bot container on-PC; Neon is reached over the network, never colocated. |
| New `docs/DEPLOY-DOCKER.md` | Docs (developer-facing) | — | Documents the existing Compose/Neon flow; no new code. |

## User Constraints

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 (scrub scope):** Scrub live + operative references AND rewrite the host-honest narrative in tracked files only. Confirmed targets: `config.py:22`, `bot.py` health-endpoint comments (~216–264, 578–589) — keep the `$PORT` read itself, strip Render/Koyeb naming — `Dockerfile` header (lines 1–2), `docker-compose.yml` ("Oracle-era legacy" comment), `.env.example` (see D-07), `CLAUDE.md` (Tech Stack "Hosting" bullet, Phase-5 build-log, `logs`/Docker/Koyeb phrasing).
- **D-02 (delete dead scripts):** Delete `scripts/archive/backup.sh`, `deploy.sh`, `keepalive.sh`, `lifecycle-policy.json` — retired by Neon PITR + UptimeRobot.
- **D-03 (blast radius):** Leave `.planning/` and `milestones/` untouched (sealed history). Skip gitignored `dexter-architecture.md` (untracked, not "the repo").
- **D-04 (K-## tags):** Keep `(K-##)` tags intact; rewrite only surrounding prose. 12 distinct tags across `bot.py`(9), `config.py`(5), `CLAUDE.md`(5), `.env.example`(3), `Dockerfile`(2), `tests/test_config.py`, `utils/logger.py`, `scripts/memory_spike.py` — none renamed/removed.
- **D-05 (new doc):** New file `docs/DEPLOY-DOCKER.md` (mirrors `docs/DEPLOY-*.md` naming). `git rm docs/DEPLOY-KOYEB.md` (179 lines) — do not leave it behind.
- **D-06 (doc shape):** Lean-but-complete: prereqs (Docker + Docker Compose), copy `.env.example` → `.env` and fill `DISCORD_TOKEN`/`GEMINI_API_KEY`/`GENIUS_TOKEN`/Neon `DATABASE_URL`, `docker compose up -d --build`, verify-alive (`/health` on `:8000` + clean `dexter.log`). Keep parked-24/7 / residential-host framing honest. Not a full 179-line runbook.
- **D-07 (.env.example reframe):** Reframe local-vs-Docker, keep the split. Relabel "Koyeb / production" guidance as "Docker on your PC + Neon"; drop Koyeb Secrets / scale-to-zero / UptimeRobot-inbound language. Keep the local-Postgres-vs-Neon `DATABASE_URL` distinction and the Healthchecks.io outbound dead-man note (K-09, host-agnostic, still valid). `DATABASE_URL` stays "the only value that differs" framing, retargeted.
- **D-08 (HOST-03 ownership):** Park HOST-03 as human-run UAT (`24-HOST-UAT.md`): build image, `docker compose up`, confirm clean startup log + `/health` responds + no new silent failures in `dexter.log`. `docker-compose.yml` already bot-only → Neon; no compose changes needed for the boot itself.
- **D-09 (HOST-04):** No repo action possible — no Render config in the repo. Render CI/CD auto-deploy + failure emails come from a dashboard-side Render service; owner deletes it in the Render dashboard. Document as standing blocked-on-human item.

### Claude's Discretion

- Exact host-honest wording of rewritten comments/narrative (must satisfy: grep for `Render`/`Koyeb`/`Oracle` in tracked non-archive files returns zero, `$PORT` read + Docker/residential framing remain).
- Section ordering and exact prose of `docs/DEPLOY-DOCKER.md` within the D-06 shape.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope. The gitignored `dexter-architecture.md` was considered and explicitly excluded per D-03 (untracked scratch, not deferred).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HOST-01 | All dead cloud-host references (Render, Koyeb, Oracle) removed from code comments, `config.py`, `Dockerfile`, `docker-compose.yml`, `.env.example` — only `$PORT` read + Docker/residential framing remain | Complete file:line enumeration below (§ Full Reference Inventory) covers every tracked, non-archive occurrence — including two files (`scripts/seed_restore_test.py`, `utils/embeds.py`) not in the CONTEXT.md list but required to hit zero on the repo-wide grep. |
| HOST-02 | `docs/DEPLOY-KOYEB.md` replaced by a Docker run guide (`docker compose up`, env setup, Neon `DATABASE_URL`, alive-verification) | § Replacement `docs/DEPLOY-DOCKER.md` Content Plan — cross-checked against the actual `docker-compose.yml` and `bot.py` `/health` endpoint so the doc is accurate to what runs today. |
| HOST-03 | `docker compose up` verified to build + boot Dexter locally against Neon — clean startup, `/health` responds, no new silent failures | § Environment Availability confirms Docker/Compose are installed and working in this environment; § HOST-03 UAT Shape gives the exact checklist matching the D-08 parked-human precedent. |
| HOST-04 (blocked-on-human) | Dashboard-side Render service deleted | § HOST-04 confirmed: zero Render config exists anywhere in the tracked repo (the only "Render" hits are the English word "render"/"rendering", never a service reference outside `bot.py`'s two now-scrubbed comment lines) — genuinely no repo-side action possible. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- CLAUDE.md is itself a scrub target (D-01): its Tech Stack "Hosting" bullet (line 24) and Phase-5 build-log narrative (lines 819, 822) name Koyeb/Oracle and must be reworded host-honest while preserving the `(K-##)` tags they carry (lines 309, 362, 687, 705, 921).
- CLAUDE.md states "`dexter-architecture.md` is a local, untracked scratch doc — gitignored... do not rely on it and do not re-add it to the repo" — consistent with D-03's exclusion.
- Critical Rule discipline (logging, `(K-##)`/`(D-##)` tag conventions) must be preserved: this phase is explicitly *not* a code-behavior change, so none of CLAUDE.md's 20 Critical Rules are touched in substance — only the Hosting bullet and build-log prose.
- No test-suite churn expected from the tag-preservation discipline (D-04) — `tests/test_config.py`'s only `(K-##)` reference (a docstring, `K-05`) is untouched content, not an assertion on prose wording.

## Full Reference Inventory (tracked, non-`.planning/`, non-`milestones/`)

Generated via `git grep -ni` (case-insensitive, tracked files only) on 2026-07-15. `.planning/` and `milestones/` excluded per D-03. **`scripts/archive/*` files are listed here for completeness but will cease to exist once D-02's deletion runs** — no scrub action needed on their content, only the `git rm`.

### `Koyeb` — 33 tracked hits, ALL true positives (zero false positives for this term)

| File:Line | Content | Disposition |
|---|---|---|
| `.env.example:7,10,23,27,30,38,41` | "Koyeb secrets/production" framing throughout | Reword per D-07 |
| `CLAUDE.md:24,687,819,822` | Tech Stack bullet, log-viewer note, Phase-5 build-log | Reword per D-01, keep K-## tags |
| `Dockerfile:1,2` | Header comment "Koyeb builds this...", "K-11/K-12" | Reword per D-01, keep tags |
| `bot.py:216,218,220,264,578,579,580,589` | Health-endpoint docstring/comments (D-01's "~216–264, 578–589" range) | Reword, keep `$PORT` read + K-02 tag |
| `config.py:22` | `# Koyeb 2GB ephemeral disk (K-07)` | Reword to `# 512MB cap on ephemeral disk (K-07)` (D-04's own worked example) |
| `docs/DEPLOY-KOYEB.md` (entire file, 179 lines, ~30 hits) | Whole Koyeb runbook | `git rm` per D-05 — no line-by-line scrub needed, file is deleted |
| `utils/logger.py:41` | stdout comment, K-16 tag | Reword, keep tag |

### `Oracle` — 21 tracked hits; 2 outside the CONTEXT.md file list (flagged)

| File:Line | Content | Disposition |
|---|---|---|
| `CLAUDE.md:22,24,780,819,820` | Containerization bullet, Hosting bullet, Phase-2/3 deferred note, Phase-5 build-log ×2 | Reword per D-01 |
| `docker-compose.yml:17` | "the colocated-Postgres override was Oracle-era legacy" | Reword per D-01 |
| `docs/DEPLOY-KOYEB.md` (6 hits) | Archived-scripts section | Deleted with the file (D-05) |
| `scripts/archive/backup.sh` (4 hits), `deploy.sh` (2 hits), `keepalive.sh` (3 hits) | Oracle Object Storage / Oracle VM references | Deleted whole-file (D-02) — no scrub needed, files vanish |
| `scripts/seed_restore_test.py:18` | `"This script is run ONCE manually by the user on Oracle (runbook check D1)."` | **NOT in CONTEXT.md's file list — flagged below, § New Findings** |
| `utils/embeds.py:294` | `# No Oracle/CPU label — baselines against actual run environment (D-19).` | **NOT in CONTEXT.md's file list — flagged below, § New Findings** |
| `docs/superpowers/specs/2026-04-12-dexter-phase1-design.md:30,117,422,504` | Historical Phase-1 design doc, "Oracle Cloud free tier deployment" | **Ambiguous scope — see § Open Questions (treat as sealed archive vs. scrub target)** |

### `Render` — 2 true positives, ~20 false positives (English word "render"/"rendering")

**True positives (must scrub):**
| File:Line | Content |
|---|---|
| `bot.py:252` | `# Render injects $PORT and routes its public URL to it; default 8000 keeps` |
| `bot.py:254` | `# pinger (UptimeRobot) is what keeps a Render free web service from sleeping.` |

Both already inside the D-01-listed `bot.py` ~216–264 range — no new file to add.

Note: `bot.py:253` (the middle line of this same comment block) also says **"Railway / PC / local working unchanged"** — "Railway" is a third dead-host name not covered by the literal HOST-01/grep-gate term list (`Render`/`Koyeb`/`Oracle`). It will not trip the grep gate if left alone, but it is the same class of dead-cloud-host cruft the D-01 "host-honest narrative rewrite" mandate targets. **Flagged as a discretionary cleanup opportunity, not a new requirement** — recommend folding it into the same comment rewrite since the plan will already be touching this exact line.

**False positives (do NOT touch — legitimate English usage, confirmed by reading each site):**
`cogs/admin.py:90` ("Render the FULL post-write config"), `cogs/music.py:304,1688` (embed re-render), `cogs/ops.py:39,415` (guild-name rendering), `scripts/render_demo_gif.py` (filename + docstring, Phase-23 GIF tooling), `utils/formatters.py:62` / `docs/superpowers/plans/2026-04-12-dexter-phase1-mvp.md:335` (progress-bar "Render" docstring), `README.md:21-27` (demo GIF rendering), `site/src/**` (CSS `text-rendering`, "renders" in demo-mock comments), `personality/prompts.py:144,192,197` ("renders byte-identical").

## New Findings (not in 24-CONTEXT.md's canonical file list)

The phase's actual success gate (ROADMAP.md success criterion 1) is a **repo-wide** grep across "code comments, `config.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, docs" — broader than the HOST-01 requirement text's narrower file list. Two tracked, non-archive files carry live `Oracle` references not enumerated in 24-CONTEXT.md and must be added to the plan's worklist or the phase will not close its own success criterion:

1. **`utils/embeds.py:294`** — `# No Oracle/CPU label — baselines against actual run environment (D-19).` Low-risk, single-line comment reword (e.g. `# No host-CPU label — baselines against actual run environment (D-19).`). Keep the `(D-19)` tag (same discipline as `(K-##)`, D-04's spirit).

2. **`scripts/seed_restore_test.py`** — bigger issue than a stray word. This script's docstring (lines 2–19) describes the *entire* Oracle-era backup/restore workflow: it calls `scripts/backup.sh` (being deleted by D-02, line 6 of the docstring: "Run scripts/backup.sh to produce a fresh dump and upload it to OCI"), references OCI Object Storage download (line 7), and says "run ONCE manually by the user on Oracle" (line 18). After D-02 deletes `scripts/backup.sh`, this script's own documented procedure becomes **factually broken** — it references a file that no longer exists in the repo, not just an outdated hosting name. Two viable options for the planner:
   - **(a) Delete it** — extends D-02's own rationale ("[backup.sh etc] retired by Neon PITR"): if the OCI-backup pipeline this script validates is gone, the validation script has no remaining purpose. Neon's PITR restore is verified via the Neon console UI, not this script.
   - **(b) Rewrite it** for a Neon-PITR-based restore-proof workflow — bigger scope than "reword a comment," would need to replace the `backup.sh`/OCI call with a Neon-console-driven step or `pg_dump` direct-to-Neon-branch equivalent.
   - This research recommends **(a)** as consistent with the phase's stated "low-risk cleanup" framing and D-02's own precedent (dead script → delete, don't half-fix) — but flags it explicitly as a **planner decision**, not a pre-locked one, since CONTEXT.md's D-02 named exactly 4 files and this is a 5th, structurally different (it's in `scripts/`, not `scripts/archive/`).

## Complete `(K-##)` Tag Census — confirms D-04's "12 distinct tags" claim

Ran `git grep -noE "K-[0-9]{2}"` across tracked, non-`.planning/`/non-`milestones/` files. **12 distinct tags confirmed: K-02, K-04, K-05, K-06, K-07, K-09, K-10, K-11, K-12, K-13, K-14, K-16.**

| File | Occurrences | Tags |
|---|---|---|
| `bot.py` | 9 | K-02, K-04(×5), K-05 |
| `config.py` | 5 | K-04(×3), K-05, K-07 |
| `CLAUDE.md` | 5 | K-04(×2), K-07(×2), K-16 |
| `.env.example` | 3 | K-09, K-13(×2) |
| `Dockerfile` | 2 | K-11, K-12 |
| `tests/test_config.py` | 2 | K-04, K-05 |
| `utils/logger.py` | 1 | K-16 |
| `scripts/memory_spike.py` | 1 | K-04 |

D-04's per-file counts (`bot.py(9), config.py(5), CLAUDE.md(5), .env.example(3), Dockerfile(2)`) are **exact matches** to the census above — confirmed, no drift.

**Tags that live ONLY in `docs/DEPLOY-KOYEB.md` and will vanish entirely once it is `git rm`'d:** K-06, K-10, K-14. This is expected and correct — D-04's preservation guarantee only covers the 8 named survivor files; these 3 tags were scoped to the Koyeb runbook itself and have no cross-reference in any of the 8 survivor files. (They may still be referenced by ID inside `.planning/`/`milestones/` archives — that's fine, those are sealed and immune to this deletion.)

**Adjacency confirmed** (term-to-scrub literally on the same line as a `(K-##)` tag — the case D-04's worked example addresses):
- `config.py:22` — `Koyeb ... (K-07)`
- `.env.example:7` — `Koyeb secrets ... — K-13.`
- `.env.example:10` — `Koyeb encrypted Secrets ... (K-13)`
- `Dockerfile:2` — `Koyeb builds ... (K-11); ... (K-12)`
- `bot.py:578` — `K-02: ... Koyeb WEB service.`
- `CLAUDE.md:687` — `Docker/Koyeb log viewers ... (K-16)`
- `utils/logger.py:41` — `Docker/Koyeb log viewers ... (K-16)`

## Verification Grep Command (the Validation Architecture backbone)

`Koyeb` and `Oracle` have **zero false positives** in this repo (every hit found above is a genuine hosting-target reference or lives in a file being deleted). `Render` has heavy false-positive noise from the English word "render"/"rendering". A single unqualified `\b(Render|Koyeb|Oracle)\b` grep is therefore **not** false-positive-free — it will always show ~20 legitimate "render/rendering/rendered" hits, which is a bad automated gate (a human/CI would have to eyeball it every run and could get gate-fatigue).

**Recommended two-part verification, both scoped to tracked files, excluding `.planning/` and `milestones/`:**

```bash
# Part 1 — Koyeb / Oracle: MUST be zero hits after the scrub. No allowlist needed.
git grep -niE '\b(Koyeb|Oracle)\b' -- . ':!.planning' ':!milestones'
# Expected: no output, exit code 1 (git grep exits 1 on no match)

# Part 2 — Render: compare against a fixed allowlist of known-legitimate
# "render/rendering/rendered" (English-word) hits. Any NEW hit not on the
# allowlist is the failure signal.
git grep -niw 'render' -- . ':!.planning' ':!milestones' > /tmp/render_hits.txt
# Diff /tmp/render_hits.txt against the allowlist below (file:line only,
# content may shift slightly on unrelated edits — match by file:line prefix).
```

**Render allowlist (expected survivors, all confirmed non-hosting English-word usage):**
```
cogs/admin.py:90
cogs/music.py:304
cogs/music.py:1688
cogs/ops.py:39
cogs/ops.py:415
docs/superpowers/plans/2026-04-12-dexter-phase1-mvp.md:335
personality/prompts.py:144
personality/prompts.py:192
personality/prompts.py:197
README.md:21
README.md:22
README.md:23
README.md:27
scripts/render_demo_gif.py:2
scripts/render_demo_gif.py:27
scripts/render_demo_gif.py:52
site/src/components/DemoMock.astro:7
site/src/data/demo-transcript.ts:11
site/src/styles/global.css:133
tests/test_formatters.py:1
utils/embeds.py:293
utils/formatters.py:1
utils/formatters.py:62
```

**Success condition for the whole gate:** Part 1 returns zero hits AND Part 2's output is a subset of the allowlist above (no unlisted file:line pairs). This is deterministic, scriptable, and CI-runnable without any secrets.

**Line count sanity check (bonus, cheap):** `test -f docs/DEPLOY-KOYEB.md && echo FAIL || echo OK` and `test -f docs/DEPLOY-DOCKER.md && echo OK || echo FAIL` — confirms the file swap happened.

## Replacement `docs/DEPLOY-DOCKER.md` Content Plan (HOST-02, D-05/D-06)

Cross-checked against the actual `docker-compose.yml` and `bot.py` `/health` endpoint so the doc doesn't drift from what really runs:

1. **Title + status line** — mirrors `docs/DEPLOY-*.md` naming convention (only prior sibling was `DEPLOY-KOYEB.md`, now gone; this becomes the sole file in that namespace).
2. **Prereqs** — Docker + Docker Compose installed (`docker --version`, `docker compose version`). [VERIFIED: this dev machine has Docker 29.5.3 / Compose v5.1.4 — a realistic residential-PC baseline].
3. **Setup steps**, matching `docker-compose.yml`'s actual comment block (lines 1–6) exactly:
   - `cp .env.example .env`
   - Fill `DISCORD_TOKEN`, `GEMINI_API_KEY`, `GENIUS_TOKEN`, and `DATABASE_URL` (Neon pooled DSN, `sslmode=require`) — reference `config.sanitize_database_url()` stripping `channel_binding`/`sslmode` at startup, so the raw Neon string can be pasted as-is.
   - `docker compose up -d --build`
4. **Verify-alive section** — `curl http://localhost:8000/health` (should return `{"status":"ok"}`, HTTP 200 per `bot.py`'s `_run_health_server`), plus `docker compose logs -f bot` / the `logs` named volume for `dexter.log` — confirm no repeated ERROR lines.
5. **Honest framing paragraph (D-06 requirement)** — explicit: this is an on-demand run on a residential IP (YouTube blocks datacenter IPs, per CLAUDE.md's standing hosting note), not a 24/7 cloud standup; the 24/7 deploy stays parked (DEPLOY-F1, future). Single-Discord-token warning carried forward from the old doc's "K-14 Break-Glass Rule" (§7 of the deleted `DEPLOY-KOYEB.md`) — **do not run two bot instances on the same Discord token simultaneously** (gateway conflict, both disconnect in a loop). This rule has zero Koyeb-specific content in its substance (it's about not double-running one token) and should carry forward reworded, not dropped.
6. **What NOT to carry forward** (explicitly out, confirmed by D-06 "lean-but-complete, not the 179-line runbook"): Neon account creation walkthrough (Section 2 of the old doc — assume the reader already has a Neon `DATABASE_URL`, this doc is about running the bot, not standing up Neon from scratch), UptimeRobot keep-alive setup (Section 5 — irrelevant, nothing scales-to-zero on a residential PC), Koyeb-specific secrets UI walkthrough (Section 4), the HeavenCloud/Wispbyte runner-swap contingency (Section 8 — dead alternatives, not relevant to the Docker path), the archived-scripts table (Section 9 — superseded by D-02's deletion + this research's `scripts/seed_restore_test.py` finding above).

**Estimated length:** roughly 40–60 lines (vs. the deleted file's 179) — matches "lean-but-complete."

## HOST-03 UAT Shape (D-08 — matches Phases 03–22 precedent)

`24-HOST-UAT.md` should follow the exact shape of prior parked-UAT docs (`*-HUMAN-UAT.md` precedent cited throughout STATE.md, e.g. `16-HUMAN-UAT.md`, `17-HUMAN-UAT.md`):

- **Checklist items** (owner-run on their PC, real secrets):
  1. `cp .env.example .env`, fill real `DISCORD_TOKEN` / `GEMINI_API_KEY` / `GENIUS_TOKEN` / Neon `DATABASE_URL`.
  2. `docker compose up -d --build` — confirm the image builds cleanly (no `pip install` failures, `ffmpeg` installs via `apt-get`).
  3. `docker compose logs -f bot` — confirm clean startup: `init_db()` succeeds, `on_ready` fires, "Health server task scheduled" logs, no repeated tracebacks.
  4. `curl http://localhost:8000/health` — expect `{"status":"ok"}` / HTTP 200 (or the degraded-503 JSON shape if `HEALTH_STRICT_STATUS` is on and something's actually degraded — that's still "no *new* silent failure," it's truthful reporting per Phase 9's `determine_health_status`).
  5. Confirm no new silent failures in `dexter.log` (the named `logs` volume) beyond what already existed pre-Phase-24 — this is a regression check, not a "must be error-free forever" bar, since e.g. yt-dlp transient errors are expected background noise per CLAUDE.md's Edge Cases table.
  6. Acknowledged-deferred marker, matching the established convention (this doc will show `partial`/deferred until the owner runs it, same as every prior phase's `*-HUMAN-UAT.md`).

**Environment note:** [VERIFIED] Docker 29.5.3 and Docker Compose v5.1.4 are installed and functional in this research session's environment. This does NOT substitute for the human-run UAT (no real Discord token/Neon DSN available in this session — D-08's stated reason for parking it stands), but confirms the boot path itself has no missing-tooling blocker on a typical dev/residential machine.

## HOST-04 Confirmation (D-09)

[VERIFIED] Full-repo grep (`git grep -in "render"`, tracked files, all directories including `.github/workflows/`) found **zero** Render *service/dashboard* configuration anywhere in the tracked repo — no `render.yaml`, no Render-specific CI step, no Render API key reference in any workflow file or script. The only two genuine "Render" hits (`bot.py:252,254`) are comment prose about the `$PORT` convention, not configuration. This confirms D-09's claim that HOST-04 is genuinely un-actionable from the repo side — the Render connection is 100% dashboard-side (GitHub-App-style auto-deploy hookup configured in Render's UI, invisible to `git grep`). No further repo investigation can surface anything here; the plan should document this finding once, not re-search for it.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | HOST-03 boot verification | ✓ | 29.5.3 | — |
| Docker Compose | HOST-03 boot verification | ✓ | v5.1.4 | — |
| Real `DISCORD_TOKEN` / Neon `DATABASE_URL` | HOST-03 actual boot | ✗ (must not live in this session, per D-08) | — | Park as human-run UAT (`24-HOST-UAT.md`) — no viable in-session fallback, by design |
| `git` (for the verification grep) | Success-gate verification | ✓ | — | — |

**Missing dependencies with no fallback:** none blocking — the one "missing" item (real secrets) is intentionally out of scope for this session per the locked D-08 decision, not an environment gap.

## Don't Hand-Roll

Not applicable in the traditional sense (no library/framework selection this phase). The one relevant "don't hand-roll" lesson: **don't hand-roll a new grep gate that includes `Render` unqualified** — as shown above, that produces permanent false-positive noise from the English word. Use the two-part allowlisted approach documented in § Verification Grep Command instead.

## Common Pitfalls

### Pitfall 1: Unqualified `Render` grep produces permanent false positives
**What goes wrong:** A CI check or UAT step that greps for bare `Render` (case-insensitive) will always show ~20 hits from legitimate "render/rendering/rendered" English-word usage across `cogs/`, `utils/formatters.py`, `personality/prompts.py`, `site/`, and `README.md`.
**Why it happens:** "Render" is both a common English verb and a proper-noun hosting service; word-boundary regex alone can't disambiguate.
**How to avoid:** Use the two-part verification (Koyeb/Oracle = zero-tolerance; Render = allowlist diff) documented above.
**Warning signs:** A "grep for Render returns 0" check that keeps failing on unrelated PRs touching `utils/formatters.py` or `site/`.

### Pitfall 2: Deleting `scripts/archive/backup.sh` without checking who else calls it
**What goes wrong:** `scripts/seed_restore_test.py` (not in `scripts/archive/`, so not directly touched by D-02) documents calling `scripts/backup.sh` as step 2 of its own procedure. If D-02's deletion runs without also addressing this file, the repo is left with a tracked script whose documented procedure references a file that no longer exists — a stale/broken reference, and it still contains the word "Oracle" (trips the success gate).
**Why it happens:** D-02's file list (4 files under `scripts/archive/`) doesn't capture cross-references from files *outside* that directory.
**How to avoid:** Address `scripts/seed_restore_test.py` in the same wave as the `scripts/archive/` deletion — either delete it too (recommended, see § New Findings) or rewrite its docstring/procedure.
**Warning signs:** `git grep -l "backup.sh"` after the archive deletion still shows `scripts/seed_restore_test.py`.

### Pitfall 3: Rewriting a `(K-##)`-tagged comment loses the tag
**What goes wrong:** A prose rewrite that changes "Koyeb 2GB ephemeral disk (K-07)" to something like "512MB cap on ephemeral disk" (dropping the trailing `(K-07)`) breaks the cross-reference contract D-04 establishes — `.planning/`/`milestones/` archives reference these IDs, and losing the tag makes a future archive-ID lookup silently fail to find its target in current code.
**Why it happens:** The scrub target (hosting name) and the thing-to-preserve (tag) are often in the same short comment/line, easy to overwrite wholesale.
**How to avoid:** Treat every prose rewrite as "find the hosting word, replace only that word/phrase, verify the `(K-##)` substring is still present in the post-edit line" — the D-04 worked example (`# Koyeb 2GB ephemeral disk (K-07)` → `# 512MB cap on ephemeral disk (K-07)`) is the template for every other line.
**Warning signs:** Post-scrub K-## census (§ above) count drops below 12 distinct tags or below the per-file counts in the table.

### Pitfall 4: Treating `docs/superpowers/` as either fully in-scope or fully out-of-scope without confirming
**What goes wrong:** `docs/superpowers/specs/2026-04-12-dexter-phase1-design.md` is a tracked file (not `.planning/`, not `milestones/`) containing 4 genuine "Oracle" mentions (historical Phase-1 design references to "Oracle Cloud free tier deployment"). It is NOT named in D-03's "explicitly NOT touched" list (which only names `.planning/`, `milestones/`, `dexter-architecture.md`) — but it is also clearly a sealed historical planning artifact from a different (pre-GSD "superpowers") workflow, structurally identical in spirit to `milestones/`.
**Why it happens:** The repo has two parallel planning-archive systems (`.planning/`+`milestones/` for GSD, `docs/superpowers/` for an earlier workflow) and D-03 only named one of them.
**How to avoid:** Planner must explicitly decide and document this (see § Open Questions) rather than silently including or excluding it.
**Warning signs:** The final verification grep either unexpectedly still shows `docs/superpowers/specs/2026-04-12-dexter-phase1-design.md` (if excluded — expected, harmless) or the plan quietly rewrote a sealed historical spec doc without a documented reason (if included without discussion).

## Code Examples

### The D-04 worked rewrite pattern (apply to every Koyeb/Oracle/Render-adjacent-to-tag line)
```python
# Source: config.py:22, this repo, verified via Read tool 2026-07-15
# BEFORE:
AUDIO_CACHE_MAX_MB = 512  # Koyeb 2GB ephemeral disk (K-07)
# AFTER (D-04's own example, locked):
AUDIO_CACHE_MAX_MB = 512  # 512MB cap on ephemeral disk (K-07)
```

### The `$PORT` survivor pattern (bot.py — keep the read, strip the naming)
```python
# Source: bot.py:252-256, this repo, verified via Read tool 2026-07-15
# BEFORE:
try:
    # Render injects $PORT and routes its public URL to it; default 8000 keeps
    # Railway / PC / local working unchanged. The /health route + an external
    # pinger (UptimeRobot) is what keeps a Render free web service from sleeping.
    _health_port = int(os.environ.get("PORT", "8000"))
# AFTER (illustrative — exact wording is Claude's Discretion per CONTEXT.md):
try:
    # $PORT is read for host portability; default 8000 keeps local/Docker
    # runs unchanged. The /health route lets an optional external uptime
    # pinger confirm the process is alive.
    _health_port = int(os.environ.get("PORT", "8000"))
```

### Verification gate, as a runnable script
```bash
# Source: derived from this research's audit, cwd = repo root
set -e
echo "--- Part 1: Koyeb/Oracle (zero-tolerance) ---"
if git grep -niE '\b(Koyeb|Oracle)\b' -- . ':!.planning' ':!milestones'; then
  echo "FAIL: live Koyeb/Oracle references remain"; exit 1
else
  echo "PASS: zero Koyeb/Oracle hits"
fi
echo "--- Part 2: Render (allowlist diff) ---"
git grep -niw 'render' -- . ':!.planning' ':!milestones' | cut -d: -f1,2 > /tmp/render_hits.txt
# Compare /tmp/render_hits.txt to the allowlist in RESEARCH.md § Verification Grep Command
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Koyeb free WEB service + UptimeRobot keep-alive + Neon (Phase 5, v1.1) | On-demand Docker Compose on residential PC + Neon (this phase's honest doc) | Phase 24 (docs-only; the *actual* hosting model already changed in practice back in Phase 5/6 when the 24/7 deploy was parked — this phase just makes the docs match reality) | No runtime change — purely a "the docs finally say what's already true" cleanup. |
| Oracle A1 free-tier VM (v1.0, Phase 4) | Retired entirely; scripts in `scripts/archive/` (soon deleted) | Phase 5 (Koyeb re-target) | Already dead before this phase; this phase removes the last textual traces. |

**Deprecated/outdated:** `docs/DEPLOY-KOYEB.md` (removed this phase), `scripts/archive/{backup,deploy,keepalive}.sh` + `lifecycle-policy.json` (removed this phase), Koyeb/Oracle/HeavenCloud/Wispbyte as viable runner options (already effectively dead; this phase is the paperwork).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `scripts/seed_restore_test.py` should be deleted rather than rewritten (this research's recommendation, option (a)) | § New Findings | Low — if the planner instead chooses to rewrite it, that's a bigger-scope task but still achievable within phase intent; either choice satisfies the grep gate. |
| A2 | `docs/superpowers/{plans,specs}/*` should be treated as a sealed historical archive (same spirit as `.planning/`/`milestones/`) and left untouched, even though D-03 didn't name it explicitly | § Open Questions / Pitfall 4 | Medium — if the planner/user decide it should be scrubbed instead, one file (`2026-04-12-dexter-phase1-design.md`) needs 4 line-level Oracle-mention edits; low effort either way, but the *decision* needs to be made, not defaulted silently. |
| A3 | The "Railway" mention adjacent to the true "Render" hits in `bot.py:253` is worth rewording in the same edit pass even though it's not a named term in HOST-01/the grep gate | § Full Reference Inventory, Render section | Low — purely cosmetic; leaving "Railway" in place does not fail any success criterion. |

**None of these are HIGH risk** — this phase's blast radius is comments/docs/config prose with no runtime behavior change, so even a wrong call on A1/A2/A3 is cheaply correctable in a follow-up edit, not a rollback-requiring mistake.

## Open Questions

1. **Does `docs/superpowers/{plans,specs}/*` count as "the repo" for the grep success criterion, or is it a sealed historical archive like `.planning/`/`milestones/`?**
   - What we know: It is tracked (not gitignored), contains genuine historical "Oracle" mentions in one file (`specs/2026-04-12-dexter-phase1-design.md`, 4 lines), and was NOT named in D-03's "explicitly NOT touched" list (which named only `.planning/`, `milestones/`, `dexter-architecture.md`).
   - What's unclear: Whether its omission from D-03 was deliberate (intended to be scrubbed) or an oversight (D-03's author didn't know this directory existed / forgot it, given it's from an earlier, largely-superseded "superpowers" planning workflow mentioned in project memory).
   - Recommendation: Treat as a sealed archive (exclude from the scrub, same treatment as `milestones/`) by default, since it is historical, dated, describes a since-superseded Phase-1 plan, and rewriting it would falsify the historical record it's meant to preserve — but the plan should state this exclusion explicitly (one line) rather than silently omitting the directory, so a future audit doesn't flag it as a missed scrub target. If the user/planner prefers strict literal-repo-wide compliance instead, the fix is a 4-line edit to one file — trivial either way.

2. **Should `scripts/seed_restore_test.py` be deleted or rewritten?**
   - What we know: Its documented procedure calls `scripts/backup.sh` (deleted by D-02) and references OCI Object Storage + "on Oracle" — the whole workflow it validates depends on infrastructure this phase is removing.
   - What's unclear: Whether the owner still wants *some* restore-proof tooling (even if reworked for Neon PITR) or considers the manual Neon-console PITR restore sufficient going forward.
   - Recommendation: Delete it (option (a) in § New Findings) — consistent with the "low-risk cleanup" phase framing and D-02's own precedent. If the owner later wants a Neon-PITR restore-proof script, that's a new, small, separately-scoped task, not part of this scrub.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing repo-wide suite; `requirements-dev.txt` pins `ruff>=0.15,<0.16` for lint, pytest itself is in `requirements.txt`/dev env, no version pin found in scanned files — confirm via `pip show pytest` at execute time if precision needed) |
| Config file | none dedicated (`pyproject.toml` only configures `[tool.ruff]`; no `[tool.pytest.ini_options]` section found) |
| Quick run command | `pytest tests/test_config.py -x` (fast, no DB needed — confirms K-tag-adjacent tests still pass) |
| Full suite command | `pytest` (repo-wide; CI runs this against a `pgvector/pgvector:pg16` service container per `.github/workflows/ci.yml`) |

### Phase Requirements → Test Map

This phase is documentation/comment/config prose — there is **no natural unit-test surface** for "did the wording change correctly." The closest existing pattern in this repo is the drift-guard style (`tests/test_invite_drift_guard.py`, `tests/test_site_drift_guard.py`) — repo-introspection tests that grep tracked files and assert on the result. That pattern **could** be extended here (see tradeoff below), but the phase's own CONTEXT.md/ROADMAP frame the grep as the success gate directly, not necessarily as a permanent CI-enforced test.

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HOST-01 | Zero live Koyeb/Oracle/Render hosting refs in tracked non-archive files | repo-introspection grep | `git grep -niE '\b(Koyeb\|Oracle)\b' -- . ':!.planning' ':!milestones'` (Part 1) + allowlist diff for Render (Part 2) — see § Verification Grep Command | ❌ Wave 0 — no test file exists yet; can be a plain shell verification step OR a new `tests/test_hosting_drift_guard.py`, planner's call (tradeoff below) |
| HOST-02 | `docs/DEPLOY-KOYEB.md` gone, `docs/DEPLOY-DOCKER.md` exists | file-existence check | `test ! -f docs/DEPLOY-KOYEB.md && test -f docs/DEPLOY-DOCKER.md` | ❌ Wave 0 |
| HOST-03 | `docker compose up` boots cleanly against Neon | manual-only (real secrets, D-08) | N/A — `24-HOST-UAT.md` checklist, human-run | N/A — parked by design |
| HOST-04 | Dashboard-side Render service deleted | manual-only (owner GitHub/Render UI) | N/A | N/A — parked by design, blocked-on-human |

### Sampling Rate
- **Per task commit:** run the Part-1/Part-2 grep verification (cheap, < 1s) after each file's prose is rewritten.
- **Per wave merge:** full grep verification + `pytest tests/test_config.py` (confirms K-05/K-04 tag-adjacent test docstrings/behavior untouched) + ruff lint (`ruff check .`) since prose edits in `.py` files must stay lint-clean.
- **Phase gate:** full grep verification passes (Part 1 = zero, Part 2 = allowlist-subset) + `docs/DEPLOY-KOYEB.md` absent + `docs/DEPLOY-DOCKER.md` present + full `pytest` suite green (proves zero runtime-code-path regression, consistent with "NO runtime code paths change") before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] **Tradeoff for the planner: pytest-based drift guard vs. documented-grep-in-UAT.** Two viable designs:
  - **Option A (lighter):** No new test file. The grep verification (§ above) is run manually/via a shell step during execution and again as part of `24-HOST-UAT.md`'s checklist, but is not a permanent CI-enforced pytest. Pro: matches the phase's "low-risk cleanup, not a feature build" framing, zero new test-maintenance surface. Con: nothing stops a *future* phase from reintroducing a "Koyeb" comment (e.g. copy-pasting old doc prose) — no permanent regression guard, unlike the `test_invite_drift_guard.py` precedent this repo already established for a structurally similar problem (drift/regression in tracked text).
  - **Option B (heavier, matches repo precedent):** A new `tests/test_hosting_drift_guard.py` mirroring `test_invite_drift_guard.py`'s shape — `_tracked_non_archive_files()` helper (git ls-files minus `.planning/`/`milestones/`), a `_scan_for_hosting_terms()` that implements the Part-1/Part-2 logic above, a positive control (inject a fake "Koyeb" string into a `tmp_path` file, assert it's caught) and a negative control (assert the real repo, post-scrub, passes). This becomes a permanent CI-enforced regression guard against hosting-term reintroduction, at the cost of a new ~150-line test file this "low-risk cleanup" phase wasn't originally scoped to include.
  - **Recommendation:** Option B is more consistent with this repo's established CI-drift-guard pattern (2 precedents already exist: invite URL, site content) and is genuinely low-effort given the invite drift-guard is a near-complete template to copy. Recommend the planner include it as a task, sized similarly to the invite drift-guard's own plan effort (~1 small task, `tests/test_hosting_drift_guard.py`), rather than leaving the grep as a one-time manual check that nothing prevents from silently regressing.

*(If Option A is chosen instead: "None — the manual grep documented in `24-HOST-UAT.md` covers HOST-01/02's verification; no CI-permanent guard is in scope this phase.")*

## Security Domain

Not applicable — this phase makes zero changes to authentication, session handling, access control, input validation, or cryptography. It is a text-content-only change (comments, docs, config-file prose) plus deleting dead shell scripts that were never on any request path. No ASVS category is implicated. `security_enforcement` may be enabled repo-wide, but this phase has no security-relevant surface to audit.

## Package Legitimacy Audit

Not applicable — this phase installs **zero** new packages (no `npm install`/`pip install` additions; `requirements.txt`/`requirements-dev.txt` are untouched by every locked decision D-01…D-09). The Package Legitimacy Gate protocol is skipped per its own trigger condition ("whenever this phase installs external packages").

## Sources

### Primary (HIGH confidence — direct repo introspection via tools, 2026-07-15)
- `git grep -ni "koyeb"` / `"render"` / `"oracle"` / `-noE "K-[0-9]{2}"` — full tracked-file census (all tables above)
- `Read` on `bot.py`, `config.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `docs/DEPLOY-KOYEB.md`, `scripts/seed_restore_test.py`, `scripts/memory_spike.py`, `utils/embeds.py`, `tests/test_config.py`, `tests/test_invite_drift_guard.py`, `pyproject.toml`, `requirements-dev.txt`
- `Bash` — `docker --version` / `docker compose version` (confirms 29.5.3 / v5.1.4 installed)
- `.planning/phases/24-hosting-honesty-docker/24-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/config.json` — locked decisions, requirement wording, success criteria, nyquist_validation flag (absent → enabled)

### Secondary (MEDIUM confidence)
- None — this phase required no external/library documentation lookups (no Context7/WebSearch calls made; the entire research surface is this repo's own tracked content).

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- File:line inventory (Koyeb/Oracle/Render): HIGH — exhaustive `git grep` against tracked files, every hit individually read and classified true/false positive.
- K-## tag census: HIGH — cross-verified against D-04's own per-file counts, exact match.
- New findings (`seed_restore_test.py`, `embeds.py`): HIGH that they exist and need action; MEDIUM on the *specific* recommended disposition (delete vs. rewrite) — flagged as A1/A2 assumptions for planner/user confirmation.
- Validation Architecture / drift-guard tradeoff: HIGH on the technical facts (existing precedent, effort estimate); the Option A vs B choice itself is a planner/user decision, not a research finding.

**Research date:** 2026-07-15
**Valid until:** Effectively indefinite for the file:line inventory (static text scrub, doesn't go stale like a library API) — but re-run the grep census once immediately before planning starts if any commits land on `main` between now and plan time, since the inventory is a point-in-time snapshot of tracked file contents.
