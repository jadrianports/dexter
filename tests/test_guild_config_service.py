"""Service-level tests for GuildConfigService (Phase 18 / CONFIG-03, D-06/D-07).

Mock-based, no live DB required (mirrors tests/test_memory.py's fake-pool
pattern and tests/test_proactive_events.py's `_make_bot`/fake-discord-object
style). Covers:

- CONFIG-03 no-round-trip: after load_all(), get() and resolve_ambient_channel()
  never touch the pool again.
- D-07 fail-closed: a raising pool leaves the cache empty, load_all() does not
  propagate, and every guild reads as unconfigured.
- D-01/D-03 resolve_ambient_channel branches: cache-miss silence, a resolvable
  + writable channel, a stale (deleted) channel, and a no-send-permission
  channel -- both skip branches leave the cache row untouched.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import discord
import pytest

from services.guild_config import GuildConfigService

# ---------------------------------------------------------------------------
# Fake pool (spy on .acquire() calls) -- mirrors tests/test_memory.py's
# _FakeConn/_FakePoolCM/_FakePool trio.
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self, rows=None, raise_on_fetch=None):
        self._rows = rows if rows is not None else []
        self._raise_on_fetch = raise_on_fetch

    async def fetch(self, sql, *params):
        if self._raise_on_fetch is not None:
            raise self._raise_on_fetch
        return self._rows

    async def fetchrow(self, sql, *params):
        return None

    async def execute(self, sql, *params):
        return "INSERT 0 1"


class _FakePoolCM:
    def __init__(self, conn: "_FakeConn"):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _SpyPool:
    """Counts every .acquire() call so tests can assert zero-round-trip reads."""

    def __init__(self, rows=None, raise_on_fetch=None):
        self.conn = _FakeConn(rows=rows, raise_on_fetch=raise_on_fetch)
        self.acquire_count = 0

    def acquire(self):
        self.acquire_count += 1
        return _FakePoolCM(self.conn)


class _RaisingPool:
    """A pool whose .acquire() itself raises -- simulates a dead connection."""

    def acquire(self):
        raise RuntimeError("pool exploded")


# ---------------------------------------------------------------------------
# Fake bot (no log_to_discord attribute unless a test opts in)
# ---------------------------------------------------------------------------


class _FakeBot:
    """Minimal fake bot -- deliberately has NO log_to_discord unless added."""

    cogs: dict = {}


# ---------------------------------------------------------------------------
# Fake discord guild/channel objects for resolver tests
# ---------------------------------------------------------------------------


def _make_channel(*, channel_id: int, can_send: bool = True):
    """Return a MagicMock spec'd as discord.TextChannel (isinstance-compatible)."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    perms = MagicMock(spec=discord.Permissions)
    perms.send_messages = can_send
    channel.permissions_for = MagicMock(return_value=perms)
    return channel


def _make_guild(*, guild_id: int, channels: dict):
    """Return a MagicMock spec'd as discord.Guild with a channel-id lookup table."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.me = MagicMock()
    guild.get_channel = lambda cid: channels.get(cid)
    guild.system_channel = None
    guild.text_channels = list(channels.values())
    return guild


# ---------------------------------------------------------------------------
# CONFIG-03: no round-trip after load_all()
# ---------------------------------------------------------------------------


def test_no_round_trip_after_load_all():
    """get() and resolve_ambient_channel() never call pool.acquire() again."""
    rows = [
        {
            "guild_id": "100",
            "ambient_channel_id": "500",
            "configured": True,
            "silenced": False,
            "is_blocked": False,
        }
    ]
    pool = _SpyPool(rows=rows)
    service = GuildConfigService(pool, _FakeBot())

    asyncio.run(service.load_all())
    assert pool.acquire_count == 1  # exactly the load_all fetch

    # Exercise both cache-only reads several times.
    channel = _make_channel(channel_id=500)
    guild = _make_guild(guild_id=100, channels={500: channel})

    assert service.get(100) is not None
    assert service.get(999) is None
    assert service.resolve_ambient_channel(guild) is channel
    assert service.resolve_ambient_channel(guild) is channel

    # Still exactly one pool access -- everything after load_all was cache-only.
    assert pool.acquire_count == 1


# ---------------------------------------------------------------------------
# D-07: fail closed
# ---------------------------------------------------------------------------


def test_load_all_fails_closed_on_pool_error():
    """A raising pool leaves the cache empty; load_all() does not propagate."""
    pool = _RaisingPool()
    service = GuildConfigService(pool, _FakeBot())

    # Must not raise.
    asyncio.run(service.load_all())

    assert service.get(100) is None
    assert service.get(1) is None
    assert service._cache == {}


def test_load_all_fails_closed_on_fetch_error():
    """An exception raised inside conn.fetch also fails closed."""
    pool = _SpyPool(raise_on_fetch=RuntimeError("neon scale-to-zero timeout"))
    service = GuildConfigService(pool, _FakeBot())

    asyncio.run(service.load_all())

    assert service._cache == {}
    assert service.get(100) is None


# ---------------------------------------------------------------------------
# D-01/D-03: resolve_ambient_channel branches
# ---------------------------------------------------------------------------


def test_resolve_ambient_channel_cache_miss_returns_none():
    """No cache row (never configured) -> None, no discord lookup attempted."""
    pool = _SpyPool(rows=[])
    service = GuildConfigService(pool, _FakeBot())
    asyncio.run(service.load_all())

    guild = _make_guild(guild_id=100, channels={})
    guild.get_channel = lambda cid: (_ for _ in ()).throw(AssertionError("should not be called"))

    assert service.resolve_ambient_channel(guild) is None


def test_resolve_ambient_channel_configured_and_writable_returns_channel():
    """Configured + resolvable + writable -> the TextChannel."""
    rows = [{"guild_id": "100", "ambient_channel_id": "500", "configured": True}]
    pool = _SpyPool(rows=rows)
    service = GuildConfigService(pool, _FakeBot())
    asyncio.run(service.load_all())

    channel = _make_channel(channel_id=500, can_send=True)
    guild = _make_guild(guild_id=100, channels={500: channel})

    assert service.resolve_ambient_channel(guild) is channel


def test_resolve_ambient_channel_stale_channel_returns_none_row_intact(caplog):
    """Configured but channel deleted -> None + WARNING, cache row untouched."""
    rows = [{"guild_id": "100", "ambient_channel_id": "500", "configured": True}]
    pool = _SpyPool(rows=rows)
    service = GuildConfigService(pool, _FakeBot())
    asyncio.run(service.load_all())

    before = service.get(100)
    guild = _make_guild(guild_id=100, channels={})  # channel 500 no longer exists

    with caplog.at_level("WARNING"):
        result = service.resolve_ambient_channel(guild)

    assert result is None
    assert service.get(100) is before  # untouched -- same object, still configured
    assert service.get(100)["configured"] is True
    assert any("no longer resolves" in r.message for r in caplog.records)


def test_resolve_ambient_channel_no_send_perms_returns_none_row_intact(caplog):
    """Configured, channel exists, but Dexter lost send_messages -> None + WARNING."""
    rows = [{"guild_id": "100", "ambient_channel_id": "500", "configured": True}]
    pool = _SpyPool(rows=rows)
    service = GuildConfigService(pool, _FakeBot())
    asyncio.run(service.load_all())

    before = service.get(100)
    channel = _make_channel(channel_id=500, can_send=False)
    guild = _make_guild(guild_id=100, channels={500: channel})

    with caplog.at_level("WARNING"):
        result = service.resolve_ambient_channel(guild)

    assert result is None
    assert service.get(100) is before
    assert service.get(100)["configured"] is True
    assert any("send_messages" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# resolve_announce_channel -- exercised here only (zero production callers)
# ---------------------------------------------------------------------------


def test_resolve_announce_channel_falls_back_to_system_channel():
    """With no env designation and no music cog, falls through to system_channel."""
    service = GuildConfigService(_SpyPool(rows=[]), _FakeBot())

    system_channel = _make_channel(channel_id=42, can_send=True)
    guild = _make_guild(guild_id=100, channels={})
    guild.system_channel = system_channel

    assert service.resolve_announce_channel(guild) is system_channel


def test_resolve_announce_channel_falls_back_to_first_writable_text_channel():
    """No system_channel writable -> first writable text_channels entry."""
    service = GuildConfigService(_SpyPool(rows=[]), _FakeBot())

    unwritable = _make_channel(channel_id=1, can_send=False)
    writable = _make_channel(channel_id=2, can_send=True)
    guild = _make_guild(guild_id=100, channels={})
    guild.system_channel = None
    guild.text_channels = [unwritable, writable]

    assert service.resolve_announce_channel(guild) is writable


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
