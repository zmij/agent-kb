from pathlib import Path

from kb.discover import _humanise, _slugify, apply_stubs, discover_uncovered


SUFFIXES = ["Technique", "Rule", "Detector"]


def test_humanise_strips_configured_suffix():
    assert _humanise("XYZWingTechnique", SUFFIXES) == "XYZ Wing"
    assert _humanise("AICTechnique", SUFFIXES) == "AIC"
    assert _humanise("SueDeCoqTechnique", SUFFIXES) == "Sue De Coq"


def test_humanise_without_suffixes_keeps_name():
    assert _humanise("XYZWingTechnique") == "XYZ Wing Technique"


def test_slugify_kebab_case():
    assert _slugify("XYZWingTechnique", SUFFIXES) == "xyz-wing"
    assert _slugify("BoxLineReductionTechnique", SUFFIXES) == "box-line-reduction"


def _seed_engine(include: Path):
    (include / "tech.hpp").write_text(
        "namespace sudoku {\n"
        "/**\n"
        " * @brief X-Wing detector.\n"
        " */\n"
        "class XWingTechnique : public Technique { public: int x(); };\n"
        "/**\n"
        " * @brief Sue de Coq pattern.\n"
        " */\n"
        "class SueDeCoqTechnique : public Technique { public: int y(); };\n"
        "}\n"
    )


def _discover(include: Path, ontology: Path, repo_root: Path):
    return discover_uncovered(
        include_root=include,
        ontology_root=ontology,
        repo_root=repo_root,
        base_classes=["Technique"],
        strip_suffixes=SUFFIXES,
        stub_subdir="techniques",
        stub_kind="technique",
    )


def test_discover_skips_already_covered(tmp_path: Path):
    include = tmp_path / "core_engine" / "include" / "sudoku"
    ontology = tmp_path / "docs" / "ontology"
    include.mkdir(parents=True)
    ontology.mkdir(parents=True)
    _seed_engine(include)
    (ontology / "x-wing.md").write_text(
        "---\nconcept: x-wing\nimplements:\n  - sudoku::XWingTechnique\n---\nbody\n"
    )

    proposals = _discover(include, ontology, tmp_path)
    qnames = [p.qualified_name for p in proposals]
    assert "sudoku::XWingTechnique" not in qnames
    assert "sudoku::SueDeCoqTechnique" in qnames


def test_apply_stubs_writes_files_but_never_overwrites(tmp_path: Path):
    include = tmp_path / "core_engine" / "include" / "sudoku"
    ontology = tmp_path / "docs" / "ontology"
    include.mkdir(parents=True)
    ontology.mkdir(parents=True)
    _seed_engine(include)

    proposals = _discover(include, ontology, tmp_path)
    written = apply_stubs(proposals, repo_root=tmp_path)
    assert {p.name for p in written} == {"x-wing.md", "sue-de-coq.md"}

    # Manually edit one of the stubs to prove apply doesn't overwrite.
    sue = ontology / "techniques" / "sue-de-coq.md"
    sue.write_text("HUMAN EDITED\n")
    written_again = apply_stubs(proposals, repo_root=tmp_path)
    assert sue.read_text() == "HUMAN EDITED\n"
    assert sue not in written_again


def test_stub_contains_brief_and_kind(tmp_path: Path):
    include = tmp_path / "core_engine" / "include" / "sudoku"
    ontology = tmp_path / "docs" / "ontology"
    include.mkdir(parents=True)
    ontology.mkdir(parents=True)
    _seed_engine(include)
    proposals = _discover(include, ontology, tmp_path)
    xw = next(p for p in proposals if p.slug == "x-wing")
    assert "X-Wing detector" in xw.to_markdown()
    assert "implements:\n  - sudoku::XWingTechnique" in xw.to_markdown()
    assert "kind: technique" in xw.to_markdown()
