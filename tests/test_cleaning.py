"""Tests for app/cleaning.py. Examples are taken from the real sample agreements.

Run from the project root:
    pytest -v
"""

from app.cleaning import clean_pages


# --- Rule 1: whitespace -------------------------------------------------------

def test_collapses_runs_of_spaces():
    # RBL home loan, p4
    assert clean_pages(["2.1    Amount of Loan"]) == ["2.1 Amount of Loan"]


def test_strips_leading_and_trailing_spaces():
    assert clean_pages(["   5.1 Interest on the Loan   "]) == ["5.1 Interest on the Loan"]


# --- Rule 2: blank lines ------------------------------------------------------

def test_drops_blank_and_whitespace_only_lines():
    raw = "1.2 Interpretation\n \n\n   \n1.2.1 In this Agreement"
    assert clean_pages([raw]) == ["1.2 Interpretation\n1.2.1 In this Agreement"]


# --- Rule 3: stray dots -------------------------------------------------------

def test_drops_lone_dot_lines():
    # AU personal loan, p3
    raw = "2 Bank's agreement to lend\n.\n2.1 The Bank agrees"
    assert clean_pages([raw]) == ["2 Bank's agreement to lend\n2.1 The Bank agrees"]


# --- Rule 4: page numbers -----------------------------------------------------

def test_drops_lone_page_numbers():
    raw = "5.3 Interest tax shall be borne by the Borrower.\n12"
    assert clean_pages([raw]) == ["5.3 Interest tax shall be borne by the Borrower."]


def test_keeps_lone_clause_number_with_dot():
    # RBL home loan, p3: "1." alone on a line IS a clause number
    raw = "1.\nIn this Agreement unless the context otherwise requires;"
    assert clean_pages([raw]) == [raw]


def test_keeps_numbers_inside_text():
    raw = "2.1 The Loan shall carry interest at 11.5% per annum"
    assert clean_pages([raw]) == [raw]


# --- Rule 5: repeated headers and footers -------------------------------------

# Each page needs DIFFERENT body text. "Clause 1", "Clause 2"... would itself
# count as a repeated header, because rule 5 ignores digits.
BODIES = [
    "The Borrower agrees to borrow",
    "Interest shall accrue monthly",
    "Penal charges apply on default",
    "This Agreement is governed by Indian law",
]


def test_removes_header_repeated_on_every_page():
    # AU personal loan: on all 24 pages
    header = "Stamp Ref No: IN-RJ09290509414932X"
    pages = [f"{header}\n{body}" for body in BODIES]
    assert clean_pages(pages) == BODIES


def test_removes_header_whose_page_number_changes():
    # AU home loan: "Version – May 2026      1", "...      2", ...
    pages = [f"Version – May 2026      {i}\n{body}" for i, body in enumerate(BODIES, 1)]
    assert clean_pages(pages) == BODIES


def test_keeps_line_that_repeats_on_few_pages():
    pages = [
        "LOAN AMOUNT\nThe Borrower agrees to borrow",
        "Some other clause",
        "Another clause",
        "Yet another clause",
    ]
    assert clean_pages(pages) == pages


def test_never_treats_clause_numbers_as_headers():
    # RBL: lone "1." / "2." lines appear on most pages, but they are clause numbers
    pages = [f"{i}.\n{body}" for i, body in enumerate(BODIES, 1)]
    assert clean_pages(pages) == pages


def test_header_rule_skipped_for_short_documents():
    pages = ["LOAN AGREEMENT\nPage one text", "LOAN AGREEMENT\nPage two text"]
    assert clean_pages(pages) == pages


# --- Output shape -------------------------------------------------------------

def test_returns_one_entry_per_page_even_if_page_becomes_empty():
    pages = ["Real text here", " \n.\n7\n", "More real text"]
    assert clean_pages(pages) == ["Real text here", "", "More real text"]


def test_empty_input():
    assert clean_pages([]) == []
