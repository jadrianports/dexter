"""Pure invite-URL builder (Phase 22 / INVITE-01 / INVITE-02 / D-03, D-07).

This is the ONLY place an invite URL is ever constructed (D-03/D-07) —
``cogs/invite.py`` (plan 22-02) calls ``build_invite_url`` and never
hand-builds a URL, and ``tests/test_invite_drift_guard.py`` (plan 22-03)
structurally enforces that every invite link anywhere in the repo's tracked
docs matches this function's output.

Deliberate convention deviation: every other ``logic/`` module's docstring
promises "no ``discord``" (Phase 10 D-01/D-02, extended Phase 16/17). This
module imports ``discord`` — a real, acknowledged break from that letter,
not a silent oversight. It is still safe and necessary:

  - discord.py's ``oauth_url()`` helper (in ``discord.utils``) and
    ``discord.Permissions()`` are both offline, deterministic, no-I/O,
    no-network helpers. This module still satisfies the *spirit* of the
    pure-seam rule (deterministic, side-effect-free, no clock/RNG/network) —
    it just also imports the one library that knows how to spell Discord's
    own query-string format correctly.
  - Hand-rolling the URL to dodge the import would recreate exactly the
    second URL constructor D-07 prohibits (no shorteners, no vanity
    redirects, no hand-built query strings — the literal OAuth2 endpoint
    only). Wrapping the library helper below is the documented,
    version-verified way to avoid that (RESEARCH.md, discord.py 2.7.1).

Locked by tests/test_invite_logic.py.
"""

from __future__ import annotations

import discord

# ---------------------------------------------------------------------------
# build_invite_url
# ---------------------------------------------------------------------------


def build_invite_url(
    *,
    client_id: int,
    permissions_value: int,
    scopes: tuple[str, ...] = ("bot", "applications.commands"),
) -> str:
    """Build Dexter's OAuth2 invite URL.

    Pure function: given the same arguments, always returns the same string.
    No clock, no RNG, no network call — this wraps a plain string formatter
    over its inputs (see the single call site below).

    Args:
        client_id: The Discord application/client ID (``config.DISCORD_CLIENT_ID``).
        permissions_value: The least-privilege bitfield
            (``config.INVITE_PERMISSIONS_VALUE`` == 309240908864, D-01/D-09).
        scopes: OAuth2 scopes to request. Defaults to the config tuple
            (``config.INVITE_SCOPES``) but is overridable — never hardcode a
            different default here than the config constant conceptually
            represents.

    Returns:
        The literal ``https://discord.com/oauth2/authorize?...`` URL — never
        a shortener or vanity redirect (D-07).
    """
    return discord.utils.oauth_url(
        client_id,
        permissions=discord.Permissions(permissions_value),
        scopes=scopes,
    )
