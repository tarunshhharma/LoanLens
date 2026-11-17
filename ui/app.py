"""LoanLens web UI: a thin Streamlit client over the FastAPI backend.

Start the API first, then, from the project root:
    python -m streamlit run ui/app.py
"""
import hmac
import os

import httpx
import streamlit as st

from ui.display import term_rows

API_URL = os.getenv("LOANLENS_API_URL", "http://127.0.0.1:8000")
TIMEOUT = 180  # seconds: /upload embeds every chunk, /extract makes 3 model calls
ACCESS_CODE = os.getenv("LOANLENS_ACCESS_CODE")  # set only on the public demo

SEVERITY_BOX = {"high": st.error, "medium": st.warning, "low": st.info}


def call_api(path: str, **kwargs) -> dict | None:
  """POST to the API. On any failure, show the error on the page and return None."""
  try:
    response = httpx.post(f"{API_URL}{path}", timeout=TIMEOUT, **kwargs)
  except httpx.HTTPError:  # connection refused, timeout, ...
    st.error(f"Can't reach the LoanLens API at {API_URL}. Is uvicorn running?")
    return None
  if response.status_code != 200:
    try:
      detail = response.json().get("detail", response.text)
    except ValueError:  # the error body wasn't JSON
      detail = response.text
    st.error(f"Error {response.status_code}: {detail}")
    return None
  return response.json()


# Streamlit reruns this whole file on every click. session_state survives reruns.
st.session_state.setdefault("document", None)
st.session_state.setdefault("answers", [])
st.session_state.setdefault("extraction", None)
st.session_state.setdefault("unlocked", False)

st.set_page_config(page_title="LoanLens", layout="wide")
st.title("LoanLens")
st.caption("Questions about your loan agreement, answered with the clause and page they come from.")

# --- Access code (public demo only) ---------------------------------------------
# Every upload and question costs OpenAI credit, so the public demo is for people given the code.
if ACCESS_CODE and not st.session_state.unlocked:
  code = st.text_input("Access code", type="password", help="Ask the author for the demo code.")
  if not code:
    st.stop()
  # compare_digest takes the same time however many characters match, so timing reveals nothing
  if not hmac.compare_digest(code.encode(), ACCESS_CODE.encode()):
    st.error("Wrong access code.")
    st.stop()
  st.session_state.unlocked = True
  st.rerun()  # draw the app without the code box

# --- Sidebar: upload ----------------------------------------------------------
with st.sidebar:
  st.header("Agreement")
  pdf = st.file_uploader("Loan agreement (PDF)", type="pdf")
  if pdf is not None and st.button("Upload and index", type="primary"):
    with st.spinner("Reading, splitting and embedding..."):
      result = call_api("/upload", files={"file": (pdf.name, pdf.getvalue(), "application/pdf")})
    if result:
      st.session_state.document = {
        "doc_id": result["doc_id"],
        "filename": result["filename"],
        "pages": result["total_pages"],
        "chunks": result["chunk_count"],
        "style": result["numbering_style"],
        "warnings": result["warnings"],
      }
      st.session_state.answers = []       # a new document starts a fresh page
      st.session_state.extraction = None

  doc = st.session_state.document
  if doc:
    st.success(f"Indexed: {doc['filename']}")
    st.caption(f"{doc['pages']} pages · {doc['chunks']} chunks · {doc['style']} numbering")
    for warning in doc["warnings"]:
      st.warning(warning)

if not doc:
  st.info("Upload a loan agreement in the sidebar to begin.")
  st.stop()  # nothing below runs until there is a document

ask_tab, terms_tab = st.tabs(["Ask a question", "Key terms & risks"])

# --- Tab 1: questions -----------------------------------------------------------
with ask_tab:
  with st.form("ask", clear_on_submit=True):
    question = st.text_input("Your question", placeholder="What happens if I pay my EMI late?")
    asked = st.form_submit_button("Ask")
  if asked and question.strip():
    with st.spinner("Searching the agreement..."):
      result = call_api("/ask", json={"doc_id": doc["doc_id"], "question": question})
    if result:
      st.session_state.answers.insert(0, result)  # newest first

  for result in st.session_state.answers:
    st.markdown(f"**Q: {result['question']}**")
    if result["found"]:
      st.write(result["answer"])
      for citation in result["citations"]:
        with st.expander(citation["label"]):
          st.text(citation["text"])
    else:
      st.warning(result["answer"])
    st.divider()

# --- Tab 2: key terms and risk flags ----------------------------------------------
with terms_tab:
  if st.button("Extract key terms"):
    with st.spinner("Reading the key terms (3 model calls)..."):
      st.session_state.extraction = call_api("/extract", json={"doc_id": doc["doc_id"]})

  extraction = st.session_state.extraction
  if extraction:
    flags = extraction["risk_flags"]
    st.subheader(f"Risk flags ({len(flags)})")
    if not flags:
      st.success("No risk flags from the terms found.")
    for flag in flags:
      sources = "; ".join(citation["label"] for citation in flag["citations"])
      SEVERITY_BOX[flag["severity"]](
        f"**{flag['title']}**  \n{flag['explanation']}  \nSource: {sources}"
      )

    st.subheader(f"Key terms ({len(extraction['found'])} of {len(extraction['terms'])} found)")
    st.dataframe(term_rows(extraction["terms"]), hide_index=True, width="stretch")

    if extraction["warnings"]:
      with st.expander(f"Extraction warnings ({len(extraction['warnings'])})"):
        for warning in extraction["warnings"]:
          st.write(warning)
