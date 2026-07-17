# Deferred Items — Phase 27

## Pre-existing ruff-format drift (out of scope, plan 27-02)

`ruff format --check .` reports 3 files needing reformatting that this plan
did not touch and are unrelated to plan 27-02's `files_modified` list:

- `services/memory.py`
- `tests/test_database_phase25.py`
- `tests/test_vision_events.py`

`git diff --stat` on all three is empty against this plan's commits —
confirmed pre-existing drift, not introduced by 27-02. Out of scope per the
executor's scope boundary rule (only auto-fix issues directly caused by the
current task's changes). Left unfixed; flag for a future formatting-only pass
if desired.
