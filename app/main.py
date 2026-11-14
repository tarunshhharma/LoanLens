import pymupdf  
from fastapi import FastAPI, HTTPException, UploadFile

app = FastAPI(
  title= "LoanLens API",
  description= "An API for LoanLens, a loan agreement simplification tool.",
)


MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
MIN_CHARS_PER_PAGE = 30


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
  with doc:
    for page in doc:
      text = page.get_text()
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



  return {
    "filename": file.filename,
    "total_pages": len(pages),
    "pages": pages,
    "warnings": warnings
  }