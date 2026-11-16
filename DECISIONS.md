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

### 4. Status codes: 400 vs 413 vs 422 vs 404 vs 502

- **400 Bad Request:** the file is not a PDF, or it is corrupted.
- **413 Payload Too Large:** over the size limit.
- **422 Unprocessable Content:** a valid PDF with no usable text (e.g. fully scanned). The request is fine; the content can't be processed. FastAPI also returns 422 by itself when the `/ask` body fails validation (e.g. a question under 3 characters).
- **404 Not Found:** `/ask` or `/extract` with a `doc_id` that was never uploaded.
- **502 Bad Gateway:** OpenAI failed. The fault is in a service behind us, not in the client's request.

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

## Storage & embeddings (Day 2)

### 19. Oversized chunks are split into parts before embedding

- **Decision:** A chunk over 4,000 characters (about 1,000 tokens) is split into parts at line boundaries. Each part keeps its `kind`, `number`, `term` and section `title`, and gets `part = 1, 2, 3...`.
- **Why:** the embedding API rejects inputs over ~8,191 tokens, and AU home's Annexure B is ~71,000 characters. Even below the limit, one vector for 27 pages is too vague to retrieve and cites "pages 49-75".
- **Why 4,000 and not ~30,000:** smaller parts give sharper vectors and tighter page citations. The cost is less context per hit.
- **Each part gets its own pages:** the splitter now records the page of every line (`line_pages`), so part 4 of clause 7 cites pages 18-19, not 13-24.
- **The section title is stored, not read from the first line:** part 2 of a schedule starts mid-sentence. The first real run cited "The Bank may, in its sole discretion... (part 2)" until this was fixed.

### 20. OpenAI `text-embedding-3-small` for embeddings; all OpenAI calls in one file

- **Decision:** `app/llm.py` is the only module that imports `openai`. Other modules receive `embed` / `complete` as function arguments.
- **Why OpenAI:** one provider for embeddings and answers, no PyTorch install, good quality, cost of a few paise per agreement.
- **Alternative:** a local `sentence-transformers` model. Free, offline, and the agreement text never leaves the machine. Worth switching to if banks require on-premise processing.
- **Why one file (dependency injection):** tests pass a 3-line fake instead of the real function, so pytest needs no key, costs nothing, and never fails because of the network.
- **The client is created lazily** (`@lru_cache` on `_client()`), so importing the app never needs a key.

### 21. One Chroma collection, filtered by `doc_id`

- **Decision:** every document's chunks go into one persistent collection (`chroma_db/`, gitignored). Each chunk's metadata holds its `doc_id`, and every query filters on it.
- **Why:** a question about one agreement can never retrieve another agreement's clause. A collection per document would also work but multiplies collections.
- **Cosine distance:** compares direction, not length, so a short question and a long clause on the same topic still match.
- **`embedding_function=None`:** we supply the vectors, so Chroma must not download and run its own model.
- **Chunk IDs are `"{doc_id}:{index}"`:** IDs must be unique across the whole collection, not just one document.
- **`None` is left out of metadata:** Chroma rejects `None` values (`TypeError: Cannot convert Python object to MetadataValue`).

### 22. `doc_id` is a hash of the file; uploading again replaces

- **Decision:** `doc_id = sha256(file bytes)[:16]`. `add_document` deletes the document's existing chunks before adding.
- **Why the hash:** the same file always gets the same ID, and two different files named `agreement.pdf` never collide. 16 hex characters = 64 bits.
- **Why delete first:** tested on Chroma 1.5: `add` with an existing ID **silently keeps the old data**. After a change to the splitter, a re-upload would keep stale chunks, and leftover IDs from a longer old split would stay searchable.

### 23. One file per upload request

- **Decision:** `/upload` takes a single `UploadFile`, not a list.
- **Why:** a bad file fails its own request with a clear status code, with no partial-success response to design. The 20 MB limit stays per file. Clients can still send several requests in parallel; sync endpoints run in the thread pool.

---

## Retrieval & answering (Day 2)

### 24. Hybrid retrieval: BM25 + vector search

- **Decision:** each question runs both a BM25 keyword search (`rank_bm25`) and a vector search, 20 candidates each.
- **Why both:** vectors find meaning ("cost of paying late" -> Penal Charges). BM25 finds exact words that embeddings blur: "MCLR", "foreclosure", "clause 2.1".
- **The tokenizer keeps dotted numbers whole:** `\w+(?:\.\w+)*` makes "5.1" one token, so "clause 5.1" matches clause 5.1 and not every chunk containing a 5.
- **Zero-score chunks are dropped:** a chunk sharing no word with the question would otherwise still earn RRF points.
- **BM25 is rebuilt from Chroma on every question:** BM25 needs every chunk of the document to compute word rarity; `vector_search` only returns the top 20 by meaning. Rebuilding takes milliseconds for one agreement and can never go out of sync with the store.

### 25. Reciprocal Rank Fusion, written by hand

- **Decision:** score = sum of `1 / (60 + rank)` over the rankings a chunk appears in. The top 5 go to the model.
- **Why ranks, not scores:** BM25 scores (0 to 15+) and cosine distances (0 to 2) are on different scales and can't be added. Ranks always are.
- **Why k = 60:** it dampens the gap between ranks, so a chunk ranked 3rd in both lists (2/63 = 0.032) beats one ranked 1st in only one (1/61 = 0.016). Agreement between two methods is strong evidence. With k = 0, a single first place would dominate.
- **Vector ranking is passed first:** it only matters for exact ties, which go to the item seen first. For plain-English questions, meaning is usually the better signal.
- **Why by hand:** it is ten lines, fully tested, and explainable. A framework would hide it.

### 26. The model picks source numbers; citations come from our metadata

- **Decision:** the prompt lists sources as `[1] Clause 5.1, page 7` + text. The model replies with JSON `{"answer": ..., "sources": [1, 3]}`. Labels and page numbers in the response are built from stored metadata.
- **Why:** a model that writes "page 7" can hallucinate "page 9". A model that picks `[1]` can only pick a chunk we sent. A citation can be missing, but never invented.
- **Why numbers, not chunk IDs, in the prompt:** `[3]` is copied back reliably; a 19-character random ID can be mistyped and then can't be looked up.

### 27. Model output is validated like user input

- **Decision:** `parse_reply` keeps only integer source numbers between 1 and the number of sources, once each. Strings (`"1"`) and booleans (`true`, which Python treats as 1) are rejected. Invalid JSON, or JSON that isn't an object, means "not found".
- **An answer with no valid source is "not found":** every answer must be traceable to the agreement. Showing nothing is safer than an unverifiable figure in a legal document.
- **No retrieved chunks means no model call:** saves cost and removes the chance of an answer from the model's general knowledge.
- **`temperature=0` and JSON mode:** the same question gives the same answer, and the reply always parses. The model is `gpt-4.1-mini` by default (cheap, non-reasoning), overridable with `OPENAI_CHAT_MODEL` in `.env`.

---

## Extraction & risk flags (Day 3)

### 28. `LoanTerms`: every value carries its citation

- **Decision:** each field is a `Term[T]` (a generic Pydantic model of `value` + `citation`) or `None`. Ten fields: amount, rate, rate type, tenure, EMI, processing fee, whether a prepayment charge applies, prepayment charges, penal charges, whether the bank can change the rate.
- **Why a generic `Term[T]`:** every field has the same shape with a different value type. Pydantic refuses to build a `Term` without a citation, so "no value without a source" is enforced by the type, not by convention.
- **`None` means "not stated":** the sample agreements are templates with blank amounts. A missing value is a normal answer; a wrong value is a validation error. The two must never look the same.

### 29. The schema is strict on purpose

- **`extra="forbid"`:** an unknown key (`"loan_amout"`, `"confidence"`) is an error. Pydantic's default silently drops it, and a dropped amount would look exactly like "the agreement states no amount" (schema drift).
- **Sanity ranges, not business rules:** rate above 0 and at most 50% per annum, tenure 1-480 months, amounts above 0. A 0% or 60% home loan means the model misread something; rejecting it beats flagging a fake risk.
- **Numbers for what code compares, text for what people read:** amount, rate, tenure and EMI are numbers because risk rules compute on them. Fees and charges come in too many shapes (`1% + GST`, `Rs 0.65 per Rs 1,000 per day`, `Nil`), so they are short text shown with their citation. `prepayment_charge_applies` is a separate bool so a rule can test it without parsing text.
- **Plain numbers only:** the prompt asks for `500000`, and the schema rejects `"5,00,000"`. The prompt is a request; the schema is the guarantee. No hand-written parser for Indian number formats.

### 30. Extraction runs one search and one model call per field group

- **Decision:** three groups (amount/rate/tenure/EMI, charges, rate changes), each with its own search query and the top 8 chunks.
- **Why groups:** related terms sit in the same part of an agreement (the schedule, the schedule of charges). 3 calls instead of 10, and each prompt carries only chunks relevant to its fields. One call for everything would need far more chunks in one prompt.
- **Why 8 chunks, not 5:** one call must cover several fields.
- **Same citation rule as `/ask`:** the model returns `{"value", "source"}` per field; the citation is built from chunk metadata.
- **`extract_terms` receives a `search` function:** it never sees Chroma or the `doc_id`. Tests pass `lambda q: CHUNKS`; a future reranker changes `main.py`, not `extract.py`.

### 31. Two validation passes, one field at a time

- **Pass 1, provenance (`parse_extraction`):** valid JSON object, a real integer source number. Same checks as decision 27.
- **Pass 2, content (`validate_terms`):** each field is validated against `LoanTerms` on its own.
- **Why one field at a time:** a misread rate drops the rate, not all ten terms. The warning names the field and shows exactly what the model sent (`got 60`).
- **`null`, and `{"value": null, "source": 3}`, mean "not stated", not a warning:** found on AU home's blank template, which produced five noise warnings before the fix. Warnings must mean something went wrong, or users learn to ignore them.

### 32. Risk flags come from plain-Python rules, not the LLM

- **Decision:** five rules, each a function `LoanTerms -> RiskFlag | None`, listed in `RULES`. Adding a rule is one function and one line.
- **Why not ask the model for risks:** the same agreement must get the same flags every run; each rule is unit-tested; every flag is explainable ("19.25 > 18"); and a rule can only fire on terms that were extracted with citations. The LLM reads; the code judges.
- **Missing data never raises a flag:** rules check `is not True` / `is None` first. `not x` would treat "unknown" as "no".
- **Every flag carries the citations of the terms that triggered it,** de-duplicated, so the user can check the clause.

### 33. The individual rules

| Rule | Severity | Fires when |
|---|---|---|
| `floating_rate_prepayment_charge` | high | floating rate + a prepayment charge applies |
| `bank_can_change_rate` | high if the rate is called fixed, else medium | the bank may change the rate |
| `high_interest_rate` | medium | rate above `HIGH_RATE_PERCENT` (18%) |
| `emi_mismatch` | medium | stated EMI differs from the reducing-balance formula by more than 5% |
| `prepayment_charge` | low | a prepayment charge applies and the rate isn't floating |

- **18% is a product choice, not a law:** a named constant, and the right value differs by loan type.
- **EMI formula:** `P * r * (1+r)^n / ((1+r)^n - 1)`, `r` = monthly rate. Rs 5 lakh at 10.5% for 240 months = Rs 4,991.9. A mismatch means a misread term or something else inside the EMI.
- **The RBI rule says "check whether this applies":** the tool flags for a human to verify; it does not give legal advice.
- **A "fixed" rate the bank can change is high:** the borrower chose fixed for certainty and the contract contradicts its own label. Found for real in AU personal (Schedule A vs clause 7.2).

### 34. `/extract` checks the document exists first

- **Decision:** an explicit existence check (`collection.get(..., limit=1, include=[])`) returns 404 before any model call.
- **Why:** without it, every search returns nothing and the response is a 200 with all fields `None`, as if the agreement stated no terms. A silent wrong answer.
- **Response:** `found` (field names), `terms` (plain dicts via `model_dump`), `risk_flags` (most severe first), `warnings`.

---

## UI (Day 3)

### 35. Streamlit as a thin client over the API

- **Decision:** `ui/app.py` only talks HTTP to `/upload`, `/ask` and `/extract`. It never imports `app.*`.
- **Why:** the API stays the product. The UI could be replaced (React) without touching `app/`, and the two can run as separate containers.
- **`st.session_state`:** Streamlit reruns the whole script on every click, so the document, answer history and extraction live in session state.
- **An explicit "Upload and index" button:** otherwise every rerun would upload and re-embed the PDF still held by the file picker.
- **Every failure is shown on the page:** API not running, timeout, 404, 422, 502. `TIMEOUT = 180` because httpx's 5-second default is shorter than embedding a 75-page agreement.
- **Formatting lives in `ui/display.py`** (Indian digit grouping `1,23,45,678`, tenure in years, Yes/No) so it can be unit-tested; Streamlit pages themselves are hard to test.
- **Run with `python -m streamlit run ui/app.py`:** `python -m` puts the project folder on the import path, so `from ui.display import ...` works.

### 36. Endpoint tests call the function directly, with `monkeypatch`

- **Decision:** `/extract` tests call `main.extract(...)` and use `monkeypatch.setattr(main, ...)` to swap in a fake model, a fake embedder and a Chroma in a temp folder.
- **Why:** `TestClient` needs `httpx2`, not installed yet. This still covers the endpoint's logic (404, 502, response shape, risk flags) and never touches the real `chroma_db/`.
- **Why it works:** `extract()` looks up `complete_json` and `embed_texts` in `main`'s globals when it runs, so replacing them in `main` changes what it calls.

---

## Known limitations

| Limitation | Example | Possible fix |
|---|---|---|
| Scanned PDFs are rejected | All-image pages return 422 | OCR (Tesseract) |
| Garbled text passes the text check | Broken font encoding (SBI specimen) | Check text quality, not only length |
| Mixed numbering styles produce one preamble chunk | `1.` top-level with `1.1` sub-clauses (`tests/fixtures/text.pdf`) | Fall back to page chunks when no clauses are found |
| Some sub-clause forms are missed | `12. 1. Appointment...` (space inside the number, AU home) | Extend the sub-clause patterns |
| Parts of a split clause lose their heading | Part 3 of AU home clause 7 doesn't contain the words of clause 7's heading | Prefix each part's embedded text with its clause number and heading |
| Wrapped definition terms are cut short | RBL `"Equated Monthly` / `Installments (EMIs)"` gets the label "Equated Monthly" | Join lines until the closing quote |
| Only three numbering styles | A new bank's format is UNKNOWN | Page fallback already works; add styles as they are found |
| Retrieval quality is not measured | The prepayment answer cited only the 3-day cooling-off clause; foreclosure charges may have been missed | Hand-written question → expected-clause cases (planned) |
| No reranker | The top 5 come straight from RRF | Cross-encoder reranker (planned extra) |
| BM25 is rebuilt on every question | Fine for one agreement; slow for very large documents or many concurrent users | Cache the index per `doc_id` |
| Agreement text is sent to OpenAI | Not acceptable for banks requiring on-premise processing | Local embedding and chat models |
| Chroma runs inside the API process | Several uvicorn workers would each open the same files | Run Chroma as a separate server |
| `/upload` and `/ask` have no endpoint tests | Bugs in `main.py` aren't caught by pytest (`/extract` has them, via `monkeypatch`) | `TestClient` tests (Day 5; needs `httpx2`) |
| The model sometimes cites a source that doesn't exist | AU home `penal_charges` was found in one run and dropped ("cited no valid source") in the next | Retry once with the validation error in the prompt (planned "go deeper") |
| Extraction varies between runs | Same agreement, different fields found, even at `temperature=0` | Retry on failure; measure with an eval set (Day 4) |
| Only ten terms, five rules | No insurance, collateral or guarantor terms; no cross-default rule | Add fields and rules as needed; each rule is one function |
| Risk thresholds are not per loan type | 18% is high for a home loan, normal for some personal loans | Thresholds per loan type |
| The UI's upload button isn't tested automatically | Streamlit's `AppTest` can't drive the file picker | Manual check; Playwright browser tests if needed |
| Chunks stored before a splitter change keep old metadata | AU home citations said "Section (part 1)" until re-uploaded | Re-upload, or store a pipeline version and re-index on change |
