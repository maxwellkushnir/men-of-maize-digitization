"""
Men of Maize — Stage 1b: Retry NEEDS_REVIEW spreads (Take 2)

Reads each raw txt file, finds every NEEDS_REVIEW block, re-renders and
re-sends those spreads to the API, and replaces the block in-place if
the retry succeeds. Leaves failures as NEEDS_REVIEW.

The content filter is inconsistent — spreads that blocked previously often
pass on a fresh attempt. Run this multiple times to progressively recover
more spreads.

Usage:
    python3 05_retry_needs_review.py              # retries all PDFs
    python3 05_retry_needs_review.py 108-.pdf     # retries one PDF only

Requirements:
    pip install anthropic PyMuPDF
    export ANTHROPIC_API_KEY="sk-ant-..."
"""

import anthropic
import base64
import re
import sys
import time
import fitz
from pathlib import Path

# ── CONFIGURATION ─────────────────────────────────────────────────────────────

BOOK_DIR   = Path(__file__).parent.parent
OUTPUT_DIR = Path(__file__).parent / "output"
MODEL      = "claude-sonnet-4-5"
ZOOM       = 3.0
MAX_TOKENS = 4096
DELAY      = 2

LARGE_SPREAD_PDFS      = {"108-.pdf"}
LARGE_SPREAD_THRESHOLD = 60
LARGE_MAX_TOKENS       = 8192

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

# ── PROMPTS ───────────────────────────────────────────────────────────────────

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

FALLBACK_PROMPT = "Transcribe all text visible on these two book pages. Include page numbers and headings exactly as printed."

SOFT_REFUSAL_PHRASES = [
    "i'm not able to transcribe", "i am not able to transcribe", "cannot transcribe",
    "i'm unable to transcribe", "i cannot reproduce", "copyrighted",
    "copyright infringement", "i'd rather not", "i would rather not",
    "reproducing substantial", "i can help by summarizing", "i can summarize",
    "i'm happy to help in other ways",
]

# ── HELPERS ───────────────────────────────────────────────────────────────────

def is_soft_refusal(text):
    lower = text.lower()
    return any(phrase in lower for phrase in SOFT_REFUSAL_PHRASES)


def find_needs_review(raw_path):
    """Return list of spread numbers marked NEEDS_REVIEW in the raw file."""
    content = raw_path.read_text(encoding="utf-8")
    pattern = re.compile(r'\[NEEDS_REVIEW: .+? spread (\d+)')
    return [int(m.group(1)) for m in pattern.finditer(content)]


def replace_block(raw_path, pdf_name, spread_num, total, new_content):
    """Replace a NEEDS_REVIEW block in the raw file with new_content."""
    content = raw_path.read_text(encoding="utf-8")

    start_marker = f'<<< SPREAD_START pdf="{pdf_name}" spread="{spread_num}" total="{total}" >>>'
    end_marker   = "<<< SPREAD_END >>>"

    start_idx = content.find(start_marker)
    if start_idx == -1:
        print(f"    WARNING: could not find block for spread {spread_num} — skipping replace")
        return False

    end_idx = content.find(end_marker, start_idx)
    if end_idx == -1:
        print(f"    WARNING: could not find end marker for spread {spread_num} — skipping replace")
        return False

    end_idx += len(end_marker)

    new_block = (
        f'{start_marker}\n'
        f'{new_content.strip()}\n'
        f'{end_marker}'
    )

    updated = content[:start_idx] + new_block + content[end_idx:]
    raw_path.write_text(updated, encoding="utf-8")
    return True


def render_spread(doc, spread_num):
    pix = doc[spread_num - 1].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace=fitz.csRGB)
    return pix.tobytes("jpeg")


def call_api(client, jpeg_bytes, prompt, max_tokens):
    b64 = base64.standard_b64encode(jpeg_bytes).decode()
    return client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
            {"type": "text", "text": prompt},
        ]}],
    )


def retry_pdf(client, pdf_name):
    raw_path = OUTPUT_DIR / f"{pdf_name}_raw.txt"
    if not raw_path.exists():
        print(f"  No output file for {pdf_name} — skipping.")
        return 0, 0

    needs_review = find_needs_review(raw_path)
    if not needs_review:
        print(f"  {pdf_name}: no NEEDS_REVIEW spreads — nothing to do.")
        return 0, 0

    print(f"\n{'─'*60}")
    print(f"  {pdf_name}: {len(needs_review)} NEEDS_REVIEW spread(s) to retry: {needs_review}")
    print(f"{'─'*60}")

    doc = fitz.open(str(BOOK_DIR / pdf_name))
    total = len(doc)
    recovered = 0

    for spread_num in needs_review:
        use_large = pdf_name in LARGE_SPREAD_PDFS and spread_num >= LARGE_SPREAD_THRESHOLD
        max_tokens = LARGE_MAX_TOKENS if use_large else MAX_TOKENS

        print(f"  Spread {spread_num:3d}/{total}  … ", end="", flush=True)
        jpeg = render_spread(doc, spread_num)
        text = None

        # Attempt 1: main prompt
        try:
            r = call_api(client, jpeg, EXTRACTION_PROMPT, max_tokens)
            text = r.content[0].text
            if is_soft_refusal(text):
                print(f"\n    Soft refusal — retrying with fallback … ", end="", flush=True)
                text = None
        except anthropic.BadRequestError as e:
            err = str(e).lower()
            if "content filtering" in err or "output blocked" in err:
                text = None
            else:
                print(f"BadRequestError: {e}")
                text = None
        except anthropic.RateLimitError:
            print(f"\n    Rate limit — waiting 30s … ", end="", flush=True)
            time.sleep(30)
        except anthropic.APIError as e:
            print(f"APIError: {e}")
            text = None

        # Attempt 2: fallback prompt
        if text is None:
            try:
                r = call_api(client, jpeg, FALLBACK_PROMPT, max_tokens)
                text = r.content[0].text
                if is_soft_refusal(text):
                    text = None
            except (anthropic.BadRequestError, anthropic.APIError):
                text = None

        if text is not None:
            replace_block(raw_path, pdf_name, spread_num, total, text)
            recovered += 1
            print(f"✓ recovered ({len(text)} chars)")
        else:
            print("⚠ still blocked")

        time.sleep(DELAY)

    doc.close()
    return recovered, len(needs_review)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) == 2:
        pdfs = [sys.argv[1]]
    elif len(sys.argv) == 1:
        pdfs = ALL_PDFS
    else:
        print("Usage: python3 05_retry_needs_review.py [pdf_filename]")
        sys.exit(1)

    client = anthropic.Anthropic()
    total_recovered = 0
    total_attempted = 0

    for pdf_name in pdfs:
        recovered, attempted = retry_pdf(client, pdf_name)
        total_recovered += recovered
        total_attempted += attempted

    print(f"\n{'═'*60}")
    print(f"  Retry complete: {total_recovered}/{total_attempted} spread(s) recovered")
    if total_attempted - total_recovered > 0:
        remaining = total_attempted - total_recovered
        print(f"  Still blocked: {remaining} spread(s) — re-run this script or try a different model")
    print(f"  Next: run 02_assemble.py to regenerate clean text + JSON")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
