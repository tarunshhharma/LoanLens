"""Evaluate LoanLens on the 40-question golden set (evals/golden.jsonl).

Each sample agreement is uploaded once through main.upload_pdf into a temporary Chroma.
Each question then runs through the same retrieval and answering code as /ask, and is
scored on four things:
  retrieval hit   - did a retrieved chunk come from the expected pages?
  citation hit    - did the answer cite the expected pages?
  answer correct  - found, and every expected fact appears in the answer
  not-found       - for questions the agreement can't answer: did it say "not found"?

From the project root (needs samples/ and OPENAI_API_KEY):
    python -m scripts.run_evals
    python -m scripts.run_evals --out evals/results/baseline.json   # also save the run
"""
import io
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

import app.main as main
from app.answer import answer_question
from app.llm import DEFAULT_CHAT_MODEL, EMBEDDING_MODEL
from app.retrieval import hybrid_search
from app.store import get_collection

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_FILE = ROOT / "evals" / "golden.jsonl"
DOCS = {
  "au_personal": ROOT / "samples" / "au-bank-personal-loan-agreement.pdf",
  "au_home": ROOT / "samples" / "au-bank-home-loan-agreementpdf.pdf",
  "rbl_home": ROOT / "samples" / "rbl-bank-Home Loan Agreement.pdf",
}


def load_golden() -> list[dict]:
  lines = GOLDEN_FILE.read_text(encoding="utf-8").splitlines()
  return [json.loads(line) for line in lines if line.strip()]


# --- Scoring (pure functions: tested without a model) ---------------------------

def overlaps(span: dict, expected: list[int]) -> bool:
  """True if a chunk or citation's page range overlaps the expected [start, end]."""
  start, end = expected
  return span["page_start"] <= end and span["page_end"] >= start

def in_expected_pages(span: dict, ranges: list[list[int]]) -> bool:
  """A fact can be stated in more than one place (a clause and the KFS): any range counts."""
  return any(overlaps(span, expected) for expected in ranges)


def includes_all(answer: str, expected: list) -> bool:
  """Every expected item must appear. An item that is a list means 'any one of these'."""
  answer = answer.lower()
  for item in expected:
    alternatives = [item] if isinstance(item, str) else item
    if not any(alternative.lower() in answer for alternative in alternatives):
      return False
  return True

def score_item(item: dict, retrieved: list[dict], result: dict) -> dict:
  score = {"id": item["id"], "type": item["type"], "found": item["found"]}
  if not item["found"]:
    # nothing to retrieve or cite: only "did it say not found?" counts
    return {**score, "retrieval_hit": None, "citation_hit": None, "correct": not result["found"]}
  return {
    **score,
    "retrieval_hit": any(in_expected_pages(chunk["metadata"], item["pages"]) for chunk in retrieved),
    "citation_hit": any(in_expected_pages(c, item["pages"]) for c in result["citations"]),
    "correct": result["found"] and includes_all(result["answer"], item["answer_includes"]),
  }


def _rate(values: list[bool]) -> float | None:
  return round(sum(values) / len(values), 3) if values else None


def summarize(scores: list[dict]) -> dict:
  found = [s for s in scores if s["found"]]
  not_found = [s for s in scores if not s["found"]]
  by_type = defaultdict(list)
  for s in scores:
    by_type[s["type"]].append(s["correct"])
  return {
    "retrieval_hit_rate": _rate([s["retrieval_hit"] for s in found]),
    "citation_accuracy": _rate([s["citation_hit"] for s in found]),
    "answer_accuracy": _rate([s["correct"] for s in found]),
    "not_found_accuracy": _rate([s["correct"] for s in not_found]),
    "overall_accuracy": _rate([s["correct"] for s in scores]),
    "by_type": {kind: _rate(values) for kind, values in by_type.items()},
  }


# --- Running against the real pipeline -------------------------------------------

def run(items: list[dict]) -> list[dict]:
  """Upload each needed agreement once, then answer and score every question."""
  scores = []
  with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    collection = get_collection(folder)
    original = main.collection
    main.collection = lambda: collection  # upload into the temporary store, not chroma_db/
    try:
      doc_ids = {}
      for doc in sorted({item["doc"] for item in items}):
        pdf = DOCS[doc].read_bytes()
        doc_ids[doc] = main.upload_pdf(UploadFile(file=io.BytesIO(pdf), filename=DOCS[doc].name))["doc_id"]

      for item in items:
        # exactly what /ask does: hybrid search, then answer from those chunks
        retrieved = hybrid_search(collection, doc_ids[item["doc"]], item["question"],
                                  main.embed_texts, main.TOP_K)
        result = answer_question(item["question"], retrieved, main.complete_json)
        scores.append(score_item(item, retrieved, result))
        print(_row(scores[-1]), flush=True)
    finally:
      main.collection = original
  return scores


def _mark(value) -> str:
  return "-" if value is None else ("yes" if value else "NO")


def _row(score: dict) -> str:
  return (f"{score['id']:4}  {score['type']:10}  {_mark(score['retrieval_hit']):9}  "
          f"{_mark(score['citation_hit']):8}  {_mark(score['correct'])}")


def _percent(value) -> str:
  return "n/a" if value is None else f"{value:.0%}"


def main_cli(argv: list[str]) -> int:
  missing = [str(path) for path in DOCS.values() if not path.exists()]
  if missing:
    print("Missing sample agreements (samples/ is not committed):", *missing, sep="\n  ")
    return 2

  items = load_golden()
  print(f"{'ID':4}  {'TYPE':10}  {'RETRIEVED':9}  {'CITED':8}  CORRECT")
  scores = run(items)
  summary = summarize(scores)

  print(f"\nRetrieval hit rate  {_percent(summary['retrieval_hit_rate'])}")
  print(f"Citation accuracy   {_percent(summary['citation_accuracy'])}")
  print(f"Answer accuracy     {_percent(summary['answer_accuracy'])}")
  print(f"Not-found accuracy  {_percent(summary['not_found_accuracy'])}")
  print(f"Overall             {_percent(summary['overall_accuracy'])}")
  print("By type:", ", ".join(f"{kind} {_percent(rate)}" for kind, rate in summary["by_type"].items()))

  if "--out" in argv:
    out = Path(argv[argv.index("--out") + 1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
      "run_at": datetime.now().isoformat(timespec="seconds"),
      "config": {"top_k": main.TOP_K, "embedding_model": EMBEDDING_MODEL,
                 "chat_model": os.getenv("OPENAI_CHAT_MODEL", DEFAULT_CHAT_MODEL)},
      "summary": summary,
      "scores": scores,
    }, indent=2), encoding="utf-8")
    print(f"\nSaved to {out}")
  return 0


if __name__ == "__main__":
  sys.exit(main_cli(sys.argv[1:]))
