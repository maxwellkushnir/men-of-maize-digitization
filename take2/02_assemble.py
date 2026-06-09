"""
Men of Maize — Stage 2: Assembly & Cleanup
Reads all raw transcription files, cleans them, and produces:
  - men_of_maize_clean.txt        (human-readable full text)
  - men_of_maize_structured.json  (structured data for PDF builder)
  - men_of_maize_assembly_log.txt (processing notes)

Usage:
    python3 02_assemble.py

Run after all 5 PDFs have been transcribed by 01_transcribe.py.
"""

import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

OUTPUT_DIR = Path(__file__).parent / "output"

# Raw files in book reading order (2-25 last because its pages sort into early positions)
RAW_FILE_ORDER = [
    "26-55.pdf_raw.txt",
    "56-75.pdf_raw.txt",
    "76-107.pdf_raw.txt",
    "108-.pdf_raw.txt",
    "2-25.pdf_raw.txt",
]

# Canonical chapter names — used for fuzzy matching
CHAPTERS = [
    {"slug": "gaspar_ilom",           "heading": "GASPAR ILÓM",                  "running_header": "GASPAR ILÓM"},
    {"slug": "machojon",              "heading": "MACHOJÓN",                      "running_header": "MACHOJÓN"},
    {"slug": "deer_seventh_fire",     "heading": "THE DEER OF THE SEVENTH FIRE",  "running_header": "THE DEER OF THE SEVENTH FIRE"},
    {"slug": "colonel_chalo_godoy",   "heading": "COLONEL CHALO GODOY",           "running_header": "COLONEL CHALO GODOY"},
    {"slug": "maria_tecun",           "heading": "MARÍA TECÚN",                   "running_header": "MARÍA TECÚN"},
    {"slug": "coyote_postman",        "heading": "COYOTE-POSTMAN",                "running_header": "COYOTE-POSTMAN"},
    {"slug": "epilogue",              "heading": "EPILOGUE",                       "running_header": "EPILOGUE"},
]

CHAPTER_HEADINGS = [c["heading"] for c in CHAPTERS]
# ASCII-folded versions for matching (Claude sometimes drops accents)
CHAPTER_HEADINGS_FOLDED = [
    h.replace("Ó", "O").replace("Ó", "O").replace("Á", "A").replace("Ú", "U").replace("É", "E")
    for h in CHAPTER_HEADINGS
]

# Running header text that appears at tops of pages — discard these as noise
RUNNING_HEADER_NOISE = {"MEN OF MAIZE", "MEN OF MAIZE\n"} | set(CHAPTER_HEADINGS) | set(CHAPTER_HEADINGS_FOLDED)

# Section break variant strings that Claude might output
SECTION_BREAK_VARIANTS = re.compile(
    r"^\[?(section break|decorative break|ornament(?:al)? break?|small square|ornament|divider)\]?$",
    re.IGNORECASE,
)

ROMAN_NUMERAL    = re.compile(r"^[IVX]+$")
PAGE_NUMBER      = re.compile(r"^\[Page\s+(\d+)\]$")
BARE_PAGE_NUMBER = re.compile(r"^\d{1,4}$")

# ── HELPERS ───────────────────────────────────────────────────────────────────

def ascii_fold(s: str) -> str:
    return (s.replace("Ó","O").replace("ó","o").replace("Á","A").replace("á","a")
             .replace("Ú","U").replace("ú","u").replace("É","E").replace("é","e")
             .replace("Í","I").replace("í","i"))


def match_chapter(line: str) -> Optional[dict]:
    stripped = line.strip()
    folded   = ascii_fold(stripped)
    # Exact match first
    for ch in CHAPTERS:
        if stripped == ch["heading"] or folded == ascii_fold(ch["heading"]):
            return ch
    # Fuzzy match
    matches = difflib.get_close_matches(folded, [ascii_fold(h) for h in CHAPTER_HEADINGS], n=1, cutoff=0.85)
    if matches:
        idx = [ascii_fold(h) for h in CHAPTER_HEADINGS].index(matches[0])
        return CHAPTERS[idx]
    return None


def is_running_header_noise(line: str) -> bool:
    stripped = line.strip()
    if stripped in RUNNING_HEADER_NOISE or ascii_fold(stripped) in {ascii_fold(n) for n in RUNNING_HEADER_NOISE}:
        return True
    # Fuzzy match for OCR variants of known running headers (e.g., "MEN OF MAREL" for "MEN OF MAIZE")
    matches = difflib.get_close_matches(
        stripped.upper(), [n.upper() for n in RUNNING_HEADER_NOISE], n=1, cutoff=0.80
    )
    return bool(matches)


def ends_mid_sentence(text: str) -> bool:
    t = text.rstrip()
    if not t:
        return False
    last_char = t[-1]
    sentence_end_chars = set('.!?"\'') | {'‘', '’', '“', '”'}
    return last_char not in sentence_end_chars and (last_char == "-" or last_char.islower())


def starts_mid_sentence(text: str) -> bool:
    t = text.lstrip()
    if not t:
        return False
    return t[0].islower()

# ── BLOCK TYPES ───────────────────────────────────────────────────────────────

@dataclass
class Block:
    type: str
    text: str = ""
    # for needs_review blocks
    source_pdf: str = ""
    spread_number: int = 0

# ── PARSING ───────────────────────────────────────────────────────────────────

def parse_raw_file(path: Path, log_lines: list) -> list:
    """
    Parse a _raw.txt file into a list of (pdf_name, spread_num, total, content_str) tuples.
    """
    if not path.exists():
        log_lines.append(f"WARNING: {path.name} not found — skipping.")
        return []

    content = path.read_text(encoding="utf-8")
    start_pat = re.compile(r'<<< SPREAD_START pdf="([^"]+)" spread="(\d+)" total="(\d+)" >>>')
    end_marker = "<<< SPREAD_END >>>"
    results = []
    pos = 0
    while True:
        m = start_pat.search(content, pos)
        if not m:
            break
        pdf_name   = m.group(1)
        spread_num = int(m.group(2))
        total      = int(m.group(3))
        end_pos    = content.find(end_marker, m.end())
        if end_pos == -1:
            log_lines.append(f"  WARNING: {pdf_name} spread {spread_num} has no SPREAD_END — incomplete, skipping.")
            break
        block_content = content[m.end():end_pos].strip()
        results.append((pdf_name, spread_num, total, block_content))
        pos = end_pos + len(end_marker)
    return results


def parse_spread_content(pdf_name: str, spread_num: int, raw: str, log_lines: list,
                         is_front_matter_spread: bool = False) -> tuple:
    """
    Parse one spread's raw text into:
      - a list of (page_number, [Block]) pairs  (may be 0, 1, or 2 pages)
      - a list of orphan blocks (content before first page marker — front matter)
    Returns: (pages_list, front_matter_blocks)
    pages_list: [ (page_num, inferred:bool, [Block]) ]
    """
    lines = raw.splitlines()

    # Check for NEEDS_REVIEW / EXTRACTION_ERROR first
    if lines and ("[NEEDS_REVIEW" in lines[0] or "[EXTRACTION_ERROR" in lines[0]):
        needs_pdf = pdf_name
        block = Block(type="needs_review", source_pdf=needs_pdf, spread_number=spread_num)
        return [], [block]

    pages        = []         # (page_num, inferred, [Block])
    current_page = None
    current_inferred = False
    current_blocks: list[Block] = []
    orphan_blocks: list[Block] = []   # content before first [Page N]
    paragraph_buf: list[str] = []

    def flush_paragraph():
        if paragraph_buf:
            # Rejoin words split by line-end hyphenation ("disap-" + "peared" → "disappeared")
            joined = []
            for part in paragraph_buf:
                if joined and joined[-1].endswith("-"):
                    joined[-1] = joined[-1][:-1] + part
                else:
                    joined.append(part)
            text = " ".join(joined).strip()
            # Catch intra-line hyphenation artifacts ("Te- cún" → "Tecún")
            text = re.sub(r'([a-záéíóúüñ])- ([a-záéíóúüñ])', lambda m: m.group(1) + m.group(2), text)
            if text:
                target = current_blocks if current_page is not None else orphan_blocks
                # Attempt to join with previous paragraph if mid-sentence continuation
                if (target and target[-1].type == "paragraph"
                        and ends_mid_sentence(target[-1].text)
                        and starts_mid_sentence(text)):
                    if target[-1].text.endswith("-"):
                        target[-1].text = target[-1].text[:-1] + text
                    else:
                        target[-1].text += " " + text
                    log_lines.append(f"  {pdf_name} spread {spread_num}: joined mid-sentence paragraph")
                else:
                    target.append(Block(type="paragraph", text=text))
            paragraph_buf.clear()

    def commit_page():
        nonlocal current_page, current_blocks, current_inferred
        if current_page is not None:
            flush_paragraph()
            pages.append((current_page, current_inferred, current_blocks))
            current_blocks = []

    for line in lines:
        stripped = line.strip()

        # Skip empty lines → paragraph separator
        if not stripped:
            flush_paragraph()
            continue

        # Strip Markdown header prefix that Mistral OCR emits (e.g., "# MEN OF MAIZE")
        if stripped.startswith('#'):
            stripped = stripped.lstrip('#').strip()
            if not stripped:
                continue

        # Discard spread-side labels Mistral emits (e.g., "LEFT PAGE:", "RIGHT PAGE:")
        if re.match(r'^(?:LEFT|RIGHT)\s+PAGE\s*:?$', stripped, re.IGNORECASE):
            continue

        # Discard OCR image-description artifacts:
        #   "[Page (left side - blank except for reversed text showing through)]"
        #   "[The left page appears blank...]"  "[This page is too faint...]" etc.
        if stripped.startswith('[') and stripped not in ('[...]', '[section break]') \
                and '[NEEDS_REVIEW' not in stripped and '[EXTRACTION_ERROR' not in stripped:
            if (stripped.startswith('[Page ') and not PAGE_NUMBER.match(stripped)) or \
               re.match(r'^\[(?:The |This |Left|Right|Both |Blank|No |I |A |An )', stripped, re.IGNORECASE) or \
               re.search(r'\b(?:blank|faint|washed.out|unclear|cannot|unable to|transcrib|not.visible|illegible)\b',
                         stripped, re.IGNORECASE):
                log_lines.append(
                    f"  {pdf_name} spread {spread_num}: discarded image description: {stripped[:70]!r}"
                )
                continue

        # Page number marker
        pm = PAGE_NUMBER.match(stripped)
        if pm:
            flush_paragraph()
            commit_page()
            current_page    = int(pm.group(1))
            current_inferred = False
            continue

        # Chapter heading (skip in front matter — TOC entries fuzzy-match chapter names)
        if not is_front_matter_spread:
            ch = match_chapter(stripped)
            if ch:
                flush_paragraph()
                target = current_blocks if current_page is not None else orphan_blocks
                if not (target and target[-1].type == "chapter_heading"):  # deduplicate
                    target.append(Block(type="chapter_heading", text=ch["heading"]))
                    log_lines.append(f"  {pdf_name} spread {spread_num}: chapter heading → {ch['heading']}")
                continue

        # Bare printed page numbers from original book (e.g., "37") — discard
        if BARE_PAGE_NUMBER.match(stripped) and 1 <= int(stripped) <= 500:
            flush_paragraph()
            log_lines.append(f"  {pdf_name} spread {spread_num}: discarded bare page number: {stripped!r}")
            continue

        # Running header noise — discard (skip in front matter — TOC entries fuzzy-match)
        if not is_front_matter_spread and is_running_header_noise(stripped):
            log_lines.append(f"  {pdf_name} spread {spread_num}: discarded running header noise: {stripped!r}")
            continue

        # Section break variants
        if SECTION_BREAK_VARIANTS.match(stripped):
            flush_paragraph()
            target = current_blocks if current_page is not None else orphan_blocks
            target.append(Block(type="section_break"))
            log_lines.append(f"  {pdf_name} spread {spread_num}: normalized section break: {stripped!r}")
            continue

        # Literal [section break] already clean
        if stripped == "[section break]":
            flush_paragraph()
            target = current_blocks if current_page is not None else orphan_blocks
            target.append(Block(type="section_break"))
            continue

        # Roman numeral section number
        if ROMAN_NUMERAL.match(stripped):
            flush_paragraph()
            target = current_blocks if current_page is not None else orphan_blocks
            target.append(Block(type="section_number", text=stripped))
            continue

        # Italic block (lines starting/ending with *)
        if stripped.startswith("*") or stripped.startswith("_"):
            flush_paragraph()
            text = stripped.strip("*_")
            target = current_blocks if current_page is not None else orphan_blocks
            target.append(Block(type="italic_block", text=text))
            continue

        # NEEDS_REVIEW inline marker
        if "[NEEDS_REVIEW" in stripped or "[EXTRACTION_ERROR" in stripped:
            flush_paragraph()
            target = current_blocks if current_page is not None else orphan_blocks
            target.append(Block(type="needs_review", source_pdf=pdf_name, spread_number=spread_num))
            continue

        # Gutter gap marker — keep as text
        if stripped == "[...]":
            paragraph_buf.append("[...]")
            continue

        # Regular text line
        paragraph_buf.append(stripped)

    flush_paragraph()
    commit_page()

    return pages, orphan_blocks

# ── ASSEMBLY ──────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_lines = []

    # Check all raw files exist
    missing = [f for f in RAW_FILE_ORDER if not (OUTPUT_DIR / f).exists()]
    if missing:
        print("WARNING: Some raw files not yet generated:")
        for m in missing:
            print(f"  {m}")
        print("Proceeding with available files. Re-run after generating missing files.\n")

    # Parse all spreads
    all_spread_data = []  # (pdf_name, spread_num, total, raw_content)
    for fname in RAW_FILE_ORDER:
        fpath = OUTPUT_DIR / fname
        spreads = parse_raw_file(fpath, log_lines)
        all_spread_data.extend(spreads)
        log_lines.append(f"Loaded {len(spreads)} spreads from {fname}")

    # Parse each spread into page-level data
    # pages_by_num: dict[int, (chapter_slug, is_inferred, [Block])]
    pages_by_num: dict = {}
    front_matter_blocks: list[Block] = []
    current_chapter = None
    needs_review_list = []

    last_page_num = 0
    last_page_by_pdf: dict = {}          # pdf_name → last page number seen from that PDF
    seen_first_marker_by_pdf: dict = {}  # pdf_name → True once we see a [Page N] marker

    for pdf_name, spread_num, total, raw in all_spread_data:
        has_page_marker = bool(re.search(r'^\[Page\s+\d+\]', raw, re.MULTILINE))
        is_front_matter_spread = (
            pdf_name == "2-25.pdf"
            and not has_page_marker
            and not seen_first_marker_by_pdf.get(pdf_name, False)
        )
        pages, orphans = parse_spread_content(pdf_name, spread_num, raw, log_lines,
                                               is_front_matter_spread=is_front_matter_spread)

        # Track whether this PDF has produced any page-numbered content yet
        if pages:
            seen_first_marker_by_pdf[pdf_name] = True

        # Orphan blocks: content before the first [Page N] marker in a spread.
        # Real front matter = early spreads of 2-25.pdf before its first page marker
        # (title page, copyright, TOC). Everything else is body content (Mistral OCR
        # output, which lacks [Page N] markers) → assign to an inferred page.
        if orphans:
            is_pre_marker = not seen_first_marker_by_pdf.get(pdf_name, False)
            is_real_front_matter = (pdf_name == "2-25.pdf" and is_pre_marker)

            body_orphans: list[Block] = []
            for blk in orphans:
                if blk.type == "needs_review":
                    needs_review_list.append({
                        "source_pdf": pdf_name,
                        "spread_number": spread_num,
                        "estimated_pages": [last_page_num + 1],
                        "failed_jpeg_path": f"../../Take 1/failed_spreads/{pdf_name}_spread_{spread_num:03d}.jpg",
                    })
                elif is_real_front_matter:
                    front_matter_blocks.append(blk)
                else:
                    body_orphans.append(blk)

            if body_orphans:
                # Update current chapter from any chapter headings in orphan content
                for blk in body_orphans:
                    if blk.type == "chapter_heading":
                        ch = match_chapter(blk.text)
                        if ch:
                            current_chapter = ch["slug"]

                # Assign an inferred page number: start after the last page seen
                # from this same PDF, incrementing to avoid collisions.
                pdf_last = last_page_by_pdf.get(pdf_name, 0)
                inferred_pg = pdf_last + 2
                while inferred_pg in pages_by_num:
                    inferred_pg += 1
                last_page_by_pdf[pdf_name] = inferred_pg

                pages_by_num[inferred_pg] = {
                    "page_number": inferred_pg,
                    "page_number_inferred": True,
                    "chapter_slug": current_chapter,
                    "is_chapter_start": any(b.type == "chapter_heading" for b in body_orphans),
                    "is_right_page": inferred_pg % 2 == 1,
                    "needs_review": False,
                    "content_blocks": [block_to_dict(b) for b in body_orphans],
                }
                last_page_num = max(last_page_num, inferred_pg)
                log_lines.append(
                    f"  {pdf_name} spread {spread_num}: orphan body content → inferred page {inferred_pg}"
                )

        for page_num, inferred, blocks in pages:
            # Update current chapter if this page starts with a chapter heading
            for blk in blocks:
                if blk.type == "chapter_heading":
                    ch = match_chapter(blk.text)
                    if ch:
                        current_chapter = ch["slug"]

            # Handle needs_review blocks
            has_review = any(b.type == "needs_review" for b in blocks)
            if has_review:
                needs_review_list.append({
                    "source_pdf": pdf_name,
                    "spread_number": spread_num,
                    "estimated_pages": [page_num] if not inferred else [page_num, page_num + 1],
                    "failed_jpeg_path": f"../../Take 1/failed_spreads/{pdf_name}_spread_{spread_num:03d}.jpg",
                })

            if page_num in pages_by_num:
                log_lines.append(f"  WARNING: duplicate page {page_num} from {pdf_name} spread {spread_num} — skipping duplicate")
                continue

            pages_by_num[page_num] = {
                "page_number": page_num,
                "page_number_inferred": inferred,
                "chapter_slug": current_chapter,
                "is_chapter_start": any(b.type == "chapter_heading" for b in blocks),
                "is_right_page": page_num % 2 == 1,
                "needs_review": has_review,
                "content_blocks": [block_to_dict(b) for b in blocks],
            }
            last_page_num = max(last_page_num, page_num)
            last_page_by_pdf[pdf_name] = max(last_page_by_pdf.get(pdf_name, 0), page_num)

    # Sort pages numerically
    sorted_pages = [pages_by_num[n] for n in sorted(pages_by_num.keys())]

    # Remove duplicate chapter headings — running headers at the top of each page
    # are transcribed as chapter names and mis-parsed as headings; only keep the first
    # occurrence of each chapter slug.
    seen_chapter_slugs: set = set()
    for pg in sorted_pages:
        filtered = []
        for blk in pg["content_blocks"]:
            if blk["type"] == "chapter_heading":
                ch = match_chapter(blk["text"])
                if ch and ch["slug"] not in seen_chapter_slugs:
                    seen_chapter_slugs.add(ch["slug"])
                    filtered.append(blk)
                else:
                    log_lines.append(f"  Removed duplicate chapter heading on page {pg['page_number']}: {blk['text']!r}")
            else:
                filtered.append(blk)
        pg["content_blocks"] = filtered
        pg["is_chapter_start"] = any(b["type"] == "chapter_heading" for b in filtered)

    # Intra-page paragraph joining — after deduplication, adjacent paragraphs that were
    # separated by a removed running-header chapter heading may need to be rejoined.
    for pg in sorted_pages:
        blocks = pg["content_blocks"]
        i = 0
        while i < len(blocks) - 1:
            a, b = blocks[i], blocks[i + 1]
            if (a["type"] == "paragraph" and b["type"] == "paragraph"
                    and ends_mid_sentence(a["text"]) and starts_mid_sentence(b["text"])):
                if a["text"].endswith("-"):
                    a["text"] = a["text"][:-1] + b["text"]
                else:
                    a["text"] += " " + b["text"]
                blocks.pop(i + 1)
                log_lines.append(f"  Intra-page join: page {pg['page_number']} block {i}")
            else:
                i += 1

    # Cross-page paragraph joining: merge paragraphs split at spread boundaries
    joins = 0
    for i in range(len(sorted_pages) - 1):
        blocks_a = sorted_pages[i]["content_blocks"]
        blocks_b = sorted_pages[i + 1]["content_blocks"]
        if not blocks_a or not blocks_b:
            continue
        last_a = blocks_a[-1]
        first_b = blocks_b[0]
        if (last_a["type"] == "paragraph"
                and first_b["type"] == "paragraph"
                and ends_mid_sentence(last_a["text"])
                and starts_mid_sentence(first_b["text"])):
            if last_a["text"].endswith("-"):
                last_a["text"] = last_a["text"][:-1] + first_b["text"]
            else:
                last_a["text"] += " " + first_b["text"]
            blocks_b.pop(0)
            joins += 1
            log_lines.append(f"  Cross-page join: page {sorted_pages[i]['page_number']} → {sorted_pages[i+1]['page_number']}")
    log_lines.append(f"Cross-page joins total: {joins}")

    # Determine first_page for each chapter
    chapter_first_pages = {}
    for pg in sorted_pages:
        slug = pg["chapter_slug"]
        if slug and slug not in chapter_first_pages:
            chapter_first_pages[slug] = pg["page_number"]

    chapters_with_pages = []
    for ch in CHAPTERS:
        entry = dict(ch)
        entry["first_page"] = chapter_first_pages.get(ch["slug"])
        chapters_with_pages.append(entry)

    structured = {
        "metadata": {
            "title": "Men of Maize",
            "author": "Miguel Ángel Asturias",
            "translator": "Gerald Martin",
            "publisher": "Delacorte Press / Seymour Lawrence",
            "year": 1975,
            "needs_review_count": len(needs_review_list),
        },
        "chapters": chapters_with_pages,
        "front_matter": blocks_to_front_matter(front_matter_blocks),
        "pages": sorted_pages,
        "needs_review_list": needs_review_list,
    }

    # ── Write outputs ──────────────────────────────────────────────────────────

    json_path = OUTPUT_DIR / "men_of_maize_structured.json"
    json_path.write_text(json.dumps(structured, indent=2, ensure_ascii=False), encoding="utf-8")

    clean_path = OUTPUT_DIR / "men_of_maize_clean.txt"
    write_clean_text(clean_path, structured)

    log_path = OUTPUT_DIR / "men_of_maize_assembly_log.txt"
    log_path.write_text("\n".join(log_lines), encoding="utf-8")

    print(f"Assembly complete.")
    print(f"  Pages assembled:  {len(sorted_pages)}")
    print(f"  Needs review:     {len(needs_review_list)} spread(s)")
    print(f"  Clean text:       {clean_path}")
    print(f"  Structured JSON:  {json_path}")
    print(f"  Assembly log:     {log_path}")
    if needs_review_list:
        print(f"\nNeeds-review spreads:")
        for item in needs_review_list:
            print(f"  {item['source_pdf']} spread {item['spread_number']} → est. pages {item['estimated_pages']}")


def block_to_dict(b: Block) -> dict:
    d = {"type": b.type}
    if b.text:
        d["text"] = b.text
    if b.type == "needs_review":
        d["source_pdf"]    = b.source_pdf
        d["spread_number"] = b.spread_number
    return d


def blocks_to_front_matter(blocks: list[Block]) -> list:
    if not blocks:
        return []
    return [{"type": "front_matter_page", "content_blocks": [block_to_dict(b) for b in blocks]}]


def write_clean_text(path: Path, structured: dict):
    lines = []
    lines.append("MEN OF MAIZE")
    lines.append("by Miguel Ángel Asturias")
    lines.append("Translated by Gerald Martin")
    lines.append("(Delacorte Press / Seymour Lawrence, 1975)")
    lines.append("")

    nr = structured["metadata"]["needs_review_count"]
    lines.append(f"[Assembly note: {nr} spread(s) need manual review — search for [NEEDS_REVIEW] below]")
    lines.append("=" * 60)
    lines.append("")

    for pg in structured["pages"]:
        pn = pg["page_number"]
        inf = " (inferred)" if pg["page_number_inferred"] else ""
        lines.append(f"[Page {pn}{inf}]")
        for blk in pg["content_blocks"]:
            t = blk["type"]
            if t == "chapter_heading":
                lines.append("")
                lines.append(blk["text"])
                lines.append("")
            elif t == "section_number":
                lines.append(blk["text"])
            elif t == "section_break":
                lines.append("")
                lines.append("[section break]")
                lines.append("")
            elif t == "paragraph":
                lines.append(blk["text"])
                lines.append("")
            elif t == "italic_block":
                lines.append(f"_{blk['text']}_")
                lines.append("")
            elif t == "needs_review":
                lines.append("")
                lines.append(f"[NEEDS_REVIEW: {blk['source_pdf']} spread {blk['spread_number']} — manual transcription required]")
                lines.append(f"[See: ../../Take 1/failed_spreads/{blk['source_pdf']}_spread_{blk['spread_number']:03d}.jpg]")
                lines.append("")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
