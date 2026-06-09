"""
Men of Maize — Check 1: Mistral blind re-transcription
Independent spread-by-spread transcription using Mistral Large 3 vision (chat API).
This is a FRESH run — NOT reusing output from 06_mistral_ocr.py.
Uses the chat completions API + explicit prompt, not the OCR document API.

Note: pixtral-large-latest was deprecated 2026-02-27 and had a repetition-loop bug.
This script uses mistral-large-2512 (Mistral Large 3), the current recommended
vision chat model per https://docs.mistral.ai/studio-api/conversations/vision

Usage:
    pip install mistralai PyMuPDF
    export MISTRAL_API_KEY="your-key-here"
    python3 08_mistral_transcribe.py 26-55.pdf      # one PDF at a time
    python3 08_mistral_transcribe.py all            # all 5 body PDFs in order

Output per PDF: take2/output/mistral_raw/<pdf_name>_mistral.txt
Resume-safe: re-running the same command skips already-completed spreads.

Requirements:
    pip install mistralai PyMuPDF
"""

import base64
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

try:
    from mistralai import Mistral
except ImportError:
    print("ERROR: mistralai package not installed. Run: pip install mistralai")
    sys.exit(1)

# ── CONFIGURATION ─────────────────────────────────────────────────────────────

BOOK_DIR   = Path(__file__).parent.parent
OUTPUT_DIR = Path(__file__).parent / "output" / "mistral_raw"
MODEL      = "mistral-large-2512"                 # Mistral Large 3 — current vision chat model
ZOOM       = 3.0
MAX_TOKENS = 4096
DELAY      = 1

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

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
8. Do NOT describe the photo, hands, table, bookmark, or anything non-textual
9. Do NOT add commentary — output only the transcribed text

Transcribe now:\
"""

# ── HELPERS ───────────────────────────────────────────────────────────────────

def render_spread(page) -> bytes:
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace=fitz.csRGB)
    return pix.tobytes("jpeg")


def call_mistral(client: Mistral, jpeg_bytes: bytes) -> str:
    b64 = base64.standard_b64encode(jpeg_bytes).decode()
    response = client.chat.complete(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )
    return response.choices[0].message.content or ""


def find_last_completed(output_path: Path) -> int:
    if not output_path.exists():
        return 0
    content = output_path.read_text(encoding="utf-8")
    start_pat = re.compile(r'<<< SPREAD_START pdf="[^"]+" spread="(\d+)"')
    end_marker = "<<< SPREAD_END >>>"
    last = 0
    pos = 0
    while True:
        m = start_pat.search(content, pos)
        if not m:
            break
        spread_num = int(m.group(1))
        end_pos = content.find(end_marker, m.end())
        if end_pos == -1:
            break
        last = spread_num
        pos = end_pos + len(end_marker)
    return last


def write_block(out, pdf_name: str, spread_num: int, total: int, content: str):
    block = (
        f'\n<<< SPREAD_START pdf="{pdf_name}" spread="{spread_num}" total="{total}" >>>\n'
        f'{content.strip()}\n'
        f'<<< SPREAD_END >>>\n'
    )
    out.write(block)
    out.flush()


# ── SMOKE TEST & QUALITY CHECKS ───────────────────────────────────────────────

def has_repetition_loop(text: str, ngram_size: int = 8, threshold: int = 3):
    """Return the offending phrase if a repetition loop is detected, else None."""
    words = text.split()
    if len(words) < ngram_size:
        return None
    ngrams = [" ".join(words[i:i+ngram_size]) for i in range(len(words) - ngram_size + 1)]
    counts = Counter(ngrams)
    most_common_phrase, count = counts.most_common(1)[0]
    if count >= threshold:
        return f"'{most_common_phrase}' (×{count})"
    return None


def smoke_test(client: Mistral) -> bool:
    """
    Fire a single real spread at the model before the main run.
    Checks: API key valid, model name correct, vision works, no repetition loop.
    Exits the program if any check fails.
    """
    test_pdf = next((BOOK_DIR / p for p in ALL_PDFS if (BOOK_DIR / p).exists()), None)
    if test_pdf is None:
        print("SMOKE TEST ERROR: No source PDF found.")
        return False

    print(f"\n  Smoke test — sending spread 1 of {test_pdf.name} to {MODEL} …", end="", flush=True)

    doc = fitz.open(str(test_pdf))
    jpeg_bytes = render_spread(doc[0])
    doc.close()

    try:
        text = call_mistral(client, jpeg_bytes)
    except Exception as e:
        print(f"\n  SMOKE TEST FAILED: API error — {e}")
        return False

    if not text or len(text.strip()) < 30:
        print(f"\n  SMOKE TEST FAILED: Response too short or empty (got: {repr(text[:100])})")
        return False

    loop = has_repetition_loop(text)
    if loop:
        print(f"\n  SMOKE TEST FAILED: Repetition loop detected — {loop}")
        print(f"  This suggests the model is not behaving correctly. Aborting.")
        return False

    word_count = len(text.split())
    print(f" OK ({word_count} words, no loops)")
    return True


# ── TRANSCRIBE ONE PDF ────────────────────────────────────────────────────────

def transcribe_pdf(client: Mistral, pdf_name: str):
    pdf_path = BOOK_DIR / pdf_name
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{pdf_name}_mistral.txt"

    last_done = find_last_completed(output_path)
    if last_done:
        print(f"  Resuming {pdf_name} from spread {last_done + 1}")

    doc = fitz.open(str(pdf_path))
    total = len(doc)

    print(f"\n{'─'*60}")
    print(f"  {pdf_name}  ({total} spreads)  →  {output_path.name}")
    print(f"{'─'*60}")

    mode = "a" if output_path.exists() else "w"
    with open(output_path, mode, encoding="utf-8") as out:
        if mode == "w":
            out.write(f"# Men of Maize — Mistral re-transcription\n# Source: {pdf_name}\n# Model: {MODEL}\n")

        for i in range(total):
            spread_num = i + 1
            if spread_num <= last_done:
                print(f"  Spread {spread_num:3d}/{total}  [skipped]")
                continue

            print(f"  Spread {spread_num:3d}/{total}  … ", end="", flush=True)

            jpeg_bytes = render_spread(doc[i])

            text = None
            for attempt in range(1, 4):
                try:
                    text = call_mistral(client, jpeg_bytes)
                    break
                except Exception as e:
                    if attempt == 3:
                        text = f"[MISTRAL_ERROR: {pdf_name} spread {spread_num}: {e}]"
                    else:
                        time.sleep(10 * attempt)

            write_block(out, pdf_name, spread_num, total, text or "[MISTRAL_ERROR: empty response]")

            if text and "[MISTRAL_ERROR" not in text:
                loop = has_repetition_loop(text)
                if loop:
                    print(f"✗ LOOP — {loop}")
                else:
                    print("✓")
            else:
                print("✗ ERROR")

            if spread_num < total:
                time.sleep(DELAY)

    doc.close()
    print(f"\n  Done: {pdf_name}  ({total} spreads)")
    print(f"  Output: {output_path}\n")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("ERROR: MISTRAL_API_KEY environment variable not set.")
        print('  export MISTRAL_API_KEY="your-key-here"')
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 08_mistral_transcribe.py 26-55.pdf")
        print("  python3 08_mistral_transcribe.py all")
        sys.exit(1)

    client = Mistral(api_key=api_key)

    if not smoke_test(client):
        sys.exit(1)

    target = sys.argv[1]
    pdfs = ALL_PDFS if target == "all" else [target]

    for pdf_name in pdfs:
        transcribe_pdf(client, pdf_name)

    print("All done. Run 09_three_way_compare.py when Qwen is also complete.")


if __name__ == "__main__":
    main()
