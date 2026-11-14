"""Generate small PDFs for manually testing the /upload endpoint.

Run from the project root:
    python scripts/make_test_pdfs.py

Creates files in tests/fixtures/:
    text.pdf        - 2 pages of normal text           -> expect 200, no warnings
    scanned.pdf     - 2 pages that are only images     -> expect 422
    mixed.pdf       - page 1 text, page 2 image        -> expect 200 + warning for page 2
    blank_page.pdf  - page 1 text, page 2 only spaces  -> expect 200 + warning for page 2
    not_a_pdf.pdf   - plain text renamed to .pdf       -> expect 400 (magic bytes)
    corrupted.pdf   - valid header, garbage body       -> expect 400 (FileDataError)
"""

from pathlib import Path

import pymupdf

OUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

CLAUSE_TEXT = (
    "1. DEFINITIONS\n"
    "1.1 \"Borrower\" means the person named in Schedule I.\n"
    "1.2 \"Loan\" means the principal amount of Rs. 5,00,000 sanctioned by the Lender.\n\n"
    "2. INTEREST\n"
    "2.1 The Loan shall carry interest at 11.5% per annum, payable monthly.\n"
    "2.2 Overdue amounts shall attract additional interest of 2% per month.\n"
)


def add_text_page(doc: pymupdf.Document, text: str) -> None:
    """Add a page whose text is real, selectable text (has a text layer)."""
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=11)


def add_image_page(doc: pymupdf.Document, text: str) -> None:
    """Add a page that *looks* like text but is only a picture (simulates a scan).

    We draw the text on a temporary page, take a screenshot of it (a pixmap),
    and paste that screenshot onto a new page. The new page has no text layer,
    so page.get_text() returns "".
    """
    tmp = pymupdf.open()
    add_text_page(tmp, text)
    pixmap = tmp[0].get_pixmap(dpi=150)
    tmp.close()

    page = doc.new_page()
    page.insert_image(page.rect, pixmap=pixmap)


def save(doc: pymupdf.Document, name: str) -> None:
    doc.save(OUT_DIR / name)
    doc.close()
    print(f"created {name}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open()
    add_text_page(doc, CLAUSE_TEXT)
    add_text_page(doc, CLAUSE_TEXT)
    save(doc, "text.pdf")

    doc = pymupdf.open()
    add_image_page(doc, CLAUSE_TEXT)
    add_image_page(doc, CLAUSE_TEXT)
    save(doc, "scanned.pdf")

    doc = pymupdf.open()
    add_text_page(doc, CLAUSE_TEXT)
    add_image_page(doc, CLAUSE_TEXT)
    save(doc, "mixed.pdf")

    doc = pymupdf.open()
    add_text_page(doc, CLAUSE_TEXT)
    add_text_page(doc, "   \n\n   \n")
    save(doc, "blank_page.pdf")

    (OUT_DIR / "not_a_pdf.pdf").write_text("This is just a text file with a .pdf name.")
    print("created not_a_pdf.pdf")

    (OUT_DIR / "corrupted.pdf").write_bytes(b"%PDF-1.7\n" + b"\x00garbage" * 50)
    print("created corrupted.pdf")


if __name__ == "__main__":
    main()
