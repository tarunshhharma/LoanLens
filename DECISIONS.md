# Design Decisions

A log of the non-obvious choices in LoanLens and why they were made.
Format: what was decided, why, and what else was considered.

---

## Upload & parsing

### 1. `/upload` is a sync `def`, not `async def`

- **Decision:** The endpoint is a regular function.
- **Why:** PyMuPDF is blocking, CPU-bound code. FastAPI runs `def` endpoints in a thread pool, so one slow PDF doesn't block other requests. Calling blocking code inside `async def` would freeze the event loop for everyone.
- **Alternative:** `async def` + `run_in_threadpool`. Same effect, more code. At larger scale, move parsing to a background job queue (Celery/RQ) and return a job ID.

### 2. Detect PDFs by magic bytes, not `content_type`

- **Decision:** Check that the file starts with `%PDF-`.
- **Why:** `content_type` is set by the client and can be anything. The first bytes are the file's real signature. Uploads are untrusted input.

### 3. Validate size before parsing (20 MB limit, 413)

- **Why:** Cheap checks run before expensive ones. MuPDF is a C library, so huge or malformed input can exhaust memory or crash the parser. Size and type checks keep untrusted input away from it.

### 4. Status codes: 400 vs 413 vs 422

- **400 Bad Request:** the file is not a PDF, or it is corrupted.
- **413 Payload Too Large:** over the size limit.
- **422 Unprocessable Content:** a valid PDF with no usable text (e.g. fully scanned). The request is fine; the content can't be processed.

### 5. Text detection is per page, not per document

- **Decision:** Each page gets `has_text`. Reject (422) only if _every_ page is empty. If _some_ are, accept and return a warning listing those pages.
- **Why:** Real agreements are often mixed: typed body + scanned signature pages or schedules. A document-wide total would let a mostly-scanned PDF pass silently. Rejecting on any empty page would throw away good documents because of one blank signature page.
- **Alternative considered:** average characters per page. Rejected: a 50% scanned document still has a high average.

### 6. A page "has text" if it has >= 30 characters after `.strip()`

- **Why 30:** Scanned pages often still carry a stamped page number or footer ("Page 12 of 40"), roughly 10–15 characters. 30 is above that noise but below any real paragraph.
- **Why `.strip()`:** blank pages can contain only whitespace/newlines, which would otherwise count as characters.
- **Known limitation:** this checks _quantity_, not _quality_. Garbled text from broken font encodings (e.g. the SBI specimen agreement) passes the check. Not handled yet.

### 7. Page numbers are 1-based in the API

- **Why:** PyMuPDF counts from 0; users and citations count from 1. Converted once, at extraction, so everything downstream (chunks, citations) uses human page numbers.

## Cleaning

### 8. Removing repeated headers and footers

- **Decision:** A line is a header/footer if it appears on at least 50% of pages. Detected after whitespace cleanup.
- **Digits are ignored when comparing lines:** headers often contain the page number ("Version – May 2026 1", "... 2"). Replacing digits with `#` makes them the same line, so they get counted together.
- **The line must contain at least 3 letters:** in the RBL agreement, clause numbers like `1.` sit alone on a line on most pages. Without this check they would look like a header (`#.`) and be deleted, and the splitter would lose its clause numbers.
- **Skipped for documents under 3 pages:** with 2 pages, 50% means 1 page, and every line appears on at least 1 page, so the rule would delete the whole document.

## Splitting into chunks

### 9. Detect the numbering style before splitting

- **Decision:** Classify each document as ARTICLE (RBL: `ARTICLE 2`, `2.1`), DOTTED (AU home: `2.`, `3.1.`), PLAIN (AU personal: `2`, `5.1`, `1.2.1`) or UNKNOWN, then split with that style's patterns.
- **Why:** The survey of real agreements (`notes/clause_patterns.md`) showed every bank numbers clauses differently. No single regex covers all three.
- **ARTICLE is checked first and needs at least 2 lines:** RBL also has many plain `2.1` sub-clauses, so counts alone would call it PLAIN. One `ARTICLE` line could be a cross-reference.
- **DOTTED vs PLAIN needs at least 5 matches; a tie is UNKNOWN:** don't decide from one data point.
- **Patterns end in `\s`:** without it, `3.1. The Bank` also matches the plain pattern and AU home is misdetected.

### 10. A top-level clause must be a heading, in sequence

- **Decision:** A line starts a top-level clause only if it matches the style's pattern, its number is `last_top + 1` or `last_top + 2`, and it looks like a heading (at most 80 characters, not ending in `;` or `,`).
- **Why the heading rule:** in AU home, clause 7 contains a numbered list that restarts at 1. Its item `8. Borrower shall not...` passes the sequence check and would hijack clauses 8–12.
- **Why a full stop is allowed:** `4. INTEREST/ APR/ FEES/CHARGES/COSTS ETC.` is a real heading.
- **Why `+ 2`:** tolerates one missing number (e.g. a heading mangled by extraction) without losing the rest of the document.

### 11. A sub-clause must belong to the current clause

- **Decision:** `5.1` only starts a chunk while inside clause 5.
- **Why:** a wrapped cross-reference like "1.1 above shall apply" inside clause 3 would otherwise become clause 1.1.

### 12. Schedules and annexures end clause detection

- **Decision:** A short line (at most 60 characters) starting with `SCHEDULE`/`ANNEXURE`, or `Schedule`/`Annexure` followed by an identifier, starts a SECTION chunk. After the first one, no more clauses are detected.
- **Why:** schedules come after the clauses, and their numbered rows ("3 Date of Execution") are not agreement clauses. Lowercase continuations like "Schedule to this Agreement..." do not match, so they stay inside their clause.

### 13. Unknown formats fall back to one chunk per page

- **Decision:** If the style is UNKNOWN, return one PAGE chunk per non-empty page and add a warning to the response.
- **Why:** it works for any bank. Citations become "page 4" instead of "clause 5.2", but nothing breaks.

### 14. Definitions are their own chunks

- **Decision:** Inside clause 1 only, a line that starts a definition starts a DEFINITION chunk carrying its `term`. Two patterns: listed (`a. "Term"`, `1. "Term"`) and bare (`"Term" means` / `shall mean` within 40 characters on the same line).
- **Why:** "what does X mean?" questions need small, citable chunks. Before this, AU home's clause 1.1 was one 13,500-character block.
- **Only in clause 1:** all three samples define terms there; a quoted "means" elsewhere is ordinary text.
- **Checked after sub-clauses:** AU personal interleaves definitions with `1.1.1` and `1.1.2`; those stay sub-clauses.
- **`"Borrower" shall include ...` is not a definition:** it mentions a term without defining it, which is why the bare pattern requires `means`.

### 15. Hand-written splitter instead of a generic text splitter

- **Decision:** Structure-aware splitting written for this domain, not LangChain's `RecursiveCharacterTextSplitter`.
- **Why:** citations are the product. A size-based splitter produces chunks that cross clause boundaries and knows nothing about definitions or restarting lists.
- **Alternatives considered:** layout-aware parsers (`unstructured`, `pymupdf4llm`). A generic splitter is still a good fallback for clauses too long to embed.

---

## API

### 16. Response chunks are built by hand

- **Decision:** `/upload` returns explicit dictionaries (`kind`, `number`, `term`, `page_start`, `page_end`, `text`), not the `Chunk` objects.
- **Why:** the API shape is a deliberate choice, separate from the internal model. Clients get `text`, not the internal `lines` list, and changing `Chunk` later doesn't silently change the API.

---

## Repository & tooling

### 17. Bank sample agreements are not committed

- **Decision:** Real agreements live in `samples/` (gitignored). The README will list their source URLs.
- **Why:** They are the banks' documents, not ours. Only synthetic test PDFs, generated by `scripts/make_test_pdfs.py`, are committed.

### 18. Lint rules are pinned in `ruff.toml`

- **Decision:** `select = ["E4", "E7", "E9", "F", "I"]`: ruff's defaults plus import sorting.
- **Why:** a project config makes every machine and CI run the same rules. `F` catches undefined names, which would have caught a `chunk`/`chunks` typo that crashed `/upload` while all tests passed.
- **FLY002 not enabled:** it rewrites one-line-per-PDF-line test fixtures into single long strings, which hurts readability.

---

## Known limitations

| Limitation | Example | Possible fix |
|---|---|---|
| Scanned PDFs are rejected | All-image pages return 422 | OCR (Tesseract) |
| Garbled text passes the text check | Broken font encoding (SBI specimen) | Check text quality, not only length |
| Mixed numbering styles produce one preamble chunk | `1.` top-level with `1.1` sub-clauses (`tests/fixtures/text.pdf`) | Fall back to page chunks when no clauses are found |
| Some sub-clause forms are missed | `12. 1. Appointment...` (space inside the number, AU home) | Extend the sub-clause patterns |
| Very long clauses | AU home clause 7 is about 44,000 characters | Split oversized chunks before embedding, keeping the clause number |
| Wrapped definition terms are cut short | RBL `"Equated Monthly` / `Installments (EMIs)"` gets the label "Equated Monthly" | Join lines until the closing quote |
| Only three numbering styles | A new bank's format is UNKNOWN | Page fallback already works; add styles as they are found |
| `/upload` has no endpoint tests | Bugs in `main.py` aren't caught by pytest | `TestClient` tests (Day 5) |
