# Phase 16: Proactive Memory Callbacks - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-03
**Phase:** 16-proactive-memory-callbacks
**Areas discussed:** Active-moment anchor, Rarity & daily cap, Opt-out control, Callback voice & shape

> **Session note:** User selected all four gray areas, then went AFK (60s no-response) on the
> first area's question. Per the Phase 14/15 "decided on the user's behalf" precedent, Claude
> adopted conservative, requirement-anchored recommendations for all four. All four are flagged
> in CONTEXT.md as recommendations the user should skim and revise before `/gsd-plan-phase 16`.

---

## Active-moment anchor

| Option | Description | Selected |
|--------|-------------|----------|
| Chat message only | Fire only on a user post in the designated channel (`on_message`); recall targets the author. Cleanest "actively here" signal; keeps the surface separate from voice-join ambient roasts. | ✓ (Claude, on user's behalf) |
| Chat + voice-join | Also fire on voice-join — but voice-join already triggers ambient roasts, risking double-fire and cadence-math confusion. | |
| Chat, only after absence | Fire on a message only after the author's silence — better timing but needs per-user last-seen tracking and narrows firing heavily. | |

**User's choice:** AFK — Claude adopted "Chat message only" (D-01).
**Notes:** Separates the three cadences cleanly; recommendation, revisable.

---

## Rarity & daily cap

| Option | Description | Selected |
|--------|-------------|----------|
| Roll < ambient + per-user daily cap | Chance strictly below 0.30–0.35, then an additive PER-USER daily cap, then a recall-floor check; all must pass. | ✓ (Claude, on user's behalf) |
| Per-guild daily cap | Cap the whole server's callbacks/day — wrong bound; lets one chatty user soak the budget or the bot pile onto one person. | |
| Cap-before-roll ordering | Check the cap before the chance roll — contradicts "additive ON TOP OF the probability roll." | |

**User's choice:** AFK — Claude adopted per-user cap, roll→cap→recall ordering (D-02).
**Notes:** Suggested chance ≈ 0.08–0.12, cap ≈ 1/user/day (numeric values planner discretion).
Per-user is the correct privacy/annoyance bound.

---

## Opt-out control

| Option | Description | Selected |
|--------|-------------|----------|
| `/memory callbacks` toggle, boolean on `user_profiles`, default opted-in | Indefinite on/off toggle under the existing `/memory` group; new `proactive_opt_out` column; touches zero memory rows (distinct from forget). | ✓ (Claude, on user's behalf) |
| Timed snooze ("pause 24h") | Auto-expiring pause — extra expiry-tracking complexity for no asked-for benefit. | |
| Separate top-level `/callbacks` command / new table | Worse discoverability than grouping under the surface it controls; a whole table for one boolean is overkill. | |

**User's choice:** AFK — Claude adopted the `/memory callbacks` indefinite toggle (D-03).
**Notes:** Default = opted-in (PROACT-02 frames it as opt-*out*). ALTER TABLE ADD COLUMN IF NOT
EXISTS mirrors Phase 8 `total_errors`.

---

## Callback voice & shape

| Option | Description | Selected |
|--------|-------------|----------|
| Gemini-framed roast, reply-anchored, no ping | Reuse the ambient recall→`build_chat_prompt`→priority-2 path; reply to the triggering message; `AllowedMentions.none()`; template fallback. Sarcasm = the anti-creepy mechanism. | ✓ (Claude, on user's behalf) |
| Verbatim memory | Post the raw stored fact — reads as surveillance, not a bit. | |
| Standalone post + @mention | Drive-by post that pings the user — higher aggression, less clearly anchored to the active moment. | |

**User's choice:** AFK — Claude adopted Gemini-framed, reply-anchored, no-ping (D-04).
**Notes:** Accuracy firewall preserved (episode from memory, numbers from live SQL). Reuse
`_generate_ambient_roast`, don't write a second recall path.

## Claude's Discretion

- Pure-logic gate seam (`logic/proactive.py` mirroring `decide_ambient_roast`).
- Exact numeric knob values (`PROACTIVE_CALLBACK_CHANCE`, `PROACTIVE_CALLBACK_DAILY_CAP`).
- Daily-counter storage mechanism (in-memory dict acceptable; durability not required).
- Trigger-glue cog placement (lean `EventsCog.on_message`).
- `proactive_opt_out` getter/setter shape in `database.py`.

## Deferred Ideas

- Voice-join / return-from-absence as an additional proactive anchor.
- Timed snooze instead of an indefinite toggle.
- Per-guild proactive budget / rate shaping.
- Salience reinforcement (MEM-R1 → v1.4).
- Vision / multimodal roasting → Phase 17.
