from kb.chunking import chunk_markdown


SAMPLE = """\
# X-Wing

A fish pattern on two rows or columns.

## How it works

When digit D has exactly two candidate cells in each of two rows, and those
cells share the same two columns, D can be eliminated from those columns in
every other row.

## Example

Consider rows 2 and 5: digit 7 appears only in columns 3 and 8.

Therefore 7 is eliminated from C3 and C8 in all other rows.

### Verification

Use `sudoku hints` to confirm the elimination set.
"""


def test_chunks_split_on_h2_and_h3():
    chunks = chunk_markdown(SAMPLE)
    paths = [c.heading_path for c in chunks]
    assert ["X-Wing"] in paths
    assert ["X-Wing", "How it works"] in paths
    assert ["X-Wing", "Example"] in paths
    assert ["X-Wing", "Example", "Verification"] in paths


def test_anchor_is_slug_of_last_heading():
    chunks = chunk_markdown(SAMPLE)
    verification = next(c for c in chunks if c.heading_path[-1:] == ["Verification"])
    assert verification.anchor == "verification"


def test_long_section_splits_with_overlap():
    big_section = "\n\n".join(["This is a paragraph." for _ in range(200)])
    doc = f"# Title\n\n## Long\n\n{big_section}\n"
    chunks = [c for c in chunk_markdown(doc, max_tokens=50, overlap_tokens=10) if c.heading_path[-1:] == ["Long"]]
    assert len(chunks) > 1
    assert all(c.heading_path == ["Title", "Long"] for c in chunks)
    assert [c.part for c in chunks] == list(range(len(chunks)))
