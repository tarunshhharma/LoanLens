"""Tests for definition handling in app/splitting.py.

Run from the project root:
    pytest -v
"""

from app.splitting import CLAUSE, DEFINITION, _match_definition, split_into_chunks


def _summary(chunks):
    return [(c.kind, c.number) for c in chunks]


def _definitions(chunks):
    return [c for c in chunks if c.kind == DEFINITION]


# --- _match_definition ------------------------------------------------------------

def test_lettered_definition_with_curly_quotes():
    # AU home loan
    assert _match_definition("a. “Agreement” means this Agreement read together") == "Agreement"


def test_uppercase_letter_is_accepted():
    # AU home loan has a stray capital: "J. “Guarantee” shall mean ..."
    assert _match_definition("J. “Guarantee” shall mean corporate/ personal guarantee") == "Guarantee"


def test_numbered_definition_with_means_on_next_line():
    # RBL: the term is alone on its line; "means" comes on the next line
    assert _match_definition("1. “Agreement”") == "Agreement"


def test_bare_definition_with_means():
    # AU personal loan
    assert _match_definition('"Loan" means the loans granted by the Bank') == "Loan"


def test_bare_definition_with_shall_mean():
    assert _match_definition("“Penal Charges” shall mean the charges applicable") == "Penal Charges"


def test_two_names_for_one_term_returns_the_first():
    line = '"EMI" or "Equated Monthly Installment" shall mean the amount payable every month'
    assert _match_definition(line) == "EMI"


def test_mentioning_a_term_is_not_defining_it():
    assert _match_definition('"Borrower" shall include his/her/their respective heirs') is None


def test_quote_in_the_middle_of_a_line_is_not_a_definition():
    assert _match_definition('and the term "Borrower" means the person named') is None


def test_ordinary_clause_line_is_not_a_definition():
    assert _match_definition("5.1 Interest on the Loan shall accrue") is None


def test_lone_number_is_not_a_definition():
    # RBL: "1." alone on a line, before the definitions start
    assert _match_definition("1.") is None


# --- split_into_chunks with definitions (AU personal loan style) ---------------

# Definitions are interleaved with numbered sub-clauses 1.1.1 and 1.1.2,
# exactly as on page 1 of the AU personal loan agreement.
PLAIN_DEFS_DOC = [
    "\n".join([
        "1 Definitions and Interpretation",
        "1.1 Definitions",
        "In this Agreement, the following words have these meanings:",
        '"Agreement" means this personal loan agreement.',
        '"Borrower" means one or more individuals',
        "1.1.1 In case the Borrower is more than one individual, all of them are",
        '"Borrower" shall include their heirs and assigns.',
        "1.1.2 In case the Borrower is a sole proprietary firm",
        '"Branch" means the branch of the Bank',
    ]),
    "\n".join([
        "where the Loan is disbursed.",
        "“Penal Charges” shall mean the charges in Schedule II",
        "1.2 Interpretation",
        "1.2.1 Singular includes plural",
        "2 Loan",
        "2.1 The Bank agrees to lend",
        "2.2 Repayment terms",
        '"Loan" means something else here, but we are outside clause 1',
    ]),
]


def test_definitions_become_their_own_chunks():
    assert _summary(split_into_chunks(PLAIN_DEFS_DOC)) == [
        (CLAUSE, "1"), (CLAUSE, "1.1"),
        (DEFINITION, None), (DEFINITION, None),
        (CLAUSE, "1.1.1"), (CLAUSE, "1.1.2"),
        (DEFINITION, None), (DEFINITION, None),
        (CLAUSE, "1.2"), (CLAUSE, "1.2.1"),
        (CLAUSE, "2"), (CLAUSE, "2.1"), (CLAUSE, "2.2"),
    ]


def test_definition_chunks_carry_their_term():
    terms = [c.term for c in _definitions(split_into_chunks(PLAIN_DEFS_DOC))]
    assert terms == ["Agreement", "Borrower", "Branch", "Penal Charges"]


def test_non_definition_chunks_have_no_term():
    chunks = split_into_chunks(PLAIN_DEFS_DOC)
    assert all(c.term is None for c in chunks if c.kind != DEFINITION)


def test_definition_spanning_two_pages():
    branch = next(c for c in split_into_chunks(PLAIN_DEFS_DOC) if c.term == "Branch")
    assert branch.lines == ['"Branch" means the branch of the Bank', "where the Loan is disbursed."]
    assert (branch.page_start, branch.page_end) == (1, 2)


def test_intro_line_stays_in_the_definitions_clause():
    clause_1_1 = next(c for c in split_into_chunks(PLAIN_DEFS_DOC) if c.number == "1.1")
    assert clause_1_1.lines == [
        "1.1 Definitions",
        "In this Agreement, the following words have these meanings:",
    ]


def test_term_mention_stays_in_its_sub_clause():
    clause = next(c for c in split_into_chunks(PLAIN_DEFS_DOC) if c.number == "1.1.1")
    assert clause.lines[-1] == '"Borrower" shall include their heirs and assigns.'


def test_definitions_outside_clause_1_are_ignored():
    clause_2_2 = next(c for c in split_into_chunks(PLAIN_DEFS_DOC) if c.number == "2.2")
    assert clause_2_2.lines[-1] == '"Loan" means something else here, but we are outside clause 1'


def test_definitions_keep_every_line():
    chunks = split_into_chunks(PLAIN_DEFS_DOC)
    total = sum(len(p.splitlines()) for p in PLAIN_DEFS_DOC)
    assert sum(len(c.lines) for c in chunks) == total


# --- split_into_chunks with definitions (RBL style) ------------------------------

ARTICLE_DEFS_DOC = ["\n".join([
    "ARTICLE 1",
    "DEFINTIONS AND INTERPRETATION",
    "1.",
    "In this Agreement unless the context otherwise requires;",
    "1. “Agreement”",
    "means this loan agreement",
    "2. “Availability Period”",
    "means the period stipulated in the Schedule",
    "ARTICLE 2",
    "LOAN",
    "2.1 Amount of Loan",
    "2.2 Interest",
])]


def test_rbl_numbered_definitions():
    chunks = split_into_chunks(ARTICLE_DEFS_DOC)
    assert _summary(chunks) == [
        (CLAUSE, "1"),
        (DEFINITION, None), (DEFINITION, None),
        (CLAUSE, "2"), (CLAUSE, "2.1"), (CLAUSE, "2.2"),
    ]
    agreement = _definitions(chunks)[0]
    assert agreement.term == "Agreement"
    assert agreement.lines == ["1. “Agreement”", "means this loan agreement"]
