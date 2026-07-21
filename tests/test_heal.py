from pathlib import Path

import pytest

from kb.heal import _replace_symbol, _score_candidate, propose
from kb.verify import verify


def test_exact_local_name_match_scores_highest():
    score, reason = _score_candidate("XWingTechnique", "sudoku::techniques::XWingTechnique")
    assert reason == "moved"
    assert score >= 0.9


def test_high_similarity_marked_as_renamed():
    score, reason = _score_candidate("XWingTechnique", "sudoku::XWingDetector")
    assert reason in {"renamed", "similar"}
    assert score >= 0.7


def test_unrelated_names_get_dropped():
    score, _ = _score_candidate("XWingTechnique", "sudoku::PuzzleState")
    assert score == 0.0


def test_short_shared_substring_not_enough():
    # "XYZ" and "WXY" share only "X" / "Y" individually — should not count.
    score, _ = _score_candidate("XYZ", "WXY")
    assert score == 0.0


def test_replace_symbol_only_touches_yaml_list_entries():
    text = """\
---
concept: x-wing
implements:
  - sudoku::XWingTechnique
underlying:
  - sudoku::FishTechnique
---

The body mentions sudoku::XWingTechnique in prose. That should NOT be replaced
because human prose may want its own update.
"""
    out = _replace_symbol(text, "sudoku::XWingTechnique", "sudoku::NewName")
    # YAML list entry replaced:
    assert "  - sudoku::NewName" in out
    # Prose mention left intact:
    assert "prose mentions sudoku::XWingTechnique" in out.lower() or "mentions sudoku::XWingTechnique in prose" in out


_BROKEN_ENTRY = """\
---
concept: x-wing
title: X-Wing
kind: technique
implements:
  - sudoku::XWingMissingClass
underlying:
  - sudoku::FishTechniqueGone
---

Body text.
"""


_GOOD_HEADERS = """\
#pragma once
namespace sudoku {
class XWingMissingClassRenamed { public: int x(); };
class FishTechniqueGoneNewName { public: int y(); };
}
"""


def test_propose_finds_renamed_candidates(tmp_path: Path):
    ontology = tmp_path / "ontology"
    include = tmp_path / "include" / "sudoku"
    ontology.mkdir(parents=True)
    include.mkdir(parents=True)
    (ontology / "x.md").write_text(_BROKEN_ENTRY)
    (include / "h.hpp").write_text(_GOOD_HEADERS)

    report = verify(ontology_root=ontology, include_root=include, repo_root=tmp_path)
    assert not report.ok

    from kb.verify import collect_engine_symbols

    symbols = collect_engine_symbols(include, tmp_path)
    suggestions = propose(report, symbols)
    assert len(suggestions) == 2
    by_missing = {s.missing.symbol: s for s in suggestions}
    xw = by_missing["sudoku::XWingMissingClass"]
    assert xw.best is not None
    assert xw.best.symbol == "sudoku::XWingMissingClassRenamed"
    fish = by_missing["sudoku::FishTechniqueGone"]
    assert fish.best is not None
    assert fish.best.symbol == "sudoku::FishTechniqueGoneNewName"
