"""Clean raw page text before splitting it into clauses.

Removes layout noise found in real agreements (see notes/clause_patterns.md):
extra spaces, blank lines, stray "." lines, page numbers, and headers or
footers that repeat on most pages.
"""

import re
import collections

# A line that appears on at least this fraction of pages is treated as a header/footer.
HEADER_PAGE_RATIO = 0.5

def _normalize(line: str) -> str:
    """Replace every run of digits with '#', so 'Page 1' and 'Page 2' look the same."""
    return re.sub(r"\d+", "#", line)

def _find_headers(pages_lines: list[list[str]]) -> set[str]:
    """Return the normalized lines that repeat on enough pages to be headers/footers."""
    page_counts = collections.Counter()

    for lines in pages_lines:
        unique_on_this_page = {_normalize(line) for line in lines}
        page_counts.update(unique_on_this_page)

    min_pages = HEADER_PAGE_RATIO * len(pages_lines)
    return {
        line
        for line, count in page_counts.items()
        if count >= min_pages and len(re.findall(r"[A-Za-z]", line)) >= 3
    }


def clean_pages(pages: list[str]) -> list[str]:
    """Clean the text of each page.

    Args:
        pages: raw text of each page, in order (pages[0] is page 1).

    Returns:
        A list of the SAME length: the cleaned text of each page, lines joined
        with "\\n". A page that ends up empty becomes "" (never removed), so that
        index i still means page i + 1.

    Rules, applied to every line:
        1. Collapse runs of spaces/tabs into one space, and strip the line.
        2. Drop empty lines.
        3. Drop lines that are only "." (layout leftover after headings).
        4. Drop lines that are only digits, e.g. "12" (page numbers).
           KEEP "1." -- in the RBL agreement that is a real clause number.
        5. Drop repeated headers/footers: a line that appears on at least
           HEADER_PAGE_RATIO of the pages, when digits are ignored
           (so "Version - May 2026 1" and "Version - May 2026 2" count as the
           same line). Only lines containing at least 3 letters qualify, so
           number-only lines like "1." are never treated as headers.
           Skip this rule for documents with fewer than 3 pages.
    """

    cleaned = []

    for page in pages:
        lines = page.splitlines()

        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
        
        lines = [line for line in lines if line]

        lines = [line for line in lines if line != "."]

        lines = [line for line in lines if not line.isdigit() ]

        cleaned.append(lines)
    
    if len(cleaned) >= 3:
        headers = _find_headers(cleaned)

        cleaned = [
            [line for line in lines if _normalize(line) not in headers]
            for lines in cleaned
        ]
        
    return ["\n".join(lines) for lines in cleaned]
