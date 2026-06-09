"""
Men of Maize — Option A: Vision-based adjudication of Q≠M≠C spans

For every span where all three models disagree (Q≠M≠C), shows the original
spread photograph to gpt-5.5 and asks it to pick the correct reading.
Spans from the same spread are batched into one API call (one image upload).

Correction rule:
  - If model picks Q → apply Q reading to base (Q overrides Mistral)
  - If model picks M or C → keep current base (no change needed)
  - UNCERTAIN → skip

Conservative safeguards:
  - Chosen phrase must appear EXACTLY ONCE in clean.txt to be replaced
  - The model must return a clear single-letter answer (A/B/C/U)

Estimated cost: ~80 API calls (one per affected spread), gpt-5.5 vision pricing.

Usage:
    pip install openai PyMuPDF
    export OPENAI_API_KEY="sk-..."
    python3 18_text_adjudication.py [--dry-run]

Output:
    output/text_adjudication_log.txt
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
CLEAN_FILE  = OUTPUT_DIR / "men_of_maize_clean.txt"
JSON_FILE   = OUTPUT_DIR / "men_of_maize_structured.json"
QWEN_DIR    = OUTPUT_DIR / "qwen_raw"
MISTRAL_DIR = OUTPUT_DIR / "mistral_raw"
LOG_FILE    = OUTPUT_DIR / "text_adjudication_log.txt"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]
CONTEXT  = 7

MODEL  = "gpt-5.5"
ZOOM   = 3.0
DELAY  = 1.0


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
    if cn is None:   return "Q≠M (C n/a)"
    if qn == mn:     return "Q=M"
    if cn == qn:     return "Q=C≠M"
    if cn == mn:     return "M=C≠Q"
    return "Q≠M≠C"


# ── COLLECT Q≠M≠C SPANS, GROUPED BY SPREAD ───────────────────────────────────

def collect_spans_by_spread(qwen_spreads, mistral_spreads, claude_pages):
    """Returns {(pdf, spread_num): [span_dict, ...]} for Q≠M≠C spans only."""
    by_spread = {}
    keys = sorted(
        set(qwen_spreads) & set(mistral_spreads),
        key=lambda k: (ALL_PDFS.index(k[0]) if k[0] in ALL_PDFS else 99, k[1])
    )
    for key in keys:
        pdf_name, spread_num = key
        q_raw  = MARKER_RE.sub(' ', qwen_spreads[key])
        m_raw  = MARKER_RE.sub(' ', mistral_spreads[key])
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
        q_to_c  = build_q_to_c(norm_words(q_words), norm_words(c_words)) if c_words else {}
        sm = SequenceMatcher(None, norm_words(q_words), norm_words(m_words), autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            q_span_text = " ".join(q_words[i1:i2])
            m_span_text = " ".join(m_words[j1:j2])
            c_span_text = claude_span_for(i1, i2, q_to_c, c_words)
            if classify(q_span_text, m_span_text, c_span_text) != "Q≠M≠C":
                continue
            left_ctx  = " ".join(q_words[max(0, i1 - CONTEXT):i1])
            right_ctx = " ".join(q_words[i2:i2 + CONTEXT])
            by_spread.setdefault(key, []).append({
                "pdf":       pdf_name,
                "spread":    spread_num,
                "pages":     sorted(set(pages)),
                "left_ctx":  left_ctx,
                "right_ctx": right_ctx,
                "q_span":    q_span_text,
                "m_span":    m_span_text,
                "c_span":    c_span_text,
            })
    return by_spread


# ── VISION API ────────────────────────────────────────────────────────────────

def render_spread(pdf_path: Path, spread_num: int) -> bytes:
    doc = fitz.open(str(pdf_path))
    page = doc[spread_num - 1]
    pix  = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace=fitz.csRGB)
    img  = pix.tobytes("jpeg")
    doc.close()
    return img

def adjudicate_spread(client: OpenAI, jpeg_bytes: bytes, spans: list) -> list:
    """
    Sends one spread image to gpt-5.5 with all Q≠M≠C spans listed.
    Returns a list of verdicts ('A', 'B', 'C', 'U') in the same order as spans.
    """
    b64 = base64.standard_b64encode(jpeg_bytes).decode()

    cases = []
    for i, span in enumerate(spans, 1):
        cases.append(
            f"Case {i}:\n"
            f"  Context: ...{span['left_ctx']} [?] {span['right_ctx']}...\n"
            f"  A (Qwen):    {span['q_span']}\n"
            f"  B (Mistral): {span['m_span']}\n"
            f"  C (current): {span['c_span']}\n"
        )

    prompt = (
        "You are checking OCR accuracy on a scanned book. "
        "I will show you the original page photograph and N specific spots where "
        "three OCR systems gave different readings. Look at the actual printed text "
        "and pick the correct reading for each case.\n\n"
        + "\n".join(cases)
        + "\nFor each case reply with only the letter: A, B, C, or U (uncertain). "
        "Format: '1:A 2:B 3:U ...' No other text."
    )

    for attempt in range(1, 4):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                max_completion_tokens=50 + len(spans) * 5,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            raw = (resp.choices[0].message.content or "").strip().upper()
            return parse_verdicts(raw, len(spans))
        except Exception as e:
            if attempt == 3:
                print(f"\n    ERROR: {e}")
                return ["ERROR"] * len(spans)
            time.sleep(10 * attempt)
    return ["ERROR"] * len(spans)

def parse_verdicts(raw: str, n: int) -> list:
    """Parse '1:A 2:B 3:U' → ['A', 'B', 'U']. Falls back to positional."""
    verdicts = ["U"] * n
    # Try 'N:X' format
    pairs = re.findall(r'(\d+)\s*[:.\)]\s*([ABCU])', raw)
    if pairs:
        for num_str, letter in pairs:
            idx = int(num_str) - 1
            if 0 <= idx < n:
                verdicts[idx] = letter
        return verdicts
    # Fallback: just take letters in order
    letters = re.findall(r'\b([ABCU])\b', raw)
    for i, letter in enumerate(letters[:n]):
        verdicts[i] = letter
    return verdicts


# ── APPLY CORRECTIONS ─────────────────────────────────────────────────────────

def apply_to_clean_txt(corrections, path: Path):
    text = path.read_text(encoding="utf-8")
    applied = 0; skipped = 0; log = []
    for old, new, reason in corrections:
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
    applied = 0; skipped = 0; log = []
    for old, new, reason in corrections:
        matched = [
            block
            for page in data["pages"]
            for block in page.get("content_blocks", [])
            if old in block.get("text", "")
        ]
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
        print("DRY RUN — no files will be modified.\n")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set.")
        sys.exit(1)
    client = OpenAI(api_key=api_key)

    print("Loading data …")
    qwen_spreads    = load_spreads(QWEN_DIR, "qwen")
    mistral_spreads = load_spreads(MISTRAL_DIR, "mistral")
    claude_pages    = load_claude_pages(CLEAN_FILE)

    print("Finding Q≠M≠C spans …")
    by_spread = collect_spans_by_spread(qwen_spreads, mistral_spreads, claude_pages)
    total_spans = sum(len(v) for v in by_spread.values())
    print(f"  {total_spans} spans across {len(by_spread)} spreads")

    print(f"\nAdjudicating with {MODEL} vision ({len(by_spread)} API calls) …")
    all_decisions = []   # (span, verdict)
    tally = {"A": 0, "B": 0, "C": 0, "U": 0, "ERROR": 0}

    for i, (key, spans) in enumerate(sorted(by_spread.items(),
            key=lambda x: (ALL_PDFS.index(x[0][0]) if x[0][0] in ALL_PDFS else 99, x[0][1])), 1):
        pdf_name, spread_num = key
        print(f"  [{i:3d}/{len(by_spread)}] {pdf_name} spread {spread_num:3d} "
              f"({len(spans)} spans) … ", end="", flush=True)

        if DRY_RUN:
            verdicts = ["U"] * len(spans)
        else:
            pdf_path   = BOOK_DIR / pdf_name
            jpeg_bytes = render_spread(pdf_path, spread_num)
            verdicts   = adjudicate_spread(client, jpeg_bytes, spans)

        for span, verdict in zip(spans, verdicts):
            tally[verdict] = tally.get(verdict, 0) + 1
            all_decisions.append((span, verdict))

        print(" ".join(verdicts))
        time.sleep(DELAY)

    print(f"\nResults: Q(A)={tally['A']} M(B)={tally['B']} C(C)={tally['C']} "
          f"Uncertain={tally['U']} Error={tally.get('ERROR',0)}")

    # Build corrections: only where model picked Q (A) and base differs
    corrections = []
    verdict_lines = []
    for span, verdict in all_decisions:
        label = {"A": "Q-chosen", "B": "M-keep", "C": "C-keep", "U": "uncertain"}.get(verdict, verdict)
        verdict_lines.append(
            f"{label:12}  {span['pdf']} s{span['spread']} p{span['pages']}  "
            f"Q={repr(span['q_span'][:35])} M={repr(span['m_span'][:35])} C={repr(span['c_span'][:35])}"
        )
        if verdict == "A":
            old = span["c_span"]
            new = span["q_span"]
            if old == "—" or not old.strip() or norm(old) == norm(new):
                continue
            corrections.append((old, new, f"vision-Q p{span['pages']} s{span['spread']}"))

    print(f"\nApplying {len(corrections)} corrections …")
    txt_applied, txt_skipped, txt_log = apply_to_clean_txt(corrections, CLEAN_FILE)
    json_applied, json_skipped, json_log = apply_to_json(corrections, JSON_FILE)
    print(f"  clean.txt: {txt_applied} applied, {txt_skipped} skipped")
    print(f"  JSON:      {json_applied} applied, {json_skipped} skipped")

    log_lines = [
        f"Vision Adjudication Log ({MODEL})",
        f"Spans: {total_spans} across {len(by_spread)} spreads",
        f"Q(A)={tally['A']} M(B)={tally['B']} C(C)={tally['C']} "
        f"Uncertain={tally['U']} Error={tally.get('ERROR',0)}",
        f"clean.txt: applied={txt_applied} skipped={txt_skipped}",
        f"JSON:      applied={json_applied} skipped={json_skipped}",
        "─" * 70,
        "Per-span verdicts:", *verdict_lines,
        "─" * 70,
        "clean.txt corrections:", *txt_log,
        "─" * 70,
        "JSON corrections:", *json_log,
    ]
    if not DRY_RUN:
        LOG_FILE.write_text("\n".join(log_lines), encoding="utf-8")
        print(f"\nLog: {LOG_FILE.name}")

    print(f"\nDone. {txt_applied} txt corrections, {json_applied} JSON corrections.")


if __name__ == "__main__":
    main()
