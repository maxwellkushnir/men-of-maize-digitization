"""
Men of Maize — Divergence Review
Generates an HTML review sheet of every Qwen-Mistral divergence, with
Qwen, Mistral, and Claude readings side by side for manual arbitration.

Qwen and Mistral are the two independent sources — their agreement is the
primary signal. Claude is a third data point, not the reference.

Each divergence is tagged:
  [Q=M≠C]  Qwen and Mistral agree, Claude differs  ← strongest signal against Claude
  [Q=C≠M]  Qwen and Claude agree, Mistral differs
  [M=C≠Q]  Mistral and Claude agree, Qwen differs
  [Q≠M≠C]  All three differ                        ← highest uncertainty

Usage:
    python3 10_divergence_review.py
Output:
    take2/output/divergence_review.html
"""

import re
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher

BASE        = Path(__file__).parent
OUTPUT_DIR  = BASE / "output"
CLAUDE_FILE = OUTPUT_DIR / "men_of_maize_clean.txt"
QWEN_DIR    = OUTPUT_DIR / "qwen_raw"
MISTRAL_DIR = OUTPUT_DIR / "mistral_raw"
HTML_OUT    = OUTPUT_DIR / "divergence_review.html"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]
CONTEXT  = 7   # words of context either side of a divergence

# ── TEXT HELPERS ──────────────────────────────────────────────────────────────

MARKER_RE = re.compile(
    r'<<< SPREAD_(?:START|END)[^>]*>>>|'
    r'^#.*$|'
    r'^\[Page\s+\d+[^\]]*\]\s*$|'
    r'^\[section break\]\s*$|'
    r'^MEN OF MAIZE\s*$|'
    r'^MIGUEL ÁNGEL ASTURIAS\s*$',
    re.MULTILINE | re.IGNORECASE,
)

PAGE_NUM_RE = re.compile(r'\[Page\s+(\d+)')

def norm(word: str) -> str:
    """Lowercase + strip accents for comparison."""
    s = unicodedata.normalize("NFD", word.lower())
    return s.encode("ascii", "ignore").decode("ascii")

def clean_block(text: str) -> str:
    """Remove structural markers, keep readable prose."""
    return MARKER_RE.sub(' ', text)

def words_of(text: str) -> list:
    """Split into whitespace tokens, preserving original form."""
    return text.split()

def norm_words(words: list) -> list:
    return [norm(w) for w in words]

def extract_page_nums(text: str) -> list:
    return [int(m.group(1)) for m in PAGE_NUM_RE.finditer(text)]


# ── LOAD SPREAD BLOCKS ────────────────────────────────────────────────────────

def load_spreads(directory: Path, suffix: str) -> dict:
    """
    Returns { (pdf_name, spread_num): raw_block_text }
    """
    spreads = {}
    block_re = re.compile(
        r'<<< SPREAD_START pdf="([^"]+)" spread="(\d+)"[^>]*>>>(.*?)<<< SPREAD_END >>>',
        re.DOTALL
    )
    for pdf in ALL_PDFS:
        path = directory / f"{pdf}_{suffix}.txt"
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for m in block_re.finditer(content):
            pdf_name   = m.group(1)
            spread_num = int(m.group(2))
            spreads[(pdf_name, spread_num)] = m.group(3)
    return spreads


# ── LOAD CLAUDE PAGES ─────────────────────────────────────────────────────────

def load_claude_pages(path: Path) -> dict:
    """Returns { page_num: text }"""
    text = path.read_text(encoding="utf-8")
    pages = {}
    matches = list(re.finditer(r'^\[Page\s+(\d+)[^\]]*\]', text, re.MULTILINE))
    for i, m in enumerate(matches):
        pn    = int(m.group(1))
        start = m.end()
        end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        pages[pn] = text[start:end].strip()
    return pages


# ── ALIGNMENT: find Claude reading for a Qwen position ───────────────────────

def build_q_to_c(q_norm: list, c_norm: list) -> dict:
    """
    Returns a sparse dict: q_index → c_index for equal-block positions.
    Also stores sentinel entries just past each equal block so we can
    interpolate what Claude has between two anchors.
    """
    sm = SequenceMatcher(None, q_norm, c_norm, autojunk=False)
    mapping = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for d in range(i2 - i1):
                mapping[i1 + d] = j1 + d
    return mapping


def claude_span_for(q_i1: int, q_i2: int, q_to_c: dict, c_words: list) -> str:
    """
    Given a Qwen divergence at [q_i1:q_i2], return what Claude has
    at the corresponding position, using the alignment map.
    """
    if not c_words:
        return "—"

    # Find the nearest aligned Qwen position before and after the span
    c_before = None
    for qi in range(q_i1 - 1, max(-1, q_i1 - 20), -1):
        if qi in q_to_c:
            c_before = q_to_c[qi] + 1   # C position just after the last match
            break

    c_after = None
    for qi in range(q_i2, min(len(q_to_c) + q_i2, q_i2 + 20)):
        if qi in q_to_c:
            c_after = q_to_c[qi]         # C position of the next match
            break

    if c_before is None and c_after is None:
        return "—"
    if c_before is None:
        c_before = max(0, c_after - (q_i2 - q_i1) - 2)
    if c_after is None:
        c_after = min(len(c_words), c_before + (q_i2 - q_i1) + 2)

    snippet = c_words[c_before:c_after]
    return " ".join(snippet) if snippet else "—"


# ── CLASSIFY DIVERGENCE ───────────────────────────────────────────────────────

def classify(q_span: str, m_span: str, c_span: str) -> str:
    qn = norm(q_span)
    mn = norm(m_span)
    cn = norm(c_span) if c_span and c_span != "—" else None

    if cn is None:
        return "Q≠M (C n/a)"
    if qn == mn:         # shouldn't happen (called only for Q≠M blocks)
        return "Q=M"
    if cn == qn:
        return "Q=C≠M"
    if cn == mn:
        return "M=C≠Q"
    return "Q≠M≠C"


# ── COLLECT ALL DIVERGENCES ───────────────────────────────────────────────────

def collect_divergences(qwen_spreads: dict, mistral_spreads: dict, claude_pages: dict) -> list:
    divergences = []
    all_keys = sorted(
        set(qwen_spreads) & set(mistral_spreads),
        key=lambda k: (ALL_PDFS.index(k[0]) if k[0] in ALL_PDFS else 99, k[1])
    )

    for key in all_keys:
        pdf_name, spread_num = key
        q_raw = clean_block(qwen_spreads[key])
        m_raw = clean_block(mistral_spreads[key])

        q_words = words_of(q_raw)
        m_words = words_of(m_raw)
        if not q_words or not m_words:
            continue

        # Find which book pages this spread covers (from Qwen, fall back to Mistral)
        pages = extract_page_nums(qwen_spreads[key]) or extract_page_nums(mistral_spreads[key])
        page_label = f"pp. {min(pages)}–{max(pages)}" if pages else "p. ?"

        # Get Claude text for these pages
        c_text = " ".join(
            claude_pages.get(p, "") for p in sorted(set(pages))
        ) if pages else ""
        c_words = words_of(c_text)

        # Build Q→C alignment
        q_to_c = build_q_to_c(norm_words(q_words), norm_words(c_words)) if c_words else {}

        # Compare Q vs M
        sm = SequenceMatcher(None, norm_words(q_words), norm_words(m_words), autojunk=False)

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue

            q_span = " ".join(q_words[i1:i2])
            m_span = " ".join(m_words[j1:j2])
            c_span = claude_span_for(i1, i2, q_to_c, c_words)

            left_ctx  = " ".join(q_words[max(0, i1 - CONTEXT):i1])
            right_ctx = " ".join(q_words[i2:i2 + CONTEXT])

            dtype = classify(q_span, m_span, c_span)

            divergences.append({
                "pdf":       pdf_name,
                "spread":    spread_num,
                "pages":     page_label,
                "left_ctx":  left_ctx,
                "q_span":    q_span,
                "m_span":    m_span,
                "c_span":    c_span,
                "right_ctx": right_ctx,
                "type":      dtype,
            })

    return divergences


# ── HTML OUTPUT ───────────────────────────────────────────────────────────────

TYPE_ORDER = {"Q=M≠C": 0, "Q≠M≠C": 1, "Q=C≠M": 2, "M=C≠Q": 3, "Q≠M (C n/a)": 4}
TYPE_COLOUR = {
    "Q=M≠C":      "#b71c1c",   # deep red  — Claude is the outlier
    "Q≠M≠C":      "#e65100",   # orange    — all differ, highest uncertainty
    "Q=C≠M":      "#1565c0",   # blue      — Mistral outlier
    "M=C≠Q":      "#2e7d32",   # green     — Qwen outlier
    "Q≠M (C n/a)":"#555555",   # grey      — no Claude text available
}

def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def span_tag(text: str, colour: str, bold: bool = True) -> str:
    w = "bold" if bold else "normal"
    return f'<span style="color:{colour};font-weight:{w}">{esc(text)}</span>'

def build_html(divergences: list) -> str:
    counts = {}
    for d in divergences:
        counts[d["type"]] = counts.get(d["type"], 0) + 1

    # Sort: Q=M≠C first (strongest signal against Claude), then all-differ, then others
    sorted_divs = sorted(divergences, key=lambda d: (
        TYPE_ORDER.get(d["type"], 9),
        ALL_PDFS.index(d["pdf"]) if d["pdf"] in ALL_PDFS else 99,
        d["spread"]
    ))

    rows = []
    for i, d in enumerate(sorted_divs, 1):
        colour = TYPE_COLOUR.get(d["type"], "#333")
        type_badge = f'<span style="background:{colour};color:#fff;padding:2px 6px;border-radius:3px;font-size:11px;white-space:nowrap">{esc(d["type"])}</span>'

        context_html = (
            f'<span style="color:#999">{esc(d["left_ctx"])}</span> '
            f'<span style="background:#fffde7;padding:1px 2px">[…]</span> '
            f'<span style="color:#999">{esc(d["right_ctx"])}</span>'
        )

        rows.append(f"""
<tr>
  <td style="color:#999;font-size:11px;white-space:nowrap">{i}</td>
  <td style="font-size:11px;white-space:nowrap">{esc(d['pdf'])}<br>spread {d['spread']}<br>{esc(d['pages'])}</td>
  <td style="font-size:12px;color:#555">{context_html}</td>
  <td style="color:#1565c0;font-weight:bold">{esc(d['q_span']) or '<i style="color:#aaa">∅</i>'}</td>
  <td style="color:#2e7d32;font-weight:bold">{esc(d['m_span']) or '<i style="color:#aaa">∅</i>'}</td>
  <td style="color:#555">{esc(d['c_span']) or '<i style="color:#aaa">—</i>'}</td>
  <td style="text-align:center">{type_badge}</td>
</tr>""")

    summary_rows = "".join(
        f'<tr><td>{esc(t)}</td><td style="text-align:right">{counts.get(t,0):,}</td></tr>'
        for t in sorted(counts, key=lambda t: TYPE_ORDER.get(t, 9))
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Men of Maize — Divergence Review</title>
<style>
  body {{ font-family: Georgia, serif; font-size: 13px; margin: 2em; color: #222; }}
  h1 {{ font-size: 1.4em; }}
  h2 {{ font-size: 1.1em; margin-top: 2em; border-bottom: 1px solid #ccc; padding-bottom: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2em; }}
  th, td {{ padding: 5px 10px; border: 1px solid #e0e0e0; vertical-align: top; }}
  th {{ background: #f5f5f5; font-size: 12px; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  .note {{ color: #555; font-size: 12px; margin: 0.5em 0 1em; }}
  .legend {{ display: flex; gap: 1.5em; flex-wrap: wrap; margin-bottom: 1em; font-size: 12px; }}
  .leg {{ display: flex; align-items: center; gap: 5px; }}
  .dot {{ width: 12px; height: 12px; border-radius: 2px; }}
</style>
</head>
<body>
<h1>Men of Maize — Qwen / Mistral Divergence Review</h1>
<p class="note">
  <strong>Qwen and Mistral are the independent sources.</strong> Claude is shown as a third
  reading only — it is not the reference. Where Q=M but C differs, Claude is most likely wrong.
  Each row requires manual arbitration against the original photograph.
</p>

<h2>Summary</h2>
<table style="width:300px">
  <tr><th>Type</th><th>Count</th></tr>
  {summary_rows}
  <tr style="font-weight:bold"><td>Total</td><td style="text-align:right">{len(divergences):,}</td></tr>
</table>

<div class="legend">
  {''.join(f'<div class="leg"><div class="dot" style="background:{c}"></div>{esc(t)}</div>' for t,c in TYPE_COLOUR.items())}
</div>

<h2>All Divergences (sorted: Q=M≠C first, then all-differ, then single-model outliers)</h2>
<p class="note">
  <strong>Qwen</strong> (blue) · <strong>Mistral</strong> (green) · Claude (grey) · context (faded)
</p>
<table>
<thead>
<tr>
  <th>#</th>
  <th>Location</th>
  <th>Context (Qwen)</th>
  <th>Qwen</th>
  <th>Mistral</th>
  <th>Claude</th>
  <th>Type</th>
</tr>
</thead>
<tbody>{"".join(rows)}</tbody>
</table>
</body>
</html>"""


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading Claude pages …")
    claude_pages = load_claude_pages(CLAUDE_FILE)
    print(f"  {len(claude_pages)} pages")

    print("Loading Qwen spreads …")
    qwen_spreads = load_spreads(QWEN_DIR, "qwen")
    print(f"  {len(qwen_spreads)} spreads")

    print("Loading Mistral spreads …")
    mistral_spreads = load_spreads(MISTRAL_DIR, "mistral")
    print(f"  {len(mistral_spreads)} spreads")

    print("Collecting divergences …")
    divs = collect_divergences(qwen_spreads, mistral_spreads, claude_pages)
    print(f"  {len(divs):,} divergent spans")

    by_type = {}
    for d in divs:
        by_type[d["type"]] = by_type.get(d["type"], 0) + 1
    for t, n in sorted(by_type.items(), key=lambda x: TYPE_ORDER.get(x[0], 9)):
        print(f"  {t}: {n:,}")

    print(f"Writing {HTML_OUT.name} …")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    HTML_OUT.write_text(build_html(divs), encoding="utf-8")
    print(f"Done: {HTML_OUT}")

    import subprocess
    subprocess.run(["open", str(HTML_OUT)])


if __name__ == "__main__":
    main()
