"""Guards that crossfade state never reaches Neon (Phase 27 / D-12 row 10).

`services/queue_persistence.py::persist()` builds a typed six-key payload dict
(tracks / current_index / loop_mode / text_channel_id / voice_channel_id /
active_filter) and never `queue.__dict__`. This file locks that construction
two independent ways: behaviorally (drive the real `persist()` against a
stubbed asyncpg pool and assert the decoded JSON payload's key set is
*exactly* the six known keys) and structurally (the repo's existing
`test_disarm_never_persisted_in_queue_persistence_payload` precedent — assert
the literal strings never appear in the module's source).

No production change is needed to make this pass — `persist()`'s explicit
typed-dict construction already excludes `crossfade_enabled` / `_xf_pending` /
`_xf_truncator` by construction. This test exists to lock that guarantee
against regression (e.g. a future `**queue.__dict__` shortcut).
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.queue import LoopMode, MusicQueue, Track
from services.queue_persistence import QueuePersistenceService


def _make_track() -> Track:
    return Track(
        video_id="abc123",
        title="Test Song",
        artist="Test Artist",
        url="https://youtube.com/watch?v=abc123",
        duration_seconds=200,
        requested_by=12345,
    )


def _make_pool_mock() -> tuple[MagicMock, AsyncMock]:
    """Build a mock pool whose acquire() works as an async context manager,
    mirroring tests/test_audio.py::_make_pool_mock's convention. Returns the
    pool mock and the conn's execute AsyncMock so callers can inspect the
    captured SQL/params.
    """
    conn_mock = MagicMock()
    conn_mock.execute = AsyncMock(return_value=None)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn_mock)
    cm.__aexit__ = AsyncMock(return_value=False)

    pool_mock = MagicMock()
    pool_mock.acquire = MagicMock(return_value=cm)
    return pool_mock, conn_mock.execute


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


@pytest.mark.asyncio
async def test_crossfade_not_persisted():
    """D-12 row 10: crossfade_enabled / _xf_pending / _xf_truncator never
    reach the persisted Neon payload, asserted two independent ways.
    """
    # --- 1. Behavioral (primary): exact key-set equality on the real payload ---
    q = MusicQueue(guild_id=1)
    q.add(_make_track())
    q.loop_mode = LoopMode.QUEUE
    q._text_channel_id = 555
    q.active_filter = "bassboost"
    # Set crossfade state that must NOT ride along into the payload.
    q.crossfade_enabled = True
    q._xf_pending = (_make_track(), 196.0)
    q._xf_truncator = object()

    pool, execute_mock = _make_pool_mock()
    service = QueuePersistenceService(pool)
    guild = _FakeGuild(1)

    await service.persist(guild, q, voice_channel_id=999)

    execute_mock.assert_awaited_once()
    _sql, guild_id_arg, payload_json = execute_mock.await_args.args
    payload = json.loads(payload_json)

    assert set(payload.keys()) == {
        "tracks",
        "current_index",
        "loop_mode",
        "text_channel_id",
        "voice_channel_id",
        "active_filter",
    }, "persisted payload must carry EXACTLY the six known keys — no crossfade field"

    # --- 2. Structural (secondary, the radio precedent) ---
    src = pathlib.Path("services/queue_persistence.py").read_text(encoding="utf-8")
    assert "crossfade" not in src
    assert "_xf_" not in src
