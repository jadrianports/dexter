# Deferred Items — Phase 26

Out-of-scope discoveries logged during execution, per the executor's SCOPE BOUNDARY rule
(only auto-fix issues directly caused by the current task's changes).

## 26-01

- `python -m ruff format --check .` flags 3 pre-existing files as needing reformat:
  `services/memory.py`, `tests/test_database_phase25.py`, `tests/test_vision_events.py`.
  None are in this plan's `files_modified` list; all last touched by Phase 25 commits
  (`b346d0e`, `f5a91dc`, `33c449b`), before this plan started. Not fixed — out of scope.
