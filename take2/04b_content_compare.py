"""
Men of Maize — Content-level comparison: Take 1 vs Take 2
Ignores page structure entirely. Diffs the full body text as a single sequence
and reports genuine word-substitution / omission divergences.

Usage:
    python3 04b_content_compare.py

Output:
    take2/output/content_diff_report.html   (open in browser)
    take2/output/content_diff_summary.txt   (plain text, quick read)
"""

import difflib
import re
import unicodedata
from pathlib import Path

TAKE1_FILE  = Path("/Users/Max/Documents/Claude Code/Men of Maize/Take 1/men_of_maize_full_text.txt")
TAKE2_FILE  = Path(__file__).parent / "output" / "men_of_maize_clean.txt"
HTML_OUT    = Path(__file__).parent / "output" / "content_diff_report.html"
TXT_OUT     = Path(__file__).parent / "output" / "content_diff_summary.txt"

# How many words of context to show either side of a divergence
CONTEXT_WORDS = 12
# Ignore substitutions where normalised forms are the same (accent-only diffs)
# Ignore single-token differences that are likely OCR noise (punctuation swap etc.)
MIN_DIFF_TOKENS = 1   # minimum tokens in a divergent block to report


# ── TEXT EXTRACTION ───────────────────────────────────────────────────────────

# Lines to discard from T1 (spread separators, extraction failures, headings)
T1_SKIP_RE = re.compile(
    r"^(━+|═+|#\s|Source:\s|MEN OF MAIZE\s*$|MIGUEL|"
    r"\[Page shows|^\[Page is blank|^\[Page -|^\[Left page|^\[Right page|"
    r"\[EXTRACTION FAILED|\[NEEDS_REVIEW|I appreciate your detailed)"
    , re.IGNORECASE
)

# Lines to discard from T2 (page markers, assembly header, section markers)
T2_SKIP_RE = re.compile(
    r"^(\[Page\s+\d+|={3,}|\[Assembly note|MEN OF MAIZE\s*$|"
    r"by Miguel|Translated by|Delacorte Press)"
    , re.IGNORECASE
)

# Chapter headings and section numbers — keep in both so context makes sense
# but don't use them as alignment anchors

def strip_accents(s: str) -> str:
    """Normalise to ASCII-comparable form (e.g. Gáspár → Gaspar)."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")

def extract_body(path: Path, skip_re: re.Pattern) -> list[str]:
    """
    Read file, discard structural noise, return list of lowercase normalised tokens.
    Keeps word tokens only (no punctuation tokens) so the diff is purely about words.
    """
    tokens = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if skip_re.search(line):
            continue
        # strip remaining bracket-style OCR descriptions [...]
        line = re.sub(r"\[[^\]]{0,80}\]", " ", line)
        # strip markdown headers from Mistral output that slipped through
        line = re.sub(r"^#+\s*", "", line)
        # normalise dashes/quotes to plain ASCII
        line = line.replace("—", " ").replace("–", " ")
        line = strip_accents(line)
        words = re.findall(r"\b[a-zA-Z']+\b", line)
        tokens.extend(w.lower() for w in words if w)
    return tokens


# ── DIFF & REPORT ─────────────────────────────────────────────────────────────

def context_str(tokens: list[str], centre: int, n: int) -> str:
    lo = max(0, centre - n)
    hi = min(len(tokens), centre + n)
    pre  = " ".join(tokens[lo:centre])
    post = " ".join(tokens[centre:hi])
    return pre, post

def build_report(t1_tokens: list[str], t2_tokens: list[str]):
    sm = difflib.SequenceMatcher(None, t1_tokens, t2_tokens, autojunk=False)
    opcodes = sm.get_opcodes()

    findings = []   # list of dicts

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue

        t1_chunk = t1_tokens[i1:i2]
        t2_chunk = t2_tokens[j1:j2]

        # Skip if both sides normalise to the same string (accent-only diff)
        if " ".join(t1_chunk) == " ".join(t2_chunk):
            continue

        # Skip very short noise (single function word swaps like "a"/"the")
        if tag == "replace" and len(t1_chunk) == 1 and len(t2_chunk) == 1:
            # Allow if words are genuinely different (not just capitalization)
            if t1_chunk[0] in {"a", "the", "an", "of", "in", "to", "and", "is", "it", "i"}:
                continue

        # Context from T1 (the "anchor" text)
        lo  = max(0, i1 - CONTEXT_WORDS)
        hi  = min(len(t1_tokens), i2 + CONTEXT_WORDS)
        pre_ctx  = " ".join(t1_tokens[lo:i1])
        post_ctx = " ".join(t1_tokens[i2:hi])

        findings.append({
            "tag":      tag,
            "t1":       " ".join(t1_chunk),
            "t2":       " ".join(t2_chunk),
            "pre":      pre_ctx,
            "post":     post_ctx,
            "t1_pos":   i1,
            "t1_len":   len(t1_tokens),
        })

    return findings


def pct(i, total):
    return f"{i / total * 100:.0f}%" if total else "?"


def write_html(findings, t1_len, t2_len, path: Path):
    rows = []
    for f in findings:
        tag_label = {"replace": "≠ different", "delete": "− T1 only", "insert": "+ T2 only"}[f["tag"]]
        tag_class = {"replace": "rep", "delete": "del", "insert": "ins"}[f["tag"]]
        book_pos  = pct(f["t1_pos"], t1_len)

        t1_html = f'<span class="t1w">{f["t1"] or "—"}</span>'
        t2_html = f'<span class="t2w">{f["t2"] or "—"}</span>'

        rows.append(f"""
  <tr>
    <td class="pos">{book_pos}</td>
    <td><span class="badge {tag_class}">{tag_label}</span></td>
    <td class="ctx">…{f["pre"]} {t1_html} {f["post"]}…</td>
    <td class="ctx">…{f["pre"]} {t2_html} {f["post"]}…</td>
  </tr>""")

    substitutions = sum(1 for f in findings if f["tag"] == "replace")
    t1_only       = sum(1 for f in findings if f["tag"] == "delete")
    t2_only       = sum(1 for f in findings if f["tag"] == "insert")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Men of Maize — Content Diff Report</title>
<style>
  body {{ font-family: Georgia, serif; font-size: 13px; margin: 2em; color: #222; }}
  h1 {{ font-size: 1.4em; }}
  h2 {{ font-size: 1.1em; margin-top: 2em; border-bottom: 1px solid #ccc; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2em; }}
  th, td {{ padding: 5px 8px; border: 1px solid #ddd; vertical-align: top; }}
  th {{ background: #f0f0f0; text-align: left; }}
  .pos {{ width: 4em; text-align: right; color: #888; font-size: 11px; }}
  .badge {{ display:inline-block; padding:2px 6px; border-radius:3px; font-size:11px; font-family:monospace; }}
  .rep {{ background:#fff3cd; color:#856404; }}
  .del {{ background:#f8d7da; color:#721c24; }}
  .ins {{ background:#d4edda; color:#155724; }}
  .ctx {{ font-size: 12px; color: #444; }}
  .t1w {{ background:#fdd; color:#900; font-weight:bold; padding:1px 3px; }}
  .t2w {{ background:#dfd; color:#060; font-weight:bold; padding:1px 3px; }}
  .summary td {{ padding: 4px 8px; }}
</style>
</head>
<body>
<h1>Men of Maize — Content Diff: Take 1 vs Take 2</h1>
<p>Whole-text comparison. Page boundaries, running headers, and accent variants ignored.
   "Book position" is approximate (token index as % of T1 length).</p>

<h2>Summary</h2>
<table class="summary">
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>T1 body tokens</td><td>{t1_len:,}</td></tr>
  <tr><td>T2 body tokens</td><td>{t2_len:,}</td></tr>
  <tr><td>Word substitutions (T1 ≠ T2)</td><td>{substitutions}</td></tr>
  <tr><td>Passages in T1 not in T2</td><td>{t1_only}</td></tr>
  <tr><td>Passages in T2 not in T1</td><td>{t2_only}</td></tr>
  <tr><td>Total divergences reported</td><td>{len(findings)}</td></tr>
</table>

<h2>Divergences</h2>
<p>Left column = Take 1 text &nbsp;|&nbsp; Right column = Take 2 (assembled) text.<br>
<span class="badge rep">≠ different</span> = same passage, different word(s) &nbsp;
<span class="badge del">− T1 only</span> = text present in T1, absent from T2 &nbsp;
<span class="badge ins">+ T2 only</span> = text present in T2, absent from T1</p>
<table>
  <thead><tr><th>~Pos</th><th>Type</th><th>Take 1</th><th>Take 2</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")


def write_txt(findings, path: Path):
    lines = [
        "Men of Maize — Content Diff Summary",
        "Take 1 vs Take 2 (accent-normalised, page-structure ignored)",
        "=" * 70,
        "",
    ]
    for i, f in enumerate(findings, 1):
        tag = {"replace": "DIFFER", "delete": "T1 ONLY", "insert": "T2 ONLY"}[f["tag"]]
        lines.append(f"[{i:03d}] {tag}  (~{pct(f['t1_pos'], f['t1_len'])} through book)")
        if f["t1"]:
            lines.append(f"  T1: …{f['pre']} >>> {f['t1']} <<< {f['post']}…")
        if f["t2"]:
            lines.append(f"  T2: …{f['pre']} >>> {f['t2']} <<< {f['post']}…")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("Extracting T1 body text …")
    t1 = extract_body(TAKE1_FILE, T1_SKIP_RE)
    print(f"  {len(t1):,} tokens")

    print("Extracting T2 body text …")
    t2 = extract_body(TAKE2_FILE, T2_SKIP_RE)
    print(f"  {len(t2):,} tokens")

    print("Running sequence diff (this may take ~30s) …")
    findings = build_report(t1, t2)

    substitutions = sum(1 for f in findings if f["tag"] == "replace")
    t1_only       = sum(1 for f in findings if f["tag"] == "delete")
    t2_only       = sum(1 for f in findings if f["tag"] == "insert")

    print(f"\nResults:")
    print(f"  Word substitutions (T1 ≠ T2): {substitutions}")
    print(f"  Passages in T1 only:           {t1_only}")
    print(f"  Passages in T2 only:           {t2_only}")
    print(f"  Total divergences:             {len(findings)}")

    write_html(findings, len(t1), len(t2), HTML_OUT)
    write_txt(findings,  TXT_OUT)

    print(f"\nHTML report: {HTML_OUT}")
    print(f"Text summary: {TXT_OUT}")
    import subprocess
    subprocess.run(["open", str(HTML_OUT)])


if __name__ == "__main__":
    main()
