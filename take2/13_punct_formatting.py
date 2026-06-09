"""
Men of Maize — Fix formatting-only Q≠M spans (Rule 2b)

Rule: where the ONLY difference between Qwen and Mistral is quote style
(curly vs straight), ellipsis style (. . . vs ... vs …), or dash style
(— vs – vs --), defer to Qwen and apply Qwen's version to Claude's text.

These are not transcription errors — both models read the same word(s).
The spans are dismissed from the manual review queue.

Qwen's preferred styles (detected from raw output):
  Quotes:   curly (" " ' ')
  Ellipsis: spaced (. . .)
  Dashes:   em dash (—)

Sub-types handled:
  quote       — only curly/straight quote chars differ
  ellipsis    — only ellipsis rendering differs (. . . / ... / …)
  other_punct — combination of the above (e.g. . . ." vs ...")

Conservatism rules (correction skipped if any fail):
  - After normalising all three formatting dimensions, Q span == M span
  - No linebreak hyphen artifact present (those handled by script 12)
  - Claude's current text for that span appears EXACTLY ONCE in the page region
  - Qwen's version must actually differ from what Claude currently has

Outputs:
  output/punct_formatting_log.txt  — full log
  (updates men_of_maize_clean.txt and men_of_maize_structured.json in place)

Usage:
    python3 13_punct_formatting.py [--dry-run]
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
LOG_FILE    = OUTPUT_DIR / "punct_formatting_log.txt"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

PAGE_NUM_RE  = re.compile(r'\[Page\s+(\d+)')
LINEBREAK_RE = re.compile(r'(\w+)-\s+(\w+)')

MARKER_RE = re.compile(
    r'<<< SPREAD_(?:START|END)[^>]*>>>|^#.*$|^\[Page\s+\d+[^\]]*\]\s*$|'
    r'^\[section break\]\s*$|^MEN OF MAIZE\s*$|^MIGUEL.*$',
    re.MULTILINE | re.IGNORECASE,
)


# ── NORMALISATION ─────────────────────────────────────────────────────────────

def norm_char(w: str) -> str:
    s = unicodedata.normalize("NFD", w.lower())
    return s.encode("ascii", "ignore").decode("ascii")

def norm_words(ws: list) -> list:
    return [norm_char(w) for w in ws]

def normalize_quotes(s: str) -> str:
    s = re.sub(r"['‘’ʼ`´]", "'", s)
    s = re.sub(r'["“”„«»]', '"', s)
    return s

def normalize_ellipsis(s: str) -> str:
    s = s.replace('…', '...')
    s = re.sub(r'\.\s*\.\s*\.', '...', s)
    return s

def normalize_dashes(s: str) -> str:
    s = re.sub(r'[–—‒―]', '--', s)
    return s

def normalize_formatting(s: str) -> str:
    return normalize_dashes(normalize_ellipsis(normalize_quotes(s)))

def has_linebreak(s: str) -> bool:
    return bool(LINEBREAK_RE.search(s))

def is_formatting_only(q: str, m: str) -> bool:
    """True if Q and M differ only in quote/ellipsis/dash formatting."""
    if q == m:
        return False
    if has_linebreak(q) or has_linebreak(m):
        # linebreak cases handled by script 12
        nq = LINEBREAK_RE.sub(lambda x: x.group(1)+x.group(2), q)
        nm = LINEBREAK_RE.sub(lambda x: x.group(1)+x.group(2), m)
        if norm_char(nq) == norm_char(nm):
            return False
    return normalize_formatting(q) == normalize_formatting(m)


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

def build_q_to_c(q_norm: list, c_norm: list) -> dict:
    sm = SequenceMatcher(None, q_norm, c_norm, autojunk=False)
    mapping = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for d in range(i2 - i1):
                mapping[i1 + d] = j1 + d
    return mapping

def claude_span_for(q_i1, q_i2, q_to_c, c_words):
    c_before = None
    for qi in range(q_i1 - 1, max(-1, q_i1 - 20), -1):
        if qi in q_to_c:
            c_before = q_to_c[qi] + 1
            break
    c_after = None
    for qi in range(q_i2, q_i2 + 20):
        if qi in q_to_c:
            c_after = q_to_c[qi]
            break
    if c_before is None and c_after is None:
        return None
    if c_before is None:
        c_before = max(0, c_after - (q_i2 - q_i1) - 2)
    if c_after is None:
        c_after = min(len(c_words), c_before + (q_i2 - q_i1) + 2)
    snippet = c_words[c_before:c_after]
    return " ".join(snippet) if snippet else None


# ── FIND CORRECTIONS ──────────────────────────────────────────────────────────

def find_corrections(qwen_spreads, mistral_spreads, claude_pages):
    corrections = []
    spans_found = 0

    keys = sorted(
        set(qwen_spreads) & set(mistral_spreads),
        key=lambda k: (ALL_PDFS.index(k[0]) if k[0] in ALL_PDFS else 99, k[1])
    )

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

        c_text  = " ".join(claude_pages.get(p, "") for p in sorted(set(pages)))
        c_words = c_text.split()

        q_to_c = build_q_to_c(norm_words(q_words), norm_words(c_words)) if c_words else {}

        sm = SequenceMatcher(None, norm_words(q_words), norm_words(m_words), autojunk=False)

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            q_span = " ".join(q_words[i1:i2])
            m_span = " ".join(m_words[j1:j2])

            if not is_formatting_only(q_span, m_span):
                continue

            spans_found += 1
            c_span = claude_span_for(i1, i2, q_to_c, c_words)

            corrections.append({
                "pdf":      pdf_name,
                "spread":   spread_num,
                "pages":    sorted(set(pages)),
                "q_span":   q_span,   # Qwen's version (preferred)
                "m_span":   m_span,
                "c_span":   c_span,   # Claude's current text (to replace)
            })

    print(f"  Formatting-only spans identified: {spans_found:,}")
    return corrections, spans_found


# ── APPLY TO CLEAN.TXT ────────────────────────────────────────────────────────

def apply_to_clean_txt(corrections, path: Path):
    text = path.read_text(encoding="utf-8")
    applied = 0
    skipped = 0
    log_lines = []

    page_matches   = list(re.finditer(r'^\[Page\s+(\d+)[^\]]*\]', text, re.MULTILINE))
    page_positions = {
        int(m.group(1)): (
            m.start(),
            page_matches[i+1].start() if i+1 < len(page_matches) else len(text)
        )
        for i, m in enumerate(page_matches)
    }

    seen = set()

    for c in corrections:
        q_span = c["q_span"]
        c_span = c["c_span"]
        pages  = c["pages"]

        if not c_span or not c_span.strip():
            skipped += 1
            log_lines.append(f"SKIP (no C alignment)  {c['pdf']} s{c['spread']}  Q={repr(q_span[:40])}")
            continue

        if c_span == q_span:
            # Claude already has Q's version — no correction needed, span still dismissed
            log_lines.append(f"ALREADY OK  {c['pdf']} s{c['spread']}  {repr(q_span[:40])}")
            continue

        key = (frozenset(pages), c_span, q_span)
        if key in seen:
            continue
        seen.add(key)

        page_starts = [page_positions[p][0] for p in pages if p in page_positions]
        page_ends   = [page_positions[p][1] for p in pages if p in page_positions]
        if not page_starts:
            skipped += 1
            log_lines.append(f"SKIP (pages not found)  {c['pdf']} s{c['spread']}  {repr(c_span[:40])}")
            continue

        region_start = min(page_starts)
        region_end   = max(page_ends)
        region       = text[region_start:region_end]

        count = region.count(c_span)
        if count != 1:
            skipped += 1
            log_lines.append(f"SKIP (found {count}×)  {c['pdf']} s{c['spread']}  {repr(c_span[:40])}")
            continue

        new_region = region.replace(c_span, q_span, 1)
        text = text[:region_start] + new_region + text[region_end:]
        applied += 1
        log_lines.append(f"APPLY  {c['pdf']} s{c['spread']}  {repr(c_span[:40])} → {repr(q_span[:40])}")

    if not DRY_RUN:
        path.write_text(text, encoding="utf-8")

    return applied, skipped, log_lines


# ── APPLY TO JSON ─────────────────────────────────────────────────────────────

def apply_to_json(corrections, path: Path):
    data       = json.loads(path.read_text(encoding="utf-8"))
    page_index = {p["page_number"]: i for i, p in enumerate(data["pages"])}

    applied   = 0
    skipped   = 0
    log_lines = []
    seen      = set()

    for c in corrections:
        q_span = c["q_span"]
        c_span = c["c_span"]
        pages  = c["pages"]

        if not c_span or not c_span.strip() or c_span == q_span:
            continue

        key = (frozenset(pages), c_span, q_span)
        if key in seen:
            continue
        seen.add(key)

        target_blocks = []
        for pn in pages:
            if pn not in page_index:
                continue
            page_obj = data["pages"][page_index[pn]]
            for block in page_obj.get("content_blocks", []):
                if c_span in block.get("text", ""):
                    target_blocks.append(block)

        if len(target_blocks) != 1:
            skipped += 1
            log_lines.append(
                f"SKIP JSON ({len(target_blocks)} blocks)  "
                f"{c['pdf']} s{c['spread']}  {repr(c_span[:40])}"
            )
            continue

        target_blocks[0]["text"] = target_blocks[0]["text"].replace(c_span, q_span, 1)
        applied += 1
        log_lines.append(
            f"APPLY JSON  {c['pdf']} s{c['spread']}  "
            f"{repr(c_span[:40])} → {repr(q_span[:40])}"
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

    print("Finding formatting-only spans (quote / ellipsis / dash style) …")
    corrections, spans_found = find_corrections(qwen_spreads, mistral_spreads, claude_pages)

    print("Applying to men_of_maize_clean.txt …")
    txt_applied, txt_skipped, txt_log = apply_to_clean_txt(corrections, CLAUDE_FILE)
    print(f"  Applied: {txt_applied}   Skipped: {txt_skipped}")

    print("Applying to men_of_maize_structured.json …")
    json_applied, json_skipped, json_log = apply_to_json(corrections, JSON_FILE)
    print(f"  Applied: {json_applied}   Skipped: {json_skipped}")

    queue_before = 3948   # after Rule 2a (linebreak)
    queue_after  = queue_before - spans_found

    log = [
        "Punctuation Formatting Correction Log (Rule 2b)",
        f"Run: {'DRY RUN' if DRY_RUN else 'LIVE'}",
        f"Formatting-only Q≠M spans dismissed: {spans_found}",
        f"  (quote style: curly vs straight, ellipsis style, dash style)",
        f"clean.txt — applied: {txt_applied}, skipped: {txt_skipped}",
        f"JSON      — applied: {json_applied}, skipped: {json_skipped}",
        f"Queue before: {queue_before}  →  Queue after: {queue_after}",
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
    print(f"Formatting-only spans dismissed:  {spans_found:,}")
    print(f"  — deferred to Qwen (curly quotes, spaced ellipsis, em dash)")
    print(f"Corrections applied to clean.txt: {txt_applied}")
    print(f"Corrections applied to JSON:      {json_applied}")
    print(f"Q≠M span queue:  {queue_before:,} → {queue_after:,}")


if __name__ == "__main__":
    main()
