// site/src/config.ts
//
// Mirrors config.py's DISCORD_CLIENT_ID / INVITE_PERMISSIONS_VALUE / INVITE_SCOPES
// (see config.py lines ~282-304) and logic/invite.py::build_invite_url()'s output
// shape. Astro cannot import Python, so this is the ONE unavoidable cross-language
// duplication of Dexter's invite URL (Phase 22 D-03/D-07 — build_invite_url() is
// the only permitted constructor everywhere else in this repo).
//
// Mirror the values; never re-derive the policy. If either side ever changes,
// tests/test_site_drift_guard.py (the D-02 CI drift scan, built-artifact level)
// fails the build — that scan is the safety net for this necessary duplication.
const DISCORD_CLIENT_ID = "1492588698364018898";
const INVITE_PERMISSIONS_VALUE = "309240908864";
const INVITE_SCOPES = "bot+applications.commands"; // pre-encoded: discord.py's oauth_url()
                                                     // joins scopes with a space, which
                                                     // application/x-www-form-urlencoded
                                                     // encodes as "+" — this is not a typo.

export const INVITE_URL =
  `https://discord.com/oauth2/authorize?client_id=${DISCORD_CLIENT_ID}` +
  `&scope=${INVITE_SCOPES}` +
  `&permissions=${INVITE_PERMISSIONS_VALUE}`;
