"""Split cleaned agreement text into clauses.

Step 1 (this file, for now): detect which numbering style a document uses.
See notes/clause_patterns.md for the three styles found in the samples.
"""
import re

# Numbering styles
ARTICLE = "article"  # RBL:         "ARTICLE 2" then "2.1 Amount of Loan"
DOTTED = "dotted"    # AU home:     "2. LOAN AMOUNT", "3.1. The Bank shall"
PLAIN = "plain"      # AU personal: "2 Bank's agreement", "5.1 Interest", "1.2.1 In this"
UNKNOWN = "unknown"  # none of the above -> caller falls back to page-based chunks

# Fewer matching lines than this is not enough evidence to pick a style.
MIN_MATCHES = 5

ARTICLE_PATTERN = re.compile(r"ARTICLE\s+\d+\b")  # ARTICLE 2
DOTTED_PATTERN = re.compile(r"\d+\.\d+\.\s")      # "3.1 The Bank"
PLAIN_PATTERN = re.compile(r"\d+(\.\d+)+\s")      # "5.1 Interest", "1.2.1 In this"

def detect_numbering_style(pages: list[str]) -> str:
    """Return the numbering style of a document: ARTICLE, DOTTED, PLAIN or UNKNOWN.

    Args:
        pages: CLEANED page text (output of clean_pages), one string per page.

    Rules (check each LINE; a pattern only counts at the START of a line):
        1. ARTICLE lines look like "ARTICLE 2" (word ARTICLE, space(s), a number).
           If there are at least 2 of them -> ARTICLE.
           (Checked first: ARTICLE documents ALSO contain plain "2.1" sub-clauses.)
        2. Otherwise count two kinds of sub-clause lines:
             DOTTED: number.number. then a space    e.g. "3.1. The Bank shall"
             PLAIN:  number.number then a space     e.g. "5.1 Interest" or "1.2.1 In this"
                     (any depth, no trailing dot)
        3. Whichever count is larger wins, but only if it is at least MIN_MATCHES.
           Otherwise -> UNKNOWN. A tie -> UNKNOWN.

    Hint: re.match(pattern, line) only matches at the start of the line.
    """
    lines = [line for page in pages for line in page.splitlines()]

    article_count = sum(1 for line in lines if ARTICLE_PATTERN.match(line))
    if article_count >= 2:
        return ARTICLE

    dotted_count = sum(1 for line in lines if DOTTED_PATTERN.match(line))
    plain_count = sum(1 for line in lines if PLAIN_PATTERN.match(line))

    if max(dotted_count, plain_count) < MIN_MATCHES or dotted_count == plain_count:
        return UNKNOWN
     
    return DOTTED if dotted_count > plain_count else PLAIN