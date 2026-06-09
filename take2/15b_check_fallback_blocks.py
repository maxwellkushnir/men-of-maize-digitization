"""
Men of Maize — Check and correct fallback blocks using Qwen

For each paragraph block in men_of_maize_structured.json that has _base_fallback=True
(blocks the Mistral transplant couldn't align), compare against Qwen's transcription:

  confidence >= 0.5, text matches  → _qwen_verified=True, no change
  confidence >= 0.5, text differs  → apply Qwen's reading, _qwen_corrected=True
  confidence < 0.5                 → _qwen_unverified=True, no change

Qwen is a reliable reference: it agreed with Mistral 94–97% of the time, and is
fully independent of Claude.

To maximise coverage of early-chapter pages (where Claude and Qwen may have
labelled the same spread with different page numbers), the Qwen spread for a
given Claude page is augmented with the adjacent spreads (±1) from the same PDF.

Usage:
    python3 15b_check_fallback_blocks.py            # full run
    python3 15b_check_fallback_blocks.py --dry-run  # no files written
"""

import json
import re
import string
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

BASE       = Path(__file__).parent
OUTPUT_DIR = BASE / "output"
QWEN_DIR   = OUTPUT_DIR / "qwen_raw"
JSON_FILE  = OUTPUT_DIR / "men_of_maize_structured.json"
LOG_FILE   = OUTPUT_DIR / "fallback_qwen_check_log.txt"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

SPREAD_RE = re.compile(
    r'<<< SPREAD_START pdf="([^"]+)" spread="(\d+)"[^>]*>>>(.*?)<<< SPREAD_END >>>',
    re.DOTALL,
)
PAGE_MARKER_RE  = re.compile(r'\[Page (\d+)\]')
TITLE_HEADER_RE = re.compile(r'^MEN OF MAIZE\s*$', re.MULTILINE | re.IGNORECASE)
# All-caps standalone lines are chapter headings / running headers in adjacent spreads
ALLCAPS_LINE_RE = re.compile(r'^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ\s\-]{3,}$', re.MULTILINE)

FALLBACK_CONFIDENCE = 0.5
MIN_BLOCK_WORDS     = 2     # skip blocks shorter than this (too ambiguous to align)


# ── NORMALISATION ─────────────────────────────────────────────────────────────

def norm(word: str) -> str:
    s = unicodedata.normalize("NFKD", word.lower())  # NFKD expands ligatures (ﬁ→fi, ﬂ→fl)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.replace("'", "")  # curly apostrophes already dropped; remove surviving straight ones
    return s.strip(string.punctuation)

def norm_words(words: list) -> list:
    return [norm(w) for w in words]


# ── LOAD QWEN SPREADS ─────────────────────────────────────────────────────────

def load_qwen_spreads() -> tuple[dict, dict]:
    """
    Returns:
      spread_text    : {(pdf, spread_num) -> cleaned spread text}
      page_to_spread : {page_num -> (pdf, spread_num)}  last-occurrence-wins
    """
    spread_text: dict[tuple, str] = {}
    page_to_spread: dict[int, tuple] = {}

    for pdf_name in ALL_PDFS:
        path = QWEN_DIR / f"{pdf_name}_qwen.txt"
        if not path.exists():
            print(f"  WARNING: missing {path.name}")
            continue
        content = path.read_text(encoding="utf-8")

        for m in SPREAD_RE.finditer(content):
            spread_num = int(m.group(2))
            raw_text   = m.group(3)

            if pdf_name == "2-25.pdf" and spread_num <= 5:
                continue

            cleaned = TITLE_HEADER_RE.sub("", raw_text).strip()
            cleaned = PAGE_MARKER_RE.sub("", cleaned).strip()   # remove [Page N] from alignment text
            cleaned = ALLCAPS_LINE_RE.sub("", cleaned).strip()  # remove chapter headings / running headers
            spread_text[(pdf_name, spread_num)] = cleaned

            for marker in PAGE_MARKER_RE.finditer(raw_text):
                page_num = int(marker.group(1))
                page_to_spread[page_num] = (pdf_name, spread_num)  # last-wins

    return spread_text, page_to_spread


def get_qwen_reference(page_num: int, spread_text: dict, page_to_spread: dict) -> str:
    """
    Return combined Qwen text for a Claude page: primary spread plus adjacent
    spreads (±1) to handle cases where Claude's page content sits in a
    neighbouring Qwen spread (common in the early GASPAR ILÓM pages).
    """
    primary = page_to_spread.get(page_num)

    # If page_num not mapped, try the closest neighbour
    if primary is None:
        for adj in [page_num - 1, page_num + 1, page_num - 2, page_num + 2]:
            if adj in page_to_spread:
                primary = page_to_spread[adj]
                break

    if primary is None:
        return ""

    pdf_name, spread_num = primary
    parts = []
    for snum in [spread_num - 1, spread_num, spread_num + 1]:
        key = (pdf_name, snum)
        if key in spread_text:
            parts.append(spread_text[key])

    return " ".join(parts)


# ── ALIGN BLOCK AGAINST QWEN REFERENCE ────────────────────────────────────────

def check_block(claude_words: list, qwen_words: list) -> tuple[float, list]:
    """
    Align claude_words against qwen_words via SequenceMatcher.
    Returns (confidence, qwen_replacement_words).
    confidence = fraction of claude_words with a valid alignment position.
    qwen_replacement_words = contiguous Qwen range covering the matched region.
    """
    if not qwen_words:
        return 0.0, []

    sm = SequenceMatcher(
        None,
        norm_words(claude_words),
        norm_words(qwen_words),
        autojunk=False,
    )
    c_to_q: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for d in range(i2 - i1):
                c_to_q[i1 + d] = j1 + d

    mapped = [c_to_q[ci] for ci in range(len(claude_words)) if ci in c_to_q]
    if not mapped:
        return 0.0, []

    confidence  = len(mapped) / len(claude_words)
    min_q, max_q = min(mapped), max(mapped)
    replacement  = qwen_words[min_q : max_q + 1]
    return confidence, replacement


def texts_match(claude_words: list, qwen_replacement: list) -> bool:
    """True if Qwen's replacement is the same as Claude's text (normalised).
    Empty norms (standalone em-dashes etc.) are excluded so spacing differences
    around punctuation don't cause false mismatches."""
    cn = [n for n in norm_words(claude_words) if n]
    rn = [n for n in norm_words(qwen_replacement) if n]
    return cn == rn


# ── MAIN LOGIC ────────────────────────────────────────────────────────────────

def run(spread_text: dict, page_to_spread: dict) -> list:
    data = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    log_lines: list[str] = []

    total_fallback = verified = corrected = unverified = skipped = 0
    correction_detail: list[str] = []

    for page in data["pages"]:
        page_num = page["page_number"]
        qwen_ref  = get_qwen_reference(page_num, spread_text, page_to_spread)
        qwen_words = qwen_ref.split() if qwen_ref else []

        for block in page.get("content_blocks", []):
            if not block.get("_base_fallback"):
                continue
            if block.get("type") != "paragraph":
                continue

            total_fallback += 1
            claude_words = block.get("text", "").split()

            # Skip blocks that are too short to align reliably
            if len(claude_words) < MIN_BLOCK_WORDS:
                block["_qwen_unverified"] = True
                unverified += 1
                log_lines.append(
                    f"SKIP (too short) p{page_num:3d}: {repr(block.get('text',''))}"
                )
                continue

            if not qwen_words:
                block["_qwen_unverified"] = True
                unverified += 1
                log_lines.append(
                    f"SKIP (no Qwen spread) p{page_num:3d}: {repr(block.get('text','')[:50])}"
                )
                continue

            confidence, qwen_replacement = check_block(claude_words, qwen_words)

            if confidence < FALLBACK_CONFIDENCE:
                block["_qwen_unverified"] = True
                unverified += 1
                log_lines.append(
                    f"UNVERIFIED (conf {confidence:.2f}) p{page_num:3d}: "
                    f"{repr(block.get('text','')[:50])}"
                )
                continue

            # Sanity check 1: replacement length should be close to block length.
            # If the ratio is way off, SequenceMatcher found the wrong region.
            length_ratio = len(qwen_replacement) / max(1, len(claude_words))
            if not (0.7 <= length_ratio <= 1.5):
                block["_qwen_unverified"] = True
                unverified += 1
                log_lines.append(
                    f"UNVERIFIED (length ratio {length_ratio:.2f}) p{page_num:3d}: "
                    f"{repr(block.get('text','')[:50])}"
                )
                continue

            # Sanity check 2: replacement content should be ≥70% similar to the
            # original block. If it's not, the alignment landed on the wrong passage
            # (e.g. chapter heading instead of body paragraph).
            sm_verify = SequenceMatcher(
                None, norm_words(claude_words), norm_words(qwen_replacement), autojunk=False
            )
            verify_ratio = sm_verify.ratio()
            if verify_ratio < 0.70:
                block["_qwen_unverified"] = True
                unverified += 1
                log_lines.append(
                    f"UNVERIFIED (verify {verify_ratio:.2f}) p{page_num:3d}: "
                    f"{repr(block.get('text','')[:50])}"
                )
                continue

            # Sanity check 3: reject if replacement contains Qwen line-break hyphen
            # artifacts (word ending in "-"). These split a single word across two
            # tokens (e.g. "mari-" + "golds") and would corrupt the block text.
            if any(w.endswith("-") for w in qwen_replacement):
                block["_qwen_unverified"] = True
                unverified += 1
                log_lines.append(
                    f"UNVERIFIED (line-break hyphen) p{page_num:3d}: "
                    f"{repr(block.get('text','')[:50])}"
                )
                continue

            if texts_match(claude_words, qwen_replacement):
                block["_qwen_verified"] = True
                verified += 1
                log_lines.append(
                    f"VERIFIED p{page_num:3d}: {repr(block.get('text','')[:60])}"
                )
            else:
                old_text = block["text"]
                new_text = " ".join(qwen_replacement)
                block["text"]           = new_text
                block["_qwen_corrected"] = True
                corrected += 1
                msg = (
                    f"CORRECT  p{page_num:3d}: "
                    f"{repr(old_text[:50])} → {repr(new_text[:50])}"
                )
                log_lines.append(msg)
                correction_detail.append(msg)

    summary = [
        "Fallback block Qwen check results:",
        f"  Total fallback blocks checked : {total_fallback}",
        f"  Verified (Q agrees with C)   : {verified}",
        f"  Corrected (Q differs from C) : {corrected}",
        f"  Unverified (low confidence)  : {unverified}",
        f"  Skipped (too short)          : {skipped}",
    ]
    if correction_detail:
        summary.append("  Corrections applied:")
        summary.extend(f"    {l}" for l in correction_detail)

    if not DRY_RUN:
        JSON_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary + [""] + log_lines


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if DRY_RUN:
        print("DRY RUN — no files will be modified.\n")

    print("Loading Qwen spreads …")
    spread_text, page_to_spread = load_qwen_spreads()
    total_words = sum(len(t.split()) for t in spread_text.values())
    print(f"  {len(spread_text)} spreads, {len(page_to_spread)} page markers, ~{total_words:,} words")

    print("\nChecking fallback blocks …")
    log_lines = run(spread_text, page_to_spread)

    # Print summary (first 12 lines) to stdout
    for line in log_lines[:12]:
        print(f"  {line}")

    if not DRY_RUN:
        LOG_FILE.write_text("\n".join(log_lines), encoding="utf-8")
        print(f"\n  Full detail log: {LOG_FILE.name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
