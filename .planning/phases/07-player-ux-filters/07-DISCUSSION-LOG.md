# Phase 7: Player UX & Filters - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-19
**Phase:** 7-Player UX & Filters
**Areas discussed:** Button control & access, Filter behavior, Favorites model, Playlists model, /seek mechanics & bounds, Command surface & naming, Error & empty states, Button feedback details

---

## Button control & access

| Option | Description | Selected |
|--------|-------------|----------|
| The 5 core | play/pause, skip, loop, shuffle, stop — exactly the success criterion | ✓ |
| 5 core + ❤ favorite | adds a save-current button | |
| 5 core + queue view | adds a queue-list button | |

**User's choice:** The 5 core buttons.

| Option | Description | Selected |
|--------|-------------|----------|
| Anyone in the voice call | listeners control; blocks text-channel hijack | ✓ |
| Anyone in the text channel | most permissive | |
| Only the song's requester | strictest | |

**User's choice:** Anyone in the voice call.

| Option | Description | Selected |
|--------|-------------|----------|
| Persist while playing / across restart | persistent view (timeout=None + custom_id, re-registered on boot) | ✓ |
| Timed view (matches existing menus) | expires after inactivity | |

**User's choice:** Persistent view.

---

## Filter behavior

| Option | Description | Selected |
|--------|-------------|----------|
| From current position | re-encode + resume at the same spot; reuses /seek -ss machinery | ✓ |
| Restart from 0:00 | rebuild source from start | |

**User's choice:** From current position.

| Option | Description | Selected |
|--------|-------------|----------|
| Sticky until /filter off | stays on for current + following tracks; guild-level state, per-track check | ✓ |
| Per-track only, auto-clears | resets each track | |

**User's choice:** Sticky until /filter off.

| Option | Description | Selected |
|--------|-------------|----------|
| One at a time | /filter replaces active; off clears | ✓ |
| Stackable | combine effects | |

**User's choice:** One at a time.
**Notes:** Per-user vs whole-channel was not asked — architecture forces whole-playback (one voice stream per guild).

---

## Favorites model

| Option | Description | Selected |
|--------|-------------|----------|
| Per-user, global | follow the user across servers; keyed by user_id | ✓ |
| Per-user, per-server | scoped to the saving server | |

**User's choice:** Per-user, global.

| Option | Description | Selected |
|--------|-------------|----------|
| Currently-playing song only | /favorite saves what's playing | ✓ |
| Current song OR search/URL | adds a resolve path | |

**User's choice:** Currently-playing song only.

| Option | Description | Selected |
|--------|-------------|----------|
| Pick-list select menu | reuse SongSelect; pick one to queue | ✓ |
| Queue all at once | dump every favorite into the queue | |
| List + 'add all' button | both | |

**User's choice:** Pick-list select menu.

| Option | Description | Selected |
|--------|-------------|----------|
| 25 — fits one menu | single select menu, no pagination | ✓ |
| 50 — paginated | needs a paginated picker | |
| No cap | unbounded | |

**User's choice:** 25.

---

## Playlists model

| Option | Description | Selected |
|--------|-------------|----------|
| Frozen snapshot | captures queue at save time; reuses guild_queues JSONB | ✓ |
| Living collection | editable named list | |

**User's choice:** Frozen snapshot.

| Option | Description | Selected |
|--------|-------------|----------|
| Per-user | parallels Favorites; keyed user_id | ✓ |
| Server-shared | anyone loads a shared name | |

**User's choice:** Per-user.

| Option | Description | Selected |
|--------|-------------|----------|
| Append to current queue | non-destructive; respects 500 cap | ✓ |
| Replace the queue | destructive 'restore' | |

**User's choice:** Append to current queue.

| Option | Description | Selected |
|--------|-------------|----------|
| Overwrite (upsert) | re-saving a name updates it | ✓ |
| Reject with an error | refuse on name clash | |

**User's choice:** Overwrite (upsert).

---

## /seek mechanics & bounds

| Option | Description | Selected |
|--------|-------------|----------|
| mm:ss and raw seconds | accept '1:30' and '90' (+ h:mm:ss) | ✓ |
| mm:ss only | only '1:30' | |
| Add relative (+30 / -10) | relative jumps too | |

**User's choice:** mm:ss and raw seconds.

| Option | Description | Selected |
|--------|-------------|----------|
| Skip to next track | advance like a skip | ✓ |
| Clamp near the end | jump to just-before-end | |
| Reject with a sarcastic error | refuse | |

**User's choice:** Skip to next track.

---

## Command surface & naming

| Option | Description | Selected |
|--------|-------------|----------|
| Two flat commands | /favorite + /favorites; removal in picker | ✓ |
| One group /favorites add\|list\|remove | subcommand group | |

**User's choice:** Two flat commands (favorites).

| Option | Description | Selected |
|--------|-------------|----------|
| Group /playlist save\|load\|list\|delete | 4 verbs under one command | ✓ |
| Flat (/saveplaylist, /loadplaylist, …) | 4 top-level commands | |

**User's choice:** Group (playlists).

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed choices dropdown | app_commands.Choices, typo-proof | ✓ |
| Free text argument | parsed against known presets | |

**User's choice:** Fixed choices dropdown (filter).

---

## Error & empty states

| Option | Description | Selected |
|--------|-------------|----------|
| Ephemeral — only the user sees | keeps channel clean | ✓ |
| Public in-channel | visible failures | |

**User's choice:** Ephemeral.

| Option | Description | Selected |
|--------|-------------|----------|
| Dexter's sarcastic templated voice | personality/responses.py pools + fallback | ✓ |
| Plain neutral errors | embeds.error() straight wording | |

**User's choice:** Dexter's sarcastic templated voice.

---

## Button feedback details

| Option | Description | Selected |
|--------|-------------|----------|
| off → single → queue → off | full LoopMode cycle; label reflects mode | ✓ |
| off → queue → off (toggle) | skip single on the button | |

**User's choice:** off → single → queue → off.

| Option | Description | Selected |
|--------|-------------|----------|
| Immediate, like /stop | one press stops + clears + leaves | ✓ |
| Confirm first | ephemeral 'really?' | |

**User's choice:** Immediate, like /stop.

| Option | Description | Selected |
|--------|-------------|----------|
| Silently update the now-playing embed | re-render to reflect state; ack interaction | ✓ |
| Ephemeral confirmation toast | short ephemeral line | |
| Public personality line | public sarcastic line per press | |

**User's choice:** Silently update the now-playing embed.

---

## Claude's Discretion

- Exact table/column names + indexes for `user_favorites` / `user_playlists`.
- `custom_id` scheme for the persistent button view.
- FFmpeg filter-chain strings per preset.
- `/seek` time-string parser implementation.
- Select-menu removal UX for `/favorites`.
- Optional tiny ephemeral "saved." / "removed." confirmation.

## Deferred Ideas

- ❤ favorite button + queue-view button on the now-playing embed.
- `/filter` stacking / combinable effects.
- Relative seek (`+30` / `-10`).
- Server-shared / living (editable) playlists.
- Favoriting by search/URL.
- Explicit `/favorites remove` command + confirm-on-stop.
