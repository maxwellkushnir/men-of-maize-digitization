"""
Men of Maize — Stage 1c: Mistral OCR for remaining NEEDS_REVIEW spreads

This script:
  1. Reads all raw txt files and finds every remaining NEEDS_REVIEW spread
  2. Builds a single PDF of just those pages from the source PDFs
  3. Uploads that PDF to Mistral OCR (one API call, no content filtering)
  4. Maps each returned page back to the correct raw txt file and replaces
     the NEEDS_REVIEW block with the transcribed text

Why Mistral OCR instead of Claude for these?
  - Claude's content filter randomly blocks spreads even with benign content
  - Mistral OCR is a purpose-built document reader with no content policy
  - Cost: ~$0.001 per page — the 49 remaining spreads cost under $0.10 total

Usage:
    pip install mistralai
    export MISTRAL_API_KEY="your-key-here"
    python3 06_mistral_ocr.py

Requirements:
    pip install mistralai PyMuPDF
"""

import os
import re
import base64
import tempfile
import fitz                          # PyMuPDF
from pathlib import Path
from mistralai import Mistral

# ── CONFIGURATION ─────────────────────────────────────────────────────────────

BOOK_DIR   = Path(__file__).parent.parent   # Raw Data (to use)/
OUTPUT_DIR = Path(__file__).parent / "output"
MODEL      = "mistral-ocr-latest"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

# ── STEP 1: Find all remaining NEEDS_REVIEW spreads ───────────────────────────

def find_needs_review_all():
    """
    Returns a list of dicts, one per blocked spread, in order:
      { "pdf_name": "108-.pdf", "spread_num": 16, "total": 68 }
    This list defines the page order inside the combined PDF we'll build.
    """
    blocked = []
    pattern = re.compile(r'\[NEEDS_REVIEW: (.+?) spread (\d+)')

    for pdf_name in ALL_PDFS:
        raw_path = OUTPUT_DIR / f"{pdf_name}_raw.txt"
        if not raw_path.exists():
            continue
        content = raw_path.read_text(encoding="utf-8")

        # Also grab total page count from any SPREAD_START line for this PDF
        total_match = re.search(r'total="(\d+)"', content)
        total = int(total_match.group(1)) if total_match else 0

        for m in pattern.finditer(content):
            blocked.append({
                "pdf_name":  m.group(1),
                "spread_num": int(m.group(2)),
                "total":      total,
            })

    return blocked


# ── STEP 2: Build a combined PDF of just the blocked spreads ──────────────────

def build_combined_pdf(blocked, out_path):
    """
    Extracts the relevant pages from source PDFs and saves them as one PDF.
    Returns the same blocked list (unchanged) — the page index in the combined
    PDF matches the index in the list.
    """
    combined = fitz.open()

    open_docs = {}   # cache open fitz documents to avoid reopening repeatedly
    try:
        for entry in blocked:
            pdf_name   = entry["pdf_name"]
            spread_num = entry["spread_num"]

            if pdf_name not in open_docs:
                open_docs[pdf_name] = fitz.open(str(BOOK_DIR / pdf_name))

            doc      = open_docs[pdf_name]
            page_idx = spread_num - 1   # spread numbers are 1-indexed
            combined.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
    finally:
        for doc in open_docs.values():
            doc.close()

    combined.save(str(out_path))
    combined.close()
    print(f"  Built combined PDF: {out_path.name}  ({len(blocked)} pages)")


# ── STEP 3: Send to Mistral OCR ───────────────────────────────────────────────

def run_mistral_ocr(client, pdf_path):
    """
    Encodes the PDF as base64 and sends it to Mistral OCR inline.
    Each item in response.pages corresponds to one page (= one spread).
    """
    print(f"  Encoding PDF as base64 …")
    with open(pdf_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    data_uri = f"data:application/pdf;base64,{b64}"
    print(f"  Sending to Mistral OCR …")
    result = client.ocr.process(
        model=MODEL,
        document={"type": "document_url", "document_url": data_uri},
    )
    return result


# ── STEP 4: Write results back into the raw txt files ─────────────────────────

def replace_block(raw_path, pdf_name, spread_num, total, new_content):
    """Replace a NEEDS_REVIEW block in-place with the OCR text."""
    content = raw_path.read_text(encoding="utf-8")

    start_marker = f'<<< SPREAD_START pdf="{pdf_name}" spread="{spread_num}" total="{total}" >>>'
    end_marker   = "<<< SPREAD_END >>>"

    start_idx = content.find(start_marker)
    if start_idx == -1:
        print(f"    WARNING: block for spread {spread_num} not found in {raw_path.name}")
        return False

    end_idx = content.find(end_marker, start_idx)
    if end_idx == -1:
        print(f"    WARNING: end marker missing for spread {spread_num}")
        return False

    end_idx += len(end_marker)
    new_block = f'{start_marker}\n{new_content.strip()}\n{end_marker}'

    updated = content[:start_idx] + new_block + content[end_idx:]
    raw_path.write_text(updated, encoding="utf-8")
    return True


def write_results(blocked, ocr_response):
    """
    Map each page in the OCR response back to its raw txt file and replace
    the NEEDS_REVIEW block. Page index in the response = index in blocked list.
    """
    recovered = 0
    pages = ocr_response.pages

    if len(pages) != len(blocked):
        print(f"  WARNING: OCR returned {len(pages)} pages but expected {len(blocked)}.")
        print(f"  Will write as many as match.")

    for i, entry in enumerate(blocked):
        if i >= len(pages):
            print(f"  ⚠ No OCR result for {entry['pdf_name']} spread {entry['spread_num']}")
            continue

        page      = pages[i]
        text      = page.markdown.strip() if page.markdown else ""
        pdf_name  = entry["pdf_name"]
        spread_num = entry["spread_num"]
        total      = entry["total"]

        if not text:
            print(f"  ⚠ {pdf_name} spread {spread_num:3d} — empty result from Mistral")
            continue

        raw_path = OUTPUT_DIR / f"{pdf_name}_raw.txt"
        ok = replace_block(raw_path, pdf_name, spread_num, total, text)

        if ok:
            recovered += 1
            print(f"  ✓ {pdf_name} spread {spread_num:3d} — recovered ({len(text)} chars)")
        else:
            print(f"  ✗ {pdf_name} spread {spread_num:3d} — replace failed")

    return recovered


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("ERROR: MISTRAL_API_KEY environment variable not set.")
        print("Get a key at https://console.mistral.ai, then run:")
        print('  export MISTRAL_API_KEY="your-key-here"')
        raise SystemExit(1)

    print("\n Men of Maize — Mistral OCR recovery")
    print("=" * 50)

    # Step 1
    print("\nStep 1: Finding remaining NEEDS_REVIEW spreads …")
    blocked = find_needs_review_all()
    if not blocked:
        print("  No NEEDS_REVIEW spreads found — nothing to do!")
        print("  Run 02_assemble.py next.")
        return

    print(f"  Found {len(blocked)} blocked spread(s):")
    from collections import Counter
    counts = Counter(e["pdf_name"] for e in blocked)
    for pdf_name in ALL_PDFS:
        if pdf_name in counts:
            print(f"    {pdf_name}: {counts[pdf_name]}")

    # Step 2
    print("\nStep 2: Building combined PDF …")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        combined_path = Path(tmp.name)
    build_combined_pdf(blocked, combined_path)

    # Step 3
    print("\nStep 3: Sending to Mistral OCR …")
    client = Mistral(api_key=api_key)
    try:
        ocr_result = run_mistral_ocr(client, combined_path)
        print(f"  OCR complete — {len(ocr_result.pages)} page(s) returned")
    finally:
        combined_path.unlink(missing_ok=True)   # delete temp file

    # Step 4
    print("\nStep 4: Writing results back into raw txt files …")
    recovered = write_results(blocked, ocr_result)

    # Summary
    print(f"\n{'=' * 50}")
    print(f"  Done: {recovered}/{len(blocked)} spread(s) recovered")
    remaining = len(blocked) - recovered
    if remaining > 0:
        print(f"  Still missing: {remaining} spread(s) — may need manual transcription")
    else:
        print(f"  All gaps filled!")
    print(f"\n  Next step: run 02_assemble.py to regenerate clean text + JSON")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    main()
