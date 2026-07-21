from pathlib import Path

from kb.parsing.cpp import parse_header


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def test_class_with_doxygen(tmp_path: Path):
    src = """\
#pragma once
namespace sudoku {

/**
 * @brief X-Wing detector
 */
class XWingDetector {
public:
    int getDifficulty() const { return 30; }
};

}  // namespace sudoku
"""
    header = _write(tmp_path, "xw.hpp", src)
    syms = list(parse_header(header, tmp_path))
    by_qn = {s.qualified_name: s for s in syms}

    cls = by_qn["sudoku::XWingDetector"]
    assert cls.kind == "class"
    assert "X-Wing detector" in cls.doxygen

    method = by_qn["sudoku::XWingDetector::getDifficulty"]
    assert method.kind == "method"


def test_private_members_skipped(tmp_path: Path):
    src = """\
namespace sudoku {
class Foo {
public:
    void pubMethod();
private:
    void privMethod();
};
}
"""
    syms = list(parse_header(_write(tmp_path, "foo.hpp", src), tmp_path))
    names = {s.qualified_name for s in syms}
    assert "sudoku::Foo::pubMethod" in names
    assert "sudoku::Foo::privMethod" not in names


def test_struct_defaults_to_public(tmp_path: Path):
    src = """\
namespace sudoku {
struct Point {
    int x;
    int method();
};
}
"""
    syms = list(parse_header(_write(tmp_path, "p.hpp", src), tmp_path))
    names = {s.qualified_name for s in syms}
    assert "sudoku::Point::method" in names


def test_forward_declaration_skipped(tmp_path: Path):
    src = """\
namespace sudoku {
class PuzzleState;  // forward decl
class Real { public: int x(); };
}
"""
    syms = list(parse_header(_write(tmp_path, "f.hpp", src), tmp_path))
    qnames = {s.qualified_name for s in syms}
    # Forward declarations have no body and must not appear as defined classes.
    classes = {s.qualified_name for s in syms if s.kind == "class"}
    assert "sudoku::PuzzleState" not in classes
    assert "sudoku::Real" in classes


def test_template_function_picks_up_doxygen(tmp_path: Path):
    src = """\
namespace sudoku {
/**
 * @brief Get the name for a fish of size N
 */
template <int N>
constexpr const char* getFishName() { return "Fish"; }
}
"""
    syms = list(parse_header(_write(tmp_path, "t.hpp", src), tmp_path))
    fn = next(s for s in syms if s.name == "getFishName")
    assert fn.kind == "function"
    assert "fish of size N" in fn.doxygen


def test_namespace_qualification_nests(tmp_path: Path):
    src = """\
namespace sudoku {
namespace detail {
void helper();
}
}
"""
    syms = list(parse_header(_write(tmp_path, "n.hpp", src), tmp_path))
    qnames = {s.qualified_name for s in syms}
    assert "sudoku::detail::helper" in qnames


def test_enum_emitted(tmp_path: Path):
    src = """\
namespace sudoku {
/** @brief Strategy for timeout */
enum class TimeoutStrategy { GRACEFUL, THROW };
}
"""
    syms = list(parse_header(_write(tmp_path, "e.hpp", src), tmp_path))
    e = next(s for s in syms if s.kind == "enum")
    assert e.qualified_name == "sudoku::TimeoutStrategy"
    assert "timeout" in e.doxygen.lower()


def test_alias_emitted(tmp_path: Path):
    src = """\
namespace sudoku {
using Deadline = int;
}
"""
    syms = list(parse_header(_write(tmp_path, "a.hpp", src), tmp_path))
    a = next(s for s in syms if s.kind == "alias")
    assert a.qualified_name == "sudoku::Deadline"
