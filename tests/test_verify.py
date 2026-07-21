from pathlib import Path

from kb.verify import verify


_BROKEN_ENTRY = """\
---
concept: broken-entry
title: Broken
kind: technique
implements:
  - sudoku::DoesNotExist
underlying:
  - sudoku::AlsoMissing
---

This entry references symbols that don't exist; the verifier should catch it.
"""


_GOOD_ENTRY = """\
---
concept: real-thing
title: Real Thing
kind: type
implements:
  - sudoku::RealClass
---

This entry references a class we will actually define.
"""


_GOOD_HEADER = """\
#pragma once
namespace sudoku {
/** Real class for the verifier test. */
class RealClass { public: int x(); };
}
"""


def test_verify_reports_missing_bindings(tmp_path: Path):
    ontology = tmp_path / "ontology"
    include = tmp_path / "include" / "sudoku"
    ontology.mkdir(parents=True)
    include.mkdir(parents=True)
    (ontology / "broken.md").write_text(_BROKEN_ENTRY)
    (include / "real.hpp").write_text(_GOOD_HEADER)

    report = verify(ontology_root=ontology, include_root=include)
    assert not report.ok
    missing_syms = {m.symbol for m in report.missing}
    assert "sudoku::DoesNotExist" in missing_syms
    assert "sudoku::AlsoMissing" in missing_syms
    assert report.checked_concepts == 1
    assert report.checked_symbols == 2


def test_verify_passes_when_all_bindings_resolve(tmp_path: Path):
    ontology = tmp_path / "ontology"
    include = tmp_path / "include" / "sudoku"
    ontology.mkdir(parents=True)
    include.mkdir(parents=True)
    (ontology / "good.md").write_text(_GOOD_ENTRY)
    (include / "real.hpp").write_text(_GOOD_HEADER)

    report = verify(ontology_root=ontology, include_root=include)
    assert report.ok
    assert report.checked_symbols == 1


def test_verify_skips_readme(tmp_path: Path):
    ontology = tmp_path / "ontology"
    include = tmp_path / "include" / "sudoku"
    ontology.mkdir(parents=True)
    include.mkdir(parents=True)
    (ontology / "README.md").write_text(_BROKEN_ENTRY)  # would fail if scanned

    report = verify(ontology_root=ontology, include_root=include)
    assert report.checked_concepts == 0
    assert report.ok
