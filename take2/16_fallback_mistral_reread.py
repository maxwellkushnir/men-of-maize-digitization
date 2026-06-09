"""
Men of Maize — Recover unverified fallback blocks from existing Mistral data

All 54 pages with _qwen_unverified blocks already have Mistral text in
mistral_raw/. The original transplant failed on ALIGNMENT (Claude's words
were too different from Mistral's for SequenceMatcher to reach 0.5 confidence),
not on coverage. This script uses paragraph-level fuzzy matching instead:

  For each _qwen_unverified block:
    1. Gather Mistral paragraphs from the page's spread ± 1 adjacent spread
    2. Compute word-recall: what fraction of Claude's (normalised) words
       appear in each Mistral paragraph
    3. Best match above threshold → replace block text with Mistral text
    4. No match → _mistral_unresolved (flag for manual review)
    5. Garbled OCR codes → _mistral_delete=True (set text to "" so PDF skips it)

Usage:
    python3 16_fallback_mistral_reread.py            # full run
    python3 16_fallback_mistral_reread.py --dry-run  # no files written
"""

import json
import re
import string
import sys
import unicodedata
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

BASE        = Path(__file__).parent
OUTPUT_DIR  = BASE / "output"
MISTRAL_DIR = OUTPUT_DIR / "mistral_raw"
JSON_FILE   = OUTPUT_DIR / "men_of_maize_structured.json"
LOG_FILE    = OUTPUT_DIR / "fallback_mistral_reread_log.txt"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

SPREAD_RE = re.compile(
    r'<<< SPREAD_START pdf="([^"]+)" spread="(\d+)"[^>]*>>>(.*?)<<< SPREAD_END >>>',
    re.DOTALL,
)
PAGE_MARKER_RE    = re.compile(r'\[Page (\d+)\]')
TITLE_HEADER_RE   = re.compile(r'^MEN OF MAIZE\s*$', re.MULTILINE | re.IGNORECASE)
SECTION_BREAK_RE  = re.compile(r'^\[section break\]\s*$', re.MULTILINE | re.IGNORECASE)
ALLCAPS_LINE_RE   = re.compile(r'^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ\s\-]{3,}$', re.MULTILINE)

# Patterns that indicate garbled OCR / print codes — not real book text
GARBLED_RE = re.compile(
    r'^('
    r'\d{3,}'                            # bare digits: 5609
    r'|[A-Z]{2,4}\d{2}[\s\d\-a-z]+'    # SE06 05990-01551m
    r'|[A-Z]{2,6}(?:\s+\d[\d\-]*){1,}' # SEDS 4 1930-01
    r'|[A-Z]{3,6}'                       # SECS
    r')$'
)

RECALL_THRESHOLD = 0.45   # fraction of Claude words that must appear in Mistral para
PRECISION_MIN    = 0.18   # avoid matching against a paragraph 5× longer than the block
MIN_BLOCK_WORDS  = 2      # blocks shorter than this can't be reliably matched


# ── NORMALISATION ─────────────────────────────────────────────────────────────

def norm(word: str) -> str:
    s = unicodedata.normalize("NFKD", word.lower())
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.replace("'", "")
    return s.strip(string.punctuation)

def norm_set(words: list) -> set:
    return {w for w in (norm(x) for x in words) if w}


# ── LOAD MISTRAL SPREADS ──────────────────────────────────────────────────────

def load_mistral_spreads() -> tuple[dict, dict]:
    spread_text: dict[tuple, str] = {}
    page_to_spread: dict[int, tuple] = {}

    for pdf_name in ALL_PDFS:
        path = MISTRAL_DIR / f"{pdf_name}_mistral.txt"
        if not path.exists():
            print(f"  WARNING: missing {path.name}")
            continue
        content = path.read_text(encoding="utf-8")
        for m in SPREAD_RE.finditer(content):
            snum = int(m.group(2))
            raw  = m.group(3)
            if pdf_name == "2-25.pdf" and snum <= 5:
                continue
            spread_text[(pdf_name, snum)] = raw
            for pm in PAGE_MARKER_RE.finditer(raw):
                page_to_spread[int(pm.group(1))] = (pdf_name, snum)

    return spread_text, page_to_spread


def get_mistral_paragraphs(page_num: int, spread_text: dict, page_to_spread: dict) -> list[str]:
    """
    Gather candidate Mistral paragraphs from the page's spread and its
    two neighbours (±1). Returns a list of paragraph strings.
    """
    primary = page_to_spread.get(page_num)
    if primary is None:
        for adj in [page_num - 1, page_num + 1, page_num - 2, page_num + 2]:
            if adj in page_to_spread:
                primary = page_to_spread[adj]
                break
    if primary is None:
        return []

    pdf_name, spread_num = primary
    paragraphs: list[str] = []

    for snum in [spread_num - 1, spread_num, spread_num + 1]:
        key = (pdf_name, snum)
        if key not in spread_text:
            continue
        raw = spread_text[key]
        cleaned = TITLE_HEADER_RE.sub("", raw)
        cleaned = PAGE_MARKER_RE.sub("", cleaned)
        cleaned = SECTION_BREAK_RE.sub("", cleaned)
        cleaned = ALLCAPS_LINE_RE.sub("", cleaned)
        paras = [p.strip() for p in re.split(r'\n\s*\n', cleaned) if p.strip()]
        paragraphs.extend(paras)

    return paragraphs


# ── MATCHING ─────────────────────────────────────────────────────────────────

def best_match(claude_words: list, candidates: list,
               used: set) -> tuple:
    """
    Find the best unused Mistral paragraph for a Claude block.
    Returns (paragraph_text, recall, precision).
    recall    = |intersection| / |claude_words|
    precision = |intersection| / |mistral_para_words|
    """
    cn = norm_set(claude_words)
    if not cn:
        return None, 0.0, 0.0

    best_recall = 0.0
    best_prec   = 0.0
    best_para   = None

    for para_text in candidates:
        if para_text in used:
            continue
        mn = norm_set(para_text.split())
        if not mn:
            continue
        inter    = cn & mn
        recall   = len(inter) / len(cn)
        precision = len(inter) / len(mn)
        if recall > best_recall:
            best_recall = recall
            best_prec   = precision
            best_para   = para_text

    return best_para, best_recall, best_prec


def is_garbled(text: str) -> bool:
    """True if the block text looks like a garbled OCR/print code."""
    return bool(GARBLED_RE.match(text.strip()))


# ── MAIN LOGIC ────────────────────────────────────────────────────────────────

def run(spread_text: dict, page_to_spread: dict) -> list[str]:
    data = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    log_lines: list[str] = []

    total = recovered = confirmed = garbled = unresolved = too_short = 0
    detail: list[str] = []

    for page in data["pages"]:
        page_num = page["page_number"]
        unverified = [b for b in page.get("content_blocks", [])
                      if b.get("_qwen_unverified")]
        if not unverified:
            continue

        candidates = get_mistral_paragraphs(page_num, spread_text, page_to_spread)
        used: set[str] = set()   # prevent two blocks claiming the same Mistral para

        for block in unverified:
            total += 1
            claude_text  = block.get("text", "")
            claude_words = claude_text.split()

            # ── Garbled OCR code ─────────────────────────────────────────────
            if is_garbled(claude_text):
                norm_claude = norm(claude_text)
                all_mistral = " ".join(candidates)
                if norm_claude not in norm(all_mistral):
                    block["text"]             = ""
                    block["_mistral_delete"]  = True
                    block.pop("_qwen_unverified", None)
                    garbled += 1
                    msg = f"GARBLED   p{page_num:3d}: {repr(claude_text)}"
                    log_lines.append(msg); detail.append(msg)
                    continue

            # ── Too short to match reliably ───────────────────────────────────
            if len(claude_words) < MIN_BLOCK_WORDS:
                block["_mistral_unresolved"] = True
                too_short += 1
                log_lines.append(f"TOO SHORT p{page_num:3d}: {repr(claude_text)}")
                continue

            # ── No Mistral paragraphs available ──────────────────────────────
            if not candidates:
                block["_mistral_unresolved"] = True
                unresolved += 1
                log_lines.append(f"NO MISTRAL p{page_num:3d}: {repr(claude_text[:60])}")
                continue

            # ── Fuzzy paragraph match ─────────────────────────────────────────
            para_text, recall, precision = best_match(claude_words, candidates, used)

            if recall >= RECALL_THRESHOLD and precision >= PRECISION_MIN:
                used.add(para_text)
                new_text = para_text
                if new_text.strip() != claude_text.strip():
                    old = block["text"]
                    block["text"]               = new_text
                    block["_mistral_recovered"] = True
                    block.pop("_qwen_unverified", None)
                    recovered += 1
                    msg = (f"RECOVERED p{page_num:3d} (R={recall:.2f} P={precision:.2f}): "
                           f"{repr(old[:45])} → {repr(new_text[:45])}")
                    log_lines.append(msg); detail.append(msg)
                else:
                    block["_mistral_confirmed"] = True
                    block.pop("_qwen_unverified", None)
                    confirmed += 1
                    log_lines.append(
                        f"CONFIRMED p{page_num:3d} (R={recall:.2f}): {repr(claude_text[:60])}"
                    )
            else:
                block["_mistral_unresolved"] = True
                unresolved += 1
                log_lines.append(
                    f"UNRESOLVED p{page_num:3d} (R={recall:.2f} P={precision:.2f}): "
                    f"{repr(claude_text[:60])}"
                )

    summary = [
        "Fallback Mistral re-read results:",
        f"  Total unverified blocks : {total}",
        f"  Recovered (text changed): {recovered}",
        f"  Confirmed (text same)   : {confirmed}",
        f"  Garbled (blanked out)   : {garbled}",
        f"  Unresolved              : {unresolved}",
        f"  Too short               : {too_short}",
    ]
    if detail:
        summary.append("  Changes / deletions:")
        summary.extend(f"    {l}" for l in detail)

    if not DRY_RUN:
        JSON_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary + [""] + log_lines


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if DRY_RUN:
        print("DRY RUN — no files will be modified.\n")

    print("Loading Mistral spreads …")
    spread_text, page_to_spread = load_mistral_spreads()
    print(f"  {len(spread_text)} spreads, {len(page_to_spread)} page markers")

    print("\nRecovering unverified fallback blocks …")
    log_lines = run(spread_text, page_to_spread)

    for line in log_lines[:14]:
        print(f"  {line}")

    if not DRY_RUN:
        LOG_FILE.write_text("\n".join(log_lines), encoding="utf-8")
        print(f"\n  Full log: {LOG_FILE.name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
