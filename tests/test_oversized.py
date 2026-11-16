"""Tests for line_pages tracking and split_oversized() in app/splitting.py.

Run from the project root:
    pytest -v
"""

from app.splitting import CLAUSE, PAGE, Chunk, split_into_chunks, split_oversized

# Every test line is 9 characters, e.g. "line 0003".
# Joined with "\n", 3 lines = 29 characters and 4 lines = 39.
# So with max_chars=30, each part holds exactly 3 lines.


def make_long_chunk(n_lines, pages=None, kind=CLAUSE, number="7", term=None):
    lines = [f"line {i:04d}" for i in range(n_lines)]
    pages = pages or [13] * n_lines
    return Chunk(kind, number, pages[0], pages[-1], lines, term=term, line_pages=pages)


# --- split_into_chunks records the page of every line -------------------------

# Dotted style: five "N.N." sub-clauses. Clause 1.2 continues onto page 2.
DOTTED_PAGES = [
    "1. DEFINITIONS\n1.1. First sub-clause\n1.2. Second sub-clause",
    "continues on page two\n2. LOAN\n2.1. Third sub-clause",
    "2.2. Fourth sub-clause\n2.3. Fifth sub-clause\nmore of 2.3",
]


def test_every_chunk_has_one_page_per_line():
    for chunk in split_into_chunks(DOTTED_PAGES):
        assert len(chunk.line_pages) == len(chunk.lines)
        assert chunk.line_pages[0] == chunk.page_start
        assert chunk.line_pages[-1] == chunk.page_end


def test_clause_spanning_two_pages_records_both():
    chunks = split_into_chunks(DOTTED_PAGES)
    clause_1_2 = next(c for c in chunks if c.number == "1.2")
    assert clause_1_2.line_pages == [1, 2]


def test_page_fallback_records_pages_too():
    chunks = split_into_chunks(["hello world\nsecond line", "", "bye"])
    assert [c.kind for c in chunks] == [PAGE, PAGE]
    assert [c.line_pages for c in chunks] == [[1, 1], [3]]


# --- split_oversized ----------------------------------------------------------

def test_short_chunk_is_unchanged():
    chunk = make_long_chunk(2)
    result = split_oversized([chunk], max_chars=30)
    assert result == [chunk]
    assert result[0].part is None


def test_long_chunk_is_split_into_parts_within_the_limit():
    parts = split_oversized([make_long_chunk(10)], max_chars=30)
    assert [len(p.lines) for p in parts] == [3, 3, 3, 1]
    assert all(len(p.text) <= 30 for p in parts)


def test_parts_keep_kind_number_and_term_and_are_numbered():
    parts = split_oversized([make_long_chunk(7, term="Penal Charges")], max_chars=30)
    assert [p.part for p in parts] == [1, 2, 3]
    assert all(p.kind == CLAUSE and p.number == "7" for p in parts)
    assert all(p.term == "Penal Charges" for p in parts)


def test_no_line_is_lost_or_reordered():
    chunk = make_long_chunk(10)
    parts = split_oversized([chunk], max_chars=30)
    assert [line for p in parts for line in p.lines] == chunk.lines


def test_each_part_gets_its_own_pages():
    # AU home clause 7 runs from page 13 to 24; each part must cite its own pages
    pages = [13, 13, 13, 14, 14, 15, 15, 15, 16, 16]
    parts = split_oversized([make_long_chunk(10, pages=pages)], max_chars=30)
    assert [(p.page_start, p.page_end) for p in parts] == [(13, 13), (14, 15), (15, 16), (16, 16)]
    assert [p.line_pages for p in parts] == [[13, 13, 13], [14, 14, 15], [15, 15, 16], [16]]


def test_a_single_line_over_the_limit_is_kept_whole():
    lines = ["short", "y" * 50, "short2"]
    chunk = Chunk(CLAUSE, "7", 1, 1, lines, line_pages=[1, 1, 1])
    parts = split_oversized([chunk], max_chars=20)
    assert [p.lines for p in parts] == [["short"], ["y" * 50], ["short2"]]


def test_section_title_is_recorded_and_kept_by_every_part():
    pages = ["1. DEFINITIONS\n1.1. a\n1.2. b\n1.3. c\n1.4. d\n1.5. e",
             "Annexure B\n" + "\n".join(f"fee row {i:02d}" for i in range(10))]
    section = next(c for c in split_into_chunks(pages) if c.title)
    assert section.title == "Annexure B"
    parts = split_oversized([section], max_chars=40)
    assert len(parts) > 1
    assert all(p.title == "Annexure B" for p in parts)


def test_only_long_chunks_are_split_and_order_is_kept():
    short_before = Chunk(CLAUSE, "6", 12, 12, ["line 9999"], line_pages=[12])
    short_after = Chunk(CLAUSE, "8", 25, 25, ["line 8888"], line_pages=[25])
    result = split_oversized([short_before, make_long_chunk(4), short_after], max_chars=30)
    assert [(c.number, c.part) for c in result] == [("6", None), ("7", 1), ("7", 2), ("8", None)]
