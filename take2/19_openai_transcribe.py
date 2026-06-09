"""
Men of Maize — Option B: OpenAI gpt-4o targeted re-transcription

Finds every spread that contains at least one Q≠M≠C (all-three-differ) span,
re-transcribes those spreads with gpt-4o (a 4th independent model), then
compares the OpenAI reading against Q, M, and C to create 2v1 majorities.

Correction rules (applied to men_of_maize_clean.txt and JSON):
  O=Q≠M:  apply Q reading  (OpenAI+Qwen 2v1 against Mistral base)
  O=M≠Q:  keep base as-is  (OpenAI+Mistral confirm the current Mistral base)
  O=C≠Q≠M: keep base as-is (OpenAI confirms current base)
  O≠Q,M,C: skip             (4th disagreement — still unresolved)

Raw output saved to: output/openai_raw/<pdf>_openai.txt
Resume-safe: already-transcribed spreads are skipped on re-run.

Estimated cost: ~$1–3 for 60–80 spreads at gpt-4o pricing.

Usage:
    pip install openai PyMuPDF
    export OPENAI_API_KEY="sk-..."
    python3 19_openai_transcribe.py [--dry-run]

Output:
    output/openai_raw/  — raw transcriptions
    output/openai_corrections_log.txt
    (also updates men_of_maize_clean.txt and men_of_maize_structured.json)
"""

import base64
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher

try:
    import fitz
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)

DRY_RUN = "--dry-run" in sys.argv

BASE        = Path(__file__).parent
BOOK_DIR    = BASE.parent
OUTPUT_DIR  = BASE / "output"
OPENAI_DIR  = OUTPUT_DIR / "openai_raw"
CLEAN_FILE  = OUTPUT_DIR / "men_of_maize_clean.txt"
JSON_FILE   = OUTPUT_DIR / "men_of_maize_structured.json"
QWEN_DIR    = OUTPUT_DIR / "qwen_raw"
MISTRAL_DIR = OUTPUT_DIR / "mistral_raw"
LOG_FILE    = OUTPUT_DIR / "openai_corrections_log.txt"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]
CONTEXT  = 7

VISION_MODEL = "gpt-5.5"
ZOOM         = 3.0
MAX_TOKENS   = 4096
DELAY        = 1.5   # seconds between API calls

EXTRACTION_PROMPT = """\
This is a photograph of an open book showing two pages side by side.
Transcribe ALL visible text accurately, reading the LEFT page first, then the RIGHT page.

Rules:
1. Preserve chapter headings in CAPS exactly as printed
2. Preserve Roman numeral section headings (I, II, III …) on their own line
3. Output page numbers on their own line as: [Page N]
4. When you see a small ornamental divider between sections, output: [section break]
5. Preserve paragraph breaks with a blank line between paragraphs
6. Preserve italicised text (songs, poems, dedications) on separate lines
7. If text disappears into the spine gutter, mark the gap with [...]
8. Do NOT describe the photo, hands, table, bookmark, or anything non-textual
9. Do NOT add commentary — output only the transcribed text

Transcribe now:\
"""


# ── TEXT HELPERS ──────────────────────────────────────────────────────────────

MARKER_RE = re.compile(
    r'<<< SPREAD_(?:START|END)[^>]*>>>|^#.*$|^\[Page\s+\d+[^\]]*\]\s*$|'
    r'^\[section break\]\s*$|^MEN OF MAIZE\s*$|^MIGUEL ÁNGEL ASTURIAS\s*$',
    re.MULTILINE | re.IGNORECASE,
)
PAGE_NUM_RE = re.compile(r'\[Page\s+(\d+)')

def norm(word: str) -> str:
    s = unicodedata.normalize("NFD", word.lower())
    return s.encode("ascii", "ignore").decode("ascii")

def norm_words(words: list) -> list:
    return [norm(w) for w in words]


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

def build_q_to_c(q_norm, c_norm):
    sm = SequenceMatcher(None, q_norm, c_norm, autojunk=False)
    mapping = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for d in range(i2 - i1):
                mapping[i1 + d] = j1 + d
    return mapping

def claude_span_for(q_i1, q_i2, q_to_c, c_words):
    if not c_words:
        return "—"
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
        return "—"
    if c_before is None:
        c_before = max(0, c_after - (q_i2 - q_i1) - 2)
    if c_after is None:
        c_after = min(len(c_words), c_before + (q_i2 - q_i1) + 2)
    snippet = c_words[c_before:c_after]
    return " ".join(snippet) if snippet else "—"

def classify(q_span, m_span, c_span):
    qn = norm(q_span)
    mn = norm(m_span)
    cn = norm(c_span) if c_span and c_span != "—" else None
    if cn is None:
        return "Q≠M (C n/a)"
    if qn == mn:   return "Q=M"
    if cn == qn:   return "Q=C≠M"
    if cn == mn:   return "M=C≠Q"
    return "Q≠M≠C"


# ── FIND SPREADS WITH Q≠M≠C SPANS ────────────────────────────────────────────

def find_affected_spreads(qwen_spreads, mistral_spreads, claude_pages):
    """Return set of (pdf, spread_num) keys that contain at least one Q≠M≠C span."""
    affected = set()
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
        c_text = " ".join(claude_pages.get(p, "") for p in sorted(set(pages)))
        c_words = c_text.split()
        q_to_c = build_q_to_c(norm_words(q_words), norm_words(c_words)) if c_words else {}
        sm = SequenceMatcher(None, norm_words(q_words), norm_words(m_words), autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            q_span_text = " ".join(q_words[i1:i2])
            m_span_text = " ".join(m_words[j1:j2])
            c_span_text = claude_span_for(i1, i2, q_to_c, c_words)
            if classify(q_span_text, m_span_text, c_span_text) == "Q≠M≠C":
                affected.add(key)
                break
    return affected


# ── PDF RENDERING ─────────────────────────────────────────────────────────────

def render_spread(page) -> bytes:
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace=fitz.csRGB)
    return pix.tobytes("jpeg")


# ── OPENAI VISION TRANSCRIPTION ───────────────────────────────────────────────

def transcribe_spread(client: OpenAI, jpeg_bytes: bytes) -> str:
    b64 = base64.standard_b64encode(jpeg_bytes).decode()
    for attempt in range(1, 4):
        try:
            resp = client.chat.completions.create(
                model=VISION_MODEL,
                max_completion_tokens=MAX_TOKENS,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": EXTRACTION_PROMPT},
                    ],
                }],
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if attempt == 3:
                return f"[OPENAI_ERROR: {e}]"
            time.sleep(10 * attempt)
    return "[OPENAI_ERROR: max retries]"

def find_last_completed(output_path: Path, suffix: str) -> int:
    if not output_path.exists():
        return 0
    content = output_path.read_text(encoding="utf-8")
    pat = re.compile(r'<<< SPREAD_START pdf="[^"]+" spread="(\d+)"')
    end_marker = "<<< SPREAD_END >>>"
    last = 0
    pos = 0
    while True:
        m = pat.search(content, pos)
        if not m:
            break
        end_pos = content.find(end_marker, m.end())
        if end_pos == -1:
            break
        last = int(m.group(1))
        pos = end_pos + len(end_marker)
    return last

def write_block(out, pdf_name: str, spread_num: int, total: int, content: str):
    block = (
        f'\n<<< SPREAD_START pdf="{pdf_name}" spread="{spread_num}" total="{total}" >>>\n'
        f'{content.strip()}\n'
        f'<<< SPREAD_END >>>\n'
    )
    out.write(block)
    out.flush()


# ── TRANSCRIBE TARGETED SPREADS ───────────────────────────────────────────────

def transcribe_targeted(client, affected_keys):
    """Transcribe only the spreads in affected_keys. Returns {(pdf, spread): text}."""
    OPENAI_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    by_pdf = {}
    for pdf_name, spread_num in sorted(affected_keys):
        by_pdf.setdefault(pdf_name, []).append(spread_num)

    for pdf_name, spread_nums in sorted(by_pdf.items()):
        pdf_path = BOOK_DIR / pdf_name
        if not pdf_path.exists():
            print(f"  WARNING: {pdf_name} not found, skipping")
            continue

        output_path = OPENAI_DIR / f"{pdf_name}_openai.txt"
        last_done = find_last_completed(output_path, "openai")

        doc = fitz.open(str(pdf_path))
        total = len(doc)

        mode = "a" if output_path.exists() else "w"
        with open(output_path, mode, encoding="utf-8") as out:
            if mode == "w":
                out.write(f"# Men of Maize — OpenAI re-transcription (targeted)\n"
                          f"# Source: {pdf_name}\n# Model: {VISION_MODEL}\n")

            for spread_num in sorted(spread_nums):
                if spread_num <= last_done:
                    # Load from existing file
                    content = output_path.read_text(encoding="utf-8")
                    block_re = re.compile(
                        rf'<<< SPREAD_START pdf="{re.escape(pdf_name)}" spread="{spread_num}"'
                        r'[^>]*>>>(.*?)<<< SPREAD_END >>>',
                        re.DOTALL
                    )
                    m = block_re.search(content)
                    if m:
                        results[(pdf_name, spread_num)] = m.group(1)
                    print(f"  {pdf_name} spread {spread_num:3d}  [skipped — already done]")
                    continue

                if spread_num > total:
                    print(f"  WARNING: spread {spread_num} > total {total} for {pdf_name}")
                    continue

                print(f"  {pdf_name} spread {spread_num:3d}/{total}  … ", end="", flush=True)
                if not DRY_RUN:
                    jpeg_bytes = render_spread(doc[spread_num - 1])
                    text = transcribe_spread(client, jpeg_bytes)
                else:
                    text = "[DRY_RUN — not transcribed]"

                write_block(out, pdf_name, spread_num, total, text)
                results[(pdf_name, spread_num)] = text

                ok = "[OPENAI_ERROR" not in text and "[DRY_RUN" not in text
                print("✓" if ok else "✗ ERROR")

                if spread_num != sorted(spread_nums)[-1]:
                    time.sleep(DELAY)

        doc.close()

    return results


# ── COMPARE OPENAI OUTPUT VS Q / M / C ────────────────────────────────────────

def compare_and_collect(openai_results, qwen_spreads, mistral_spreads, claude_pages):
    """
    For each Q≠M≠C span, find the OpenAI reading and determine the verdict.
    Returns list of (old_phrase, new_phrase, reason) corrections.
    """
    corrections = []
    log_lines   = []

    keys = sorted(
        set(qwen_spreads) & set(mistral_spreads),
        key=lambda k: (ALL_PDFS.index(k[0]) if k[0] in ALL_PDFS else 99, k[1])
    )

    for key in keys:
        pdf_name, spread_num = key
        if key not in openai_results:
            continue   # spread wasn't in the affected set

        q_raw = MARKER_RE.sub(' ', qwen_spreads[key])
        m_raw = MARKER_RE.sub(' ', mistral_spreads[key])
        o_raw = MARKER_RE.sub(' ', openai_results[key])

        q_words = q_raw.split()
        m_words = m_raw.split()
        o_words = o_raw.split()

        if not q_words or not m_words or not o_words:
            continue

        pages = [int(x) for x in PAGE_NUM_RE.findall(qwen_spreads[key])]
        if not pages:
            pages = [int(x) for x in PAGE_NUM_RE.findall(mistral_spreads[key])]
        if not pages:
            continue

        c_text  = " ".join(claude_pages.get(p, "") for p in sorted(set(pages)))
        c_words = c_text.split()
        q_to_c  = build_q_to_c(norm_words(q_words), norm_words(c_words)) if c_words else {}
        q_to_o  = build_q_to_c(norm_words(q_words), norm_words(o_words))

        sm_qm = SequenceMatcher(None, norm_words(q_words), norm_words(m_words), autojunk=False)

        for tag, i1, i2, j1, j2 in sm_qm.get_opcodes():
            if tag == "equal":
                continue

            q_span_text = " ".join(q_words[i1:i2])
            m_span_text = " ".join(m_words[j1:j2])
            c_span_text = claude_span_for(i1, i2, q_to_c, c_words)

            if classify(q_span_text, m_span_text, c_span_text) != "Q≠M≠C":
                continue

            # Find what OpenAI says at this position
            o_span_text = claude_span_for(i1, i2, q_to_o, o_words)
            if not o_span_text or o_span_text == "—":
                log_lines.append(
                    f"SKIP (O n/a)  {pdf_name} s{spread_num}  "
                    f"Q={repr(q_span_text[:30])} M={repr(m_span_text[:30])}"
                )
                continue

            o_norm = norm(o_span_text)
            q_norm = norm(q_span_text)
            m_norm = norm(m_span_text)
            c_norm = norm(c_span_text) if c_span_text != "—" else None

            if o_norm == q_norm and o_norm != m_norm:
                # O=Q≠M → apply Q reading (current base has M)
                old = c_span_text if c_span_text != "—" else m_span_text
                new = q_span_text
                if norm(old) != norm(new):
                    corrections.append((old, new,
                        f"O=Q p{pages} {pdf_name} s{spread_num}"))
                    log_lines.append(
                        f"O=Q→APPLY  {pdf_name} s{spread_num} p{pages}  "
                        f"Q={repr(q_span_text[:40])} M={repr(m_span_text[:40])} O={repr(o_span_text[:40])}"
                    )
            elif o_norm == m_norm and o_norm != q_norm:
                log_lines.append(
                    f"O=M→KEEP  {pdf_name} s{spread_num} p{pages}  "
                    f"M={repr(m_span_text[:40])}"
                )
            elif c_norm is not None and o_norm == c_norm:
                log_lines.append(
                    f"O=C→KEEP  {pdf_name} s{spread_num} p{pages}  "
                    f"C={repr(c_span_text[:40])}"
                )
            else:
                log_lines.append(
                    f"O≠Q,M,C→SKIP  {pdf_name} s{spread_num}  "
                    f"Q={repr(q_span_text[:30])} M={repr(m_span_text[:30])} O={repr(o_span_text[:30])}"
                )

    return corrections, log_lines


# ── APPLY CORRECTIONS ─────────────────────────────────────────────────────────

def apply_to_clean_txt(corrections, path: Path):
    text = path.read_text(encoding="utf-8")
    applied = 0
    skipped = 0
    log = []
    for old, new, reason in corrections:
        if not old.strip() or not new.strip():
            continue
        count = text.count(old)
        if count != 1:
            skipped += 1
            log.append(f"SKIP ({count}×)  {repr(old[:60])}")
            continue
        text = text.replace(old, new, 1)
        applied += 1
        log.append(f"APPLY  {repr(old[:50])} → {repr(new[:50])}  [{reason}]")
    if not DRY_RUN:
        path.write_text(text, encoding="utf-8")
    return applied, skipped, log

def apply_to_json(corrections, path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    applied = 0
    skipped = 0
    log = []
    for old, new, reason in corrections:
        if not old.strip() or not new.strip():
            continue
        matched = []
        for page in data["pages"]:
            for block in page.get("content_blocks", []):
                if old in block.get("text", ""):
                    matched.append(block)
        if len(matched) != 1:
            skipped += 1
            log.append(f"SKIP JSON ({len(matched)} blocks)  {repr(old[:50])}")
            continue
        matched[0]["text"] = matched[0]["text"].replace(old, new, 1)
        applied += 1
        log.append(f"APPLY JSON  {repr(old[:50])} → {repr(new[:50])}")
    if not DRY_RUN:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return applied, skipped, log


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if DRY_RUN:
        print("DRY RUN — transcription skipped, no files modified.\n")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set.")
        print('  export OPENAI_API_KEY="sk-..."')
        sys.exit(1)
    client = OpenAI(api_key=api_key)

    print("Loading raw transcriptions and current base …")
    qwen_spreads    = load_spreads(QWEN_DIR, "qwen")
    mistral_spreads = load_spreads(MISTRAL_DIR, "mistral")
    claude_pages    = load_claude_pages(CLEAN_FILE)
    print(f"  Q: {len(qwen_spreads)}  M: {len(mistral_spreads)}  C: {len(claude_pages)} pages")

    print("Finding spreads with Q≠M≠C spans …")
    affected = find_affected_spreads(qwen_spreads, mistral_spreads, claude_pages)
    by_pdf = {}
    for pdf, s in sorted(affected):
        by_pdf.setdefault(pdf, []).append(s)
    total_spreads = sum(len(v) for v in by_pdf.values())
    print(f"  {total_spreads} spreads across {len(by_pdf)} PDFs:")
    for pdf, nums in sorted(by_pdf.items()):
        print(f"    {pdf}: spreads {sorted(nums)}")

    print(f"\nTranscribing {total_spreads} spreads with {VISION_MODEL} …")
    openai_results = transcribe_targeted(client, affected)
    print(f"  {len(openai_results)} spreads transcribed")

    print("\nComparing OpenAI output against Q / M / C …")
    corrections, comp_log = compare_and_collect(
        openai_results, qwen_spreads, mistral_spreads, claude_pages
    )
    print(f"  {len(corrections)} corrections to apply")

    print("Applying corrections …")
    txt_applied, txt_skipped, txt_log = apply_to_clean_txt(corrections, CLEAN_FILE)
    json_applied, json_skipped, json_log = apply_to_json(corrections, JSON_FILE)
    print(f"  clean.txt: applied={txt_applied} skipped={txt_skipped}")
    print(f"  JSON:      applied={json_applied} skipped={json_skipped}")

    log_lines = [
        f"OpenAI ({VISION_MODEL}) Targeted Correction Log",
        f"Spreads transcribed: {len(openai_results)} / {total_spreads}",
        f"Corrections found: {len(corrections)}",
        f"clean.txt: applied={txt_applied} skipped={txt_skipped}",
        f"JSON:      applied={json_applied} skipped={json_skipped}",
        "─" * 70,
        "Comparison log:",
        *comp_log,
        "─" * 70,
        "clean.txt corrections:",
        *txt_log,
        "─" * 70,
        "JSON corrections:",
        *json_log,
    ]
    if not DRY_RUN:
        LOG_FILE.write_text("\n".join(log_lines), encoding="utf-8")
        print(f"\nLog: {LOG_FILE.name}")
        print(f"Raw output: {OPENAI_DIR}/")

    print(f"\nDone. {txt_applied} txt corrections, {json_applied} JSON corrections.")
    print("Next: re-run 09_three_way_compare.py and 10_divergence_review.py, then build the PDF.")


if __name__ == "__main__":
    main()
