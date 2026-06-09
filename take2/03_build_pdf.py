"""
Men of Maize — Stage 3: PDF Generation
Reads men_of_maize_structured.json and typesets it into a book PDF using WeasyPrint.

Usage:
    python3 03_build_pdf.py

Requirements:
    brew install pango          (system dependency for WeasyPrint)
    pip install weasyprint PyMuPDF
"""

import base64
import io
import json
import re
import sys
from html import escape
from pathlib import Path

# Set True for a clean reader edition: removes ※ markers and the uncertainty appendix.
# Set False to keep QA indicators for proofreading.
READER_EDITION = True

OUTPUT_DIR = Path(__file__).parent / "output"
BOOK_DIR   = Path(__file__).parent.parent   # Raw Data (to use)/
COVER_PDF  = BOOK_DIR / "1.pdf"

STRUCTURED_JSON = OUTPUT_DIR / "men_of_maize_structured.json"
OUTPUT_PDF      = OUTPUT_DIR / "men_of_maize.pdf"

# Baskerville font — local copy (same dir as script) takes priority over macOS system path
_baskerville_local  = Path(__file__).parent / "Baskerville.ttc"
_baskerville_system = Path("/System/Library/Fonts/Supplemental/Baskerville.ttc")
BASKERVILLE_PATH = str(_baskerville_local if _baskerville_local.exists() else _baskerville_system)

# Copperplate font — used for chapter headings and running headers
_copperplate_local  = Path(__file__).parent / "Copperplate.ttc"
_copperplate_system = Path("/System/Library/Fonts/Supplemental/Copperplate.ttc")
COPPERPLATE_PATH = str(_copperplate_local if _copperplate_local.exists() else _copperplate_system)

# Cover PDF — check next to script and one level up (handles both Colab and local layouts)
COVER_PDF = next(
    (p for p in [BOOK_DIR / "1.pdf", Path(__file__).parent / "1.pdf"] if p.exists()),
    BOOK_DIR / "1.pdf"
)

# Ornament images — embedded as base64 so Colab needs no extra file access
def _load_ornament(filename: str) -> str:
    p = Path(__file__).parent / filename
    if not p.exists():
        return ""
    try:
        from PIL import Image
        import io
        img = Image.open(p).convert("RGB")
        gray = img.convert("L")
        # Find bounding box of pixels darker than 200 (the actual ornament content)
        thresholded = gray.point(lambda x: 255 if x < 200 else 0)
        bbox = thresholded.getbbox()
        if bbox:
            pad = 6
            w, h = img.size
            bbox = (max(0, bbox[0]-pad), max(0, bbox[1]-pad),
                    min(w, bbox[2]+pad), min(h, bbox[3]+pad))
            img = img.crop(bbox)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.standard_b64encode(buf.getvalue()).decode()
    except Exception:
        return base64.standard_b64encode(p.read_bytes()).decode()

ORN_BREAK = _load_ornament("ornament_fancy.png")   # section break (between scenes)
ORN_FANCY = _load_ornament("ornament_break.png")   # chapter / section opener

# Text-cleaning helpers — strip [Page N] plus any chapter header that follows it
_CHAPTER_NAMES = (
    r'MEN\s+OF\s+MAIZE|GASPAR\s+IL[OÓ]M|MACHOJ[OÓ]N|'
    r'THE\s+DEER\s+OF\s+THE\s+SEVENTH\s+FIRE|'
    r'COLONEL\s+CHALO\s+GODOY|MAR[IÍ]A\s+TEC[UÚ]N|'
    r'COYOTE[\s\-‐]*POSTMAN|EPILOGUE'
)
_PAGE_MARKER = re.compile(
    r'\[Page(?:\s+LEFT|\s+RIGHT)?\s*\d*\]\s*(?:' + _CHAPTER_NAMES + r')?\s*',
    re.IGNORECASE
)
# Bare ALL-CAPS running headers that appear without a [Page N] prefix
_INLINE_HEADER = re.compile(
    r'(?:MEN\s+OF\s+MAIZE|GASPAR\s+IL[OÓ]M|MACHOJ[OÓ]N|'
    r'THE\s+DEER\s+OF\s+THE\s+SEVENTH\s+FIRE|COLONEL\s+CHALO\s+GODOY|'
    r'MAR[IÍ]A\s+TEC[UÚ]N|COYOTE[\-\s‐]*POSTMAN|EPILOGUE)'
)
_ELLIPSIS_BRACKET = re.compile(r'\[\s*\.{2,}\s*\]|\[\s*…\s*\]')
_ORN_TEXT    = re.compile(
    r'^\s*(?:'
    r'[\[◆*•\-]*\s*(?:decorative|ornamental|ornament)\s*(?:symbol|break|ornament|element)?\s*[\]]*|'
    r'◆|[*]{3}|\*\s*\*\s*\*'
    r')\s*$',
    re.IGNORECASE
)
_SENT_END    = re.compile(r'[.!?…"\')\]]\s*$')


def _clean(text: str) -> str:
    """Strip [Page N] markers, bare running headers, and normalise placeholders."""
    text = _PAGE_MARKER.sub("", text)
    text = _INLINE_HEADER.sub("", text)
    text = _ELLIPSIS_BRACKET.sub("[illegible]", text)
    # Collapse whitespace left by removals
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def _preprocess_blocks(blocks: list) -> list:
    """Clean text in paragraph blocks; convert ornament-description paragraphs to section breaks."""
    result = []
    for blk in blocks:
        if blk["type"] == "paragraph":
            text = _clean(blk["text"])
            if not text:
                continue
            if _ORN_TEXT.match(text):
                result.append({"type": "section_break"})
                continue
            result.append({**blk, "text": text})
        else:
            result.append(blk)
    return result


def _merge_page_fragments(pages: list) -> list:
    """Merge paragraph fragments split across page boundaries."""
    pages = [dict(pg, content_blocks=list(pg["content_blocks"])) for pg in pages]
    for i in range(len(pages) - 1):
        bt, bn = pages[i]["content_blocks"], pages[i + 1]["content_blocks"]
        if not bt or not bn:
            continue
        last, first = bt[-1], bn[0]
        if last["type"] != "paragraph" or first["type"] != "paragraph":
            continue
        pt = _clean(last["text"])
        nt = _clean(first["text"])
        if not _SENT_END.search(pt) or (nt and nt[0].islower()):
            bt[-1] = {**last, "text": last["text"].rstrip() + " " + first["text"].lstrip()}
            bn.pop(0)
    return pages

# ── PREREQUISITE CHECK ────────────────────────────────────────────────────────

def check_prerequisites():
    try:
        import weasyprint
    except ImportError:
        print("ERROR: WeasyPrint not installed.")
        print("  pip install weasyprint")
        print("  brew install pango   ← required system library")
        sys.exit(1)

    try:
        ver = tuple(int(x) for x in weasyprint.__version__.split(".")[:1])
        if ver < (53,):
            print(f"ERROR: WeasyPrint >= 53 required (found {weasyprint.__version__}).")
            print("  pip install --upgrade weasyprint")
            sys.exit(1)
    except Exception:
        pass  # version check not critical

    if not STRUCTURED_JSON.exists():
        print(f"ERROR: {STRUCTURED_JSON} not found. Run 02_assemble.py first.")
        sys.exit(1)

    try:
        import fitz
    except ImportError:
        print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF")
        sys.exit(1)

# ── COVER IMAGE ───────────────────────────────────────────────────────────────

def render_cover_b64() -> str:
    """Render 1.pdf page 0 to a JPEG and return as base64 string."""
    try:
        import fitz
        doc = fitz.open(str(COVER_PDF))
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0), colorspace=fitz.csRGB)
        jpeg = pix.tobytes("jpeg")
        doc.close()
        return base64.standard_b64encode(jpeg).decode("utf-8")
    except Exception as e:
        print(f"  WARNING: Could not render cover ({e}). Skipping cover page.")
        return ""

# ── HTML GENERATION ───────────────────────────────────────────────────────────

def _orn_img(b64: str, css_class: str) -> str:
    if not b64:
        return ""
    return f'<img src="data:image/png;base64,{b64}" class="{css_class}" alt="">'


def blocks_to_html(blocks: list, is_uncertain: bool = False) -> str:
    parts = []
    first_para_done = False
    blocks = _preprocess_blocks(blocks)
    for blk in blocks:
        t = blk["type"]
        if t == "chapter_heading":
            opener = f'<div class="orn-opener">{_orn_img(ORN_FANCY, "orn-fancy")}</div>' if ORN_FANCY else ""
            parts.append(f'{opener}<h2 class="chapter-heading">{escape(blk["text"])}</h2>')
        elif t == "section_number":
            opener = f'<div class="orn-opener">{_orn_img(ORN_BREAK, "orn-break")}</div>' if ORN_BREAK else ""
            parts.append(f'{opener}<p class="section-number">{escape(blk["text"])}</p>')
        elif t == "section_break":
            inner = _orn_img(ORN_BREAK, "orn-break") if ORN_BREAK else "◆"
            parts.append(f'<div class="section-break">{inner}</div>')
        elif t == "paragraph":
            if is_uncertain and not first_para_done and not READER_EDITION:
                parts.append(f'<p class="uncertain-page">{escape(blk["text"])}</p>')
                first_para_done = True
            else:
                parts.append(f'<p>{escape(blk["text"])}</p>')
        elif t == "italic_block":
            parts.append(f'<p class="italic-block"><em>{escape(blk["text"])}</em></p>')
        elif t == "needs_review":
            pdf  = blk.get("source_pdf", "?")
            num  = blk.get("spread_number", "?")
            parts.append(
                f'<div class="needs-review">'
                f'[Pages missing — {escape(str(pdf))} spread {escape(str(num))} '
                f'requires manual transcription]'
                f'</div>'
            )
    return "\n".join(parts)


def front_matter_to_html(front_matter: list) -> str:
    if not front_matter:
        return ""
    parts = ['<div class="front-matter">']
    for section in front_matter:
        parts.append('<div class="fm-section">')
        parts.append(blocks_to_html(section.get("content_blocks", [])))
        parts.append('</div>')
    parts.append('</div>')
    return "\n".join(parts)


def pages_to_html(pages: list) -> str:
    pages = _merge_page_fragments(pages)
    parts = []
    for pg in pages:
        is_uncertain = pg.get("_uncertain", False)
        parts.append(blocks_to_html(pg["content_blocks"], is_uncertain))
    return "\n".join(parts)


def uncertainty_appendix_html(structured: dict) -> str:
    """Generate a clean appendix page listing all uncertain passages."""
    import json as _json
    uncertain_pages = []
    for pg in structured.get("pages", []):
        if pg.get("_uncertain"):
            spans = pg.get("_uncertain_spans", [])
            uncertain_pages.append((pg["page_number"], spans))

    if not uncertain_pages:
        return ""

    rows = ""
    for pn, spans in sorted(uncertain_pages):
        for sp in spans:
            q   = escape(sp.get("q",""))
            m   = escape(sp.get("m",""))
            base = escape(sp.get("base","—"))
            cat  = escape(sp.get("cat",""))
            rows += (f'<tr><td>{pn}</td>'
                     f'<td style="color:#1565c0">{q}</td>'
                     f'<td style="color:#2e7d32">{m}</td>'
                     f'<td style="color:#555">{base}</td>'
                     f'<td style="font-size:8pt;color:#888">{cat}</td></tr>\n')

    page_list = ", ".join(str(pn) for pn, _ in sorted(uncertain_pages))

    return f"""
<div class="appendix-page">
  <h2 class="appendix-heading">Note on Textual Uncertainties</h2>
  <p class="appendix-intro">
    This edition was prepared from photographs of the 1975 Delacorte/Seymour Lawrence
    first US edition using multiple independent AI transcription models (Claude, Qwen,
    Mistral, GPT-5.5). The following {len(uncertain_pages)} pages contain passages where
    all models disagreed and no majority reading could be determined. These are marked
    with a small <span class="unc-symbol">※</span> at the start of the relevant paragraph.
    They are candidates for verification against the original photographs in a future revision.
  </p>
  <p class="appendix-pages"><strong>Affected pages:</strong> {page_list}</p>
  <table class="appendix-table">
    <thead>
      <tr>
        <th>Page</th>
        <th style="color:#1565c0">Qwen read</th>
        <th style="color:#2e7d32">Mistral read</th>
        <th>Current text</th>
        <th>Type</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def build_html(structured: dict, cover_b64: str) -> str:
    font_src        = f'url("file://{BASKERVILLE_PATH}")'  if Path(BASKERVILLE_PATH).exists()  else "local('Baskerville')"
    copperplate_src = f'url("file://{COPPERPLATE_PATH}")' if Path(COPPERPLATE_PATH).exists() else "local('Copperplate')"

    cover_html = ""
    if cover_b64:
        cover_html = f'''
    <div class="cover-page">
      <img src="data:image/jpeg;base64,{cover_b64}" alt="Cover">
    </div>'''

    fm_html      = front_matter_to_html(structured.get("front_matter", []))
    body_html    = pages_to_html(structured.get("pages", []))
    appendix_html = "" if READER_EDITION else uncertainty_appendix_html(structured)

    css = f"""
    @font-face {{
      font-family: 'Baskerville';
      src: {font_src};
    }}
    @font-face {{
      font-family: 'Copperplate';
      src: {copperplate_src};
    }}

    /* ── PAGE LAYOUT ── */
    @page {{
      size: 5.5in 8.5in;
      margin: 0.875in 0.75in 0.875in 0.875in;
      background: #ccc1b0;
    }}

    @page :left {{
      @top-left {{
        content: "MEN OF MAIZE";
        font-family: 'Copperplate', Copperplate, 'Copperplate Gothic Light', serif;
        font-size: 8pt;
        color: #444;
      }}
      @bottom-left {{
        content: counter(page);
        font-family: 'Baskerville', Baskerville, Georgia, serif;
        font-size: 9pt;
        color: #555;
      }}
    }}

    @page :right {{
      @top-right {{
        content: string(chapter-running-header);
        font-family: 'Copperplate', Copperplate, 'Copperplate Gothic Light', serif;
        font-size: 8pt;
        color: #444;
        text-align: right;
      }}
      @bottom-right {{
        content: counter(page);
        font-family: 'Baskerville', Baskerville, Georgia, serif;
        font-size: 9pt;
        color: #555;
        text-align: right;
      }}
    }}

    @page cover-page {{
      margin: 0;
      @top-left {{ content: none; }}
      @top-right {{ content: none; }}
      @bottom-left {{ content: none; }}
      @bottom-right {{ content: none; }}
    }}

    /* ── COVER ── */
    .cover-page {{
      page: cover-page;
      width: 5.5in;
      height: 8.5in;
      overflow: hidden;
    }}
    .cover-page img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
    }}

    /* ── FRONT MATTER ── */
    .fm-section {{
      page-break-after: always;
      text-align: center;
      padding-top: 2in;
    }}

    body {{
      font-family: 'Baskerville', Baskerville, 'Book Antiqua', Georgia, serif;
      font-size: 10pt;
      line-height: 1.3;
      color: #111;
      hyphens: auto;
      background-color: #ccc1b0;
    }}

    p {{
      margin: 0;
      text-indent: 1.5em;
      text-align: justify;
      text-align-last: left;
    }}
    p:first-of-type,
    h2.chapter-heading + p,
    p.section-number + p,
    .section-break + p {{
      text-indent: 0;
    }}

    /* ── CHAPTER HEADINGS ── */
    .orn-opener {{
      text-align: center;
      margin-top: 1.5in;
      margin-bottom: 0.2in;
      line-height: 1;
    }}
    .orn-fancy {{
      height: 36pt;
      width: auto;
    }}
    h2.chapter-heading {{
      string-set: chapter-running-header content();
      font-family: 'Copperplate', Copperplate, 'Copperplate Gothic Light', serif;
      font-weight: normal;
      font-size: 17pt;
      letter-spacing: 0.12em;
      text-align: center;
      margin-top: 0.2in;
      margin-bottom: 0.5in;
      page-break-before: right;
    }}

    /* ── SECTION NUMBER ── */
    p.section-number {{
      text-indent: 0;
      text-align: center;
      font-size: 11pt;
      margin-top: 0.75em;
      margin-bottom: 0.75em;
    }}

    /* ── SECTION BREAK ORNAMENT ── */
    .section-break {{
      text-align: center;
      margin: 1.25em 0;
      line-height: 1;
    }}
    .orn-break {{
      height: 18pt;
      width: auto;
    }}

    /* ── ITALIC BLOCK (poems, songs, dedications) ── */
    p.italic-block {{
      text-indent: 0;
      text-align: left;
      font-style: italic;
      margin: 0.75em 1.5em;
    }}

    /* ── NEEDS REVIEW PLACEHOLDER ── */
    .needs-review {{
      border: 0.75pt solid #bbb;
      padding: 8pt 10pt;
      margin: 1em 0;
      font-style: italic;
      font-size: 9pt;
      color: #777;
      background: #f9f9f9;
    }}

    /* ── UNCERTAIN PASSAGE MARKER ── */
    p.uncertain-page::before {{
      content: "※ ";
      color: #b71c1c;
      font-size: 7pt;
      vertical-align: super;
    }}

    /* ── UNCERTAINTY APPENDIX ── */
    .appendix-page {{
      page-break-before: always;
      margin-top: 1.5in;
    }}
    h2.appendix-heading {{
      font-family: 'Copperplate', Copperplate, 'Copperplate Gothic Light', serif;
      font-weight: normal;
      font-size: 13pt;
      letter-spacing: 0.1em;
      text-align: center;
      margin-bottom: 0.5in;
    }}
    p.appendix-intro {{
      font-size: 9pt;
      line-height: 1.5;
      text-indent: 0;
      margin-bottom: 0.5em;
    }}
    p.appendix-pages {{
      font-size: 9pt;
      text-indent: 0;
      margin-bottom: 1em;
    }}
    .unc-symbol {{
      color: #b71c1c;
      font-size: 8pt;
    }}
    .appendix-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 8pt;
      margin-top: 0.5em;
    }}
    .appendix-table th, .appendix-table td {{
      border: 0.5pt solid #ccc;
      padding: 3pt 5pt;
      vertical-align: top;
    }}
    .appendix-table th {{
      background: #f0ebe3;
      font-weight: bold;
    }}
    """

    html = f"""<!DOCTYPE html>
<html lang="en" xml:lang="en">
<head>
  <meta charset="utf-8">
  <title>Men of Maize — Miguel Ángel Asturias</title>
  <style>{css}</style>
</head>
<body>
{cover_html}
{fm_html}
<div id="body-start">
{body_html}
</div>
{appendix_html}
</body>
</html>"""
    return html

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    check_prerequisites()
    import weasyprint

    print("Loading structured JSON …")
    structured = json.loads(STRUCTURED_JSON.read_text(encoding="utf-8"))

    nr = structured["metadata"]["needs_review_count"]
    pages = len(structured["pages"])
    print(f"  {pages} pages  |  {nr} needs-review spread(s)")

    print("Rendering cover …")
    cover_b64 = render_cover_b64()

    print("Building HTML …")
    html = build_html(structured, cover_b64)

    # Optionally save HTML for debugging
    html_debug = OUTPUT_DIR / "men_of_maize_debug.html"
    html_debug.write_text(html, encoding="utf-8")
    print(f"  HTML saved for inspection: {html_debug.name}")

    print("Generating PDF (this may take a minute) …")
    try:
        weasyprint.HTML(string=html, base_url=str(OUTPUT_DIR)).write_pdf(str(OUTPUT_PDF))
    except Exception as e:
        print(f"\nERROR during PDF generation: {e}")
        print("If you see a Pango/Cairo error, make sure you ran: brew install pango")
        sys.exit(1)

    size_mb = OUTPUT_PDF.stat().st_size / 1_048_576
    print(f"\nPDF generated: {OUTPUT_PDF}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"\nOpen and verify:")
    print(f"  open \"{OUTPUT_PDF}\"")
    print(f"\nChecklist:")
    print(f"  □ Cover displays correctly")
    print(f"  □ Left pages: 'MEN OF MAIZE' at top-left, page number at bottom-left")
    print(f"  □ Right pages: chapter name at top-right, page number at bottom-right")
    print(f"  □ Chapter names start on right-hand (odd) pages")
    print(f"  □ Section break ornaments (◆) appear between sections")
    print(f"  □ [NEEDS_REVIEW] placeholder boxes visible where content was blocked")


if __name__ == "__main__":
    main()
