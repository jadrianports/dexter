"""Wave-0 test scaffold for Phase 11 RAG long-term memory (MEM-01).

This file will hold pure-logic unit tests for models/memory.py and related
helpers once those modules are added in plans 11-03, 11-04, 11-05, and 11-07.

Pure-logic seam convention (mirrors compute_streak, _build_ffmpeg_opts):
  - All testable functions are clock-injectable / dependency-free
  - No asyncpg, no Discord, no Gemini client required
  - Tests run in any env with just `python -m pytest tests/test_memory.py`

Planned test classes (stubs — filled in by later plans):
  - TestRerank         (11-04: rerank() weighted scoring)
  - TestDedup          (11-04: dedup_decision() cosine threshold)
  - TestDecay          (11-04: decay_predicate() + recency_score())
  - TestSalience       (11-05: compute_salience() + choose_eviction())
  - TestIsScheduled    (11-07: memory_distill_batch / sweep scheduling)
  - TestNovelty        (11-04: novelty_score() anti-repetition)

Until models/memory.py exists this file must still be collectable (pytest
--collect-only exits 0) — the placeholder test below satisfies that gate.
"""

from __future__ import annotations


class TestMemoryScaffold:
    """Placeholder class keeping this file collectable before models/memory.py lands."""

    def test_scaffold_collects(self) -> None:
        """Trivially passing test — ensures pytest can collect this file without
        importing models/memory.py (which does not exist yet in Wave 0).

        Remove this test once TestRerank (11-04) is populated.
        """
        assert True, "Wave-0 scaffold collected cleanly"
