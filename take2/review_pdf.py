"""
Men of Maize — PDF review script.
Finds the latest PDF in take2/PDFs/, runs automated checks, and prints a
structured report in the standard review format.

Usage:
    python3 review_pdf.py                  # scans the latest PDF
    python3 review_pdf.py men_of_maize-15.pdf  # scans a specific file
"""

import re
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip install pymupdf")
    sys.exit(1)

# ── CONFIG ────────────────────────────────────────────────────────────────────

PDFS_DIR = Path(__file__).parent / "PDFs"

CHAPTER_HEADERS = {
    "MEN OF MAIZE", "GASPAR ILÓM", "MACHOJÓN",
    "THE DEER OF THE SEVENTH FIRE", "COLONEL CHALO GODOY",
    "MARÍA TECÚN", "COYOTE-POSTMAN", "EPILOGUE",
    "NOTE ON TEXTUAL UNCERTAINTIES",
}

CHAPTER_ORDER = [
    "GASPAR ILÓM", "MACHOJÓN", "THE DEER OF THE SEVENTH FIRE",
    "COLONEL CHALO GODOY", "MARÍA TECÚN", "COYOTE-POSTMAN", "EPILOGUE",
]

# Patterns
_PAGE_MARKER  = re.compile(r'\[Page(?:\s+LEFT|\s+RIGHT)?\s*\d*\]', re.IGNORECASE)
_ORN_DESC     = re.compile(r'\[(?:decorative|ornamental|ornament)\s*(?:symbol|break|element)?\]', re.IGNORECASE)
_UNCERTAINTY  = re.compile(r'[※]')
_QWEN_HEADER  = re.compile(r'\bQwen\s+read\b|\bMistral\s+read\b|\bCurrent\s+text\b', re.IGNORECASE)
_SENT_END     = re.compile(r'[.!?…"\')\]—]\s*$')
_BRACKET_ART  = re.compile(r'\[Page\s*(?:LEFT|RIGHT)?\s*\d+\]', re.IGNORECASE)

# ── HELPERS ───────────────────────────────────────────────────────────────────

def find_latest_pdf() -> Path:
    def _num(p: Path) -> int:
        m = re.search(r'-(\d+)\.pdf$', p.name)
        return int(m.group(1)) if m else 0
    pdfs = sorted(PDFS_DIR.glob("men_of_maize-*.pdf"), key=_num)
    if not pdfs:
        print(f"ERROR: No PDFs found in {PDFS_DIR}")
        sys.exit(1)
    return pdfs[-1]


def get_body_text(page) -> list[str]:
    """Return non-header text blocks for a page."""
    blocks = page.get_text("blocks")
    result = []
    for b in blocks:
        t = b[4].strip()
        if not t:
            continue
        first = t.splitlines()[0].strip()
        if first in CHAPTER_HEADERS or first.isdigit():
            continue
        result.append(t)
    return result


def excerpt(text: str, match_start: int, match_end: int, ctx: int = 40) -> str:
    start = max(0, match_start - ctx)
    end   = min(len(text), match_end + ctx)
    s = text[start:end].replace('\n', ' ').strip()
    if start > 0:
        s = "…" + s
    if end < len(text):
        s = s + "…"
    return s


# ── CHECKS ────────────────────────────────────────────────────────────────────

def check_artifacts(doc) -> list[dict]:
    rows = []
    for pn in range(doc.page_count):
        page   = doc[pn]
        blocks = get_body_text(page)
        full   = " ".join(blocks)

        for m in _PAGE_MARKER.finditer(full):
            rows.append({
                "page": pn + 1,
                "type": "ARTIFACT",
                "excerpt": excerpt(full, m.start(), m.end()),
                "notes": "[Page N] marker in body text",
            })
        for m in _ORN_DESC.finditer(full):
            rows.append({
                "page": pn + 1,
                "type": "ARTIFACT",
                "excerpt": excerpt(full, m.start(), m.end()),
                "notes": "Ornament described as text instead of rendered as image",
            })
        for m in _UNCERTAINTY.finditer(full):
            rows.append({
                "page": pn + 1,
                "type": "ARTIFACT",
                "excerpt": excerpt(full, m.start(), m.end()),
                "notes": "※ uncertainty marker visible to reader",
            })
        for m in _QWEN_HEADER.finditer(full):
            rows.append({
                "page": pn + 1,
                "type": "ARTIFACT",
                "excerpt": excerpt(full, m.start(), m.end()),
                "notes": "AI pipeline metadata (Qwen/Mistral labels) visible",
            })
    return rows


def check_duplicates(doc) -> list[dict]:
    rows = []
    for pn in range(doc.page_count):
        page   = doc[pn]
        blocks = get_body_text(page)
        full   = " ".join(blocks)
        words  = full.split()

        # Sliding window: look for any 10-word sequence that appears twice
        seen: dict[str, int] = {}
        for i in range(len(words) - 10):
            key = " ".join(words[i:i + 10])
            if key in seen and i - seen[key] > 5:
                snippet = key[:80]
                rows.append({
                    "page": pn + 1,
                    "type": "DUPLICATE",
                    "excerpt": snippet + "…",
                    "notes": f"10-word sequence repeated within page",
                })
                break  # one per page is enough
            seen[key] = i
    return rows


def check_fragments(doc) -> list[dict]:
    rows = []
    for pn in range(doc.page_count - 1):
        blocks_this = get_body_text(doc[pn])
        blocks_next = get_body_text(doc[pn + 1])
        if not blocks_this or not blocks_next:
            continue

        last_block = blocks_this[-1].rstrip()
        next_block = blocks_next[0].lstrip()

        last_char  = last_block[-1] if last_block else ''
        next_word  = next_block.split()[0] if next_block.split() else ''

        # Skip if last block is a header / section number / very short
        if last_block.isupper() or len(last_block) < 5:
            continue

        if (not _SENT_END.search(last_block)) and next_word and next_word[0].islower():
            rows.append({
                "page": pn + 1,
                "type": "FRAGMENT",
                "excerpt": f"…{last_block[-60:]} ↦ {next_block[:60]}…",
                "notes": "Sentence appears to continue across page boundary",
            })
    return rows


def check_layout(doc) -> list[dict]:
    rows = []

    # Check chapter pages are odd (right-hand)
    for pn in range(doc.page_count):
        page  = doc[pn]
        lines = [l.strip() for l in page.get_text("text").splitlines() if l.strip()]
        for line in lines[:6]:  # chapter heading is near top
            if line in CHAPTER_ORDER:
                pdf_page = pn + 1
                if pdf_page % 2 == 0:
                    rows.append({
                        "page": pdf_page,
                        "type": "LAYOUT",
                        "excerpt": line,
                        "notes": "Chapter starts on even (left-hand) page — should be odd",
                    })
                break

    # Unexpected blank pages (more than 1 blank in a row)
    blank_run = 0
    for pn in range(doc.page_count):
        text = doc[pn].get_text("text").strip()
        if not text or text.isdigit():
            blank_run += 1
            if blank_run > 1:
                rows.append({
                    "page": pn + 1,
                    "type": "LAYOUT",
                    "excerpt": "(blank)",
                    "notes": f"Multiple consecutive blank pages (run of {blank_run})",
                })
        else:
            blank_run = 0

    return rows


# ── REPORT ────────────────────────────────────────────────────────────────────

def print_report(pdf_path: Path, rows: list[dict], page_count: int):
    counts = {}
    for r in rows:
        counts[r["type"]] = counts.get(r["type"], 0) + 1

    print(f"\n{'='*70}")
    print(f"REVIEW REPORT — {pdf_path.name}")
    print(f"  {page_count} pages   |   {len(rows)} issues found")
    for t, n in sorted(counts.items()):
        print(f"    {t}: {n}")
    print(f"{'='*70}\n")

    if not rows:
        print("No issues found.")
        return

    col_w = [6, 12, 50, 30]
    header = (f"{'PAGE':<{col_w[0]}}  {'TYPE':<{col_w[1]}}  "
              f"{'EXCERPT':<{col_w[2]}}  {'NOTES':<{col_w[3]}}")
    print(header)
    print("-" * (sum(col_w) + 6))

    current_type = None
    for r in sorted(rows, key=lambda x: (x["page"], x["type"])):
        if r["type"] != current_type:
            if current_type is not None:
                print()
            current_type = r["type"]

        exc   = r["excerpt"][:col_w[2] - 1]
        notes = r["notes"][:col_w[3] - 1]
        print(f"{r['page']:<{col_w[0]}}  {r['type']:<{col_w[1]}}  "
              f"{exc:<{col_w[2]}}  {notes}")

    print(f"\n{'='*70}")

    # Verdict
    artifact_n  = counts.get("ARTIFACT", 0)
    duplicate_n = counts.get("DUPLICATE", 0)
    fragment_n  = counts.get("FRAGMENT", 0)
    layout_n    = counts.get("LAYOUT", 0)

    print("\nVERDICT")
    if artifact_n == 0 and duplicate_n == 0 and layout_n == 0 and fragment_n < 5:
        print("  Reader-ready: no blocking issues found.")
    else:
        blockers = []
        if artifact_n:
            blockers.append(f"{artifact_n} artifact(s) (metadata/markers in body text)")
        if duplicate_n:
            blockers.append(f"{duplicate_n} duplicate passage(s)")
        if layout_n:
            blockers.append(f"{layout_n} layout issue(s)")
        if fragment_n >= 5:
            blockers.append(f"{fragment_n} cross-page sentence fragments")
        print("  NOT reader-ready. Fix before publishing:")
        for b in blockers:
            print(f"    • {b}")
    print()


def save_report(pdf_path: Path, rows: list[dict], page_count: int):
    out = pdf_path.with_suffix(".review.txt")
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_report(pdf_path, rows, page_count)
    out.write_text(buf.getvalue(), encoding="utf-8")
    print(f"Report saved to: {out.name}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        pdf_path = PDFS_DIR / sys.argv[1]
        if not pdf_path.exists():
            pdf_path = Path(sys.argv[1])
    else:
        pdf_path = find_latest_pdf()

    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found.")
        sys.exit(1)

    print(f"Scanning: {pdf_path.name}")
    doc = fitz.open(str(pdf_path))

    print("  Checking for artifacts …")
    artifact_rows = check_artifacts(doc)

    print("  Checking for duplicates …")
    dup_rows = check_duplicates(doc)

    print("  Checking for cross-page fragments …")
    frag_rows = check_fragments(doc)

    print("  Checking layout …")
    layout_rows = check_layout(doc)

    all_rows = artifact_rows + dup_rows + frag_rows + layout_rows
    print_report(pdf_path, all_rows, doc.page_count)
    save_report(pdf_path, all_rows, doc.page_count)


if __name__ == "__main__":
    main()
