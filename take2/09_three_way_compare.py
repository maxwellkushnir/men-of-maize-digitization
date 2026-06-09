"""
Men of Maize — Check 1: Three-way comparison
Compares the assembled Claude text against fresh Qwen and Mistral transcriptions.

Bucketing strategy:
  - Uses Claude's assembled page markers to define ~50-page buckets (1–50, 51–100, …)
  - Finds the corresponding proportional word-window in Qwen and Mistral outputs
    (by word-count fraction, since those texts won't have identical page numbering)
  - Computes pairwise word-sequence similarity (SequenceMatcher ratio) for each bucket
  - The Qwen vs Mistral column is the key arbitration signal: if both independent
    models agree but diverge from Claude, Claude's text is the suspect.

Usage:
    python3 09_three_way_compare.py

Prerequisites:
    07_qwen_transcribe.py all        ← must be complete
    08_mistral_transcribe.py all     ← must be complete

Output:
    take2/output/three_way_report.html
"""

import difflib
import re
import unicodedata
from pathlib import Path

# ── PATHS ─────────────────────────────────────────────────────────────────────

BASE        = Path(__file__).parent
OUTPUT_DIR  = BASE / "output"
CLAUDE_FILE = OUTPUT_DIR / "men_of_maize_clean.txt"
QWEN_DIR    = OUTPUT_DIR / "qwen_raw"
MISTRAL_DIR = OUTPUT_DIR / "mistral_raw"
HTML_OUT    = OUTPUT_DIR / "three_way_report.html"

ALL_PDFS    = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

# Pages per bucket for the comparison table
BUCKET_SIZE = 50

# Similarity threshold below which a bucket is flagged
FLAG_THRESHOLD = 0.80

# ── TEXT EXTRACTION ───────────────────────────────────────────────────────────

NOISE_RE = re.compile(
    r"^(#\s|<<< SPREAD|={3,}|MEN OF MAIZE\s*$|MIGUEL|"
    r"\[Page shows|\[Page is blank|\[Page -|\[Left page|\[Right page|"
    r"\[EXTRACTION FAILED|\[NEEDS_REVIEW|\[QWEN_ERROR|\[MISTRAL_ERROR|"
    r"by Miguel|Translated by|Delacorte Press|\[Assembly note)"
    , re.IGNORECASE
)

def strip_accents(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")

def tokenize_text(text: str) -> list[str]:
    """Strip all structural markers and return lowercase word tokens."""
    tokens = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if NOISE_RE.search(line):
            continue
        line = re.sub(r"\[[^\]]{0,120}\]", " ", line)   # remove [...] blocks
        line = re.sub(r"^#+\s*", "", line)               # markdown headers
        line = line.replace("—", " ").replace("–", " ")
        line = strip_accents(line)
        tokens.extend(w.lower() for w in re.findall(r"\b[a-zA-Z']+\b", line) if w)
    return tokens


# ── CLAUDE PAGE EXTRACTION ────────────────────────────────────────────────────

PAGE_RE = re.compile(r"^\[Page\s+(\d+)(?:\s+\(inferred\))?\]", re.MULTILINE)

def extract_claude_pages(text: str) -> dict[int, str]:
    pages = {}
    matches = list(PAGE_RE.finditer(text))
    for i, m in enumerate(matches):
        pn = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        pages[pn] = text[start:end].strip()
    return pages


# ── LOAD RAW FILES ────────────────────────────────────────────────────────────

def load_raw_dir(directory: Path, suffix: str) -> list[str]:
    """Load all raw txt files from a directory, in source-PDF order, return as token list."""
    tokens = []
    for pdf_name in ALL_PDFS:
        path = directory / f"{pdf_name}_{suffix}.txt"
        if not path.exists():
            print(f"  WARNING: {path.name} not found — skipping")
            continue
        tokens.extend(tokenize_text(path.read_text(encoding="utf-8")))
    return tokens


# ── WINDOWED SIMILARITY ───────────────────────────────────────────────────────

def similarity(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()

def get_window(tokens: list[str], frac_start: float, frac_end: float) -> list[str]:
    """Extract the proportional slice of a token list."""
    n = len(tokens)
    lo = int(frac_start * n)
    hi = int(frac_end * n)
    return tokens[lo:hi]


# ── BUILD REPORT ─────────────────────────────────────────────────────────────

def build_report(claude_pages, qwen_tokens, mistral_tokens):
    if not claude_pages:
        return [], 0

    all_page_nums = sorted(claude_pages.keys())
    min_page = all_page_nums[0]
    max_page = all_page_nums[-1]

    # Total Claude tokens (for proportion calculation)
    claude_all_tokens = tokenize_text(CLAUDE_FILE.read_text(encoding="utf-8"))
    total_claude = len(claude_all_tokens)

    # Build (start_page, end_page, claude_tokens) buckets
    buckets = []
    page = min_page
    while page <= max_page:
        end = min(page + BUCKET_SIZE - 1, max_page)
        chunk_text = " ".join(
            claude_pages[p] for p in range(page, end + 1) if p in claude_pages
        )
        c_tokens = tokenize_text(chunk_text)

        # Approximate position of this bucket in the full Claude token stream
        # Use word count up to this point as a fraction
        words_before = sum(
            len(tokenize_text(claude_pages[p]))
            for p in all_page_nums if p < page
        )
        words_in_bucket = len(c_tokens)
        frac_start = words_before / total_claude if total_claude else 0
        frac_end   = (words_before + words_in_bucket) / total_claude if total_claude else 1

        q_tokens = get_window(qwen_tokens, frac_start, frac_end)
        m_tokens = get_window(mistral_tokens, frac_start, frac_end)

        buckets.append({
            "pages":     f"{page}–{end}",
            "cq":        similarity(c_tokens, q_tokens),
            "cm":        similarity(c_tokens, m_tokens),
            "qm":        similarity(q_tokens, m_tokens),
            "c_words":   len(c_tokens),
            "flagged":   False,
        })
        page = end + 1

    # Flag any bucket below threshold on any column
    for b in buckets:
        if min(b["cq"], b["cm"], b["qm"]) < FLAG_THRESHOLD:
            b["flagged"] = True

    return buckets, total_claude


def write_html(buckets, total_claude, qwen_total, mistral_total, path: Path):
    flagged_count = sum(1 for b in buckets if b["flagged"])

    rows = []
    for b in buckets:
        flag = " ⚠" if b["flagged"] else ""
        row_class = ' class="flagged"' if b["flagged"] else ""

        def pct_cell(val):
            col = "red" if val < FLAG_THRESHOLD else ("orange" if val < 0.90 else "green")
            return f'<td style="color:{col};font-weight:bold">{val:.0%}</td>'

        rows.append(f"""
  <tr{row_class}>
    <td>{b["pages"]}{flag}</td>
    {pct_cell(b["cq"])}
    {pct_cell(b["cm"])}
    {pct_cell(b["qm"])}
    <td style="color:#888;font-size:11px">{b["c_words"]:,}</td>
  </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Men of Maize — Three-Way Comparison</title>
<style>
  body {{ font-family: Georgia, serif; font-size: 13px; margin: 2em; color: #222; }}
  h1 {{ font-size: 1.4em; }}
  h2 {{ font-size: 1.1em; margin-top: 2em; border-bottom: 1px solid #ccc; }}
  table {{ border-collapse: collapse; width: 600px; margin-bottom: 2em; }}
  th, td {{ padding: 5px 12px; border: 1px solid #ddd; text-align: center; }}
  th {{ background: #f0f0f0; }}
  td:first-child {{ text-align: left; }}
  tr.flagged {{ background: #fff8e1; }}
  .note {{ color: #555; font-size: 12px; margin-top: 0.5em; }}
</style>
</head>
<body>
<h1>Men of Maize — Three-Way Transcription Comparison</h1>

<h2>Overview</h2>
<table>
  <tr><th>Source</th><th>Total words</th></tr>
  <tr><td>Claude (assembled)</td><td>{total_claude:,}</td></tr>
  <tr><td>Qwen</td><td>{qwen_total:,}</td></tr>
  <tr><td>Mistral (Pixtral)</td><td>{mistral_total:,}</td></tr>
</table>

<h2>Bucket-by-Bucket Results</h2>
<p class="note">
  Similarity = word-sequence match (SequenceMatcher ratio). Qwen and Mistral windows are
  matched to each Claude bucket by proportional word-count position.<br>
  <strong>Qwen vs Mistral</strong> is the arbitration column — if both independent models
  agree but Claude diverges, Claude's text is suspect.<br>
  Flagged (⚠) = any column below {FLAG_THRESHOLD:.0%}. Cross-check against original photographs.
</p>
<table>
  <thead>
    <tr>
      <th>Pages (Claude ref.)</th>
      <th>Claude vs Qwen</th>
      <th>Claude vs Mistral</th>
      <th>Qwen vs Mistral</th>
      <th>Claude words</th>
    </tr>
  </thead>
  <tbody>{"".join(rows)}</tbody>
</table>

<p><strong>{flagged_count} bucket(s) flagged</strong> (below {FLAG_THRESHOLD:.0%} on at least one column).</p>
<p class="note">
  Also consult <code>t1_vs_t2_divergences.md</code> in the project root for specific
  word-level differences flagged during the Check 2 pass (covers ~0–30% of the book).
</p>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    # Check inputs exist
    if not CLAUDE_FILE.exists():
        print(f"ERROR: {CLAUDE_FILE} not found. Run 02_assemble.py first.")
        return

    qwen_files    = [QWEN_DIR    / f"{p}_qwen.txt"    for p in ALL_PDFS]
    mistral_files = [MISTRAL_DIR / f"{p}_mistral.txt" for p in ALL_PDFS]

    missing_qwen    = [f for f in qwen_files    if not f.exists()]
    missing_mistral = [f for f in mistral_files if not f.exists()]

    if missing_qwen:
        print("Missing Qwen output files:")
        for f in missing_qwen:
            print(f"  {f.name}")
        print("Run: python3 07_qwen_transcribe.py all")
        return

    if missing_mistral:
        print("Missing Mistral output files:")
        for f in missing_mistral:
            print(f"  {f.name}")
        print("Run: python3 08_mistral_transcribe.py all")
        return

    print("Loading Claude assembled text …")
    claude_text = CLAUDE_FILE.read_text(encoding="utf-8")
    claude_pages = extract_claude_pages(claude_text)
    print(f"  {len(claude_pages)} pages found")

    print("Loading Qwen output …")
    qwen_tokens = load_raw_dir(QWEN_DIR, "qwen")
    print(f"  {len(qwen_tokens):,} tokens")

    print("Loading Mistral output …")
    mistral_tokens = load_raw_dir(MISTRAL_DIR, "mistral")
    print(f"  {len(mistral_tokens):,} tokens")

    print(f"Computing {BUCKET_SIZE}-page buckets …")
    buckets, total_claude = build_report(claude_pages, qwen_tokens, mistral_tokens)

    print(f"\nResults ({len(buckets)} buckets):")
    print(f"  {'Pages':<12} {'C vs Q':>8} {'C vs M':>8} {'Q vs M':>8}")
    print(f"  {'─'*42}")
    for b in buckets:
        flag = " ⚠" if b["flagged"] else ""
        print(f"  {b['pages']:<12} {b['cq']:>8.1%} {b['cm']:>8.1%} {b['qm']:>8.1%}{flag}")

    flagged = sum(1 for b in buckets if b["flagged"])
    print(f"\n  {flagged} bucket(s) flagged (below {FLAG_THRESHOLD:.0%})")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_html(buckets, total_claude, len(qwen_tokens), len(mistral_tokens), HTML_OUT)
    print(f"\nHTML report: {HTML_OUT}")

    import subprocess
    subprocess.run(["open", str(HTML_OUT)])


if __name__ == "__main__":
    main()
