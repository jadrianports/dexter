"""Drift guard for the D-17 `AudioPlayer.send_silence` suppression patch
(Phase 27 / DJ-03, D-17.4b — VALIDATION rows 17, 18).

The closest analog in the repo is `tests/test_invite_drift_guard.py` — the
only other "fail the build when an external fact drifts" guard, and the
origin of the discipline this file copies: a drift guard is only trustworthy
once a **mandatory positive control** proves it can actually fail.

Tests:
- test_send_silence_patch_target_exists          — THE guard (row 17). Asserts
  BOTH that AudioPlayer.send_silence exists AND that AudioPlayer._do_run's
  source still calls it. A hasattr-only guard would silently pass a discord.py
  bump that kept the method but stopped calling it from _do_run — resurrecting
  the 100ms end-of-transmission dropout behind a green build. That is exactly
  the failure mode this test exists to prevent.
- test_drift_guard_actually_detects_a_mismatch   — mandatory positive control.
  Covers BOTH drift shapes separately, because they fail differently: a class
  with no send_silence attribute at all, and (the shape a naive hasattr guard
  would miss) a class that HAS send_silence but whose _do_run never calls it.
- test_drift_guard_accepts_the_canonical_target  — negative control for the
  positive control: the real AudioPlayer passes through the same
  parameterized helper the real guard uses.
- test_patch_install_fails_soft                  — THE guard (row 18). With the
  target removed via monkeypatch, install_send_silence_suppression() returns
  False and raises nothing; the module stays importable with the target absent
  (the boot-crash rail D-17.4a exists to forbid).
- test_install_is_idempotent                     — calling install twice does
  not double-wrap (Task 1 acceptance criterion).

A drift guard nobody has proven can fail is not a guard — that is the reason
the positive control here is mandatory, not optional polish.

Isolation: AudioPlayer.send_silence is a real third-party class attribute,
not a per-test double, so `_restore_send_silence` (module-scoped, autouse)
captures the pristine method once at collection time and restores it after
every test, and resets `discord_patch._INSTALLED` alongside it — a leaked
patch or a leaked install-marker would otherwise poison later tests/full-suite
runs (the plan's "pytest -q full suite ... proving no leaked patch state").
"""

from __future__ import annotations

import importlib

import pytest
from discord.player import AudioPlayer

import utils.discord_patch as discord_patch
from utils.discord_patch import (
    install_send_silence_suppression,
    send_silence_patch_target_present,
)

_ORIGINAL_SEND_SILENCE = AudioPlayer.send_silence


@pytest.fixture(autouse=True)
def _restore_send_silence():
    """Guarantee every test starts and ends with the pristine AudioPlayer
    class and a clean install marker — no leaked patch state escapes this
    file into the rest of the suite."""
    yield
    AudioPlayer.send_silence = _ORIGINAL_SEND_SILENCE
    discord_patch._INSTALLED = False


# ---------------------------------------------------------------------------
# Row 17 — the real drift guard
# ---------------------------------------------------------------------------


def test_send_silence_patch_target_exists():
    """Fails if AudioPlayer.send_silence is removed, or if _do_run stops
    calling it while the method still exists. Both halves via the shared
    helper so the guard and the install can never assert different things."""
    assert callable(getattr(AudioPlayer, "send_silence", None))
    assert send_silence_patch_target_present(AudioPlayer) is True


# ---------------------------------------------------------------------------
# Positive control: both drift shapes, driven through the real helper
# ---------------------------------------------------------------------------


class _NoSendSilenceAtAll:
    """Drift shape 1: send_silence removed entirely."""

    def _do_run(self) -> None:  # pragma: no cover - source-inspected only
        pass


class _SendSilenceButUncalled:
    """Drift shape 2 — the one a naive `hasattr` guard would miss: the method
    still exists, but _do_run's source no longer calls it (e.g. discord.py
    renamed the call site during an internal refactor)."""

    def send_silence(self, count: int = 5) -> None:  # pragma: no cover
        pass

    def _do_run(self) -> None:  # pragma: no cover - source-inspected only
        # Deliberately does NOT reference the pause/silence-emitting call site.
        pass


def test_drift_guard_actually_detects_a_mismatch():
    """Mandatory positive control. Proves the guard is not a no-op by feeding
    the exact helper the real guard uses two deliberately-drifted stand-ins."""
    assert send_silence_patch_target_present(_NoSendSilenceAtAll) is False
    # This is the drift shape a bare `hasattr(AudioPlayer, "send_silence")`
    # guard would MISS entirely: the attribute is present and callable, but
    # the call site is gone.
    assert send_silence_patch_target_present(_SendSilenceButUncalled) is False


def test_drift_guard_accepts_the_canonical_target():
    """Negative control for the positive control: the real AudioPlayer,
    driven through the same parameterized helper, returns True."""
    assert send_silence_patch_target_present(AudioPlayer) is True
    # Also confirm the default argument resolves to the real class.
    assert send_silence_patch_target_present() is True


# ---------------------------------------------------------------------------
# Row 18 — fail-soft install
# ---------------------------------------------------------------------------


def test_patch_install_fails_soft(monkeypatch):
    """With the target absent, install returns False and raises nothing.
    Uses the monkeypatch fixture so the real AudioPlayer is restored after
    the test — a leaked patch would poison every later test in the session."""
    monkeypatch.delattr(AudioPlayer, "send_silence", raising=False)

    result = install_send_silence_suppression()

    assert result is False


def test_module_importable_with_target_absent(monkeypatch):
    """The boot-crash rail (D-17.4a): importing this module must be
    unconditionally safe, even when AudioPlayer.send_silence is absent."""
    monkeypatch.delattr(AudioPlayer, "send_silence", raising=False)
    # Re-executing the module's top level (a real re-import) must not raise
    # AttributeError or anything else, target absent or not.
    importlib.reload(discord_patch)


# ---------------------------------------------------------------------------
# Task 1 acceptance criterion: idempotent install
# ---------------------------------------------------------------------------


def test_install_is_idempotent():
    """Calling install twice returns True both times and does not double-wrap."""
    first = install_send_silence_suppression()
    assert first is True

    wrapped_once = AudioPlayer.send_silence

    second = install_send_silence_suppression()
    assert second is True
    # No re-wrap happened — same function object as after the first install.
    assert AudioPlayer.send_silence is wrapped_once
