# Clause Patterns

Patterns observed in the sample agreements in `samples/`, used to design the clause splitter.

**Files:** AU home loan (`au-bank-home-loan-agreementpdf.pdf`, 75 pages), AU personal loan (`au-bank-personal-loan-agreement.pdf`, 24 pages), RBL home loan (`rbl-bank-Home Loan Agreement.pdf`, 23 pages)

**Level:** top = main clause, sub = sub-clause, sub-sub = deeper nesting, item = lettered/roman list inside a clause, definition = one defined term, section = document part (recitals, schedule, annexure)

**Key finding:** each bank uses a different numbering style. No single regex covers all three. The splitter needs a set of patterns, and has to pick the right one per document.

## Clause starts

| Pattern | Example from the PDF | File | Page | Level |
|---|---|---|---|---|
| `N.` + CAPS heading | `1. DEFINITIONS AND INTERPRETATION` | AU home | 1 | top |
| `N.N.` (trailing dot) | `3.1. The Bank shall, subject to the provisions of this Agreement...` | AU home | 5 | sub |
| `N` + space (no dot) + heading | `2 Bank's agreement to lend and Borrower's agreement to borrow` | AU personal | 3 | top |
| `N.N` (no trailing dot) | `5.1 Interest on the Loan shall accrue from the date...` | AU personal | 4 | sub |
| `N.N.N` | `1.2.1 In this Agreement, singular shall include plural...` | AU personal | 2 | sub-sub |
| `N.N.N.N` | `1.2.8.1 all statutory instruments or orders including...` | AU personal | 2 | sub-sub-sub |
| `ARTICLE N` + heading on next line | `ARTICLE 2` / `LOAN` | RBL home | 4 | top |
| `N.N` + several spaces + heading | `2.1    Amount of Loan` | RBL home | 4 | sub |
| `(a)` | `(a) The Borrower meets the Bank's requirement of creditworthiness.` | RBL home | 5 | item |
| `a)` | `a) the Borrower has capacity and authority to enter into this Agreement...` | AU home | 15 | item |
| `(i)` roman | `(i) There is no suit pending in the Municipal Magistrate's Court...` | RBL home | 7 | item |
| `i.` roman | `iii. In default of regular payment of interest on the due dates...` | RBL home | 4 | item |
| `"Term" means` (unnumbered) | `"Agreement" means this personal loan agreement.` | AU personal | 1 | definition |
| `x. "Term" means` (lettered) | `a. "Agreement" means this Agreement read together with all the Schedules...` | AU home | 1 | definition |
| `N. "Term"` then `means` on the next line | `1. "Agreement"` / `means this loan agreement` | RBL home | 3 | definition |

## Before clause 1 (parties, recitals, preamble)

| What it is | Example from the PDF | File | Page |
|---|---|---|---|
| Title | `HOME LOAN AGREEMENT` / `AGREEMENT FOR PERSONAL LOAN` | AU home / AU personal | 1 |
| Demand promissory note (separate document before the agreement) | `DEMAND PROMISSORY NOTE` | RBL home | 2 |
| Recitals | `WHEREAS, the Borrower and the Guarantor has/have approached the Bank...` | AU home | 1 |
| Recitals | `WHEREAS:` | RBL home | 3 |
| End of preamble marker | `NOW, THESE PRESENTS WITNESSETH AND IT IS HEREBY AGREED BY AND BETWEEN THE PARTIES HERETO AS FOLLOWS:` | AU home | 1 |
| End of preamble marker | `IT IS AGREED BY AND BETWEEN THE PARTIES AS FOLLOWS` | AU personal | 1 |
| End of preamble marker | `NOW THIS AGREEMENT WITNESSETH AS UNDER:` | RBL home | 3 |

## After the clauses (schedules, annexures, signatures)

| What it is | Example from the PDF | File | Page |
|---|---|---|---|
| Schedule | `Schedule A` | AU home | 35 |
| Schedule | `SCHEDULE-1` | AU home | 37 |
| Key Facts Statement (RBI-mandated summary) | `KEY FACTS STATEMENT` | AU home | 45 |
| Annexure | `ANNEXURE- A` / `Annexure B` | AU home | 46 / 49 |
| Attached letter | `LETTER OF GENERAL LIEN AND SET OFF` | AU home, AU personal | 49 / 20 |
| Attached letter | `LETTER OF DEBIT AUTHORISATION` | AU home | 64 |
| Schedule | `Schedule A` | AU personal | 15 |
| Annexure | `Annexure- 1` / `Annexure- 2` | AU personal | 20 / 22 |
| Signature block | `SIGNED AND DELIVERED` | RBL home | 16 |
| Schedule | `SCHEDULE-I: LIST OF TITLE DEEDS` | RBL home | 17 |
| Schedule | `SCHEDULE II` | RBL home | 22 |

## False positives (looks like a clause start, but isn't)

| Text | Why it's not a clause | File | Page |
|---|---|---|---|
| `...shall all times be governed by Clause 4 of this Agreement` | Cross-reference in the middle of a sentence, not at line start | AU personal | 3 |
| `1872 or any other applicable law, the Bank may...` | Wrapped line that starts with a year (Indian Contract Act, 1872) | AU home | 10 |
| `12 months from last disbursement date` | Table cell starting with a number | AU home | 43 |
| `14 SARFAESI Act` | Table cell / footnote starting with a number | AU home | 42 |
| `1. Charges are as applicable for the respective Personal Loan...` | Numbered note inside the Schedule of Charges, not an agreement clause | AU personal | 14 |
| `10 Date of commencement of EMI` | Row number in the schedule's table | RBL home | 15 |
| `1. "Agreement"` | Numbered definition; restarts at 1 inside Article 1, collides with clause numbering | RBL home | 3 |
| `i. "Conversion Charges" means...` | Letter **i** in an a, b, c... list, not roman numeral one (also `v.`, `x.`) | AU home | 2-3 |
| A line that is just a number, e.g. `12` | Page number | All | most pages |
| `.` on its own line | Layout leftover after every top-level heading | AU personal | 1, 3, 4... |
| `Stamp Ref No: IN-RJ09290509414932X` | Header repeated on all 24 pages | AU personal | all |
| `Version – May 2026` | Header repeated on all 75 pages | AU home | all |

## Other observations

- **Numbering style is per bank.** AU home uses `1.` / `1.1.`, AU personal uses `1` / `1.1` / `1.1.1`, RBL uses `ARTICLE 1` / `2.1`. Detect the style first, then split.
- **Definitions are mixed with numbered sub-clauses** (AU personal, p1): `"Borrower" means...` is followed by `1.1.1` and `1.1.2` (which explain "Borrower"), then unnumbered definitions resume (`"Branch" means...`). Splitting on numbers alone would glue every definition after `1.1.2` onto clause 1.1.2.
- **Definition terms can wrap across lines** (RBL, p3): `5. "Marginal Cost of Funds` / `based Lending Rate` / `(MCLR)"` / `means...`. Joining lines before matching is required.
- **Letter vs roman ambiguity:** `i.`, `v.`, `x.` can be letters (AU home definitions a–z) or roman numerals (RBL `iii.`). Decide by context: what came before? (`h.` -> `i.` is a letter; `ii.` -> `iii.` is roman.)
- **Inconsistent case:** `J. "Guarantee"` in an otherwise lowercase list (AU home, p2). Matching should be case-insensitive for list letters.
- **Typos in headings:** `DEFINTIONS AND INTERPRETATION` (RBL, p3). Don't match on exact heading words.
- **Irregular spacing:** RBL has runs of spaces (`2.1    Amount of Loan`, `means    the    rate`). Normalize whitespace before matching.
- **Half the document isn't clauses.** AU home: clauses end around p35 of 75. The rest is schedules, KFS, annexures, letters. These need their own handling (or separate chunking) rather than being glued onto the last clause.
- **Cross-page clauses.** Clauses run across page breaks, with headers/page numbers in the middle. Strip repeating headers and page numbers first, and track the start page of each clause.
- **Curly quotes and dashes:** definitions use both `"Term"` and `“Term”`, and dashes like `–`. Patterns must accept both quote styles. (On Windows, print with `python -X utf8` or these show as `�` in the terminal. That's a console display issue, not the PDF.)
