---
phase: 18-per-guild-config-foundation-ci-gate
reviewed: 2026-07-10T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - database.py
  - logic/guild_config.py
  - services/guild_config.py
  - bot.py
  - cogs/events.py
  - config.py
  - .github/workflows/ci.yml
  - pyproject.toml
  - requirements-dev.txt
  - tests/conftest.py
  - tests/test_guild_config_logic.py
  - tests/test_guild_config_service.py
  - tests/test_database_phase18.py
  - tests/test_proactive_events.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 18: Code Review Report

**Reviewed:** 2026-07-10
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Reviewed the Phase 18 per-guild config foundation: the `guild_config` DDL + boot
helpers in `database.py`, the pure `logic/guild_config.py` decision seam,
`GuildConfigService` (cache load-all, strict resolver, home-guild seed), the
`bot.py`/`cogs/events.py` rewiring off the single-env-var `DEXTER_CHANNEL_ID`
model, and the new CI workflow + Ruff/pytest tooling.

The core logic seam is well-designed and well-tested: `decide_ambient_channel`/
`is_ambient_channel` are pure, mock-free, and fully branch-covered; the three
voice-event call sites and the two `on_message` gates were correctly converted
to the new synchronous `resolve_ambient_channel`/`is_ambient_channel` API with
no dangling `await` on a now-sync call and no leftover reference to the deleted
`_resolve_dexter_channel`/`_get_ambient_channel` duplicates (verified via
`git show` on the two consolidation commits and a repo-wide grep). The
`ON CONFLICT (guild_id) DO NOTHING` seed idiom and the `load_all()` fail-closed
behavior are both correct and covered by dedicated tests. I ran the full test
suite locally (874 passed / 111 skipped, 0 failed) and `ruff check .` /
`ruff format --check .` (both clean) to confirm the CI gate would pass as
configured.

However, I found and reproduced one blocking defect: the CI workflow's own
`TEST_DATABASE_URL` value is byte-identical to the "not configured" sentinel
literal hard-coded in four test modules (including this phase's own
`test_database_phase18.py`), so the live-DB integration tests those files
exist to run are **silently skipped in CI**, even against the pgvector
Postgres service CI provisions specifically to run them — directly
contradicting the workflow's own inline comment ("D-15: unskips the ~107
live-DB tests"). I verified this by setting the exact CI env value locally and
observing the skip markers fire regardless of Postgres availability.

## Critical Issues

### CR-01: CI's `TEST_DATABASE_URL` value matches the test files' own "unconfigured" sentinel, so 4 modules' live-DB tests never actually run in CI

**File:** `.github/workflows/ci.yml:38`, `tests/test_database_phase18.py:33-35` (same pattern also present pre-existing in `tests/test_database_phase11.py:35-37`, `tests/test_database_phase15.py:32-34`, `tests/test_database_phase16.py:33-35`)

**Issue:** `test_database_phase18.py` (this phase's own new test file) gates its
three live-DB tests with:

```python
_LOCAL_DEFAULT = "postgresql://dexter:dexter@localhost:5432/dexter_test"
_TEST_DSN = os.getenv("TEST_DATABASE_URL", _LOCAL_DEFAULT)
_SKIP_LIVE = _TEST_DSN == _LOCAL_DEFAULT
...
@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
```

i.e. the tests are skipped whenever `TEST_DATABASE_URL` is *absent* **or**
*explicitly set to the literal default string*. The CI workflow sets:

```yaml
env:
  TEST_DATABASE_URL: postgresql://dexter:dexter@localhost:5432/dexter_test
```

— which is character-for-character identical to `_LOCAL_DEFAULT`. So in CI,
`_SKIP_LIVE` evaluates to `True` and all three live-DB tests
(`test_guild_config_columns_and_defaults`, `test_seed_guild_config_if_absent_is_idempotent`,
`test_load_all_guild_configs_returns_seeded_rows`) are skipped — even though
CI stands up a real `pgvector/pgvector:pg16` service reachable at exactly that
DSN. This is not a hypothetical: I reproduced it directly —

```
$ TEST_DATABASE_URL="postgresql://dexter:dexter@localhost:5432/dexter_test" \
  python -m pytest tests/test_database_phase18.py -v
...
test_guild_config_columns_and_defaults SKIPPED
test_seed_guild_config_if_absent_is_idempotent SKIPPED
test_load_all_guild_configs_returns_seeded_rows SKIPPED
6 passed, 3 skipped
```

The same defect independently affects `test_database_phase11.py` (6 tests),
`test_database_phase15.py` (1 test), and `test_database_phase16.py` (2 tests)
— 12 tests total, all silently skipped under CI's exact configuration,
regardless of whether the live Postgres service is up. This directly
contradicts the workflow's own comment: `# D-15: unskips the ~107 live-DB
tests with zero secrets and zero Neon traffic`. The CI badge will show green
while never having actually exercised the `guild_config` schema-shape/defaults
assertions or the D-09 seed-idempotence guarantee against a real Postgres —
exactly the coverage CICD-01 and this phase's own `18-02` test file were
written to provide.

**Fix:** Make the two mechanisms agree. Either:

1. Change the skip-guard to check whether the env var was *explicitly set*,
   not whether its value happens to equal the placeholder string:

```python
_SKIP_LIVE = "TEST_DATABASE_URL" not in os.environ
```

   (matches the intent already documented in every one of these files' own
   module docstring: "Set TEST_DATABASE_URL ... before running the live
   tests" — presence, not a specific non-default value, is what should gate
   this.)

2. Or, if the sentinel-comparison idiom is kept, change CI's value so it no
   longer collides with the sentinel, e.g. append a harmless marker query
   param CI-only:

```yaml
TEST_DATABASE_URL: postgresql://dexter:dexter@localhost:5432/dexter_test?ci=1
```

   (asyncpg tolerates unknown query params; would need spot-checking against
   `conftest.py`'s `asyncpg.connect(dsn=dsn)` call.)

Option 1 is the safer fix — it also repairs the same latent bug in
`test_database_phase11.py`, `test_database_phase15.py`, and
`test_database_phase16.py` without touching the CI YAML at all.

## Warnings

### WR-01: `decide_ambient_channel` can raise uncaught on a malformed `ambient_channel_id`, breaking this phase's own "fail closed" convention

**File:** `logic/guild_config.py:66`

**Issue:** `return int(channel_id) if channel_id is not None else None` only
guards against `None`. If `ambient_channel_id` is ever a non-numeric or empty
string (e.g. `""`), `int(channel_id)` raises `ValueError`. Neither
`GuildConfigService.resolve_ambient_channel` (`services/guild_config.py:139`)
nor its three call sites in `cogs/events.py` (lines 222, 264, 307) or
`bot.py` (lines 519, 737) wrap the call in a `try/except`, so a corrupted row
would propagate an unhandled exception out of a `discord.py` event listener
(`on_voice_state_update`) instead of degrading to silence the way every other
uncertain-state branch in this module is documented to do (D-01/D-03: "fails
closed ... resolves to silence"). Currently unreachable via the only writer
this phase ships (`seed_guild_config_if_absent`, which always passes
`str(channel.id)`), but the column has no `CHECK` constraint and Phase 19's
`/setup` will add a second writer — this gap should be closed before that
lands, not discovered by an on-call incident.

**Fix:**
```python
channel_id = config_row.get("ambient_channel_id")
if channel_id is None:
    return None
try:
    return int(channel_id)
except (TypeError, ValueError):
    return None
```
Add a matching test case (`ambient_channel_id="not-a-number"` -> `None`) to
`tests/test_guild_config_logic.py::TestDecideAmbientChannel`.

### WR-02: Duplicate `is_ambient_channel` gate computation in `on_message`

**File:** `cogs/events.py:398-416`

**Issue:** The proactive-callback gate and the vision-roast gate each call
`self.bot.guild_config.get(message.guild.id)` and re-evaluate
`is_ambient_channel(config_row=..., channel_id=message.channel.id)`
independently, even though both checks are against the exact same
`(guild, channel)` pair for the same message. This is harmless functionally
(cache lookup is O(1)), but it is duplicated logic that will silently drift if
one of the two call sites is edited without the other (e.g. a future channel
allowlist per-surface), and it re-derives a boolean that could be computed
once per `on_message` invocation.

**Fix:**
```python
in_ambient_channel = message.guild is not None and is_ambient_channel(
    config_row=self.bot.guild_config.get(message.guild.id),
    channel_id=message.channel.id,
)
if in_ambient_channel:
    await self._maybe_fire_proactive_callback(message)
if in_ambient_channel and message.attachments:
    await self._maybe_fire_vision_roast(message)
```

### WR-03: `_post_startup_messages` aborts posting to remaining guilds if one guild's `channel.send` fails

**File:** `bot.py:507-526`

**Issue:** The entire `for guild in bot.guilds` loop lives inside one
`try/except Exception`. If `channel.send(...)` raises for guild #1 (e.g.
`discord.Forbidden` after a permission change, or a transient
`discord.HTTPException`), the exception is caught at the *outer* level and the
loop never proceeds to guild #2, #3, etc. — one guild's Discord hiccup
silences the startup announcement for every other guild the bot is in. This
predates Phase 18 (the loop structure was unchanged by the `_resolve_dexter_channel`
deletion — only the resolver call was repointed at
`bot.guild_config.resolve_ambient_channel`), but it is now more consequential
than before: as the bot grows to more guilds (this phase's stated goal — a
foundation for multi-tenant, per-guild config), single-guild send failures
become proportionally more likely to occur on any given boot, and its blast
radius (all guilds after the failing one) scales with guild count.

**Fix:** Move the `try/except` inside the loop body so one guild's failure is
logged and skipped without aborting the rest:
```python
for guild in bot.guilds:
    try:
        channel = bot.guild_config.resolve_ambient_channel(guild)
        if channel:
            await channel.send(
                _pick_random(STARTUP_MESSAGES),
                allowed_mentions=discord.AllowedMentions.none(),
            )
    except Exception as exc:
        log.warning("Startup message post failed for guild %s: %s", guild.id, exc)
```

## Info

### IN-01: Ruff's selected rule set has no security or bug-pattern linters

**File:** `pyproject.toml:6`

**Issue:** `select = ["E", "F", "W", "I"]` covers pycodestyle errors/warnings,
pyflakes, and import sorting — but omits `B` (flake8-bugbear, catches mutable
default args, loop-variable-in-closure, etc.) and `S` (flake8-bandit,
catches `eval`, hardcoded passwords, weak crypto, etc.). Given this repo
handles a Discord bot token, a Gemini API key, and a Postgres DSN, a
bandit-equivalent pass would be a reasonably low-cost addition to the new CI
gate this phase introduces.

**Fix:** Consider adding `"B"` and `"S"` to `select` in a follow-up (may
require a pass of `ruff check --fix` plus manual triage of any real hits, so
not necessarily a same-phase blocker).

### IN-02: `GuildConfigService.__init__` and `.get()` are untyped on `bot`/`guild_id`

**File:** `services/guild_config.py:54,88`

**Issue:** `def __init__(self, pool: asyncpg.Pool, bot) -> None` and
`def get(self, guild_id) -> asyncpg.Record | None` leave `bot` and `guild_id`
unannotated, inconsistent with the otherwise fully-typed signatures elsewhere
in this file (`resolve_ambient_channel(self, guild: discord.Guild)`, etc.).
`bot` can't easily be typed without a circular import on `DexterBot`, but
`guild_id: int | str` would cost nothing and matches the docstring's stated
`{str(guild_id): ...}` cache-key contract.

**Fix:**
```python
def get(self, guild_id: int | str) -> asyncpg.Record | None:
```

---

_Reviewed: 2026-07-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
