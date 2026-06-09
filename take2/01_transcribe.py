"""
Men of Maize — Stage 1: Transcription (Take 2)
Sends each spread photo to Claude vision and writes raw text to an output file.

Usage:
    python3 01_transcribe.py 26-55.pdf

Run one PDF at a time. Resume-safe: re-running the same command picks up where it left off.

Requirements:
    pip install anthropic PyMuPDF
    export ANTHROPIC_API_KEY="sk-ant-..."
"""

import anthropic
import base64
import re
import sys
import time
from pathlib import Path

# ── CONFIGURATION ─────────────────────────────────────────────────────────────

BOOK_DIR   = Path(__file__).parent.parent          # Raw Data (to use)/
OUTPUT_DIR = Path(__file__).parent / "output"
MODEL      = "claude-sonnet-4-5"
ZOOM       = 3.0                                   # ~225 dpi; 2.0 was too low for later sections
MAX_TOKENS = 4096
DELAY      = 2                                     # seconds between API calls

# Last few spreads of 108-.pdf may be dense (glossary/appendix) — give more room
LARGE_SPREAD_PDFS = {"108-.pdf"}
LARGE_SPREAD_THRESHOLD = 60                        # spread index >= this → use bigger token limit
LARGE_MAX_TOKENS = 8192

# ── PROMPTS ───────────────────────────────────────────────────────────────────
# No system prompt — naming the book/author/copyright triggers refusals.
# A neutral, mechanical transcription instruction works best.

EXTRACTION_PROMPT = """\
This is a photograph of an open book showing two pages side by side.
Transcribe ALL visible text accurately, reading the LEFT page first, then the RIGHT page.

Rules:
1. Preserve chapter headings in CAPS exactly as printed
2. Preserve Roman numeral section headings (I, II, III …) on their own line
3. Output page numbers on their own line as: [Page N]
4. When you see a small ornamental divider between sections, output: [section break]
5. Preserve paragraph breaks with a blank line between paragraphs
6. Preserve italicised text (songs, poems, dedications) on separate lines
7. If text disappears into the spine gutter, mark the gap with [...]
8. Do NOT describe the photo, hands, table, bookmark, barcode, or anything non-textual
9. Do NOT add commentary — output only the transcribed text

Transcribe now:\
"""

# Ultra-minimal fallback — used on content-filter retry
FALLBACK_PROMPT = "Transcribe all text visible on these two book pages. Include page numbers and headings exactly as printed."

# Phrases that indicate a soft refusal in the response text (model refused via text, not API error)
SOFT_REFUSAL_PHRASES = [
    "i'm not able to transcribe",
    "i am not able to transcribe",
    "cannot transcribe",
    "i'm unable to transcribe",
    "i cannot reproduce",
    "copyrighted",
    "copyright infringement",
    "i'd rather not",
    "i would rather not",
    "reproducing substantial",
    "i can help by summarizing",
    "i can summarize",
    "i'm happy to help in other ways",
]


def is_soft_refusal(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in SOFT_REFUSAL_PHRASES)

# ── HELPERS ───────────────────────────────────────────────────────────────────

def render_page(page) -> bytes:
    mat = page.parent.matrix if hasattr(page.parent, "matrix") else None
    import fitz
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace=fitz.csRGB)
    return pix.tobytes("jpeg")


def call_claude(client: anthropic.Anthropic, jpeg_bytes: bytes, use_fallback: bool = False) -> str:
    b64 = base64.standard_b64encode(jpeg_bytes).decode("utf-8")
    user_text = FALLBACK_PROMPT if use_fallback else EXTRACTION_PROMPT

    kwargs = dict(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": user_text},
            ],
        }],
    )
    if not use_fallback:
        kwargs["system"] = SYSTEM_PROMPT

    response = client.messages.create(**kwargs)
    return response.content[0].text


def find_last_completed_spread(output_path: Path) -> int:
    """Return the spread number of the last complete block in the output file (0 = none)."""
    if not output_path.exists():
        return 0
    content = output_path.read_text(encoding="utf-8")
    start_pat = re.compile(r'<<< SPREAD_START pdf="[^"]+" spread="(\d+)" total="\d+" >>>')
    end_marker = "<<< SPREAD_END >>>"
    last_complete = 0
    pos = 0
    while True:
        m = start_pat.search(content, pos)
        if not m:
            break
        spread_num = int(m.group(1))
        end_pos = content.find(end_marker, m.end())
        if end_pos == -1:
            break                       # incomplete block — stop here
        last_complete = spread_num
        pos = end_pos + len(end_marker)
    return last_complete


def write_block(out, pdf_name: str, spread_num: int, total: int, content: str):
    block = (
        f'\n<<< SPREAD_START pdf="{pdf_name}" spread="{spread_num}" total="{total}" >>>\n'
        f'{content.strip()}\n'
        f'<<< SPREAD_END >>>\n'
    )
    out.write(block)
    out.flush()

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 01_transcribe.py <pdf_filename>")
        print("Example: python3 01_transcribe.py 26-55.pdf")
        sys.exit(1)

    pdf_name = sys.argv[1]

    if pdf_name == "1.pdf":
        print("1.pdf is the cover — it's used as an image by 03_build_pdf.py.")
        print("No transcription needed. Skip to the next PDF.")
        sys.exit(0)

    pdf_path = BOOK_DIR / pdf_name
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{pdf_name}_raw.txt"

    # Resume: find the last successfully written spread
    last_done = find_last_completed_spread(output_path)
    if last_done > 0:
        print(f"  Resuming {pdf_name} from spread {last_done + 1} (already completed {last_done}).")

    try:
        import fitz
    except ImportError:
        print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF")
        sys.exit(1)

    client = anthropic.Anthropic()

    doc = fitz.open(str(pdf_path))
    total = len(doc)

    print(f"\n{'─'*60}")
    print(f"  {pdf_name}  ({total} spreads)  →  {output_path.name}")
    print(f"{'─'*60}")

    # Open in append mode — safe for resume; create with header if new
    mode = "a" if output_path.exists() else "w"
    with open(output_path, mode, encoding="utf-8") as out:
        if mode == "w":
            out.write(f"# Men of Maize — raw transcription\n# Source: {pdf_name}\n")

        for i in range(total):
            spread_num = i + 1

            if spread_num <= last_done:
                print(f"  Spread {spread_num:3d}/{total}  [skipped — already done]")
                continue

            use_large = pdf_name in LARGE_SPREAD_PDFS and spread_num >= LARGE_SPREAD_THRESHOLD
            effective_max_tokens = LARGE_MAX_TOKENS if use_large else MAX_TOKENS

            print(f"  Spread {spread_num:3d}/{total}  … ", end="", flush=True)

            jpeg_bytes = render_page(doc[i])

            text = None
            b64 = base64.standard_b64encode(jpeg_bytes).decode()

            def make_message(prompt_text):
                return [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                        {"type": "text", "text": prompt_text},
                    ],
                }]

            # Attempt 1: main extraction prompt, no system prompt
            for attempt in range(1, 4):
                try:
                    response = client.messages.create(
                        model=MODEL,
                        max_tokens=effective_max_tokens,
                        messages=make_message(EXTRACTION_PROMPT),
                    )
                    text = response.content[0].text
                    break
                except anthropic.BadRequestError as e:
                    err_str = str(e).lower()
                    if "content filtering" in err_str or "output blocked" in err_str:
                        text = None  # handle below
                        break
                    if attempt == 3:
                        text = f"[EXTRACTION_ERROR: {pdf_name} spread {spread_num}: {e}]"
                        break
                    time.sleep(10 * attempt)
                except anthropic.RateLimitError:
                    wait = 30 * attempt
                    print(f"\n    Rate limit — waiting {wait}s … ", end="", flush=True)
                    time.sleep(wait)
                except anthropic.APIError as e:
                    if attempt == 3:
                        text = f"[EXTRACTION_ERROR: {pdf_name} spread {spread_num}: {e}]"
                        break
                    time.sleep(10 * attempt)

            # Detect soft refusal (model refused via text, not API error)
            if text is not None and is_soft_refusal(text):
                print(f"\n    Soft refusal detected — retrying with fallback prompt … ", end="", flush=True)
                text = None

            # Attempt 2: fallback prompt if content-filtered or soft refusal
            if text is None:
                try:
                    response = client.messages.create(
                        model=MODEL,
                        max_tokens=effective_max_tokens,
                        messages=make_message(FALLBACK_PROMPT),
                    )
                    text = response.content[0].text
                    if is_soft_refusal(text):
                        text = None
                except (anthropic.BadRequestError, anthropic.APIError):
                    text = None

            if text is None:
                text = f"[NEEDS_REVIEW: {pdf_name} spread {spread_num} — refused after 2 attempts]"

            write_block(out, pdf_name, spread_num, total, text)

            if "[NEEDS_REVIEW" in text:
                print("⚠ NEEDS REVIEW")
            elif "[EXTRACTION_ERROR" in text:
                print("✗ ERROR")
            else:
                print("✓")

            if spread_num < total:
                time.sleep(DELAY)

    doc.close()

    needs_review = sum(
        1 for line in output_path.read_text(encoding="utf-8").splitlines()
        if "[NEEDS_REVIEW" in line
    )

    print(f"\n{'─'*60}")
    print(f"  Done: {pdf_name}  ({total} spreads processed)")
    print(f"  Needs review: {needs_review} spread(s)")
    print(f"  Output: {output_path}")
    print(f"{'─'*60}\n")
    print("Next step: inspect the output file, then run the next PDF.")


if __name__ == "__main__":
    main()
