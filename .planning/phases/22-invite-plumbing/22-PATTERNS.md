# Phase 22: Invite Plumbing - Pattern Map

**Mapped:** 2026-07-14
**Files analyzed:** 8 (5 new, 3 modified)
**Analogs found:** 7 / 8 (1 file has no close analog — flagged explicitly, not forced)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `logic/invite.py` | utility (pure builder) | transform | `logic/vision.py` / `logic/proactive.py` | role-match (with one deliberate deviation — see below) |
| `cogs/invite.py` | controller (slash command) | request-response | `cogs/help.py` | exact (structural template) |
| `config.py` (modify) | config | — | existing `OWNER_ID`/`DEXTER_CHANNEL_ID` lines | exact (idiom match) |
| `bot.py` (modify) | config/wiring | — | existing cog-load list (2 sites) | exact |
| `cogs/help.py` (modify) | controller (data table) | — | `COMMANDS_INFO` list itself | exact |
| `tests/test_invite_logic.py` | test | transform | `tests/test_vision_logic.py` / `tests/test_proactive_logic.py` | exact |
| `tests/test_invite_drift_guard.py` | test (repo introspection) | batch/file-I/O | `tests/test_autoqueue_wiring.py` (source-inspection, nearest cousin in spirit) | **no close analog** — see below |
| `tests/test_invite_cog.py` | test (cog-level, mocked interaction) | request-response | `tests/test_memory_command.py` | exact |

## Pattern Assignments

### `logic/invite.py` (utility, transform)

**Analog:** `logic/vision.py` (also `logic/proactive.py` — same convention, one file needed)

**Docstring / purity-convention pattern** (`logic/vision.py` lines 1-19):
```python
"""Pure vision-roast firing-decision gate (Phase 17 / VIS-01 / D-04).

All functions in this module are deterministic and side-effect-free: no ``random``,
no ``asyncio``, no ``datetime``, no ``discord``.

Any nondeterministic value (the chance roll, the per-user cooldown state, the
opt-out flag read from the database) is computed by the calling cog glue and
passed in as a primitive — following the established seam pattern from
``logic/roasts.py`` and ``logic/proactive.py`` (Phase 10 / 16 convention).
...
Locked by tests/test_vision_logic.py (mock-free boundary coverage).
"""

from __future__ import annotations

import config
```

**Keyword-only signature pattern** (`logic/proactive.py` lines 30-37):
```python
def should_fire_proactive_callback(
    *,
    opted_out: bool,
    chance_roll: float,
    daily_count: int,
    chance: float = config.PROACTIVE_CALLBACK_CHANCE,
    daily_cap: int = config.PROACTIVE_CALLBACK_DAILY_CAP,
) -> bool:
```

**IMPORTANT JUDGMENT CALL FOR THE PLANNER — flag, don't silently resolve:**
Every existing `logic/` module's stated purity contract is "no `random`, no `asyncio`, no `datetime`, **no `discord`**" (verbatim in both `logic/vision.py:3-4` and the same line pattern in `logic/proactive.py:3-4`, and implicitly in `logic/roasts.py`, `logic/guild_config.py`, `logic/autoqueue.py`, `logic/skip_stats.py`, `logic/health.py`, `logic/playback.py`). `logic/invite.py` as scoped by CONTEXT.md/RESEARCH.md **must** `import discord` (for `discord.utils.oauth_url()` + `discord.Permissions`) to satisfy D-03/D-07 ("only one place a URL is ever constructed" — the discord.py wrapper is explicitly recommended over hand-rolling). This is a **real deviation** from the established 8-module convention, not an oversight to silently fix. Two honest options for the planner to choose between:
  1. Accept the deviation, and have `logic/invite.py`'s docstring **explicitly call out** why it breaks the no-`discord`-import rule (pure in the sense of "deterministic, no I/O, no network, no side effects" — just not pure in the sense of "no discord.py import"). This is what RESEARCH.md's own code example does (see its `logic/invite.py` code block, which imports `discord` and cites the Phase 10 seam rule anyway).
  2. Note it's still safe: `discord.utils.oauth_url()` and `discord.Permissions(...)` are both offline, deterministic, no-I/O calls — `import discord` here is a static-dependency deviation only, not a functional violation of the "no I/O/no randomness/no clock" spirit the rule is actually protecting.

Recommend option 1 (RESEARCH.md's own example already does this) — call it out explicitly in the module docstring rather than silently matching the letter of the other 7 modules' "no discord" line.

**Function shape to follow (from RESEARCH.md's own worked example, since no existing `logic/` module returns a URL string):**
```python
def build_invite_url(
    *,
    client_id: int,
    permissions_value: int,
    scopes: tuple[str, ...] = ("bot", "applications.commands"),
) -> str:
    return discord.utils.oauth_url(
        client_id,
        permissions=discord.Permissions(permissions_value),
        scopes=scopes,
    )
```

---

### `cogs/invite.py` (controller, request-response)

**Analog:** `cogs/help.py` (60-line single-command cog — exact structural template)

**Imports + Cog skeleton pattern** (`cogs/help.py` lines 1-8, 32-38, 61-62):
```python
"""Help slash command."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

class HelpCog(commands.Cog):
    """Provides the /help command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
```

**Command decorator pattern** (`cogs/help.py` line 38-40 — note: help has a cooldown, invite deliberately does not per Claude's-Discretion note):
```python
    @app_commands.command(name="help", description="Show all available commands")
    @app_commands.checks.cooldown(1, 5.0)
    async def help_command(self, interaction: discord.Interaction) -> None:
```
`/invite` drops the `@app_commands.checks.cooldown(...)` line entirely (D-05/discretion: "no cooldown, nothing to rate-limit" — a reviewer seeing help.py's cooldown and NOT seeing one on invite.py should read this as deliberate, so the plan's action description should say so explicitly).

**Embed construction pattern** (`cogs/help.py` lines 41-45 — same `color=0x2C76DD` blurple used project-wide including `cogs/memory.py:109` variants):
```python
        embed = discord.Embed(
            title="Dexter — Commands",
            description="Here's what I can do.",
            color=0x2C76DD,
        )
```

**Link-button view pattern (NEW to this phase — no existing analog since Phase 7's `NowPlayingView` is a persistent callback-button view, not a link view).** RESEARCH.md confirms (Pitfall 4, verified locally against installed discord.py 2.7.1) `discord.ui.Button(style=link, url=..., label=...)` needs no `custom_id` and no `setup_hook` persistent-view registration — a plain `discord.ui.View()` (default `timeout=180.0`) is sufficient since it exists only to carry one button on a single response, never to survive a restart:
```python
        view = discord.ui.View()
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, url=url, label="Add to Discord"))
        await interaction.response.send_message(embed=embed, view=view)  # public — no ephemeral=True (D-05)
```
Contrast with `cogs/memory.py`'s views (`MemoryPageView`, `ForgetConfirmView`), which use interactive (non-link) buttons and DO need `custom_id`-bearing `@discord.ui.button` decorators plus `on_timeout` disable-handling — none of that machinery applies here.

---

### `config.py` (modify)

**Analog:** existing `os.getenv(...) or default` idiom lines

**Exact idiom to copy** (`config.py` lines 57, 86):
```python
DEXTER_CHANNEL_ID = int(os.getenv("DEXTER_CHANNEL_ID") or "0") or None
OWNER_ID = int(os.getenv("OWNER_ID") or "0")
```

**Applied to D-04's public-constant-with-override:**
```python
# --- Phase 22: Invite Plumbing (INVITE-01/02) ---
DISCORD_CLIENT_ID = int(os.getenv("DISCORD_CLIENT_ID") or "1492588698364018898")

# D-01/D-02/D-09: least-privilege, functional-complete bitfield — test-locked,
# see tests/test_invite_logic.py::test_bitfield_excludes_dangerous_permissions.
INVITE_PERMISSIONS_VALUE = 309240908864
INVITE_SCOPES: tuple[str, ...] = ("bot", "applications.commands")
```
Placement convention: each phase's block is a commented `# --- Phase N: ... ---` header directly in `config.py` (see the `# Phase 6`, `# Phase 7`, `# Phase 16` blocks already present) — append at the end of the file in the same style, not interleaved into an unrelated existing block.

---

### `bot.py` (modify)

**Analog:** the existing two cog-load call sites — a plain list AND a fallback sequential-load block

**List-form load site** (`bot.py` lines 543-556):
```python
        "cogs.music",
        "cogs.help",
        "cogs.events",
        "cogs.library",
        "cogs.ops",
        "cogs.memory",
        "cogs.admin",
```
Add `"cogs.invite"` to this list (alongside `cogs.memory`/`cogs.admin`, i.e. non-AI-gated cogs — invite has no Gemini dependency so it belongs in the unconditional list, NOT the `for _ext in ("cogs.ai", "cogs.imagine")` conditional block).

**Sequential fallback load site** (`bot.py` lines 1383-1391):
```python
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.help")
    await bot.load_extension("cogs.events")
    await bot.load_extension("cogs.library")
    await bot.load_extension("cogs.ops")
    await bot.load_extension("cogs.memory")
```
Both sites must be updated — `bot.py` maintains cog registration in TWO places (the primary loop and a fallback path around line 1379's comment referencing "the library commands missing because cogs.ops and cogs.library were" not loaded — a prior scar about exactly this dual-registration gotcha). Add `await bot.load_extension("cogs.invite")` to this block too, in the same relative position (after `cogs.memory`, before the AI-gated ones).

---

### `cogs/help.py` (modify)

**Analog:** the `COMMANDS_INFO` list itself (self-modification, not cross-file)

**Exact entry-formatting convention** (`cogs/help.py` lines 9-23):
```python
COMMANDS_INFO = [
    ("/play <query or URL>", "Search YouTube or queue a URL directly"),
    ...
    ("/help", "Show this help message"),
]
```
Add `("/invite", "Get Dexter's invite link")` (or similar dry copy) as a new tuple in this list, under Utility per D-06 — append near `/help` at the end of `COMMANDS_INFO`, not in `ADMIN_COMMANDS_INFO`.

---

### `tests/test_invite_logic.py` (test, transform)

**Analog:** `tests/test_vision_logic.py` (mock-free pure-unit convention + config-derived boundary constants)

**File-level docstring + no-mocks discipline pattern** (`tests/test_vision_logic.py` lines 1-8):
```python
"""Exhaustive pure-unit tests for logic/vision.py (VIS-01 / D-04).

No mocks, no clocks, no RNG — all inputs are plain Python primitives.
Rolls (floats), the opt-out flag, and the pre-computed cooldown_elapsed bool
are passed directly, mirroring tests/test_proactive_logic.py's discipline.

If a test needs a mock the cut-line in logic/vision.py is wrong.
"""

import config
from logic.vision import should_fire_vision_roast
```

**Config-derived boundary constant pattern** (`tests/test_vision_logic.py` lines 17-19 — apply the identical idiom to the bitfield/URL assertions):
```python
CHANCE_PASS = config.VISION_ROAST_CHANCE - 0.01  # just under the threshold
CHANCE_FAIL = config.VISION_ROAST_CHANCE  # exactly at threshold -> False
```
For `test_invite_logic.py`, the equivalent "named scar regression" test is D-02's negative-assertion lock — construct a `discord.Permissions(config.INVITE_PERMISSIONS_VALUE)` and assert `.administrator is False`, `.manage_guild is False`, `.manage_roles is False`, `.manage_channels is False`, `.ban_members is False`, `.kick_members is False`, AND `.value == 309240908864` exactly — mirroring how `test_vision_logic.py` asserts exact boundary values rather than loose ranges.

---

### `tests/test_invite_drift_guard.py` (test, repo-introspection)

**No close analog exists in this codebase — stated explicitly rather than forced.** No existing test shells out to `git` or uses `subprocess` (`Grep` across `tests/` for `subprocess`/`git ls-files` returned zero hits outside RESEARCH.md's own proposed skeleton). The **nearest cousins in spirit** (both source-inspection, not git-introspection):

- `tests/test_autoqueue_wiring.py` (Phase 14) — uses `inspect.getsource(AICog.try_auto_queue)` to assert wiring exists without a live Discord/Gemini/DB path:
  ```python
  """Source-assertion regression tests for Phase 14 auto-queue taste-aware wiring
  (BRAIN-01 / D-01, D-02, D-03) — plan 14-03.

  These tests use `inspect.getsource` to assert the wiring exists in
  `cogs\\ai.py::try_auto_queue`, without needing a live Discord/Gemini/DB path.
  """
  import inspect
  from cogs.ai import AICog

  def _try_auto_queue_source() -> str:
      return inspect.getsource(AICog.try_auto_queue)
  ```
  The shared idea worth carrying over: a private `_helper()` function that produces the "thing to inspect" (source text there; here, the list of matched files/URLs), then multiple test functions assert against it.
- Phase 21's `T-21-03` invariant check (per pattern-mapping context note) is the other cited cousin — a structural/literal-list check rather than a dynamic introspection, matching this phase's own D-03 preference for a hardcoded exclusion rule (`.planning/` prefix) over a clever heuristic.

**No existing test uses `git` subprocess calls at all** — this will be the first. Recommend the plan explicitly note this is new test infrastructure (a `_repo_root()`/`_tracked_doc_files()` helper pair, per RESEARCH.md's own skeleton) rather than implying a pattern is being followed. `conftest.py` was checked — it holds pgvector/DB fixtures only (no repo-introspection helpers to reuse or extend).

**CI environment constraint confirmed** (`.github/workflows/ci.yml` lines 1-59): the `test` job runs on `ubuntu-latest`, checks out via `actions/checkout@v4` (so `.git` is present and `git ls-files`/`git rev-parse --show-toplevel` will work), sets only `TEST_DATABASE_URL` (a local pgvector service container connection string) — **no `DISCORD_CLIENT_ID`, no Discord/Gemini secrets of any kind**. This confirms D-04's premise exactly: `config.DISCORD_CLIENT_ID`'s committed default (not an env-only value) is what the drift-guard test resolves in CI. `permissions: contents: read` is set at workflow level — read-only is sufficient for `git ls-files`.

---

### `tests/test_invite_cog.py` (test, cog-level mocked interaction)

**Analog:** `tests/test_memory_command.py` (mocked bot + mocked interaction convention, no live Discord/DB)

**Fake-bot / fake-interaction helper pattern** (`tests/test_memory_command.py` lines 42-69):
```python
def _make_bot() -> MagicMock:
    """Return a minimal fake bot with a pool (MemoryCog has no gemini dep)."""
    bot = MagicMock()
    bot.pool = MagicMock()
    return bot


def _make_interaction(user_id: int = 1) -> MagicMock:
    """Return a minimal fake discord.Interaction."""
    interaction = MagicMock(spec=discord.Interaction)

    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.display_name = "Invoker"
    user.bot = False
    interaction.user = user

    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.original_response = AsyncMock(return_value=_make_message_mock())
    return interaction
```
For `cogs/invite.py`'s test, the fake bot additionally needs `bot.application_id = <int>` set (for the D-04 fallback branch: `config.DISCORD_CLIENT_ID or self.bot.application_id`) — `test_memory_command.py`'s `_make_bot()` doesn't need this since `MemoryCog` has no such fallback, so this is one deliberate addition on top of the copied pattern, not a verbatim reuse.

**Docstring test-list convention** (`tests/test_memory_command.py` lines 1-24) — list each test name with a one-line purpose comment at the top of the file; apply the same convention, e.g.:
```
- test_invite_command_sends_correct_url    — embed+button URL == build_invite_url()'s output
- test_invite_command_is_public            — response never sets ephemeral=True (D-05)
- test_invite_command_uses_fallback_client_id — bot.application_id used when config constant is falsy (D-04 discretion)
```

**Mock-style structural signature guard convention** — `test_memory_command.py` line 18 ("`test_memory_subcommands_have_no_target_param` — V4 structural self-scoping guard") shows the project's convention for asserting a command's parameter list via `inspect.signature`. Not directly needed for `/invite` (no user-identity parameter to guard), but worth knowing this idiom exists if the planner wants a lightweight "no unexpected params" guard test.

## Shared Patterns

### Pure `logic/` seam convention (Phase 10 D-01/D-02, extended Phase 16/17)
**Source:** `logic/proactive.py`, `logic/vision.py`
**Apply to:** `logic/invite.py`
Deterministic, keyword-only, config-defaulted parameters; a module docstring stating what nondeterminism is excluded and citing the Phase 10 seam rule; locked by a dedicated `tests/test_*_logic.py` file. **Deviation to flag:** `logic/invite.py` is the first `logic/` module that imports `discord` — call this out explicitly in its docstring rather than silently breaking the convention (see Pattern Assignments above for the two framings).

### `config.py` env-override-with-committed-default idiom
**Source:** `config.py:57` (`DEXTER_CHANNEL_ID`), `config.py:86` (`OWNER_ID`)
**Apply to:** `DISCORD_CLIENT_ID`
```python
X = int(os.getenv("X") or "0") or None   # or/and variants depending on falsy-handling needed
```

### Blurple embed color convention
**Source:** `cogs/help.py:44`, `cogs/memory.py` (uses a different purple `0x9B59B6` deliberately for its own view — note colors are NOT universally shared, they vary per-cog for visual distinction)
**Apply to:** `cogs/invite.py`'s embed — `0x2C76DD` matches `/help`'s color since both are "meta/utility" surfaces, not a hard requirement.

### Dual cog-registration sites in `bot.py`
**Source:** `bot.py:543-556` (primary list) and `bot.py:1383-1391` (fallback sequential block)
**Apply to:** `cogs/invite.py` registration — MUST be added to BOTH sites; `bot.py:1379`'s adjacent comment documents a prior real incident where only one site was updated ("the library commands missing because cogs.ops and cogs.library were" not loaded in the other path).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `tests/test_invite_drift_guard.py` | test (repo introspection) | file-I/O / batch | No existing test in `tests/` shells out to `git` or does a `git ls-files`-driven file scan. Nearest cousins are source-inspection tests (`tests/test_autoqueue_wiring.py`'s `inspect.getsource` pattern) and Phase 21's T-21-03 hardcoded-literal-list discipline, but neither does git-tracked-file enumeration. The planner should treat this as genuinely new test infrastructure, following RESEARCH.md's own worked-out code skeleton (which is HIGH-confidence, already verified: `_repo_root()` via `git rev-parse --show-toplevel`, `_tracked_doc_files()` via `git ls-files` filtered to exclude `.planning/` and non-text extensions, a literal-match assertion loop, plus a `tmp_path`-based positive-control test). |

## Metadata

**Analog search scope:** `logic/` (all 8 pure-seam modules, `proactive.py`/`vision.py` read in full), `cogs/` (`help.py`, `memory.py` read in full), `config.py` (grep for `os.getenv` idiom), `bot.py` (grep for cog-load sites), `tests/` (grep for `subprocess`/`inspect.getsource`/`git ls-files` across 20 candidate files; `test_vision_logic.py`, `test_memory_command.py`, `test_autoqueue_wiring.py` read in relevant part), `.github/workflows/ci.yml` (read in full for the CI-env constraint).
**Files scanned:** ~15 read/grepped directly, plus 20 test files searched by grep.
**Pattern extraction date:** 2026-07-14
