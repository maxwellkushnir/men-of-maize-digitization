"""
Men of Maize — Stage 4: QA Comparison
Word-for-word diff of Take 2 output vs. Take 1's partial output (~70%).

Usage:
    python3 04_compare.py

Outputs:
    output/comparison_report.html   (open in a browser)
"""

import difflib
import re
from pathlib import Path

OUTPUT_DIR   = Path(__file__).parent / "output"
TAKE1_FILE   = Path(__file__).parent.parent.parent / "Take 1" / "men_of_maize_full_text.txt"
TAKE2_FILE   = OUTPUT_DIR / "men_of_maize_clean.txt"
REPORT_FILE  = OUTPUT_DIR / "comparison_report.html"

# Similarity thresholds
GOOD_MATCH_THRESHOLD       = 0.92
MINOR_DIVERGENCE_THRESHOLD = 0.70

# ── PARSING ───────────────────────────────────────────────────────────────────

PAGE_RE = re.compile(r"^\[Page\s+(\d+)(?:\s+\(inferred\))?\]", re.MULTILINE)


def extract_pages(text: str) -> dict:
    """Return {page_num: content_string} from a text file using [Page N] markers."""
    pages = {}
    matches = list(PAGE_RE.finditer(text))
    for i, m in enumerate(matches):
        page_num = int(m.group(1))
        start = m.end()
        end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        pages[page_num] = content
    return pages


def page_status(content: str) -> str:
    if "[EXTRACTION FAILED" in content or "[NEEDS_REVIEW" in content or "[NEEDS MANUAL TRANSCRIPTION" in content:
        return "missing"
    return "present"


def tokenize(text: str) -> list:
    return re.findall(r"\b\w+\b", text.lower())

# ── DIFF HTML ─────────────────────────────────────────────────────────────────

def word_diff_html(text1: str, text2: str) -> str:
    words1 = tokenize(text1)
    words2 = tokenize(text2)
    sm = difflib.SequenceMatcher(None, words1, words2, autojunk=False)
    parts = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            parts.append(f'<span class="match">{" ".join(words1[i1:i2])}</span> ')
        elif tag == "replace":
            parts.append(f'<span class="del">{" ".join(words1[i1:i2])}</span> ')
            parts.append(f'<span class="ins">{" ".join(words2[j1:j2])}</span> ')
        elif tag == "delete":
            parts.append(f'<span class="del">{" ".join(words1[i1:i2])}</span> ')
        elif tag == "insert":
            parts.append(f'<span class="ins">{" ".join(words2[j1:j2])}</span> ')
    return "".join(parts)

# ── REPORT ────────────────────────────────────────────────────────────────────

def classify(page_num: int, t1: dict, t2: dict) -> tuple:
    """Return (status_label, ratio, t1_content, t2_content)."""
    in_t1 = page_num in t1
    in_t2 = page_num in t2
    c1 = t1.get(page_num, "")
    c2 = t2.get(page_num, "")

    if not in_t1 and not in_t2:
        return "orphan", 0.0, c1, c2
    if not in_t1:
        return "orphan_t2_only", 0.0, c1, c2
    if not in_t2:
        return "orphan_t1_only", 0.0, c1, c2

    s1 = page_status(c1)
    s2 = page_status(c2)
    if s1 == "missing" or s2 == "missing":
        return "one_side_missing", 0.0, c1, c2

    words1 = tokenize(c1)
    words2 = tokenize(c2)
    if not words1 and not words2:
        return "good_match", 1.0, c1, c2
    if not words1 or not words2:
        return "significant_divergence", 0.0, c1, c2

    ratio = difflib.SequenceMatcher(None, words1, words2, autojunk=False).ratio()
    if ratio >= GOOD_MATCH_THRESHOLD:
        return "good_match", ratio, c1, c2
    elif ratio >= MINOR_DIVERGENCE_THRESHOLD:
        return "minor_divergence", ratio, c1, c2
    else:
        return "significant_divergence", ratio, c1, c2


def build_report(t1_pages: dict, t2_pages: dict, needs_review_list: list) -> str:
    all_pages = sorted(set(t1_pages) | set(t2_pages))
    results = []
    for pn in all_pages:
        status, ratio, c1, c2 = classify(pn, t1_pages, t2_pages)
        results.append((pn, status, ratio, c1, c2))

    counts = {k: 0 for k in ["good_match", "minor_divergence", "significant_divergence",
                               "one_side_missing", "orphan_t1_only", "orphan_t2_only"]}
    for _, status, _, _, _ in results:
        counts[status] = counts.get(status, 0) + 1

    total_comparable = counts["good_match"] + counts["minor_divergence"] + counts["significant_divergence"]
    pct_good = (counts["good_match"] / total_comparable * 100) if total_comparable else 0

    # ── HTML ──────────────────────────────────────────────────────────────────
    rows_html = []
    for pn, status, ratio, c1, c2 in results:
        if status == "good_match":
            badge = f'<span class="badge good">✓ {ratio:.0%}</span>'
            detail = ""
        elif status == "minor_divergence":
            badge = f'<span class="badge minor">~ {ratio:.0%}</span>'
            detail = f'<div class="diff">{word_diff_html(c1, c2)}</div>'
        elif status == "significant_divergence":
            badge = f'<span class="badge sig">✗ {ratio:.0%}</span>'
            detail = f'<div class="diff">{word_diff_html(c1, c2)}</div>'
        elif status == "one_side_missing":
            badge = '<span class="badge missing">⚠ missing</span>'
            detail = ""
        else:
            badge = f'<span class="badge orphan">{status}</span>'
            detail = ""

        rows_html.append(f"""
      <tr>
        <td class="pn">{pn}</td>
        <td>{badge}</td>
        <td>{detail}</td>
      </tr>""")

    nr_rows = ""
    for item in needs_review_list:
        src = item.get("source_pdf", "?")
        num = item.get("spread_number", "?")
        pgs = item.get("estimated_pages", [])
        jpg = item.get("failed_jpeg_path", "")
        nr_rows += f"""
      <tr>
        <td>{src}</td>
        <td>Spread {num}</td>
        <td>~pages {pgs}</td>
        <td><a href="{jpg}">view JPEG</a></td>
      </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Men of Maize — QA Comparison Report</title>
<style>
  body {{ font-family: Georgia, serif; font-size: 13px; margin: 2em; color: #222; }}
  h1 {{ font-size: 1.4em; }}
  h2 {{ font-size: 1.1em; margin-top: 2em; border-bottom: 1px solid #ccc; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2em; }}
  th, td {{ padding: 4px 8px; border: 1px solid #ddd; vertical-align: top; }}
  th {{ background: #f0f0f0; text-align: left; }}
  .pn {{ width: 4em; text-align: right; font-weight: bold; }}
  .badge {{ display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 11px; font-family: monospace; }}
  .good  {{ background: #d4edda; color: #155724; }}
  .minor {{ background: #fff3cd; color: #856404; }}
  .sig   {{ background: #f8d7da; color: #721c24; }}
  .missing {{ background: #e2e3e5; color: #383d41; }}
  .orphan {{ background: #cce5ff; color: #004085; }}
  .diff {{ font-size: 11px; font-family: monospace; max-height: 120px; overflow-y: auto; }}
  .match {{ color: #555; }}
  .del   {{ background: #fdd; color: #900; text-decoration: line-through; margin: 0 1px; }}
  .ins   {{ background: #dfd; color: #060; margin: 0 1px; }}
  .summary-table td {{ font-size: 13px; }}
  .pct {{ font-size: 1.5em; font-weight: bold; color: {'#155724' if pct_good >= 85 else '#856404' if pct_good >= 70 else '#721c24'}; }}
</style>
</head>
<body>
<h1>Men of Maize — QA Comparison: Take 1 vs. Take 2</h1>

<h2>Summary</h2>
<table class="summary-table">
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Total pages in Take 1</td><td>{len(t1_pages)}</td></tr>
  <tr><td>Total pages in Take 2</td><td>{len(t2_pages)}</td></tr>
  <tr><td>Pages compared (both present, both non-missing)</td><td>{total_comparable}</td></tr>
  <tr><td>Good match (≥ {GOOD_MATCH_THRESHOLD:.0%})</td><td>{counts['good_match']}</td></tr>
  <tr><td>Minor divergence ({MINOR_DIVERGENCE_THRESHOLD:.0%}–{GOOD_MATCH_THRESHOLD:.0%})</td><td>{counts['minor_divergence']}</td></tr>
  <tr><td>Significant divergence (< {MINOR_DIVERGENCE_THRESHOLD:.0%})</td><td>{counts['significant_divergence']}</td></tr>
  <tr><td>One side missing / needs review</td><td>{counts['one_side_missing']}</td></tr>
  <tr><td>Orphan (one version only)</td><td>{counts['orphan_t1_only'] + counts['orphan_t2_only']}</td></tr>
  <tr><td class="pct" colspan="2">Overall accuracy (good match rate): {pct_good:.1f}%</td></tr>
</table>

<h2>Page-by-Page Results</h2>
<table>
  <thead><tr><th>Page</th><th>Status</th><th>Diff</th></tr></thead>
  <tbody>{"".join(rows_html)}</tbody>
</table>

<h2>Appendix: Needs-Review Spreads</h2>
<p>These spreads were blocked by content filtering in Take 2 and require manual transcription.</p>
<table>
  <thead><tr><th>Source PDF</th><th>Spread</th><th>Est. Pages</th><th>Image</th></tr></thead>
  <tbody>{nr_rows}</tbody>
</table>
</body>
</html>"""
    return html

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if not TAKE1_FILE.exists():
        print(f"ERROR: Take 1 file not found at:\n  {TAKE1_FILE}")
        print("Check the path in TAKE1_FILE constant.")
        import sys; sys.exit(1)

    if not TAKE2_FILE.exists():
        print(f"ERROR: Take 2 clean text not found. Run 02_assemble.py first.")
        import sys; sys.exit(1)

    print("Loading Take 1 output …")
    t1_text = TAKE1_FILE.read_text(encoding="utf-8")
    t1_pages = extract_pages(t1_text)
    print(f"  {len(t1_pages)} pages found in Take 1")

    print("Loading Take 2 output …")
    t2_text = TAKE2_FILE.read_text(encoding="utf-8")
    t2_pages = extract_pages(t2_text)
    print(f"  {len(t2_pages)} pages found in Take 2")

    # Load needs_review_list from JSON if available
    needs_review_list = []
    json_path = OUTPUT_DIR / "men_of_maize_structured.json"
    if json_path.exists():
        import json
        data = json.loads(json_path.read_text(encoding="utf-8"))
        needs_review_list = data.get("needs_review_list", [])

    print("Computing diff …")
    html = build_report(t1_pages, t2_pages, needs_review_list)

    REPORT_FILE.write_text(html, encoding="utf-8")
    print(f"\nReport written: {REPORT_FILE}")
    print(f"Open in browser: open \"{REPORT_FILE}\"")


if __name__ == "__main__":
    main()
