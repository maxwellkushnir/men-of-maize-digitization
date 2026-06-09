"""
Men of Maize - Text Extraction Script
Extracts text from photographed book spread PDFs using Claude's vision API.

Usage:
    python extract_text.py

Requirements:
    pip install anthropic PyMuPDF
    export ANTHROPIC_API_KEY="your-key-here"
"""

import anthropic
import base64
import time
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF")
    sys.exit(1)


# ── CONFIGURATION ─────────────────────────────────────────────────────────────
# Update this path to wherever your PDFs live on your Mac.
BOOK_DIR = Path("/Users/Max/Documents/Claude Code/Men of Maize/Divided")

# Output file (will be created in the same folder as your PDFs)
OUTPUT_FILE = BOOK_DIR / "men_of_maize_full_text.txt"

# PDFs in reading order (skip any you don't have)
PDF_FILES = [
    "1.pdf",
    "2-25.pdf",
    "26-55.pdf",
    "56-75.pdf",
    "76-107.pdf",
    "108-.pdf",
]

# Seconds to wait between API calls — keeps you within rate limits
DELAY_BETWEEN_CALLS = 3

# Claude model to use
MODEL = "claude-sonnet-4-5"

# ── PROMPT ────────────────────────────────────────────────────────────────────
# This is the instruction sent to Claude for every spread photo.
EXTRACTION_PROMPT = """This is a photograph of an open book showing two pages side by side.
Please transcribe ALL visible text accurately, reading the LEFT page first, then the RIGHT page.

Follow these rules exactly:
1. Preserve chapter headings in CAPS (e.g. GASPAR ILÓM, MACHOJÓN, THE DEER OF THE SEVENTH FIRE)
2. Preserve Roman numeral section headings (I, II, III, IV, etc.)
3. Preserve page numbers — output them on their own line as: [Page N]
4. When you see the small square decorative dividers between sections, output: [section break]
5. Preserve all paragraph breaks with a blank line between paragraphs
6. Preserve italicized text (song lyrics, poems, dedications) on separate lines
7. If text disappears into the spine gutter, use [...] to mark the gap
8. Do NOT include descriptions of the photo, hands, tiles, or anything non-textual
9. Do NOT add commentary — output only the transcribed text

Transcribe now:"""


# ── HELPERS ───────────────────────────────────────────────────────────────────

def pdf_page_to_jpeg(page) -> bytes:
    """Render a single PDF page to a high-quality JPEG byte string."""
    # 2x zoom gives ~150 dpi → good enough for OCR, not wasteful on tokens
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    return pix.tobytes("jpeg")


def call_claude(client: anthropic.Anthropic, jpeg_bytes: bytes) -> str:
    """Send one spread image to Claude and return the extracted text."""
    b64 = base64.standard_b64encode(jpeg_bytes).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )
    return response.content[0].text


def process_pdf(client: anthropic.Anthropic, pdf_path: Path, out) -> int:
    """
    Open a PDF, process each page (spread photo) with Claude,
    and write results to the output file handle `out`.
    Returns the number of spreads processed.
    """
    doc = fitz.open(str(pdf_path))
    total = len(doc)
    print(f"\n{'─'*60}")
    print(f"  PDF: {pdf_path.name}  ({total} spread photo{'s' if total != 1 else ''})")
    print(f"{'─'*60}")

    for i in range(total):
        spread_num = i + 1
        print(f"  Spread {spread_num}/{total} … ", end="", flush=True)

        # Render the page to JPEG
        jpeg_bytes = pdf_page_to_jpeg(doc[i])

        # Call Claude with retry on transient errors
        for attempt in range(1, 4):
            try:
                text = call_claude(client, jpeg_bytes)
                break
            except anthropic.RateLimitError:
                wait = 30 * attempt
                print(f"\n    Rate limit hit — waiting {wait}s …", end="", flush=True)
                time.sleep(wait)
            except anthropic.APIError as e:
                if attempt == 3:
                    print(f"\n    ERROR after 3 attempts: {e}")
                    text = f"[EXTRACTION FAILED for {pdf_path.name} spread {spread_num}: {e}]"
                    break
                time.sleep(10 * attempt)

        # Write a clear separator so you can find individual spreads later
        out.write(f"\n\n{'━'*60}\n")
        out.write(f"  Source: {pdf_path.name}  |  Spread {spread_num}/{total}\n")
        out.write(f"{'━'*60}\n\n")
        out.write(text.strip())
        out.write("\n")
        out.flush()  # Save after every spread — so you don't lose work if it crashes

        print("✓")

        if spread_num < total:
            time.sleep(DELAY_BETWEEN_CALLS)

    doc.close()
    return total


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("\n╔══════════════════════════════════════════════╗")
    print("║   Men of Maize — Text Extraction             ║")
    print("╚══════════════════════════════════════════════╝")

    # Check that the book directory exists
    if not BOOK_DIR.exists():
        print(f"\nERROR: Book directory not found:\n  {BOOK_DIR}")
        print("Please update the BOOK_DIR variable at the top of this script.")
        sys.exit(1)

    # Build the list of PDFs that actually exist
    pdfs_to_process = []
    for name in PDF_FILES:
        p = BOOK_DIR / name
        if p.exists():
            pdfs_to_process.append(p)
        else:
            print(f"  WARNING: {name} not found — skipping.")

    if not pdfs_to_process:
        print("\nERROR: No PDFs found. Check BOOK_DIR and PDF_FILES in the script.")
        sys.exit(1)

    print(f"\nFound {len(pdfs_to_process)} PDF(s) to process.")
    print(f"Output → {OUTPUT_FILE}\n")

    # Initialise the Anthropic client (reads ANTHROPIC_API_KEY from environment)
    try:
        client = anthropic.Anthropic()
    except anthropic.AuthenticationError:
        print("ERROR: ANTHROPIC_API_KEY is missing or invalid.")
        print("Run:  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    # Open output file and write header
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("MEN OF MAIZE\n")
        out.write("by Miguel Ángel Asturias\n")
        out.write("Translated from the Spanish by Gerald Martin\n")
        out.write("(Delacorte Press / Seymour Lawrence, 1975)\n")
        out.write("\n" + "═" * 60 + "\n")
        out.write("Digitized with Claude claude-sonnet-4-20250514 vision API\n")
        out.write("═" * 60 + "\n")

        total_spreads = 0
        for pdf_path in pdfs_to_process:
            total_spreads += process_pdf(client, pdf_path, out)

        out.write(f"\n\n{'═'*60}\n")
        out.write(f"END OF TEXT  |  {total_spreads} spreads processed\n")
        out.write(f"{'═'*60}\n")

    print(f"\n{'═'*60}")
    print(f"  Done!  {total_spreads} spreads processed.")
    print(f"  Text saved to:")
    print(f"  {OUTPUT_FILE}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
