# logic/ — pure, side-effect-free decision functions extracted from cog glue (Phase 10, TEST-01).
# Modules in this package import from each other but never from discord, asyncio, or the DB.
# ONE documented exception (Phase 22): logic/invite.py imports discord solely for the offline,
# deterministic OAuth2-URL-building and Permissions helpers in discord.utils (no I/O) — see
# that module's docstring for why this is safe and necessary.
