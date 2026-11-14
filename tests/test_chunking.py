"""Tests for split_into_chunks and _is_heading in app/splitting.py.

Each fixture is a miniature of a real case found in the sample agreements.

Run from the project root:
    pytest -v
"""

from app.splitting import (
    CLAUSE,
    PAGE,
    PREAMBLE,
    SECTION,
    _is_heading,
    split_into_chunks,
)


def _summary(chunks):
    """(kind, number) of every chunk -- compact to compare in asserts."""
    return [(c.kind, c.number) for c in chunks]


def _line_count(pages):
    return sum(len(p.splitlines()) for p in pages)


def _find(chunks, number):
    return next(c for c in chunks if c.number == number)


# --- _is_heading ----------------------------------------------------------------

def test_short_line_is_heading():
    assert _is_heading("2. LOAN AMOUNT")


def test_heading_may_end_with_full_stop():
    # AU home loan, p7
    assert _is_heading("4. INTEREST/ APR/ FEES/CHARGES/COSTS ETC.")


def test_line_ending_with_semicolon_or_comma_is_not_heading():
    assert not _is_heading("10. Borrower shall not change the use of the Property;")
    assert not _is_heading("2. Borrower shall not leave India for employment,")


def test_long_line_is_not_heading():
    line = "8. Borrower shall not provide any consent to the builder and/or the developer or to any other person"
    assert len(line) > 80
    assert not _is_heading(line)


# --- PLAIN style (AU personal loan) -----------------------------------------------

PLAIN_DOC = [
    "\n".join([
        "AGREEMENT FOR PERSONAL LOAN",
        "IT IS AGREED BY AND BETWEEN THE PARTIES AS FOLLOWS",
        "1 Definitions and Interpretation",
        "1.1 Definitions",
        '"Agreement" means this personal loan agreement.',
        "1.2 Interpretation",
    ]),
    "\n".join([
        "1.2.1 In this Agreement, singular shall include plural",
        "2 Bank's agreement to lend",
        "2.1 The Bank agrees to lend",
        "2.2 The relationship between the Bank and the Borrower",
        "shall commence from the date of this Agreement",
    ]),
    "\n".join([
        "and continues onto page three.",
        "3 Fees, Charges, Costs and Claims",
        "3.1 The Borrower shall pay all fees",
    ]),
]


def test_plain_document_structure():
    assert _summary(split_into_chunks(PLAIN_DOC)) == [
        (PREAMBLE, None),
        (CLAUSE, "1"), (CLAUSE, "1.1"), (CLAUSE, "1.2"), (CLAUSE, "1.2.1"),
        (CLAUSE, "2"), (CLAUSE, "2.1"), (CLAUSE, "2.2"),
        (CLAUSE, "3"), (CLAUSE, "3.1"),
    ]


def test_preamble_holds_lines_before_first_clause():
    preamble = split_into_chunks(PLAIN_DOC)[0]
    assert preamble.lines == [
        "AGREEMENT FOR PERSONAL LOAN",
        "IT IS AGREED BY AND BETWEEN THE PARTIES AS FOLLOWS",
    ]
    assert (preamble.page_start, preamble.page_end) == (1, 1)


def test_chunk_starts_with_the_line_that_started_it():
    clause = _find(split_into_chunks(PLAIN_DOC), "1.1")
    assert clause.text == '1.1 Definitions\n"Agreement" means this personal loan agreement.'


def test_clause_spanning_two_pages():
    clause = _find(split_into_chunks(PLAIN_DOC), "2.2")
    assert (clause.page_start, clause.page_end) == (2, 3)
    assert clause.lines[-1] == "and continues onto page three."


def test_every_line_ends_up_in_exactly_one_chunk():
    chunks = split_into_chunks(PLAIN_DOC)
    assert sum(len(c.lines) for c in chunks) == _line_count(PLAIN_DOC)


def test_top_level_number_must_follow_sequence():
    # "12 Months ..." matches the PLAIN top pattern, but 12 is not 3 or 4
    pages = PLAIN_DOC[:2] + ["12 Months from the date of disbursement\n" + PLAIN_DOC[2]]
    clause = _find(split_into_chunks(pages), "2.2")
    assert "12 Months from the date of disbursement" in clause.lines


def test_sub_clause_must_belong_to_current_clause():
    # A wrapped cross-reference "1.1 above" inside clause 3 is not clause 1.1
    pages = PLAIN_DOC + ["1.1 above shall apply to all fees"]
    chunks = split_into_chunks(pages)
    assert [c.number for c in chunks].count("1.1") == 1
    assert chunks[-1].number == "3.1"
    assert chunks[-1].lines[-1] == "1.1 above shall apply to all fees"


# --- DOTTED style with a restarting list (AU home loan, clause 7) --------------

DOTTED_DOC = ["\n".join([
    "1. DEFINITIONS",
    "1.1. In this Agreement, unless the context otherwise requires",
    "1.2. Unless a contrary indication appears",
    "2. LOAN AMOUNT",
    "2.1. The Borrower agrees to borrow",
    "2.2. The Bank agrees to lend",
    "3. BORROWER'S COVENANTS AND UNDERTAKINGS:",
    "1. Borrower shall not stand surety for anybody;",
    "4. Borrower shall not provide any consent to the builder and/or the developer or to any other person",
    "5. Borrower shall not change the use of the Property;",
    "4. EVENTS OF DEFAULT",
    "4.1. Non-payment of any amount due",
])]


def test_restarting_list_does_not_hijack_clause_numbers():
    assert _summary(split_into_chunks(DOTTED_DOC)) == [
        (CLAUSE, "1"), (CLAUSE, "1.1"), (CLAUSE, "1.2"),
        (CLAUSE, "2"), (CLAUSE, "2.1"), (CLAUSE, "2.2"),
        (CLAUSE, "3"),
        (CLAUSE, "4"), (CLAUSE, "4.1"),
    ]


def test_list_items_stay_inside_their_clause():
    clause = _find(split_into_chunks(DOTTED_DOC), "3")
    assert len(clause.lines) == 4   # heading + 3 list items


# --- ARTICLE style (RBL home loan) ------------------------------------------------

ARTICLE_DOC = [
    "\n".join([
        "LOAN AGREEMENT",
        "WHEREAS:",
        "NOW THIS AGREEMENT WITNESSETH AS UNDER:",
        "ARTICLE 1",
        "DEFINTIONS AND INTERPRETATION",
        "1.1 Agreement means this loan agreement",
    ]),
    "\n".join([
        "ARTICLE 2",
        "LOAN",
        "2.1 Amount of Loan",
        "The Borrower agrees to borrow",
        "2.2 Interest",
        "10 Date of commencement of EMI",
    ]),
]


def test_article_document_structure():
    assert _summary(split_into_chunks(ARTICLE_DOC)) == [
        (PREAMBLE, None),
        (CLAUSE, "1"), (CLAUSE, "1.1"),
        (CLAUSE, "2"), (CLAUSE, "2.1"), (CLAUSE, "2.2"),
    ]


def test_article_heading_keeps_its_title_line():
    article = _find(split_into_chunks(ARTICLE_DOC), "2")
    assert article.lines == ["ARTICLE 2", "LOAN"]
    assert (article.page_start, article.page_end) == (2, 2)


# --- Sections: schedules and annexures --------------------------------------------

SECTION_DOC = [
    "\n".join([
        "1 Definitions",
        "1.1 Loan means the loan sanctioned",
        "1.2 Property means the property described in the",
        "Schedule to this Agreement on the terms set out",
        "2 Interest",
        "2.1 Interest accrues monthly",
        "2.2 Penal charges apply on default",
    ]),
    "\n".join([
        "SCHEDULE-1",
        "3 Date of Execution",
        "2.1 Rate of interest 11.5%",
        "Annexure- 1",
        "LETTER OF GENERAL LIEN",
    ]),
]


def test_schedules_and_annexures_become_sections():
    assert _summary(split_into_chunks(SECTION_DOC)) == [
        (CLAUSE, "1"), (CLAUSE, "1.1"), (CLAUSE, "1.2"),
        (CLAUSE, "2"), (CLAUSE, "2.1"), (CLAUSE, "2.2"),
        (SECTION, None), (SECTION, None),
    ]


def test_lowercase_schedule_continuation_is_not_a_section():
    clause = _find(split_into_chunks(SECTION_DOC), "1.2")
    assert clause.lines[-1] == "Schedule to this Agreement on the terms set out"


def test_no_clauses_inside_sections():
    # "3 Date of Execution" and "2.1 Rate..." look like clauses, but they are schedule rows
    schedule = split_into_chunks(SECTION_DOC)[6]
    assert schedule.lines == ["SCHEDULE-1", "3 Date of Execution", "2.1 Rate of interest 11.5%"]
    assert (schedule.page_start, schedule.page_end) == (2, 2)


# --- UNKNOWN style fallback -----------------------------------------------------

def test_unknown_style_falls_back_to_one_chunk_per_page():
    pages = ["Just a paragraph.", "", "Another paragraph.\nSecond line."]
    chunks = split_into_chunks(pages)
    assert _summary(chunks) == [(PAGE, None), (PAGE, None)]
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 1), (3, 3)]
    assert chunks[1].lines == ["Another paragraph.", "Second line."]


def test_empty_document():
    assert split_into_chunks([]) == []
