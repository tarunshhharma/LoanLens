"""Keep only the text a human reader can see.

Hidden text is the usual carrier for indirect prompt injection: white-on-white or 1-point
text is invisible on paper, but page.get_text() extracts it like any other text. The
attack suite showed leetspeak in hidden text ("N0te t0 the extract0r ...") gets past the
pattern scanner, so it is removed here, before scanning, redaction or storage.

A span is invisible if it is:
  - smaller than MIN_FONT_SIZE points, or
  - near-white with no darker fill behind it. AU home's Schedule of Charges has white
    headers on an orange fill (readable: kept) and, on page 47, white headers on white
    (blank on paper: dropped).
Text placed entirely off the page needs no check: PyMuPDF already clips it from get_text().
"""
import pymupdf

MIN_FONT_SIZE = 4.0   # points; body text in the samples is 9-12
NEAR_WHITE = 0xF0     # every RGB channel at least 240 of 255
LIGHT_FILL = 0.9      # a fill this light (0-1 per channel) doesn't make white text readable


def _is_near_white(color: int) -> bool:
  red, green, blue = color >> 16 & 0xFF, color >> 8 & 0xFF, color & 0xFF
  return min(red, green, blue) >= NEAR_WHITE


def _dark_fills(page: pymupdf.Page) -> list[pymupdf.Rect]:
  """Rectangles filled with a colour dark enough for white text to show on."""
  return [pymupdf.Rect(drawing["rect"]) for drawing in page.get_drawings()
          if drawing.get("fill") and min(drawing["fill"]) < LIGHT_FILL]


def visible_text(page: pymupdf.Page) -> tuple[str, int]:
  """Return (the page's visible text, how many invisible spans were dropped)."""
  fills = None  # looked up only if the page has white text: get_drawings() is slow
  lines, hidden = [], 0
  for block in page.get_text("dict")["blocks"]:
    if block["type"] != 0:
      continue  # an image block, no text
    for line in block["lines"]:
      kept = []
      for span in line["spans"]:
        if not span["text"].strip():
          kept.append(span["text"])  # spacing is never an attack
          continue
        invisible = span["size"] < MIN_FONT_SIZE
        if not invisible and _is_near_white(span["color"]):
          if fills is None:
            fills = _dark_fills(page)
          box = pymupdf.Rect(span["bbox"])
          centre = (box.tl + box.br) / 2
          invisible = not any(fill.contains(centre) for fill in fills)
        if invisible:
          hidden += 1
        else:
          kept.append(span["text"])
      lines.append("".join(kept))

  if hidden == 0:
    return page.get_text(), 0  # nothing hidden: keep PyMuPDF's own text exactly
  return "\n".join(lines) + "\n", hidden
