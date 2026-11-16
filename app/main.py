import hashlib
from functools import lru_cache

import openai
import pymupdf
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.answer import answer_question
from app.cleaning import clean_pages
from app.extract import TOP_K_EXTRACT, extract_terms
from app.llm import complete_json, embed_texts
from app.retrieval import hybrid_search
from app.risk import assess_risks
from app.splitting import (
  UNKNOWN,
  detect_numbering_style,
  split_into_chunks,
  split_oversized,
)
from app.store import add_document, get_collection

load_dotenv()  # puts OPENAI_API_KEY (and OPENAI_CHAT_MODEL, if set) from .env into os.environ

app = FastAPI(
  title= "LoanLens API",
  description= "An API for LoanLens, a loan agreement simplification tool.",
)


MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
MIN_CHARS_PER_PAGE = 30
TOP_K = 5  # chunks sent to the model per question


@lru_cache(maxsize=1)
def collection():
  # Opened once, on first request, then reused.
  return get_collection()


@app.post("/upload")
def upload_pdf(file: UploadFile):
  pdf_bytes = file.file.read()


  # 1. Validate before doing any work
  if len(pdf_bytes) > MAX_FILE_SIZE:
    raise HTTPException(status_code=413, detail="File size exceeds the maximum limit of 20 MB.")
  if not pdf_bytes.startswith(b"%PDF-"):
    raise HTTPException(status_code=400, detail="File is not a PDF")


  # 2. Parse the PDF
  try:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
  except pymupdf.FileDataError:
    raise HTTPException(status_code=400, detail="PDF is corrupted or unreadable.")


  # 3. Extract text page by page, keeping track of page numbers
  pages = []
  page_texts = []
  with doc:
    for page in doc:
      text = page.get_text()
      page_texts.append(text)
      char_count = len(text.strip())
      pages.append({
        "page_number": page.number +1, # PyMuPDF counts from 0, so we add 1 to make it human-readable
        "char_count": char_count,
        "has_text": char_count >= MIN_CHARS_PER_PAGE,
        "preview": text[:200],
      })
  
  empty_pages = [p["page_number"] for p in pages if not p["has_text"]]

  
  if len(empty_pages) == len(pages):
    raise HTTPException(status_code=422, detail="No extractable text found. This PDF looks scanned (image-only). Upload a text-based PDF; OCR is not supported yet.")

  warnings = []

  if empty_pages:
    warnings.append(f"Pages {empty_pages} have no extractable text (possibly scanned).")

  # 4. Clean, split into clauses, then break oversized chunks into parts
  cleaned = clean_pages(page_texts)
  style = detect_numbering_style(cleaned)
  chunks = split_oversized(split_into_chunks(cleaned))

  if style == UNKNOWN:
    warnings.append("Could not detect clause numbering; the document was split by page instead.")

  # 5. Embed and store. Same file bytes -> same doc_id, so a re-upload replaces, not duplicates.
  doc_id = hashlib.sha256(pdf_bytes).hexdigest()[:16]
  try:
    add_document(collection(), doc_id, file.filename, chunks, embed_texts)
  except openai.OpenAIError:
    raise HTTPException(status_code=502, detail="The embedding service failed. Try again later.")

  return {
    "doc_id": doc_id,
    "filename": file.filename,
    "total_pages": len(pages),
    "pages": pages,
    "warnings": warnings,
    "numbering_style": style,
    "chunk_count": len(chunks),
    "chunks": [
      {
        "kind": c.kind,
        "number": c.number,
        "term": c.term,
        "part": c.part,
        "page_start": c.page_start,
        "page_end": c.page_end,
        "text": c.text,
    }
    for c in chunks
    ]
  }


class AskRequest(BaseModel):
  doc_id: str
  question: str = Field(min_length=3, max_length=1000)


@app.post("/ask")
def ask(request: AskRequest):
  try:
    chunks = hybrid_search(collection(), request.doc_id, request.question, embed_texts, TOP_K)
    if not chunks:
      raise HTTPException(status_code=404, detail="Unknown doc_id. Upload the PDF first.")
    result = answer_question(request.question, chunks, complete_json)
  except openai.OpenAIError:
    raise HTTPException(status_code=502, detail="The language model service failed. Try again later.")

  return {"doc_id": request.doc_id, "question": request.question, **result}


class ExtractRequest(BaseModel):
  doc_id: str

@app.post("/extract")
def extract(request: ExtractRequest):
  # Check the document exists first: otherwise every search returns [] and we'd
  # answer 200 with all fields None, as if the agreement stated nothing.
  if not collection().get(where={"doc_id": request.doc_id}, limit=1, include=[])["ids"]:
    raise HTTPException(status_code=404, detail="Unknown doc_id. Upload the PDF first.")

  def search(query: str) -> list[dict]:
    # A closure: it remembers request.doc_id, so extract_terms only has to pass a query.
    return hybrid_search(collection(), request.doc_id, query, embed_texts, TOP_K_EXTRACT)

  try:
    result = extract_terms(search, complete_json)
  except openai.OpenAIError:
    raise HTTPException(status_code=502, detail="The language model service failed. Try again later.")
  
  terms = result["terms"]
  return {
    "doc_id": request.doc_id,
    "found": terms.found_fields(),
    "terms": terms.model_dump(),
    "warnings": result["warnings"],
    "risk_flags": [flag.model_dump() for flag in assess_risks(terms)],
  }