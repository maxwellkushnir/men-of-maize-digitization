"""
Men of Maize — Base swap: Claude → Mistral Large 3

Part 1: Assemble men_of_maize_clean.txt from Mistral raw files
Part 2: Hybrid JSON transplant — replace paragraph block text with Mistral-aligned
         text while preserving Claude's structural skeleton (headings, section numbers,
         section breaks, page metadata, chapter slugs, running headers).

KEY IMPLEMENTATION NOTE:
Mistral places [Page N] markers at the BOTTOM of each page (matching the printed
book page number position). This means body text for page N appears BEFORE the
[Page N] marker in the transcript, not after. The algorithm therefore uses the
FULL spread text for alignment rather than trying to extract per-page slices —
the SequenceMatcher finds the matching portion of each spread for each Claude page.

See proposed_base_swap.md for full specification and implementation decisions.

Usage:
    python3 14_build_mistral_base.py            # full run
    python3 14_build_mistral_base.py --dry-run  # no files written
"""

import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

BASE        = Path(__file__).parent
OUTPUT_DIR  = BASE / "output"
MISTRAL_DIR = OUTPUT_DIR / "mistral_raw"
CLEAN_TXT   = OUTPUT_DIR / "men_of_maize_clean.txt"
JSON_FILE   = OUTPUT_DIR / "men_of_maize_structured.json"
LOG_FILE    = OUTPUT_DIR / "mistral_base_transplant_log.txt"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

SPREAD_RE = re.compile(
    r'<<< SPREAD_START pdf="([^"]+)" spread="(\d+)"[^>]*>>>(.*?)<<< SPREAD_END >>>',
    re.DOTALL,
)
# Numeric [Page N] only — non-numeric variants ([Page Left], [Page RIGHT], etc.) excluded
PAGE_MARKER_RE = re.compile(r'\[Page (\d+)\]')

# Strip only the book-title running header that appears on every body page.
# More aggressive stripping risks removing legitimate body text (e.g. lines
# starting with character names), so we keep it minimal.
TITLE_HEADER_RE = re.compile(r'^MEN OF MAIZE\s*$', re.MULTILINE | re.IGNORECASE)

FALLBACK_CONFIDENCE = 0.5   # fraction of block words that must have a valid alignment
MIN_SPREAD_WORDS    = 5     # ignore spreads shorter than this (can't align meaningfully)


# ── NORMALISATION ─────────────────────────────────────────────────────────────

def norm(word: str) -> str:
    s = unicodedata.normalize("NFD", word.lower())
    return s.encode("ascii", "ignore").decode("ascii")

def norm_words(words: list) -> list:
    return [norm(w) for w in words]


# ── LOAD MISTRAL SPREADS ──────────────────────────────────────────────────────

def load_mistral_spreads() -> tuple[dict, dict, list]:
    """
    Returns:
      spread_text : {(pdf, spread_num) -> cleaned spread text (no spread markers)}
      page_to_spread : {page_num -> (pdf, spread_num)}  last-occurrence-wins
      log_lines  : list of log messages
    """
    spread_text: dict[tuple, str] = {}
    page_to_spread: dict[int, tuple] = {}
    duplicates: list[int] = []
    log_lines: list[str] = []

    for pdf_name in ALL_PDFS:
        path = MISTRAL_DIR / f"{pdf_name}_mistral.txt"
        if not path.exists():
            log_lines.append(f"WARNING: missing {path.name}")
            continue
        content = path.read_text(encoding="utf-8")

        for m in SPREAD_RE.finditer(content):
            spread_num = int(m.group(2))
            raw_text   = m.group(3)

            # Skip 2-25.pdf front matter — spreads 1-5 have only non-numeric
            # page markers and no body prose
            if pdf_name == "2-25.pdf" and spread_num <= 5:
                continue

            # Strip the "MEN OF MAIZE" running header; keep all other text
            cleaned = TITLE_HEADER_RE.sub("", raw_text).strip()
            spread_text[(pdf_name, spread_num)] = cleaned

            # Map numeric page numbers to their spread (last-occurrence-wins:
            # duplicate page 2 in 2-25.pdf — spread 7 has empty content,
            # spread 9 has the body text; overwriting gives us spread 9)
            for marker in PAGE_MARKER_RE.finditer(raw_text):
                page_num = int(marker.group(1))
                if page_num in page_to_spread:
                    duplicates.append(page_num)
                    log_lines.append(
                        f"DUPLICATE [Page {page_num}]: "
                        f"had {page_to_spread[page_num]}, "
                        f"overwriting with ({pdf_name}, spread {spread_num})"
                    )
                page_to_spread[page_num] = (pdf_name, spread_num)

    if duplicates:
        log_lines.append(f"Duplicate pages resolved: {sorted(set(duplicates))}")

    spread_count = len(spread_text)
    page_count   = len(page_to_spread)
    total_words  = sum(len(t.split()) for t in spread_text.values())
    log_lines.append(
        f"Loaded {spread_count} spreads, {page_count} unique page markers, "
        f"~{total_words:,} total words"
    )
    return spread_text, page_to_spread, log_lines


# ── PART 1: BUILD CLEAN.TXT ───────────────────────────────────────────────────

def build_clean_txt(spread_text: dict) -> list:
    """
    Write men_of_maize_clean.txt by concatenating all spread texts in book order.
    [Page N] markers are preserved in place. Text appearing before the first
    [Page N] in a spread (the left-side page whose number Mistral placed at the
    bottom) is included without a separate page marker.
    """
    log_lines: list[str] = []

    lines = [
        "MEN OF MAIZE",
        "by Miguel Ángel Asturias",
        "Translated by Gerald Martin",
        "(Delacorte Press / Seymour Lawrence, 1975)",
        "",
        "[Assembly note: Mistral Large 3 base — assembled from mistral_raw/ spread files]",
        "=" * 60,
        "",
    ]

    total_words = 0
    for pdf_name in ALL_PDFS:
        for key in sorted(spread_text, key=lambda k: (ALL_PDFS.index(k[0]), k[1])):
            if key[0] != pdf_name:
                continue
            text = spread_text[key]
            if text:
                lines.append(text)
                lines.append("")
                total_words += len(text.split())

    log_lines.append(f"clean.txt: ~{total_words:,} words (target ~118,116 ±1,000)")

    if not DRY_RUN:
        CLEAN_TXT.write_text("\n".join(lines), encoding="utf-8")
        log_lines.append(f"Written: {CLEAN_TXT}")
    else:
        log_lines.append("DRY RUN — clean.txt not written")

    return log_lines


# ── PART 2: HYBRID JSON TRANSPLANT ────────────────────────────────────────────

def transplant_json(spread_text: dict, page_to_spread: dict) -> list:
    """
    For each page in Claude's JSON:
      - Find the Mistral spread that contains [Page N] (via page_to_spread)
      - Use the FULL spread text for alignment (body text in Mistral spans both
        before and after the [Page N] marker; the spread is the correct unit)
      - Build Claude's page word sequence from ALL content blocks (headings
        included as alignment anchors)
      - Run SequenceMatcher; map Claude word indices to Mistral word indices
      - For each PARAGRAPH block: replace text with contiguous Mistral word range
        [min_mapped : max_mapped + 1]
      - Set _base_fallback=True on blocks where confidence < 0.5 or no mapping
    Non-paragraph blocks (chapter_heading, section_number, section_break) untouched.
    """
    data = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    log_lines: list[str] = []

    total_para = 0
    replaced   = 0
    fallback   = 0
    fallback_detail: list[str] = []

    for page in data["pages"]:
        page_num = page["page_number"]
        blocks   = page.get("content_blocks", [])
        para_blocks = [b for b in blocks if b.get("type") == "paragraph"]
        total_para += len(para_blocks)

        if not para_blocks:
            continue

        # Find the Mistral spread for this page
        spread_key   = page_to_spread.get(page_num)
        mistral_full = spread_text.get(spread_key, "") if spread_key else ""
        mistral_words = mistral_full.split() if mistral_full else []

        # Pages 22, 328 and any not covered by Mistral fall back to Claude
        if len(mistral_words) < MIN_SPREAD_WORDS:
            for b in para_blocks:
                b["_base_fallback"] = True
                fallback_detail.append(
                    f"  p{page_num:3d} [no/short Mistral spread]:  "
                    f"{repr(b.get('text', '')[:50])}"
                )
            fallback += len(para_blocks)
            continue

        # Build Claude word sequence from ALL blocks — headings provide alignment
        # anchors (Mistral also transcribes chapter headings and section numbers)
        all_claude_words: list[str] = []
        block_ranges: list[tuple]   = []   # (block_dict, c_start, c_end)
        for block in blocks:
            c_start = len(all_claude_words)
            words = block.get("text", "").split()
            all_claude_words.extend(words)
            c_end = len(all_claude_words)
            block_ranges.append((block, c_start, c_end))

        if not all_claude_words:
            continue

        # SequenceMatcher: Claude word index → Mistral word index
        sm = SequenceMatcher(
            None,
            norm_words(all_claude_words),
            norm_words(mistral_words),
            autojunk=False,
        )
        c_to_m: dict[int, int] = {}
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for d in range(i2 - i1):
                    c_to_m[i1 + d] = j1 + d

        # Replace paragraph blocks only; leave heading/section/break blocks untouched
        for block, c_start, c_end in block_ranges:
            if block.get("type") != "paragraph":
                continue
            block_len = c_end - c_start
            if block_len == 0:
                continue

            mapped = [c_to_m[ci] for ci in range(c_start, c_end) if ci in c_to_m]

            if not mapped:
                block["_base_fallback"] = True
                fallback += 1
                fallback_detail.append(
                    f"  p{page_num:3d} [no mapping]:         "
                    f"{repr(block.get('text', '')[:50])}"
                )
                continue

            confidence = len(mapped) / block_len
            if confidence < FALLBACK_CONFIDENCE:
                block["_base_fallback"] = True
                fallback += 1
                fallback_detail.append(
                    f"  p{page_num:3d} [conf {confidence:.2f}]:           "
                    f"{repr(block.get('text', '')[:50])}"
                )
                continue

            # Contiguous Mistral range — preserves Mistral's novel readings
            # in gap positions (where C and M diverge), not just mapped words
            min_m = min(mapped)
            max_m = max(mapped)
            block["text"] = " ".join(mistral_words[min_m : max_m + 1])
            replaced += 1

    log_lines.append("JSON transplant results:")
    log_lines.append(f"  Paragraph blocks total : {total_para}")
    log_lines.append(f"  Replaced with Mistral  : {replaced}")
    log_lines.append(f"  Fallback to Claude     : {fallback}")
    if fallback_detail:
        log_lines.append("  Fallback block detail:")
        log_lines.extend(fallback_detail)

    if not DRY_RUN:
        JSON_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log_lines.append(f"Written: {JSON_FILE}")
    else:
        log_lines.append("DRY RUN — JSON not written")

    return log_lines


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if DRY_RUN:
        print("DRY RUN — no files will be modified.\n")

    print("Loading Mistral spreads …")
    spread_text, page_to_spread, load_log = load_mistral_spreads()
    for line in load_log:
        print(f"  {line}")

    print(f"\nPart 1 — Building {CLEAN_TXT.name} …")
    clean_log = build_clean_txt(spread_text)
    for line in clean_log:
        print(f"  {line}")

    print(f"\nPart 2 — Hybrid JSON transplant ({JSON_FILE.name}) …")
    json_log = transplant_json(spread_text, page_to_spread)
    for line in json_log:
        print(f"  {line}")

    all_log = (
        ["Mistral Base Transplant Log", "=" * 60, ""]
        + load_log + [""]
        + clean_log + [""]
        + json_log
    )
    if not DRY_RUN:
        LOG_FILE.write_text("\n".join(all_log), encoding="utf-8")
        print(f"\nLog written to {LOG_FILE.name}")

    print("\nDone.")
    print("Next steps (see proposed_base_swap.md Steps 3–6):")
    print("  1. Review fallback blocks in mistral_base_transplant_log.txt")
    print("  2. Write and run 15_apply_cq_corrections.py (new Rule 1)")
    print("  3. Re-run 12_linebreak_hyphen.py and 13_punct_formatting.py")
    print("  4. Re-run 09_three_way_compare.py and 10_divergence_review.py")
    print("  5. Re-run 03_build_pdf.py → men_of_maize-14.pdf")


if __name__ == "__main__":
    main()
