"""Tests for app/splitting.py. Examples are taken from the real sample agreements.

Run from the project root:
    pytest -v
"""

from app.splitting import ARTICLE, DOTTED, PLAIN, UNKNOWN, detect_numbering_style

# --- detect_numbering_style ---------------------------------------------------

def test_detects_plain_style():
    # AU personal loan
    page = "\n".join([
        "1 Definitions and Interpretation",
        "1.1 Definitions",
        "1.2 Interpretation",
        "1.2.1 In this Agreement, singular shall include plural",
        "1.2.2 Any expression not defined herein",
        "5.1 Interest on the Loan shall accrue",
    ])
    assert detect_numbering_style([page]) == PLAIN


def test_detects_dotted_style():
    # AU home loan
    page = "\n".join([
        "1. DEFINITIONS AND INTERPRETATION",
        "1.1. In this Agreement, unless the context otherwise requires",
        "1.2. Unless a contrary indication appears",
        "3.1. The Bank shall, subject to the provisions",
        "3.2. The Bank may disburse the Loan",
        "4.1. Interest shall be payable monthly",
    ])
    assert detect_numbering_style([page]) == DOTTED


def test_detects_article_style():
    # RBL home loan: only a few ARTICLE lines, but lots of plain sub-clauses
    pages = [
        "ARTICLE 1\nDEFINTIONS AND INTERPRETATION\n1.1 Agreement\n1.2 Loan",
        "ARTICLE 2\nLOAN\n2.1 Amount of Loan\n2.2 Interest\n2.3 Computation of Interest",
        "ARTICLE 3\nCONDITIONS\n3.1 Conditions precedent\n3.2 Disbursement",
    ]
    assert detect_numbering_style(pages) == ARTICLE


def test_single_article_mention_is_not_enough():
    # One "ARTICLE" line (could be a cross-reference) must not override the rest
    page = "\n".join([
        "ARTICLE 7 of the Agreement shall apply",
        "5.1 Interest on the Loan shall accrue",
        "5.2 Interest shall be computed",
        "5.3 Interest tax shall be borne",
        "5.4 The Bank shall be entitled",
        "5.5 All amounts in default",
    ])
    assert detect_numbering_style([page]) == PLAIN


def test_counts_across_pages():
    pages = [
        "1.1. First clause",
        "1.2. Second clause\n2.1. Third clause",
        "2.2. Fourth clause",
        "3.1. Fifth clause",
    ]
    assert detect_numbering_style(pages) == DOTTED


def test_too_few_matches_is_unknown():
    page = "1.1 Only one\n1.2 Two\n1.3 Three"
    assert detect_numbering_style([page]) == UNKNOWN


def test_no_numbering_is_unknown():
    page = "This document has no numbered clauses at all.\nJust paragraphs."
    assert detect_numbering_style([page]) == UNKNOWN


def test_empty_document_is_unknown():
    assert detect_numbering_style([]) == UNKNOWN


def test_numbers_inside_a_line_do_not_count():
    page = "\n".join(
        f"The Loan carries interest at 1{i}.5 per cent as per clause {i}.1 above"
        for i in range(10)
    )
    assert detect_numbering_style([page]) == UNKNOWN


def test_decimal_amount_at_line_start_does_not_count():
    # A wrapped line can start with a rate like "11.5%" -- no space after the number
    page = "\n".join(["11.5% per annum, payable monthly"] * 10)
    assert detect_numbering_style([page]) == UNKNOWN


def test_majority_wins_when_both_styles_appear():
    # AU home has 40 dotted and a few plain lines (e.g. in schedules)
    dotted = [f"{i}.1. Clause text" for i in range(1, 9)]
    plain = [f"{i}.1 Table row" for i in range(1, 4)]
    assert detect_numbering_style(["\n".join(dotted + plain)]) == DOTTED


def test_tie_is_unknown():
    dotted = [f"{i}.1. Clause text" for i in range(1, 6)]
    plain = [f"{i}.2 Clause text" for i in range(1, 6)]
    assert detect_numbering_style(["\n".join(dotted + plain)]) == UNKNOWN
