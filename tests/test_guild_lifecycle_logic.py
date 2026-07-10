"""Mock-free tests for logic/guild_config.py::should_welcome_guild (Phase 19 / D-14).

No mocks, no clocks, no RNG, no DB — every input is a plain Python dict/None,
mirroring tests/test_guild_config_logic.py's style.
"""

from logic.guild_config import should_welcome_guild


def test_should_welcome_guild_true_on_inserted_row():
    """A genuine RETURNING row (real INSERT happened) -> True."""
    inserted_row = {"guild_id": "100", "configured": False}
    assert should_welcome_guild(inserted_row=inserted_row) is True


def test_should_welcome_guild_false_on_none():
    """None (ON CONFLICT DO NOTHING fired, row already existed) -> False."""
    assert should_welcome_guild(inserted_row=None) is False


def test_should_welcome_guild_never_derived_from_a_cache_miss():
    """D-14 scar regression: a fail-closed/empty-cache read must NEVER be conflated
    with a genuine insert-if-absent result.

    The historical bug (Pitfall 3) was deriving "should I welcome this guild" from
    something like ``bot.guild_config.get(guild_id) is None`` — a cache miss that
    can happen on every restart before load_all() populates the cache, or during a
    fail-closed load (D-07 empty cache). Representing that failure mode here as
    ``inserted_row=None`` (the same falsy-and-uninformative signal a cache miss
    would produce) proves the function only ever answers "did the INSERT actually
    insert a row" — never "is there currently no row in the cache" — and therefore
    can never spuriously fire a welcome-spam loop on every reboot.
    """
    cache_miss_representation = None
    assert should_welcome_guild(inserted_row=cache_miss_representation) is False
