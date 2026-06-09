"""
Men of Maize — Check 1: Qwen blind re-transcription
Independent spread-by-spread transcription using Qwen3-VL via DashScope API.
Output is kept entirely separate from the Claude pipeline.

Usage:
    pip install openai PyMuPDF
    export DASHSCOPE_API_KEY="your-key-here"
    python3 07_qwen_transcribe.py 26-55.pdf      # one PDF at a time
    python3 07_qwen_transcribe.py all            # all 5 body PDFs in order

Output per PDF: take2/output/qwen_raw/<pdf_name>_qwen.txt
Resume-safe: re-running the same command skips already-completed spreads.

Requirements:
    pip install openai PyMuPDF
"""

import base64
import os
import re
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)

# ── CONFIGURATION ─────────────────────────────────────────────────────────────

BOOK_DIR   = Path(__file__).parent.parent          # Raw Data (to use)/
OUTPUT_DIR = Path(__file__).parent / "output" / "qwen_raw"
MODEL      = "qwen3-vl-plus"                        # DashScope model name
ZOOM       = 3.0                                   # same as Claude script
MAX_TOKENS = 4096
DELAY      = 1                                     # seconds between calls

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


def call_qwen(client: OpenAI, jpeg_bytes: bytes) -> str:
    b64 = base64.standard_b64encode(jpeg_bytes).decode()
    response = client.chat.completions.create(
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


# ── TRANSCRIBE ONE PDF ────────────────────────────────────────────────────────

def transcribe_pdf(client: OpenAI, pdf_name: str):
    pdf_path = BOOK_DIR / pdf_name
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{pdf_name}_qwen.txt"

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
            out.write(f"# Men of Maize — Qwen re-transcription\n# Source: {pdf_name}\n# Model: {MODEL}\n")

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
                    text = call_qwen(client, jpeg_bytes)
                    break
                except Exception as e:
                    if attempt == 3:
                        text = f"[QWEN_ERROR: {pdf_name} spread {spread_num}: {e}]"
                    else:
                        time.sleep(10 * attempt)

            write_block(out, pdf_name, spread_num, total, text or "[QWEN_ERROR: empty response]")

            if text and "[QWEN_ERROR" not in text:
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
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("ERROR: DASHSCOPE_API_KEY environment variable not set.")
        print('  export DASHSCOPE_API_KEY="your-key-here"')
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 07_qwen_transcribe.py 26-55.pdf")
        print("  python3 07_qwen_transcribe.py all")
        sys.exit(1)

    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1",
    )

    target = sys.argv[1]
    pdfs = ALL_PDFS if target == "all" else [target]

    for pdf_name in pdfs:
        transcribe_pdf(client, pdf_name)

    print("All done. Run 09_three_way_compare.py when Mistral is also complete.")


if __name__ == "__main__":
    main()
