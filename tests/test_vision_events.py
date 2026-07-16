"""Behavioral glue tests for the Phase 17 vision-roast surface (VIS-01/VIS-02).

Locks `EventsCog._maybe_fire_vision_roast`, `EventsCog._generate_vision_roast`,
and the module-level `_first_valid_image_attachment` structural gate:

  * the D-02 before-download mime/size gate (zero bytes fetched on reject),
  * the VIS-02 silent-skip (safety block / empty) vs template-fallback
    (transport failure) distinction — the safety-critical piece,
  * the reply-anchored AllowedMentions.none() send + per-user cooldown mark,
  * the shared Phase 16 opt-out.

Mock style mirrors tests/test_proactive_events.py (`_make_bot` helper, spec'd
discord.* mocks, patched `cogs.events.database.get_proactive_opt_out` +
`cogs.events.random.random`); no live Discord or DB connection.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import config
from cogs.events import EventsCog, _first_valid_image_attachment
from personality import roasts
from services.gemini import GeminiAPIError, GeminiRateLimitError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot() -> MagicMock:
    """Return a minimal fake bot with a pool; memory_service explicitly disabled.

    Phase 20 / D-14: `_maybe_fire_vision_roast` now re-checks the silence-aware
    `guild_config` cache immediately before `message.reply` (SC-2 pre-send
    re-check). Without an explicit configured/non-silenced row here, a bare
    `MagicMock()` `.get(...)` return value is truthy for every key lookup
    (including `silenced`), which would make the re-check bail on every test.
    Mirrors `tests/test_proactive_events.py::_make_bot`'s shape.

    MEM-07: `_maybe_fire_vision_roast`'s success tail now spawns a fire-and-forget
    `memory_service.distill_and_remember(...)` via `asyncio.create_task`. A bare
    `MagicMock()` bot would make `getattr(self.bot, "memory_service", None)`
    return a truthy auto-generated Mock (not None), whose `distill_and_remember(...)`
    call returns a non-awaitable MagicMock — `asyncio.create_task` then raises
    `TypeError: a coroutine was expected`. Set `memory_service = None` explicitly so
    these reply/cooldown-focused tests stay isolated from the MEM-07 write path
    (covered instead by the live-DB `TestVisionRoastMemory` round-trip in
    `tests/test_database_phase25.py`), consistent with the existing Phase 16/17
    "Discord glue is untested-by-design" precedent for fire-and-forget writes.
    """
    bot = MagicMock()
    bot.pool = MagicMock()
    bot.memory_service = None
    bot.guild_config = MagicMock()
    bot.guild_config.get = MagicMock(
        return_value={
            "configured": True,
            "ambient_channel_id": "500",
            "ambient_roasts_enabled": True,
            "vision_roasts_enabled": True,
        }
    )
    return bot


def _make_bot_with_memory() -> MagicMock:
    """Like `_make_bot()`, but with a wired `memory_service` (WR-03).

    `_make_bot()` sets `memory_service = None` to dodge a real bug: a bare
    `MagicMock()` auto-attributes `.distill_and_remember(...)` as a truthy,
    non-awaitable child `MagicMock`, and `asyncio.create_task(...)` on that
    raises `TypeError: a coroutine was expected` (see 25-02 SUMMARY). The
    correct fix for exercising the MEM-07 write's call-site wiring is NOT to
    reintroduce a bare `MagicMock()` — it's to give `memory_service` an
    explicit `AsyncMock` `distill_and_remember`, whose call DOES return a real
    awaitable coroutine (so `create_task` works) while still recording call
    args for assertion.
    """
    bot = _make_bot()
    bot.memory_service = MagicMock()
    bot.memory_service.distill_and_remember = AsyncMock()
    return bot


def _make_attachment(content_type: str | None, size: int) -> MagicMock:
    """Return a fake discord.Attachment with content_type/size and an AsyncMock read."""
    attachment = MagicMock(spec=discord.Attachment)
    attachment.content_type = content_type
    attachment.size = size
    attachment.read = AsyncMock(return_value=b"\x89PNG fake image bytes")
    return attachment


def _make_message(
    attachments: list | None = None,
    user_id: int = 1,
    guild_id: int = 100,
    channel_id: int = 500,
) -> MagicMock:
    """Return a minimal fake discord.Message with a spec'd Member author + attachments."""
    message = MagicMock(spec=discord.Message)

    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    message.guild = guild

    channel = MagicMock()
    channel.id = channel_id
    message.channel = channel

    author = MagicMock(spec=discord.Member)
    author.id = user_id
    author.display_name = "Tester"
    author.bot = False
    message.author = author

    message.content = "look at this"
    message.attachments = attachments if attachments is not None else []
    message.reply = AsyncMock()
    return message


_GOOD_SIZE = 1024  # well under MAX_VISION_IMAGE_BYTES (8MB)


# ---------------------------------------------------------------------------
# (A) structural gate — before-download mime/size reject (D-02 / VIS-01 / T-17-01)
# ---------------------------------------------------------------------------


def test_structural_gate_rejects_oversized():
    """An attachment over MAX_VISION_IMAGE_BYTES is rejected on metadata alone."""
    oversized = _make_attachment("image/png", config.MAX_VISION_IMAGE_BYTES + 1)
    message = _make_message(attachments=[oversized])
    assert _first_valid_image_attachment(message) is None
    oversized.read.assert_not_awaited()


def test_structural_gate_rejects_non_allowlisted_mime():
    """image/gif (deliberately excluded) is rejected — never reaches Gemini."""
    gif = _make_attachment("image/gif", _GOOD_SIZE)
    message = _make_message(attachments=[gif])
    assert _first_valid_image_attachment(message) is None
    gif.read.assert_not_awaited()


def test_structural_gate_rejects_none_content_type():
    """A None content_type normalizes to '' and is rejected (Pitfall 3)."""
    unknown = _make_attachment(None, _GOOD_SIZE)
    message = _make_message(attachments=[unknown])
    assert _first_valid_image_attachment(message) is None


def test_structural_gate_normalizes_charset_suffix():
    """'image/jpeg; charset=utf-8' normalizes to 'image/jpeg' and IS accepted (Pitfall 3)."""
    good = _make_attachment("image/jpeg; charset=utf-8", _GOOD_SIZE)
    message = _make_message(attachments=[good])
    assert _first_valid_image_attachment(message) is good


def test_structural_gate_returns_first_valid():
    """The FIRST passing attachment is returned (roast the first valid image, D-02)."""
    bad = _make_attachment("image/gif", _GOOD_SIZE)
    good1 = _make_attachment("image/png", _GOOD_SIZE)
    good2 = _make_attachment("image/webp", _GOOD_SIZE)
    message = _make_message(attachments=[bad, good1, good2])
    assert _first_valid_image_attachment(message) is good1


@pytest.mark.asyncio
async def test_maybe_fire_skips_on_structural_reject():
    """A rejected-only-attachment message reads no bytes and never replies/calls Gemini."""
    gif = _make_attachment("image/gif", _GOOD_SIZE)
    message = _make_message(attachments=[gif])
    cog = EventsCog(_make_bot())

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(cog, "_generate_vision_roast", new=AsyncMock()) as gen,
    ):
        await cog._maybe_fire_vision_roast(message)

    gif.read.assert_not_awaited()
    gen.assert_not_awaited()
    message.reply.assert_not_awaited()


# ---------------------------------------------------------------------------
# (B) safety-block silent skip (VIS-02) — dispatch decision under test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safety_block_silent_skip():
    """Gate passes but _generate_vision_roast -> None -> no reply, no cooldown mark."""
    good = _make_attachment("image/png", _GOOD_SIZE)
    message = _make_message(attachments=[good], user_id=7)
    cog = EventsCog(_make_bot())

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(cog, "_generate_vision_roast", new=AsyncMock(return_value=None)),
    ):
        await cog._maybe_fire_vision_roast(message)

    message.reply.assert_not_awaited()
    assert message.author.id not in cog._vision_roast_cooldowns


# ---------------------------------------------------------------------------
# (C) transport-failure template fallback (VIS-02) — a visible reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transport_fallback_replies():
    """Gate passes and _generate_vision_roast -> a fallback string -> reply IS awaited."""
    good = _make_attachment("image/png", _GOOD_SIZE)
    message = _make_message(attachments=[good], user_id=8)
    cog = EventsCog(_make_bot())
    fallback = roasts.VISION_ROAST_FALLBACKS[0]

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(cog, "_generate_vision_roast", new=AsyncMock(return_value=fallback)),
    ):
        await cog._maybe_fire_vision_roast(message)

    message.reply.assert_awaited_once()
    call_args, _ = message.reply.call_args
    assert call_args[0] == fallback


# ---------------------------------------------------------------------------
# (D) VIS-02 regression — the direct silent-skip-vs-fallback distinction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_vision_roast_none_on_safety_block():
    """chat() -> None (safety-blocked/empty) -> silent skip (None), never a fallback."""
    bot = _make_bot()
    bot.gemini_service = MagicMock()
    bot.gemini_service.chat = AsyncMock(return_value=None)
    cog = EventsCog(bot)

    result = await cog._generate_vision_roast(_make_message().author, b"bytes", "image/png")
    assert result is None


@pytest.mark.asyncio
async def test_generate_vision_roast_empty_string_is_silent_skip():
    """An empty/whitespace response is also a silent skip (falsy -> None)."""
    bot = _make_bot()
    bot.gemini_service = MagicMock()
    bot.gemini_service.chat = AsyncMock(return_value="")
    cog = EventsCog(bot)

    result = await cog._generate_vision_roast(_make_message().author, b"bytes", "image/png")
    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [GeminiRateLimitError, GeminiAPIError])
async def test_generate_vision_roast_fallback_on_transport(exc):
    """A transport failure (rate-limit OR API error) -> a VISION_ROAST_FALLBACKS line."""
    bot = _make_bot()
    bot.gemini_service = MagicMock()
    bot.gemini_service.chat = AsyncMock(side_effect=exc("boom"))
    cog = EventsCog(bot)

    result = await cog._generate_vision_roast(_make_message().author, b"bytes", "image/png")
    assert result in roasts.VISION_ROAST_FALLBACKS


@pytest.mark.asyncio
async def test_generate_vision_roast_success_normalizes():
    """A successful line is stripped and lowercased-at-the-first-char."""
    bot = _make_bot()
    bot.gemini_service = MagicMock()
    bot.gemini_service.chat = AsyncMock(return_value="  Nice cat i guess  ")
    cog = EventsCog(bot)

    result = await cog._generate_vision_roast(_make_message().author, b"bytes", "image/png")
    assert result == "nice cat i guess"


@pytest.mark.asyncio
async def test_generate_vision_roast_none_without_gemini():
    """No gemini_service -> silent skip (None), not a transport fallback."""
    bot = _make_bot()
    bot.gemini_service = None  # getattr(self.bot, "gemini_service", None) -> None
    cog = EventsCog(bot)

    result = await cog._generate_vision_roast(_make_message().author, b"bytes", "image/png")
    assert result is None


# ---------------------------------------------------------------------------
# (E) reply-anchor + cooldown mark on a real fire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reply_anchor_and_cooldown_mark():
    """A real fire replies with AllowedMentions.none() + mention_author=False, marks cooldown."""
    good = _make_attachment("image/png", _GOOD_SIZE)
    message = _make_message(attachments=[good], user_id=9)
    cog = EventsCog(_make_bot())

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(cog, "_generate_vision_roast", new=AsyncMock(return_value="dry line")),
    ):
        await cog._maybe_fire_vision_roast(message)

    message.reply.assert_awaited_once()
    call_args, call_kwargs = message.reply.call_args
    assert call_args[0] == "dry line"

    allowed_mentions = call_kwargs.get("allowed_mentions")
    assert isinstance(allowed_mentions, discord.AllowedMentions)
    assert allowed_mentions.everyone is False
    assert allowed_mentions.roles is False
    assert allowed_mentions.users is False
    assert call_kwargs.get("mention_author") is False

    message.channel.send.assert_not_called()
    assert message.author.id in cog._vision_roast_cooldowns


@pytest.mark.asyncio
async def test_bytes_read_only_after_gate_passes():
    """attachment.read() is awaited only AFTER should_fire_vision_roast passes."""
    good = _make_attachment("image/png", _GOOD_SIZE)
    message = _make_message(attachments=[good], user_id=13)
    cog = EventsCog(_make_bot())

    # Chance roll fails (0.99 >= 0.12) -> gate returns False -> no read.
    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.99),
        patch.object(cog, "_generate_vision_roast", new=AsyncMock()) as gen,
    ):
        await cog._maybe_fire_vision_roast(message)

    good.read.assert_not_awaited()
    gen.assert_not_awaited()
    message.reply.assert_not_awaited()


# ---------------------------------------------------------------------------
# (F) shared Phase 16 opt-out short-circuits before any I/O
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opt_out_short_circuits():
    """get_proactive_opt_out -> True -> no read, no reply (shared Phase 16 control)."""
    good = _make_attachment("image/png", _GOOD_SIZE)
    message = _make_message(attachments=[good], user_id=14)
    cog = EventsCog(_make_bot())

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=True)),
        patch("cogs.events.random.random", return_value=0.0),
    ):
        await cog._maybe_fire_vision_roast(message)

    good.read.assert_not_awaited()
    message.reply.assert_not_awaited()
    assert message.author.id not in cog._vision_roast_cooldowns


# ---------------------------------------------------------------------------
# (G) MEM-07 memory-write call-site wiring (WR-03)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_write_fires_with_expected_kwargs_on_success():
    """A genuine (non-fallback) roast line schedules distill_and_remember with
    the expected user_id/guild_id/kind/raw_text/base_salience — exercises the
    call-site WIRING itself (kwarg names, guild stamping), which the live-DB
    `TestVisionRoastMemory` tests cannot catch since they call
    `distill_and_remember` directly and never go through `_maybe_fire_vision_roast`.
    """
    good = _make_attachment("image/png", _GOOD_SIZE)
    message = _make_message(attachments=[good], user_id=21, guild_id=777)
    bot = _make_bot_with_memory()
    cog = EventsCog(bot)

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(
            cog, "_generate_vision_roast", new=AsyncMock(return_value="a genuinely generated line")
        ),
    ):
        await cog._maybe_fire_vision_roast(message)
        await asyncio.sleep(0)  # let the fire-and-forget asyncio.create_task run

    bot.memory_service.distill_and_remember.assert_awaited_once_with(
        user_id="21",
        guild_id="777",
        raw_text="a genuinely generated line",
        kind="vision_roast",
        base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"],
    )


@pytest.mark.asyncio
async def test_memory_write_skipped_when_line_is_none():
    """VIS-02 silent skip (line is None) must never reach the memory write."""
    good = _make_attachment("image/png", _GOOD_SIZE)
    message = _make_message(attachments=[good], user_id=22)
    bot = _make_bot_with_memory()
    cog = EventsCog(bot)

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(cog, "_generate_vision_roast", new=AsyncMock(return_value=None)),
    ):
        await cog._maybe_fire_vision_roast(message)
        await asyncio.sleep(0)

    bot.memory_service.distill_and_remember.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_write_skipped_when_reply_fails():
    """A failed message.reply (discord.HTTPException) must never reach the
    memory write — the write is gated strictly after a confirmed successful
    send, never pre-send."""
    good = _make_attachment("image/png", _GOOD_SIZE)
    message = _make_message(attachments=[good], user_id=23)
    message.reply = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(status=500, reason="boom"), "boom")
    )
    bot = _make_bot_with_memory()
    cog = EventsCog(bot)

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(
            cog, "_generate_vision_roast", new=AsyncMock(return_value="a genuinely generated line")
        ),
    ):
        await cog._maybe_fire_vision_roast(message)
        await asyncio.sleep(0)

    bot.memory_service.distill_and_remember.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_write_skipped_for_transport_fallback_line():
    """WR-02 regression: a canned VISION_ROAST_FALLBACKS template line (what
    _generate_vision_roast returns on a Gemini transport failure) must NOT be
    memorized — the fallback IS still sent to the user (VIS-02: a transport
    failure is not a safety block), but only genuinely-generated commentary is
    worth a vision_roast memory."""
    good = _make_attachment("image/png", _GOOD_SIZE)
    message = _make_message(attachments=[good], user_id=24)
    bot = _make_bot_with_memory()
    cog = EventsCog(bot)
    fallback = roasts.VISION_ROAST_FALLBACKS[0]

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(cog, "_generate_vision_roast", new=AsyncMock(return_value=fallback)),
    ):
        await cog._maybe_fire_vision_roast(message)
        await asyncio.sleep(0)

    message.reply.assert_awaited_once()
    bot.memory_service.distill_and_remember.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_write_skipped_when_memory_service_absent():
    """A bot with no memory_service attached (the default `_make_bot()` shape,
    memory_service=None) must not attempt the write and must not raise."""
    good = _make_attachment("image/png", _GOOD_SIZE)
    message = _make_message(attachments=[good], user_id=25)
    cog = EventsCog(_make_bot())  # memory_service=None

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(
            cog, "_generate_vision_roast", new=AsyncMock(return_value="a genuinely generated line")
        ),
    ):
        await cog._maybe_fire_vision_roast(message)  # must not raise

    message.reply.assert_awaited_once()
