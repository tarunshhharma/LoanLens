"""Split cleaned agreement text into clauses.

Step 1 (this file, for now): detect which numbering style a document uses.
See notes/clause_patterns.md for the three styles found in the samples.
"""
import re
from dataclasses import dataclass, field

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

# =============================================================================
# Step 3: split a document into chunks (preamble, clauses, sections)
# =============================================================================

# Chunk kinds
PREAMBLE = "preamble"  # everything before the first clause (title, parties, WHEREAS)
CLAUSE = "clause"      # a numbered clause or sub-clause, e.g. "5" or "5.1"
SECTION = "section"    # a schedule or annexure at the end of the agreement
PAGE = "page"          # fallback for UNKNOWN style: one chunk per page
DEFINITION = "definition"  # one defined term inside clause 1, e.g. "Penal Charges"

# Top-level clause starts, per style. group(1) is the clause number.
TOP_PATTERNS = {
    PLAIN: re.compile(r"(\d+)\s+[A-Z]"),         # "2 Bank's agreement to lend"
    DOTTED: re.compile(r"(\d+)\.\s+[A-Z]"),      # "2. LOAN AMOUNT"
    ARTICLE: re.compile(r"ARTICLE\s+(\d+)\b"),   # "ARTICLE 2"
}

# Sub-clause starts, per style. group(1) is the full number, e.g. "5.1" or "1.2.8".
SUB_PATTERNS = {
    PLAIN: re.compile(r"(\d+(?:\.\d+)+)\s"),     # "5.1 Interest"
    DOTTED: re.compile(r"(\d+(?:\.\d+)+)\.\s"),  # "3.1. The Bank"
    ARTICLE: re.compile(r"(\d+(?:\.\d+)+)\s"),   # "2.1 Amount of Loan"
}

# Schedules and annexures: "SCHEDULE-1", "Schedule A", "ANNEXURE- A", "Annexure B".
# Lowercase-word continuations like "Schedule to this Agreement..." must NOT match.
SECTION_PATTERN = re.compile(r"(SCHEDULE|ANNEXURE)\b|(Schedule|Annexure)[\s-]+[A-Z0-9]+\b")

MAX_SECTION_LEN = 60   # section titles are short lines
MAX_HEADING_LEN = 80   # top-level clause headings are short lines

# Definitions. Quotes may be straight (") or curly (“ ”). group(1) is the term.
# Listed: a letter or number, a dot, then a quoted term. "means" may be on the next line.
#   'a. “Agreement” means ...' (AU home)    '1. “Agreement”' (RBL)
LISTED_DEFINITION_PATTERN = re.compile(r'(?:[A-Za-z]|\d{1,2})\.\s+["“]([^"”]+)')
# Bare: a quoted term, then "means" / "shall mean" within 40 characters on the SAME line.
#   '"Loan" means ...'    '"EMI" or "Equated Monthly Installment" shall mean ...' (AU personal)
# Does NOT match '"Borrower" shall include ...' -- that mentions a term, it doesn't define it.
BARE_DEFINITION_PATTERN = re.compile(r'["“]([^"”]+)["”][^.]{0,40}?\b(?:means|shall mean)\b')


@dataclass
class Chunk:
    kind: str                 # PREAMBLE, CLAUSE, SECTION, PAGE or DEFINITION
    number: str | None        # clause number like "5.1"; None for other kinds
    page_start: int           # 1-based page where the chunk starts
    page_end: int             # 1-based page where the chunk ends
    lines: list[str] = field(default_factory=list)
    term: str | None = None   # the defined term, only for DEFINITION chunks

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _is_heading(line: str) -> bool:
    """True if a line looks like a heading rather than a sentence.

    A heading is at most MAX_HEADING_LEN characters long and does NOT end with
    ";" or ",". (It MAY end with "." -- e.g. "4. INTEREST/ APR/ FEES/CHARGES/COSTS ETC.")
    """
    return len(line) <= MAX_HEADING_LEN and not line.endswith((";", ","))


def _match_definition(line: str) -> str | None:
    """Return the defined term if the line starts a definition, else None.

    Try LISTED_DEFINITION_PATTERN first, then BARE_DEFINITION_PATTERN.
    Return the term (group 1) with surrounding whitespace stripped.
        'a. “Agreement” means this Agreement'   -> "Agreement"
        '"Loan Account" shall mean the account' -> "Loan Account"
        '"Borrower" shall include his heirs'    -> None
    """
    m = LISTED_DEFINITION_PATTERN.match(line)

    if m:
        return m.group(1).strip()
    
    m = BARE_DEFINITION_PATTERN.match(line)

    if m:
        return m.group(1).strip()

    return None

def split_into_chunks(pages: list[str]) -> list[Chunk]:
    """Split a cleaned document into preamble, clause and section chunks.

    Args:
        pages: CLEANED page text (output of clean_pages), one string per page.

    Returns:
        Chunks in document order. Every line ends up in exactly one chunk.

    Rules:
        0. style = detect_numbering_style(pages).
           If UNKNOWN: return one PAGE chunk per NON-EMPTY page, and stop.

        Go through every line of every page, keeping track of the page number
        (1-based) and `last_top`, the number of the last top-level clause (starts at 0).
        For each line, check in this order:

        1. SECTION start: line is at most MAX_SECTION_LEN long and matches
           SECTION_PATTERN -> start a new SECTION chunk.
           From then on, never start a CLAUSE again (schedules come after the clauses;
           their numbered lists are not agreement clauses).
        2. TOP-LEVEL clause: TOP_PATTERNS[style] matches, AND its number is
           last_top + 1 or last_top + 2 (allows one skipped number), AND _is_heading(line)
           -> start a new CLAUSE chunk with that number; update last_top.
        3. SUB-clause: SUB_PATTERNS[style] matches, AND the first part of its number
           equals last_top ("5.1" only counts while inside clause 5)
           -> start a new CLAUSE chunk with that number.
        3b. DEFINITION: only while inside top-level clause 1 (last_top == 1; all three
           sample agreements put their definitions there), if _match_definition(line)
           returns a term -> start a new DEFINITION chunk: number None, term set.
           Checked AFTER rule 3, so "1.1.1 In case..." is still a sub-clause.
        4. Otherwise the line continues the current chunk: append it and update the
           chunk's page_end. If there is no current chunk yet, start a PREAMBLE chunk.

        A new chunk's first line is the line that started it.
    """
    style = detect_numbering_style(pages)
    if style == UNKNOWN:
        return [
            Chunk(PAGE, None, page_number, page_number, page.splitlines())
            for page_number, page in enumerate(pages, start=1)
            if page
        ]
    
    chunks = []
    current = None
    last_top = 0
    in_sections = False

    for page_number, page in enumerate(pages, start=1):
        for line in page.splitlines():
            new_chunk = None

            # Rule 1: schedule / annexure
            if len(line) <= MAX_SECTION_LEN and SECTION_PATTERN.match(line):
                in_sections = True
                new_chunk = Chunk(SECTION, None, page_number, page_number, [line])
            
            elif not in_sections:
                # Rule 2: top-level clause ("5 Interest", "5. INTEREST", "ARTICLE 5")
                top = TOP_PATTERNS[style].match(line)
                if top and last_top + 1 <= int(top.group(1)) <= last_top + 2 and _is_heading(line):
                    last_top = int(top.group(1))
                    new_chunk = Chunk(CLAUSE, top.group(1), page_number, page_number, [line])
                
                # Rule 3: sub-clause ("5.1"), only inside the current top-level clause
                else:
                    sub = SUB_PATTERNS[style].match(line)
                    if sub and sub.group(1).split(".")[0] == str(last_top):
                        new_chunk = Chunk(CLAUSE, sub.group(1), page_number, page_number, [line])
                    
                    # Rule 3b: definition, only inside clause 1
                    elif last_top == 1 and (term:= _match_definition(line)):
                        new_chunk = Chunk(DEFINITION, None, page_number, page_number, [line], term=term)

            if new_chunk:
                chunks.append(new_chunk)
                current = new_chunk
                continue
            
            # Rule 4: the line continues the current chunk
            if current is None:
                current = Chunk(PREAMBLE, None, page_number, page_number, [])
                chunks.append(current)
            current.lines.append(line)
            current.page_end = page_number

    return chunks