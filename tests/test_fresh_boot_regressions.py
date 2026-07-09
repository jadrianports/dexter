"""Regressions for bugs that only surface on a freshly-booted host (first CI run, Phase 18).

Two latent defects shipped for several phases because they are invisible on a machine
with long uptime — the developer's PC — and only appear where uptime is small:

1. ``bot.py`` called ``sys.exit(1)`` at IMPORT time when ``DISCORD_TOKEN`` was unset, so
   any test that did ``import bot`` died with ``SystemExit`` in an environment without a
   ``.env`` (i.e. CI, which deliberately holds zero secrets).

2. A ``0.0`` "never happened" sentinel was compared against a monotonic clock. Both
   ``time.monotonic()`` and ``asyncio.get_event_loop().time()`` count from system boot,
   so ``0.0`` means "at boot", not "long ago". On a host whose uptime is shorter than the
   throttle/cooldown window, a never-yet-roasted user looked like they had *just* been
   roasted, and yt-dlp self-heal looked like it had *just* run. Net effect in production:
   after a reboot Dexter would refuse to vision-roast for ``VISION_ROAST_COOLDOWN_SECONDS``
   and refuse to self-heal yt-dlp for ``_UPDATE_THROTTLE_SECONDS``.

The fix in both cases is ``float("-inf")`` — genuinely "infinitely long ago", independent
of uptime. These tests fail against the old ``0.0`` sentinel on any uptime.
"""

from __future__ import annotations

import ast
import math

import pytest

import config
from logic.roasts import cooldown_elapsed

# Uptimes shorter than every throttle/cooldown window in the codebase. On a fresh
# GitHub Actions runner monotonic() lands in roughly this range.
FRESH_BOOT_UPTIMES = [0.5, 5.0, 60.0, 300.0]


class TestNoImportTimeExit:
    """bot.py must be importable without a DISCORD_TOKEN (regression: SystemExit on import)."""

    def test_bot_module_has_no_import_time_sys_exit(self):
        tree = ast.parse(open("bot.py", encoding="utf-8").read())
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue  # exits inside a function body are fine — they run on demand
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    is_sys_exit = isinstance(func, ast.Attribute) and func.attr == "exit"
                    assert not is_sys_exit, (
                        "bot.py must not call sys.exit() at import time — importing a module "
                        "must never terminate the interpreter (breaks the suite wherever "
                        "DISCORD_TOKEN is unset, e.g. CI)"
                    )

    def test_require_discord_token_exits_when_unset(self, monkeypatch):
        import bot

        monkeypatch.setattr(bot, "DISCORD_TOKEN", None)
        with pytest.raises(SystemExit):
            bot._require_discord_token()

    def test_require_discord_token_returns_when_set(self, monkeypatch):
        import bot

        monkeypatch.setattr(bot, "DISCORD_TOKEN", "a-token")
        assert bot._require_discord_token() is None


class TestMonotonicSentinelIsNegativeInfinity:
    """ "Never happened" must not be spelled 0.0 against a boot-relative clock."""

    def test_ytdlp_update_sentinel_is_negative_infinity(self):
        import services.youtube as yt

        assert yt._last_ytdlp_update == -math.inf, (
            "_last_ytdlp_update must default to -inf; 0.0 means 'at boot' to time.monotonic()"
        )

    @pytest.mark.parametrize("uptime", FRESH_BOOT_UPTIMES)
    def test_ytdlp_self_heal_permitted_on_freshly_booted_host(self, uptime):
        """The throttle gate must open on a first failure regardless of uptime."""
        import services.youtube as yt

        # This is the exact predicate services/youtube.py evaluates before self-healing.
        assert uptime - yt._last_ytdlp_update >= yt._UPDATE_THROTTLE_SECONDS

        # ...and the old sentinel demonstrably closes it, which is why CI went red.
        assert not (uptime - 0.0 >= yt._UPDATE_THROTTLE_SECONDS)

    @pytest.mark.parametrize("uptime", FRESH_BOOT_UPTIMES)
    def test_vision_roast_not_cooled_down_for_unseen_user_on_fresh_boot(self, uptime):
        """An unseen user has no cooldown entry — the default must read as 'long ago'."""
        seconds_since_last = uptime - -math.inf
        assert cooldown_elapsed(seconds_since_last, config.VISION_ROAST_COOLDOWN_SECONDS)

        # The old 0.0 default suppressed the roast for the whole cooldown window post-boot.
        assert not cooldown_elapsed(uptime - 0.0, config.VISION_ROAST_COOLDOWN_SECONDS)

    @pytest.mark.parametrize("uptime", FRESH_BOOT_UPTIMES)
    @pytest.mark.parametrize("ceiling", [30.0, 300.0, 600.0, 3600.0])
    def test_unseen_user_is_never_cooled_down_for_any_ceiling(self, uptime, ceiling):
        """Holds for every cooldown window in the codebase, at any uptime."""
        assert cooldown_elapsed(uptime - -math.inf, ceiling)

    def test_events_cooldown_lookups_default_to_negative_infinity(self):
        """Lock the call sites so a future edit cannot quietly reintroduce 0.0."""
        src = open("cogs/events.py", encoding="utf-8").read()
        assert "get(member.id, 0.0)" not in src
        assert "get(message.author.id, 0.0)" not in src
        assert src.count('float("-inf")') >= 3
