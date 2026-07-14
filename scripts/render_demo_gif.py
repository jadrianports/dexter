#!/usr/bin/env python3
"""Render docs/demo.gif from the landing page's demo mock (D-07, Phase 23-07).

One source, two derivatives: `site/src/components/DemoMock.astro` is the
landing page's Discord-conversation reconstruction (PORT-02); this script
mechanically derives the README's demo GIF from the SAME built artifact via
a Playwright video recording plus a two-pass ffmpeg palette conversion. There
is no second authoring pass here -- the README and the landing page cannot
drift into telling different stories about what Dexter said.

--------------------------------------------------------------------------
ONE-TIME LOCAL SETUP (never run in CI, never added to a requirements file --
see the rationale below):

    pip install playwright
    playwright install chromium

--------------------------------------------------------------------------
USAGE:

    Build the site first:

        cd site && npm ci && npm run build

    Then, from the repo root:

        python scripts/render_demo_gif.py

    Produces docs/demo.gif. Target: under 2MB with legible text. If a full
    loop overshoots the budget, tune FPS first, then WIDTH (the two
    constants below) -- record whatever you land on wherever this script's
    output is described (a plan SUMMARY, a commit message).

--------------------------------------------------------------------------
WHY PLAYWRIGHT NEVER ENTERS requirements.txt / requirements-dev.txt:

`requirements.txt` is baked into the production Docker image -- a headless
browser has zero runtime relevance to a Discord bot. `requirements-dev.txt`
installs on every CI run and is deliberately minimal (currently just
`ruff`). This script is a dev-machine-only, run-once tool: the GIF is a
committed, generated-once asset that changes only when the mock's copy
changes, and no CI workflow ever regenerates it -- adding a headless-browser
download to every CI run would trade away the fast, minimal-privilege job
posture this project is built around. The one-time setup is documented here,
in the script's own header, the same way `ci.yml` documents conditional
manual steps without baking them into the default path.

--------------------------------------------------------------------------
HONESTY GATE (D-06 / D-07):

This script does not inspect or care what the demo mock's transcript says --
it faithfully records whatever `site/dist/index.html` actually renders. If
the mock still carries its `{{DEXTER_DEMO_LINE_*}}` placeholder tokens (see
`site/src/data/demo-transcript.ts`), the resulting GIF will visibly show
those tokens verbatim. Do NOT run this script to produce a committed
`docs/demo.gif` until the real, verbatim Dexter lines have landed and the
placeholders are gone -- a placeholder-token GIF on a page whose entire
thesis is honest disclosure is a worse failure mode than shipping no GIF at
all. See `.planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md` for
the current status of this dependency.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Tunables. If a full loop overshoots the ~2MB budget, tune FPS first, then
# WIDTH -- in that order (Task 1 instruction / RESEARCH Finding 7).
# ---------------------------------------------------------------------------
FPS = 12
WIDTH = 640
LOOP_SECONDS = 16.5  # one full 16s CSS loop (site/src/components/DemoMock.astro) + margin
VIDEO_SIZE = {"width": 900, "height": 560}  # matches the mock's desktop geometry

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_INDEX = REPO_ROOT / "site" / "dist" / "index.html"
OUTPUT_GIF = REPO_ROOT / "docs" / "demo.gif"


def _record_webm(scratch_dir: Path) -> Path:
    """Launch Chromium, record one full loop of the built demo mock, and
    return the path to the recorded .webm.

    Uses Playwright's browser-context video recording (not a screenshot
    loop) -- screenshot capture disables CSS animations by default, which
    would fight the mock's CSS-keyframe-driven reveal instead of using it.
    The video only finalizes on `context.close()` -- the single easiest
    step in this whole pipeline to get wrong.
    """
    from playwright.sync_api import sync_playwright

    if not DIST_INDEX.exists():
        raise SystemExit(f"{DIST_INDEX} does not exist -- build the site first: cd site && npm ci && npm run build")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            record_video_dir=str(scratch_dir),
            record_video_size=VIDEO_SIZE,
            viewport=VIDEO_SIZE,
        )
        page = context.new_page()
        page.goto(DIST_INDEX.as_uri())

        # Bring the demo section into view -- the mock's CSS loop plays
        # regardless of scroll position, but framing the recording on it
        # matches what a README reader expects the GIF to show.
        demo_section = page.locator("#demo")
        demo_section.scroll_into_view_if_needed()

        page.wait_for_timeout(int(LOOP_SECONDS * 1000))

        video = page.video
        context.close()  # video only finalizes here
        browser.close()

        if video is None:
            raise SystemExit("Playwright did not attach a video to the page -- record_video_dir misconfigured?")
        return Path(video.path())


def _convert_to_gif(webm_path: Path, output_gif: Path) -> None:
    """Two-pass ffmpeg palette conversion (palettegen/paletteuse) -- the
    standard technique for small, crisp-text GIFs. Runs on a dev machine
    only; ffmpeg is already a project dependency (used by the bot itself),
    never invoked here from CI or the Docker image."""
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg not found on PATH -- required for the .webm -> .gif conversion")

    output_gif.parent.mkdir(parents=True, exist_ok=True)
    palette_path = output_gif.parent / "_demo_palette.png"
    scale_filter = f"fps={FPS},scale={WIDTH}:-1:flags=lanczos"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(webm_path),
            "-vf",
            f"{scale_filter},palettegen=stats_mode=diff",
            str(palette_path),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(webm_path),
            "-i",
            str(palette_path),
            "-filter_complex",
            f"{scale_filter}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5",
            str(output_gif),
        ],
        check=True,
    )
    palette_path.unlink(missing_ok=True)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dexter-demo-gif-") as scratch:
        webm_path = _record_webm(Path(scratch))
        _convert_to_gif(webm_path, OUTPUT_GIF)

    size_mb = OUTPUT_GIF.stat().st_size / 1_048_576
    print(f"Wrote {OUTPUT_GIF} ({size_mb:.2f}MB, {FPS}fps, {WIDTH}px wide)")
    if size_mb > 2.0:
        print("WARNING: over the 2MB budget -- tune FPS first, then WIDTH, and re-run.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
