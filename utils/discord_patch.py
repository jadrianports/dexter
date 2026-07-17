"""Wrapped, fail-soft install of the D-17 `AudioPlayer.send_silence` suppression
patch (Phase 27 / DJ-03, D-17.4a).

**This patches an undocumented discord.py internal**
(`AudioPlayer.send_silence`, `discord/player.py:892` in the pinned 2.7.1),
called from `AudioPlayer._do_run` at `:796` (the paused-loop branch) and
`:833` (after the main playback loop exits). Why: the 5 silence frames
`send_silence` emits advance the RTP timestamp unconditionally, so Discord's
decoder genuinely hears them — and a crossfade must start *before* the
outgoing track ends, landing that hole mid-music at roughly -9.8 dBFS. Left
unsuppressed, a crossfade sounds *worse* than the hard cut it replaces.

Why this does not trip D-01 (the playback-engine invariant): `play()` is
still called exactly once per track, one `AudioSource` per `play()`, and the
generation counter is untouched. This patch declines a library-injected gap
in an existing transmission; it does not replace or reshape the engine
model.

Two mandatory guard rails (D-17.4a/D-17.4b — see `27-CONTEXT.md` D-17):

1. **Fail-soft install.** `install_send_silence_suppression()` never raises.
   If the target it depends on has moved or vanished, it logs a warning and
   returns `False` — the degrade path is "the 100ms comes back", not a boot
   crash. Importing this module can never raise `AttributeError` either;
   there is no bare module-level `AudioPlayer.send_silence` access outside a
   guarded function.
2. **A drift guard that asserts the call site, not just the attribute.**
   `tests/test_discord_patch.py` is that guard — it fails if `send_silence`
   is removed AND if `_do_run` stops calling it while the method still
   exists. A `hasattr`-only guard would silently pass a discord.py bump that
   kept the method but stopped calling it, silently resurrecting the 100ms
   dropout behind a green build. See that file's module docstring for the
   full test roster and the mandatory positive control proving the guard is
   not a no-op.

The suppression itself is duck-typed and source-attribute-gated: the patched
method only diverges from the original when `self.source` carries a truthy
`_suppress_end_silence` (set only by `TruncatingSource` at the instant it
cuts short for a fade — see `services/audio.py`). Nothing else in the
codebase ever sets that attribute, so with crossfade off — or for any
non-fade source — every call falls through to the original, unchanged
method. This module never imports `services.audio` and never
`isinstance`-checks the source; the `getattr(..., False)` default IS the
byte-identical-when-off guarantee.
"""

from __future__ import annotations

import inspect

from discord.player import AudioPlayer

from utils.logger import log

# ---------------------------------------------------------------------------
# Module-level install marker (idempotency guard)
# ---------------------------------------------------------------------------

_INSTALLED = False


# ---------------------------------------------------------------------------
# Shared assertion — the install and the drift guard can never diverge
# ---------------------------------------------------------------------------


def send_silence_patch_target_present(player_cls: type = AudioPlayer) -> bool:
    """True iff *player_cls* still exposes the patch target this module needs.

    Both halves are required:
      1. ``callable(getattr(player_cls, "send_silence", None))`` — the method exists.
      2. ``"send_silence"`` appears in ``inspect.getsource(player_cls._do_run)`` —
         ``_do_run`` still actually calls it.

    Fact 2 is the whole point (see module docstring): a discord.py bump that
    kept the method but stopped calling it from ``_do_run`` would pass a
    ``hasattr``-only check while silently resurrecting the 100ms dropout.

    ``player_cls`` is parameterizable so the drift-guard's positive control
    (a deliberately-drifted stand-in class) drives this exact code path
    rather than a reimplementation. Defaults to the real ``AudioPlayer``.

    ``inspect.getsource`` is wrapped because source is unavailable for a
    C-extension or a frozen build — that case degrades to "target absent",
    same as a missing method.
    """
    if not callable(getattr(player_cls, "send_silence", None)):
        return False

    do_run = getattr(player_cls, "_do_run", None)
    if do_run is None:
        return False

    try:
        source = inspect.getsource(do_run)
    except (OSError, TypeError):
        return False

    return "send_silence" in source


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------


def install_send_silence_suppression() -> bool:
    """Install the D-17 suppression patch onto ``AudioPlayer.send_silence``.

    Returns ``True`` when installed (or already installed — idempotent).
    Returns ``False`` and logs a warning when the target is absent or
    anything else goes wrong while installing. **Never raises** — a patch
    install must not be able to crash boot (D-17.4a).
    """
    global _INSTALLED

    if _INSTALLED:
        return True

    try:
        if not send_silence_patch_target_present():
            log.warning(
                "discord_patch: AudioPlayer.send_silence patch target not found "
                "(library drift) — crossfade transitions will carry discord.py's "
                "100ms end-of-transmission silence. tests/test_discord_patch.py "
                "should have caught this drift in CI."
            )
            return False

        _original = AudioPlayer.send_silence

        def _patched_send_silence(self, count: int = 5) -> None:
            """Suppress the silence burst only when the current source flags a fade cut."""
            if getattr(self.source, "_suppress_end_silence", False):
                return
            return _original(self, count)

        AudioPlayer.send_silence = _patched_send_silence
        _INSTALLED = True
        log.info("discord_patch: installed AudioPlayer.send_silence suppression (D-17)")
        return True
    except Exception as exc:  # noqa: BLE001 — a patch install must never crash boot
        log.warning("discord_patch: failed to install send_silence suppression: %s", exc)
        return False
