"""Structural review for cogs/ops.py's /guilds app_commands.Group (Phase 20,
OWNER-01…06 / RATE-01).

No live Discord connection — this is the same "structural review + clean
boot" discipline .planning/codebase/TESTING.md prescribes for Discord/process
glue (cog wiring is untested-by-design for *behavior*; these structural
invariants are cheap to lock and catch a real class of regressions):

- the group exposes exactly the six subcommands the plan specifies
- every subcommand's source opens with the inline is_owner() gate
  (OWNER-06/D-06 — default_permissions is a UI hint only, never the real gate)
- _parse_guild_id never raises on malformed input (V5/T-20-05)
- guilds_leave / guilds_block resolve the target via bot.get_guild(...),
  never interaction.guild (Pitfall 3), and reference the OWNER-03 teardown
  tokens (_play_generation, clear_persisted)
"""

from __future__ import annotations

import inspect

from cogs.ops import OpsCog

EXPECTED_SUBCOMMAND_NAMES = {"list", "silence", "unsilence", "leave", "block", "unblock"}


def test_guilds_group_has_six_subcommands():
    """The /guilds group exposes exactly the six subcommands the plan specifies."""
    names = {c.name for c in OpsCog.guilds.commands}
    assert names == EXPECTED_SUBCOMMAND_NAMES


def test_guilds_group_default_permissions_is_admin_ui_hint():
    """default_permissions is set (a UI hint only, D-06) — not the real gate."""
    assert OpsCog.guilds.default_permissions is not None


def test_every_guilds_subcommand_opens_with_inline_is_owner_gate():
    """Every /guilds subcommand's callback source contains the inline is_owner
    check as its real (first-statement) gate — OWNER-06/D-06. default_permissions
    on the group is cosmetic only; this inline check is what actually enforces it."""
    for cmd in OpsCog.guilds.commands:
        src = inspect.getsource(cmd.callback)
        assert "is_owner(interaction.user)" in src, f"{cmd.name} is missing the inline is_owner gate"
        # The gate must be the first real statement in the function body — i.e.
        # it must appear before any other bot/database/gemini access line.
        body_lines = [line for line in src.splitlines() if line.strip() and not line.strip().startswith(("@", '"""'))]
        # Find the first non-docstring, non-decorator, non-def statement inside the body.
        first_stmt_idx = next(
            i for i, line in enumerate(body_lines) if line.strip().startswith(("if not await self.bot.is_owner",))
        )
        # Nothing awaits/accesses bot state before that line except the def signature itself.
        preceding = body_lines[:first_stmt_idx]
        assert all(
            line.strip().startswith(("async def", "def", '"""', "'''")) or "is_owner" not in line for line in preceding
        )


def test_parse_guild_id_never_raises_on_malformed_input():
    """_parse_guild_id returns None (never raises) on non-numeric input (V5/T-20-05)."""
    cog_method = OpsCog._parse_guild_id
    assert cog_method(None, "not-a-number") is None
    assert cog_method(None, "") is None
    assert cog_method(None, None) is None


def test_parse_guild_id_parses_valid_numeric_string():
    """_parse_guild_id parses a well-formed numeric string to int."""
    assert OpsCog._parse_guild_id(None, "123") == 123
    assert OpsCog._parse_guild_id(None, "  456  ") == 456


def _code_only(src: str) -> str:
    """Strip full-line and inline `#` comments so a comment mentioning a
    forbidden token (e.g. explaining what NOT to do) doesn't false-positive
    a source-grep assertion."""
    lines = []
    for line in src.splitlines():
        code_part = line.split("#", 1)[0]
        lines.append(code_part)
    return "\n".join(lines)


def test_guilds_leave_resolves_target_via_get_guild_never_interaction_guild():
    """guilds_leave resolves the target guild via bot.get_guild(...), never
    interaction.guild (Pitfall 3) — the owner invokes this from their own
    guild/DM against a guild they are not necessarily present in."""
    src = _code_only(inspect.getsource(OpsCog.guilds_leave.callback))
    assert "self.bot.get_guild(" in src
    assert "interaction.guild" not in src


def test_guilds_block_resolves_target_via_get_guild_never_interaction_guild():
    """Same Pitfall-3 guard for guilds_block."""
    src = _code_only(inspect.getsource(OpsCog.guilds_block.callback))
    assert "self.bot.get_guild(" in src
    assert "interaction.guild" not in src


def test_force_leave_teardown_mirrors_stop_template_tokens():
    """_force_leave_teardown references the exact /stop teardown sequence
    tokens: _play_generation bump, clear_persisted, and voice disconnect —
    the OWNER-03 discipline (cogs/music.py::stop)."""
    src = inspect.getsource(OpsCog._force_leave_teardown)
    assert "_play_generation" in src
    assert "clear_persisted" in src
    assert "queue.clear()" in src
    assert "voice_client.stop()" in src
    assert "voice_client.disconnect()" in src
    assert "target_guild.leave()" in src


def test_guilds_block_runs_teardown_then_blacklist_insert():
    """/guilds block calls _force_leave_teardown (when the target is present)
    THEN block_guild — teardown-then-blacklist, in that order (D-11)."""
    src = inspect.getsource(OpsCog.guilds_block.callback)
    teardown_idx = src.index("_force_leave_teardown")
    block_idx = src.index("block_guild(")
    assert teardown_idx < block_idx


def test_guilds_block_still_blacklists_a_guild_already_gone():
    """block_guild is called unconditionally, outside any `if target is not
    None` guard — a guild the bot is no longer in can still be blacklisted."""
    src = inspect.getsource(OpsCog.guilds_block.callback)
    # The block_guild call must be at the same (or lower) indentation as the
    # `if target is not None:` teardown branch, i.e. NOT nested inside it.
    lines = src.splitlines()
    teardown_branch_indent = None
    block_call_indent = None
    for line in lines:
        if "if target is not None:" in line:
            teardown_branch_indent = len(line) - len(line.lstrip())
        if "await self.bot.guild_config.block_guild(" in line:
            block_call_indent = len(line) - len(line.lstrip())
    assert teardown_branch_indent is not None
    assert block_call_indent is not None
    assert block_call_indent <= teardown_branch_indent


def test_guilds_unblock_does_not_rejoin():
    """/guilds unblock never calls guild.join or invites — deletion only (D-11)."""
    src = inspect.getsource(OpsCog.guilds_unblock.callback)
    assert "unblock_guild(" in src
    assert ".join(" not in src


def test_silence_unsilence_use_parse_guild_id_and_report_no_row_honestly():
    """silence/unsilence parse guild_id via _parse_guild_id and honor the
    False (no-row) contract from the service methods — no false success."""
    silence_src = inspect.getsource(OpsCog.guilds_silence.callback)
    unsilence_src = inspect.getsource(OpsCog.guilds_unsilence.callback)
    for src, method in ((silence_src, "silence_guild"), (unsilence_src, "unsilence_guild")):
        assert "_parse_guild_id(" in src
        assert f"{method}(" in src
        assert "if not ok" in src
