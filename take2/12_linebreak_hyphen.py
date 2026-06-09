"""
Men of Maize — Fix line-break hyphen artifacts (Rule 2, pass 1)

Rule: within a Q≠M divergence span, if one model wrote a word split across
a print line (e.g. "Lis- ten") and the other model wrote it joined ("Listen"),
and after collapsing the hyphen-space the two spans agree on the word content
(punctuation differences ignored), then the collapsed form is correct.

Only the specific split word is fixed in Claude's text — surrounding
punctuation differences in the same span are left for later review.

Conservatism rules (correction skipped if any fail):
  - The split form must match the pattern \w+- \w+ (hyphen then space)
  - After collapsing all linebreak hyphens in Q and M, the word content
    must match (case-insensitive, punctuation stripped)
  - The split form must appear EXACTLY ONCE in Claude's relevant page text
  - The split form must actually differ from the collapsed form (sanity check)

Outputs:
  output/linebreak_corrections_log.txt  — full log
  (updates men_of_maize_clean.txt and men_of_maize_structured.json in place)

Usage:
    python3 12_linebreak_hyphen.py [--dry-run]
"""

import json
import re
import sys
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher

DRY_RUN = "--dry-run" in sys.argv

BASE        = Path(__file__).parent
OUTPUT_DIR  = BASE / "output"
CLAUDE_FILE = OUTPUT_DIR / "men_of_maize_clean.txt"
JSON_FILE   = OUTPUT_DIR / "men_of_maize_structured.json"
QWEN_DIR    = OUTPUT_DIR / "qwen_raw"
MISTRAL_DIR = OUTPUT_DIR / "mistral_raw"
LOG_FILE    = OUTPUT_DIR / "linebreak_corrections_log.txt"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

LINEBREAK_RE = re.compile(r'(\w+)-\s+(\w+)')
PAGE_NUM_RE  = re.compile(r'\[Page\s+(\d+)')

MARKER_RE = re.compile(
    r'<<< SPREAD_(?:START|END)[^>]*>>>|^#.*$|^\[Page\s+\d+[^\]]*\]\s*$|'
    r'^\[section break\]\s*$|^MEN OF MAIZE\s*$|^MIGUEL.*$',
    re.MULTILINE | re.IGNORECASE,
)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def norm(word: str) -> str:
    s = unicodedata.normalize("NFD", word.lower())
    return s.encode("ascii", "ignore").decode("ascii")

def norm_words(words: list) -> list:
    return [norm(w) for w in words]

def words_no_punct(text: str) -> list:
    """Strip all punctuation, lowercase, split — for content comparison only."""
    cleaned = re.sub(r'[^\w\s]', '', text, flags=re.UNICODE)
    return [norm(w) for w in cleaned.split() if w]

def collapse_linebreaks(text: str) -> str:
    """'Lis- ten' → 'Listen',  'mis- fortune' → 'misfortune'"""
    return LINEBREAK_RE.sub(lambda m: m.group(1) + m.group(2), text)

def is_linebreak_span(q_span: str, m_span: str) -> bool:
    """
    True if the ONLY reason Q≠M is a linebreak hyphen artifact in one (or both).
    After collapsing, word content must match (punctuation ignored).
    """
    if not LINEBREAK_RE.search(q_span) and not LINEBREAK_RE.search(m_span):
        return False
    q_collapsed = collapse_linebreaks(q_span)
    m_collapsed = collapse_linebreaks(m_span)
    return words_no_punct(q_collapsed) == words_no_punct(m_collapsed)

def find_split_words(q_span: str, m_span: str) -> list:
    """
    Return list of (split_form, collapsed_form) for every linebreak artifact
    found in either span. The collapsed form is the correct word.
    """
    results = []
    seen = set()

    # Find in Q — check collapsed token appears in M
    q_collapsed_text = collapse_linebreaks(q_span)
    m_collapsed_text = collapse_linebreaks(m_span)

    for match in LINEBREAK_RE.finditer(q_span):
        split_form = match.group(0)          # e.g. 'Lis- ten'
        collapsed  = match.group(1) + match.group(2)  # e.g. 'Listen'
        if split_form in seen:
            continue
        # Verify collapsed form exists in M (case-insensitive)
        if norm(collapsed) in [norm(w) for w in m_collapsed_text.split()]:
            results.append((split_form, collapsed))
            seen.add(split_form)

    for match in LINEBREAK_RE.finditer(m_span):
        split_form = match.group(0)
        collapsed  = match.group(1) + match.group(2)
        if split_form in seen:
            continue
        if norm(collapsed) in [norm(w) for w in q_collapsed_text.split()]:
            results.append((split_form, collapsed))
            seen.add(split_form)

    return results


# ── LOAD DATA ─────────────────────────────────────────────────────────────────

def load_spreads(directory: Path, suffix: str) -> dict:
    spreads = {}
    block_re = re.compile(
        r'<<< SPREAD_START pdf="([^"]+)" spread="(\d+)"[^>]*>>>(.*?)<<< SPREAD_END >>>',
        re.DOTALL
    )
    for pdf in ALL_PDFS:
        path = directory / f"{pdf}_{suffix}.txt"
        if not path.exists():
            continue
        for m in block_re.finditer(path.read_text(encoding="utf-8")):
            spreads[(m.group(1), int(m.group(2)))] = m.group(3)
    return spreads

def load_claude_pages(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    pages = {}
    matches = list(re.finditer(r'^\[Page\s+(\d+)[^\]]*\]', text, re.MULTILINE))
    for i, m in enumerate(matches):
        pn    = int(m.group(1))
        start = m.end()
        end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        pages[pn] = text[start:end]
    return pages


# ── FIND CORRECTIONS ──────────────────────────────────────────────────────────

def find_corrections(qwen_spreads, mistral_spreads, claude_pages):
    corrections = []  # list of {pdf, spread, pages, split_form, collapsed_form}

    keys = sorted(
        set(qwen_spreads) & set(mistral_spreads),
        key=lambda k: (ALL_PDFS.index(k[0]) if k[0] in ALL_PDFS else 99, k[1])
    )

    span_count   = 0
    linebrk_spans = 0

    for key in keys:
        pdf_name, spread_num = key
        q_raw = MARKER_RE.sub(' ', qwen_spreads[key])
        m_raw = MARKER_RE.sub(' ', mistral_spreads[key])

        q_words = q_raw.split()
        m_words = m_raw.split()
        if not q_words or not m_words:
            continue

        pages = [int(x) for x in PAGE_NUM_RE.findall(qwen_spreads[key])]
        if not pages:
            pages = [int(x) for x in PAGE_NUM_RE.findall(mistral_spreads[key])]
        if not pages:
            continue

        sm = SequenceMatcher(None, norm_words(q_words), norm_words(m_words), autojunk=False)

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue

            q_span = " ".join(q_words[i1:i2])
            m_span = " ".join(m_words[j1:j2])
            span_count += 1

            if not is_linebreak_span(q_span, m_span):
                continue

            linebrk_spans += 1
            split_words = find_split_words(q_span, m_span)

            for split_form, collapsed_form in split_words:
                corrections.append({
                    "pdf":            pdf_name,
                    "spread":         spread_num,
                    "pages":          sorted(set(pages)),
                    "split_form":     split_form,
                    "collapsed_form": collapsed_form,
                    "q_span":         q_span,
                    "m_span":         m_span,
                })

    print(f"  Total Q≠M divergence spans: {span_count:,}")
    print(f"  Linebreak-resolvable spans:  {linebrk_spans:,}")
    print(f"  Split-word corrections found: {len(corrections):,}")
    return corrections, linebrk_spans


# ── APPLY TO CLEAN.TXT ────────────────────────────────────────────────────────

def apply_to_clean_txt(corrections, path: Path):
    text = path.read_text(encoding="utf-8")
    applied = 0
    skipped = 0
    log_lines = []

    page_matches = list(re.finditer(r'^\[Page\s+(\d+)[^\]]*\]', text, re.MULTILINE))
    page_positions = {
        int(m.group(1)): (m.start(), page_matches[i+1].start() if i+1 < len(page_matches) else len(text))
        for i, m in enumerate(page_matches)
    }

    # Deduplicate: same split_form on same pages should only be applied once
    seen = set()

    for c in corrections:
        split_form     = c["split_form"]
        collapsed_form = c["collapsed_form"]
        pages          = c["pages"]
        key            = (frozenset(pages), split_form)

        if key in seen:
            continue
        seen.add(key)

        if split_form == collapsed_form:
            skipped += 1
            log_lines.append(f"SKIP (no change)  {c['pdf']} spread {c['spread']}  {repr(split_form)}")
            continue

        page_starts = [page_positions[p][0] for p in pages if p in page_positions]
        page_ends   = [page_positions[p][1] for p in pages if p in page_positions]
        if not page_starts:
            skipped += 1
            log_lines.append(f"SKIP (pages not in text)  {c['pdf']} spread {c['spread']}  {repr(split_form)}")
            continue

        region_start = min(page_starts)
        region_end   = max(page_ends)
        region       = text[region_start:region_end]

        count = region.count(split_form)
        if count != 1:
            skipped += 1
            log_lines.append(f"SKIP (found {count}×)  {c['pdf']} spread {c['spread']}  {repr(split_form)}")
            continue

        new_region = region.replace(split_form, collapsed_form, 1)
        text = text[:region_start] + new_region + text[region_end:]
        applied += 1
        log_lines.append(
            f"APPLY  {c['pdf']} spread {c['spread']}  p{pages}  "
            f"{repr(split_form)} → {repr(collapsed_form)}"
        )

    if not DRY_RUN:
        path.write_text(text, encoding="utf-8")

    return applied, skipped, log_lines


# ── APPLY TO JSON ─────────────────────────────────────────────────────────────

def apply_to_json(corrections, path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    page_index = {p["page_number"]: i for i, p in enumerate(data["pages"])}

    applied = 0
    skipped = 0
    log_lines = []

    seen = set()

    for c in corrections:
        split_form     = c["split_form"]
        collapsed_form = c["collapsed_form"]
        pages          = c["pages"]
        key            = (frozenset(pages), split_form)

        if key in seen:
            continue
        seen.add(key)

        if split_form == collapsed_form:
            continue

        target_blocks = []
        for pn in pages:
            if pn not in page_index:
                continue
            page_obj = data["pages"][page_index[pn]]
            for block in page_obj.get("content_blocks", []):
                if split_form in block.get("text", ""):
                    target_blocks.append(block)

        if len(target_blocks) != 1:
            skipped += 1
            log_lines.append(
                f"SKIP JSON (found in {len(target_blocks)} blocks)  "
                f"{c['pdf']} spread {c['spread']}  {repr(split_form)}"
            )
            continue

        target_blocks[0]["text"] = target_blocks[0]["text"].replace(split_form, collapsed_form, 1)
        applied += 1
        log_lines.append(
            f"APPLY JSON  {c['pdf']} spread {c['spread']}  "
            f"{repr(split_form)} → {repr(collapsed_form)}"
        )

    if not DRY_RUN:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return applied, skipped, log_lines


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if DRY_RUN:
        print("DRY RUN — no files will be modified.\n")

    print("Loading data …")
    qwen_spreads    = load_spreads(QWEN_DIR, "qwen")
    mistral_spreads = load_spreads(MISTRAL_DIR, "mistral")
    claude_pages    = load_claude_pages(CLAUDE_FILE)
    print(f"  Q: {len(qwen_spreads)} spreads  M: {len(mistral_spreads)} spreads  C: {len(claude_pages)} pages")

    print("Finding linebreak-hyphen corrections …")
    corrections, linebrk_spans = find_corrections(qwen_spreads, mistral_spreads, claude_pages)

    print("Applying to men_of_maize_clean.txt …")
    txt_applied, txt_skipped, txt_log = apply_to_clean_txt(corrections, CLAUDE_FILE)
    print(f"  Applied: {txt_applied}   Skipped: {txt_skipped}")

    print("Applying to men_of_maize_structured.json …")
    json_applied, json_skipped, json_log = apply_to_json(corrections, JSON_FILE)
    print(f"  Applied: {json_applied}   Skipped: {json_skipped}")

    log = [
        "Line-break Hyphen Correction Log",
        f"Run: {'DRY RUN' if DRY_RUN else 'LIVE'}",
        f"Linebreak-resolvable Q≠M spans identified: {linebrk_spans}",
        f"Split-word correction instances found:      {len(corrections)}",
        f"clean.txt — applied: {txt_applied}, skipped: {txt_skipped}",
        f"JSON      — applied: {json_applied}, skipped: {json_skipped}",
        "─" * 60,
        "clean.txt corrections:",
        *txt_log,
        "─" * 60,
        "JSON corrections:",
        *json_log,
    ]

    if not DRY_RUN:
        LOG_FILE.write_text("\n".join(log), encoding="utf-8")
        print(f"\nLog written to {LOG_FILE.name}")

    print(f"\n── SUMMARY ──────────────────────────────────────────")
    print(f"Linebreak-resolvable Q≠M spans:  {linebrk_spans}")
    print(f"Split words fixed in clean.txt:  {txt_applied}")
    print(f"Split words fixed in JSON:       {json_applied}")
    print(f"Remaining Q≠M span count:        4,245 − {linebrk_spans} = {4245 - linebrk_spans}")
    print(f"(Remaining count is approximate — spans may be partially resolved)")


if __name__ == "__main__":
    main()
