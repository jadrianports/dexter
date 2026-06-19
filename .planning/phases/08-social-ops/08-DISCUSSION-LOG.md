# Phase 8: Social & Ops - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-19
**Phase:** 8-Social & Ops
**Areas discussed:** /roast @user behavior, /leaderboard scope & data, /stats + quota content, Rich /health surface & security, Cog organization, Leaderboard edge cases, Roast tone & prompt, Stats/roast reuse details

---

## /roast @user behavior (SOCIAL-01)

### Visibility
| Option | Description | Selected |
|--------|-------------|----------|
| Public | Everyone in the channel sees the roast | ✓ |
| Ephemeral | Only the invoker sees it | |

### Targets / edge cases
| Option | Description | Selected |
|--------|-------------|----------|
| Anyone — Dex adapts | Self-roast special line; bots turned around; zero-history → "who even are you" | ✓ |
| Humans w/ history only | Block self + bots; no-history → gentle decline | |
| Block self & bots only | No self/bots, but no-history human still roasted | |

### Data scope
| Option | Description | Selected |
|--------|-------------|----------|
| Global per-user | Across all servers; reuses get_user_summary() | ✓ |
| This server only | Guild-scoped; needs new queries | |

### Cooldown
| Option | Description | Selected |
|--------|-------------|----------|
| 30s per-user | One roast / 30s per invoker | ✓ |
| Per-user + per-target | Also limits same-victim frequency | |
| 5s like /ask | Light touch | |

**User's choice:** Public · Anyone (Dex adapts) · Global per-user · 30s per-user.
**Notes:** Roast reuses the priority-1 Gemini path + guaranteed template fallback.

---

## /leaderboard scope & data (SOCIAL-02)

### Scope
| Option | Description | Selected |
|--------|-------------|----------|
| This server only | Per-guild; needs new song_history-by-guild_id aggregates (streaks remain global) | ✓ |
| Global (all servers) | Reuses global user_profiles counters; no new queries | |
| You decide | Planning picks | |

### "Most-skipped" meaning
| Option | Description | Selected |
|--------|-------------|----------|
| Songs (titles) | Rank tracks by skip count (was_skipped grouped by title) | ✓ |
| Users (biggest skippers) | Rank people by skip frequency | |
| Both | Both sections | |

### Layout
| Option | Description | Selected |
|--------|-------------|----------|
| One 3-section embed | All three lists in one embed | ✓ |
| Switchable categories | Dropdown/buttons, one view at a time | |

### Depth / tone
| Option | Description | Selected |
|--------|-------------|----------|
| Top 5 + dry commentary | Top 5 per category + one Dexter line | ✓ |
| Top 10, no commentary | Deeper, plain | |
| Top 5, no commentary | Clean, neutral | |

**User's choice:** Per-server · most-skipped = songs · one 3-section embed · top 5 + dry commentary.
**Notes:** Streaks are global on user_profiles — resolved as: streak section ranks guild-active users by their global streak (D-15).

---

## /stats + quota content (OPS-01 / OPS-03)

### Window
| Option | Description | Selected |
|--------|-------------|----------|
| Today only | Today's bot_daily_stats row | ✓ |
| Today + 7-day | Plus a rolling 7-day total/sparkline | |

### Error counter
| Option | Description | Selected |
|--------|-------------|----------|
| Add total_errors field | New column + increment at error-log site | ✓ |
| Skip error count | Ship without errors this phase | |
| Count from log file | Parse error.log at command time | |

### Quota content
| Option | Description | Selected |
|--------|-------------|----------|
| RPM headroom + image cap | X/15 RPM + today's image generations vs cap | ✓ |
| RPM headroom only | Just the 15-RPM window | |
| RPM + image + raw counts | Plus per-feature raw counts | |

### Quota surface
| Option | Description | Selected |
|--------|-------------|----------|
| Fold into /stats | Quota is a section of the /stats embed | ✓ |
| Separate /quota | Dedicated owner command | |

**User's choice:** Today-only · add total_errors · RPM headroom + image cap · folded into /stats.
**Notes:** Needs a public getter on the rate limiter; /stats is owner-only + bot-wide.

---

## Rich /health surface & security (OPS-02)

### Rich surface
| Option | Description | Selected |
|--------|-------------|----------|
| Rich in Discord /stats | Public /health minimal; rich metrics owner-only in /stats | ✓ |
| Rich on public HTTP | Full metrics JSON from GET /health | |
| Token-gated HTTP /metrics | Secret-guarded rich endpoint | |

### Degraded state
| Option | Description | Selected |
|--------|-------------|----------|
| Degraded body, still 200 | {status:degraded, reasons} but HTTP 200 — no kill-loop | ✓ |
| Non-200 on degraded | 503 → platform restart | |
| Always 200 {status:ok} | Liveness only, as Phase 5 shipped | |

### Phase-6 dependency
| Option | Description | Selected |
|--------|-------------|----------|
| Build with what exists now | Ship with available state + hooks for Phase-6 metrics | ✓ |
| Wait for Phase 6 | Reorder so Phase 6 lands first | |
| You decide | Planning sequences it | |

### Host metrics
| Option | Description | Selected |
|--------|-------------|----------|
| Link Koyeb dashboard | /stats links the platform dashboards | ✓ |
| psutil in-process | Read process/host CPU+RAM in-process | |
| Drop host metrics | Gemini quota only | |

**User's choice:** Rich in Discord /stats · degraded body @ 200 · build with what exists now · link Koyeb/Neon dashboard.
**Notes:** Honors Phase-5 K-02 security; resolves the stale "Oracle CPU/memory" wording → Koyeb+Neon.

---

## Cog organization

### Cog layout
| Option | Description | Selected |
|--------|-------------|----------|
| ops.py + /roast in ai.py | cogs/ops.py for /leaderboard + /stats + health helper; /roast in ai.py | ✓ |
| One social/ops cog | All three in one new cog | |
| ops.py + /roast in events.py | /roast with the ambient-roast helper | |

**User's choice:** cogs/ops.py for dashboards; /roast in ai.py.
**Notes:** /roast is a Gemini slash command like /ask (cooldown + mood + gemini_service already there).

---

## Leaderboard edge cases

### Ties
| Option | Description | Selected |
|--------|-------------|----------|
| Earliest-achieved wins | Secondary sort by oldest first_seen_at | ✓ |
| Alphabetical | Secondary sort by username | |
| You decide | Planning picks | |

### Empty state
| Option | Description | Selected |
|--------|-------------|----------|
| Dry empty-state line | Personality message instead of empty embed | ✓ |
| Empty embed | Embed with zeros / "no data" | |

### Threshold
| Option | Description | Selected |
|--------|-------------|----------|
| Exclude zeros | ≥1 song to rank; skipped board needs ≥1 skip | ✓ |
| Show everyone | Include 0-activity users | |
| You decide | Planning sets minimums | |

**User's choice:** Earliest-achieved ties · dry empty-state line · exclude zeros.

---

## Roast tone & prompt

### Tone
| Option | Description | Selected |
|--------|-------------|----------|
| Harsher, with guardrails | Hits harder (opt-in) but no slurs/protected-class/cruelty; about music behavior | ✓ |
| Same as ambient | No extra meanness | |
| Maximum savage | As hard as Gemini allows | |

### Prompt
| Option | Description | Selected |
|--------|-------------|----------|
| Reuse system prompt + scenario | DEXTER_SYSTEM_PROMPT + "roast this user" scenario + get_user_summary() | ✓ |
| Dedicated roast prompt | Separate harder system prompt | |

**User's choice:** Harsher-with-guardrails · reuse system prompt + scenario.
**Notes:** Respects MAX_AI_RESPONSE_LENGTH=500; CLAUDE.md "dial back for serious" still overrides.

---

## Stats/roast reuse details

### Roast mood
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — reuse mood | Tired/exhausted Dex roasts shorter, like /ask | ✓ |
| No — always full | /roast ignores mood | |

### Leaderboard visibility
| Option | Description | Selected |
|--------|-------------|----------|
| Public | Shareable/competitive | ✓ |
| Ephemeral | Only invoker sees it | |

**User's choice:** /roast respects mood · /leaderboard public.
**Notes:** /stats scope resolved as bot-wide (bot_daily_stats is global by date), owner-only.

---

## Claude's Discretion

- Exact `total_errors` column definition + any new index for leaderboard aggregates.
- Exact SQL for per-guild leaderboard aggregates + the guild-active global-streak ranking query.
- Rate-limiter public getter signature (rpm_usage / rpm_headroom).
- Embed field layout/ordering for /stats and /leaderboard; COLOR_* choices.
- Slash-command names/parameters.
- Roast scenario wording + self/bot/zero-history special-case lines.
- Shared metrics-gatherer helper's home + signature.
- Tertiary tie-break sort (if any).

## Deferred Ideas

- Most-skipped USERS board (chose songs).
- /stats 7-day trend/sparkline (chose today-only).
- Rich metrics on public HTTP / token-gated /metrics (chose Discord-only).
- Non-200 degraded health (chose 200 + degraded body).
- In-process psutil host metrics (chose linked dashboard).
- Phase-6-instrumented pipeline metrics in /stats|/health (hooks left, deferred).
- Per-target roast cooldown / anti-harassment limit (chose per-user 30s).
- Maximum-savage roast / dedicated roast prompt (chose harsher-with-guardrails + reuse).
- Switchable leaderboard category view (chose single 3-section embed).
