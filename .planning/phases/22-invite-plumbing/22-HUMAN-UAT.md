---
status: partial
phase: 22-invite-plumbing
source: [22-VERIFICATION.md]
started: 2026-07-14T00:07:05Z
updated: 2026-07-14T00:07:05Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live invite-and-join flow (Roadmap SC-1 / SC-2 outcome half)
expected: Run /invite in a guild the invoker manages, click "Add to Discord", authorize. Dexter joins the guild, slash commands appear (proving applications.commands scope), and it can join voice + post an embed (proving the permission set is sufficient).
result: [pending]

### 2. /invite usability in a DM (D-06)
expected: Run /invite in a DM with Dexter. The same public embed + "Add to Discord" button appears, with no "this command can't be used here" refusal.
result: [pending]

### 3. Developer Portal byte-for-byte comparison (D-08)
expected: Copy /invite's URL, paste into Discord Developer Portal → Dexter → Installation → install link field, re-run /invite, compare byte-for-byte. The Developer Portal copy and the in-bot /invite copy are identical.
result: [pending]

### 4. Live granted-permissions confirmation (Roadmap SC-1)
expected: In the freshly-invited guild: Server Settings → Roles → Dexter. The ten requested permissions (view_channel, send_messages, embed_links, attach_files, add_reactions, read_message_history, connect, speak, create_public_threads, send_messages_in_threads) are present; Administrator / Manage Server / Manage Roles are NOT.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
