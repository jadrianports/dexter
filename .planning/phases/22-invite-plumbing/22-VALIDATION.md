---
phase: 22
slug: invite-plumbing
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-14
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `22-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (installed; `requirements.txt`) — 1132 tests currently collected |
| **Config file** | none — pytest runs on defaults; `tests/conftest.py` holds shared fixtures (pgvector codec, DB) |
| **Quick run command** | `pytest tests/test_invite_logic.py tests/test_invite_drift_guard.py tests/test_invite_cog.py -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~2s (this phase's own tests); full suite unchanged |

**CI parity note (D-04's entire rationale):** `.github/workflows/ci.yml` runs `pytest -q` with
**zero secrets** and no `.env` (only a pgvector service container for `TEST_DATABASE_URL`). Every
test below is designed to pass green in that environment — which is *why* `DISCORD_CLIENT_ID` is a
committed public constant rather than env-only. This phase touches no DB, no Gemini, no voice.

---

## Sampling Rate

- **After every task commit:** Run the quick command above
- **After every plan wave:** Run `pytest -q` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 22-01-* | 01 | 1 | INVITE-01 | T-22-01 | Bitfield is exactly `309240908864`; `administrator`, `manage_guild`, `manage_roles`, `manage_channels`, `ban_members`, `kick_members` all assert `False` (D-02 negative lock) — a future silent privilege escalation fails CI instead of shipping | unit | `pytest tests/test_invite_logic.py -q` | ❌ W0 | ⬜ pending |
| 22-01-* | 01 | 1 | INVITE-01 | — | `build_invite_url()` output carries `scope=bot+applications.commands` and the locked permissions value | unit | `pytest tests/test_invite_logic.py::test_url_contains_expected_scopes -q` | ❌ W0 | ⬜ pending |
| 22-02-* | 02 | 2 | INVITE-02 | T-22-02 | Every git-tracked, non-`.planning/`, text-extension doc's OAuth2 URL literally equals `build_invite_url()`'s output — drift is structurally impossible, not merely discouraged (SC-3) | unit (repo-introspection) | `pytest tests/test_invite_drift_guard.py::test_no_doc_contains_a_drifted_invite_url -q` | ❌ W0 | ⬜ pending |
| 22-02-* | 02 | 2 | INVITE-02 | T-22-02 | **Positive control:** the scanner provably FINDS a URL when one is present (`tmp_path` fixture) — proves today's vacuous pass is not a false green | unit | `pytest tests/test_invite_drift_guard.py::test_drift_guard_actually_detects_a_mismatch -q` | ❌ W0 | ⬜ pending |
| 22-02-* | 02 | 2 | INVITE-02 (SC-2) | — | `/invite` exists, is DM-allowed, and replies publicly with an embed + link-style button whose `url` equals `build_invite_url()`'s output | unit (cog-level, mocked interaction) | `pytest tests/test_invite_cog.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_invite_logic.py` — INVITE-01: bitfield lock + D-02 negative assertion + URL/scope shape
- [ ] `tests/test_invite_drift_guard.py` — INVITE-02/SC-3: git-doc drift guard + positive control
- [ ] `tests/test_invite_cog.py` — SC-2: cog-level, mocked `interaction.response.send_message`
- [ ] No new `conftest.py` fixtures needed — this phase touches no DB, Gemini, or voice; bare pytest suffices

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Developer Portal install-link field matches `/invite` byte-for-byte | INVITE-02 / SC-3 (**D-08**) | The Dev Portal install-link field is set by hand in a third-party web UI — genuinely not code, and no CI can reach it | Run `/invite`, copy the URL. In the Discord Developer Portal → Dexter app → Installation → set the install link to that exact URL. Re-run `/invite` and compare byte-for-byte. |
| The link actually adds Dexter to a real guild | INVITE-02 / SC-2 | Requires a live Discord OAuth2 consent flow against a real guild the invoker manages | Click `/invite`'s "Add to Discord" button, select a test guild, authorize. Confirm Dexter joins, slash commands appear (`applications.commands` scope), and it can join voice + post embeds (permission set is sufficient). |
| Granted permissions match the requested 10 | INVITE-01 / SC-1 | Requires inspecting Dexter's role in a live, freshly-invited guild | In the new guild: Server Settings → Roles → Dexter. Confirm the 10 permissions from D-01/D-09 are present and that **Administrator / Manage Server / Manage Roles are NOT**. |

**Note:** These land in `22-HUMAN-UAT.md` at phase close — the same acknowledged-deferred pattern
every phase since 11 has used (blocked on a live Discord host). They are `human_needed`
verification, **not** code gaps.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-14
