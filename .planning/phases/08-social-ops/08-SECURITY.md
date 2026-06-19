---
phase: 08
slug: social-ops
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-19
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Plans: 08-01 (data/service foundation), 08-02 (/roast), 08-03 (ops surface — /leaderboard, /stats, /health).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| caller → database leaderboard helpers | `get_leaderboard_*` receive a Discord `guild_id` snowflake string | guild_id (untrusted string) into SQL |
| caller → `increment_daily_stat` | a stat-field name string selects a column to update | field name (must be allowlisted) into a column update |
| Discord user → `/roast` | invoker selects a target Member; `target.display_name` flows into a public message | display name (untrusted) into public Discord send |
| `/roast` → Gemini | target taste summary flows into the LLM prompt | user's own tracked music data into the LLM |
| public internet → `GET /health` | unauthenticated HTTP request from Koyeb / UptimeRobot / anyone | bot health status crosses out to the public |
| Discord user → `/stats` | only the bot owner may see rich bot-state | guild/shard/pool/quota internals (owner-only) |
| Discord user → `/leaderboard` | guild_id flows into per-guild aggregate queries | guild_id into SQL; results scoped to one guild |
| error path → `log_to_discord` | a stat-field write happens on the error path (recursion risk) | total_errors increment on an already-failing path |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-08-01 | Tampering | `get_leaderboard_*` SQL (guild_id, title) — database.py | mitigate | asyncpg `$1`/`$2` positional params only; `guild_id` bound as a value, `title` read back from rows, never interpolated. Evidence: `database.py:402,424,449`. | closed |
| T-08-02 | Tampering | `increment_daily_stat` field-name — database.py | mitigate | `allowed_fields` allowlist gates the column name (`"total_errors"` added); non-allowlisted field raises `ValueError`. Evidence: `database.py:274-281`. | closed |
| T-08-03 | Tampering | npm/pip installs (Plan 01) | accept | No new packages this phase; `requirements.txt` unchanged since Phase 5 (`7e5d66f`). | closed |
| T-08-04 | Spoofing | public `/roast` send (target string) — cogs/ai.py | mitigate | `allowed_mentions=discord.AllowedMentions.none()` on every public followup (success / empty / fallback); `display_name` is a plain string, never a raw mention tag. Evidence: `cogs/ai.py:201,205,210`. | closed |
| T-08-05 | Denial of Service | shared 15-RPM Gemini budget (/roast) | mitigate | 30s per-invoker cooldown + `priority=1` (waits, never spins) + guaranteed template fallback. Evidence: `config.py:64`, `cogs/ai.py:150,192,207-210`. | closed |
| T-08-06 | Information Disclosure | roast content (no slurs / protected-class) | accept | Guardrails encoded in system prompt + `ROAST_*` pools (music-behavior only, lowercase voice constraints `personality/roasts.py:1-15`); no PII beyond the user's own tracked data; content quality is a manual UAT gate. | closed |
| T-08-07 | Tampering | npm/pip installs (Plan 02) | accept | No new packages this phase; `requirements.txt` unchanged. | closed |
| T-08-08 | Information Disclosure | public `GET /health` body — bot.py | mitigate | Body contains only `status` + generic `reasons` strings — no guild/shard/pool internals; rich metrics live only in owner `/stats` (ephemeral). Evidence: `bot.py:219-222`. | closed |
| T-08-09 | Elevation of Privilege | `/stats` owner gate — cogs/ops.py | mitigate | Authoritative inline `await self.bot.is_owner(interaction.user)` is the FIRST statement, before `defer()` and any data access; non-owner gets ephemeral refusal + return. Evidence: `cogs/ops.py:183-185`. | closed |
| T-08-10 | Tampering | `/leaderboard` SQL (guild_id) — cogs/ops.py | mitigate | Cog passes `str(guild.id)` to Plan-01 helpers, which bind it as `$1`; never interpolated; guild-scoped (no cross-guild leak). Evidence: `cogs/ops.py:152-157`, `database.py:402,424,449`. | closed |
| T-08-11 | Denial of Service | non-200 `/health` kill-loop — bot.py | mitigate | `_aio_web.Response` returned with no `status=` kwarg → HTTP 200 in every branch (incl. the `except` fallback) so Koyeb/Neon never kill-loop. Evidence: `bot.py:215,224-227`. | closed |
| T-08-12 | Denial of Service | `total_errors` increment recursion — utils/logger.py | mitigate | Inner `try/except Exception: pass` around the increment isolates a DB-down failure so it never re-enters `log_to_discord`. Evidence: `utils/logger.py:68-73`. | closed |
| T-08-13 | Tampering | npm/pip installs (Plan 03) | accept | No new packages this phase; `requirements.txt` unchanged. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-08-01 | T-08-03 | No new packages introduced in Phase 8 Plan 01; `requirements.txt` last modified in Phase 5 (`7e5d66f`). | gsd-security-auditor | 2026-06-19 |
| AR-08-02 | T-08-06 | Roast content guardrails enforced via voice-register constraints (`personality/roasts.py:1-15`) — music-behavior only, no slurs/protected-class; no PII beyond the user's own tracked music data; quality is a manual UAT gate. | gsd-security-auditor | 2026-06-19 |
| AR-08-03 | T-08-07 | No new packages introduced in Phase 8 Plan 02; `requirements.txt` unchanged. | gsd-security-auditor | 2026-06-19 |
| AR-08-04 | T-08-13 | No new packages introduced in Phase 8 Plan 03; `requirements.txt` unchanged. | gsd-security-auditor | 2026-06-19 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-19 | 13 | 13 | 0 | gsd-security-auditor (model: sonnet) via /gsd:secure-phase 08 |

### Audit Notes (2026-06-19)

- **T-08-01 (SQL injection — leaderboard):** `guild_id` is never interpolated into an f-string in any of the three leaderboard helpers; `title` in `get_leaderboard_skips` is read back from result rows only, not used to build SQL.
- **T-08-04 (mention spoofing):** All three `followup.send()` paths in `/roast` (success, empty-result, exception fallback) carry `allowed_mentions=discord.AllowedMentions.none()` — no path skips the guard (`cogs/ai.py:196-210`).
- **T-08-09 (owner gate):** The `is_owner` check fires before `defer()`, so the gate executes before any async data work begins.
- **T-08-11 (health HTTP 200):** The aiohttp `Response` constructor has no `status=` argument; the `except` fallback (`reasons = ["metrics gatherer unavailable"]`) routes to the same return, so no 5xx is ever emitted.
- **T-08-12 (recursion guard):** The inner `try/except Exception: pass` is nested inside the outer `try` covering `channel.send`; the increment fires only after a successful send and its failure is isolated from the outer error path.
- **Unregistered flags:** None. All three SUMMARY.md files report zero threat flags; no new attack surface detected beyond the registered threats.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-19
