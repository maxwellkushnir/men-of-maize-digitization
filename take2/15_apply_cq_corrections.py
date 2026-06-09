"""
Men of Maize — Auto-correct Q=C≠M cases (against Mistral base)

Finds every position where Qwen and Claude agree but Mistral differs,
and applies the Q/C reading to men_of_maize_clean.txt and
men_of_maize_structured.json (both now Mistral-based).

Rule: Q=C≠M → where Qwen and Claude agree but Mistral (the base) differs,
trust Q/C and correct Mistral — no manual photo check needed.

Conservatism rules (correction is skipped if any fail):
  - Q/C phrase must be >= 2 words
  - M phrase must also be >= 1 word (skips pure insertions)
  - The Mistral phrase must appear EXACTLY ONCE in the full clean.txt
  - The replacement must differ from the current text

Uses men_of_maize_clean_CLAUDE_BASE.txt as the Claude source (the original
Claude-assembled text before the Mistral base swap in script 14).

Outputs:
  output/cq_corrections_log.txt  — full log of applied and skipped corrections
  (also updates men_of_maize_clean.txt and men_of_maize_structured.json)

Usage:
    python3 15_apply_cq_corrections.py [--dry-run]
"""

import json
import re
import sys
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher

DRY_RUN = "--dry-run" in sys.argv

BASE         = Path(__file__).parent
OUTPUT_DIR   = BASE / "output"
CLAUDE_FILE  = OUTPUT_DIR / "men_of_maize_clean_CLAUDE_BASE.txt"
MISTRAL_FILE = OUTPUT_DIR / "men_of_maize_clean.txt"
JSON_FILE    = OUTPUT_DIR / "men_of_maize_structured.json"
QWEN_DIR     = OUTPUT_DIR / "qwen_raw"
MISTRAL_DIR  = OUTPUT_DIR / "mistral_raw"
LOG_FILE     = OUTPUT_DIR / "cq_corrections_log.txt"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

MIN_PHRASE_WORDS = 2

# ── HELPERS ───────────────────────────────────────────────────────────────────

MARKER_RE = re.compile(
    r'<<< SPREAD_(?:START|END)[^>]*>>>|^#.*$|^\[Page\s+\d+[^\]]*\]\s*$|'
    r'^\[section break\]\s*$|^MEN OF MAIZE\s*$|^MIGUEL.*$',
    re.MULTILINE | re.IGNORECASE,
)
PAGE_NUM_RE = re.compile(r'\[Page\s+(\d+)')

def norm(word: str) -> str:
    s = unicodedata.normalize("NFD", word.lower())
    return s.encode("ascii", "ignore").decode("ascii")

def norm_words(words: list) -> list:
    return [norm(w) for w in words]

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
        if tag == "equal":
            for d in range(i2 - i1):
                mapping[i1 + d] = j1 + d
    return mapping

def get_c_span(q_i1, q_i2, q_to_c, c_words):
    """Return (c_start, c_end) indices into c_words for Q span [q_i1:q_i2]."""
    c_positions = [q_to_c[qi] for qi in range(q_i1, q_i2) if qi in q_to_c]
    if not c_positions:
        c_before = None
        for qi in range(q_i1 - 1, max(-1, q_i1 - 10), -1):
            if qi in q_to_c:
                c_before = q_to_c[qi] + 1
                break
        c_after = None
        for qi in range(q_i2, min(q_i2 + 10, q_i2 + 10 + len(q_to_c))):
            if qi in q_to_c:
                c_after = q_to_c[qi]
                break
        if c_before is None or c_after is None:
            return None, None
        return c_before, c_after
    return min(c_positions), max(c_positions) + 1


# ── FIND Q=C≠M CASES ─────────────────────────────────────────────────────────

def find_cqm_cases(qwen_spreads, mistral_spreads, claude_pages):
    """Find spans where Qwen and Claude agree but Mistral differs."""
    cases = []
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
        if not c_words:
            continue

        # Align Q→C to find where Claude's text corresponds to Qwen positions
        q_to_c = build_q_to_c(norm_words(q_words), norm_words(c_words))

        # Compare Q vs M to find all disagreements
        sm_qm = SequenceMatcher(None, norm_words(q_words), norm_words(m_words), autojunk=False)

        for tag, i1, i2, j1, j2 in sm_qm.get_opcodes():
            if tag == "equal":
                continue

            q_span_len = i2 - i1
            m_span_len = j2 - j1

            # Skip pure insertions (Q has text M doesn't) and pure deletions
            if q_span_len == 0 or m_span_len == 0:
                continue
            if q_span_len < MIN_PHRASE_WORDS:
                continue

            q_phrase = " ".join(q_words[i1:i2])
            m_phrase = " ".join(m_words[j1:j2])

            # Find corresponding Claude span
            c_start, c_end = get_c_span(i1, i2, q_to_c, c_words)
            if c_start is None:
                continue

            c_phrase = " ".join(c_words[c_start:c_end])

            q_norm = " ".join(norm_words(q_words[i1:i2]))
            c_norm = " ".join(norm_words(c_words[c_start:c_end]))
            m_norm = " ".join(norm_words(m_words[j1:j2]))

            if q_norm != c_norm:
                continue  # Claude doesn't match Qwen

            if q_norm == m_norm:
                continue  # Mistral already matches (normalized)

            cases.append({
                "pdf":      pdf_name,
                "spread":   spread_num,
                "pages":    sorted(set(pages)),
                "q_phrase": q_phrase,   # Q=C reading (replacement)
                "m_phrase": m_phrase,   # current Mistral text (to replace)
                "q_norm":   q_norm,
                "m_norm":   m_norm,
            })

    return cases


# ── APPLY CORRECTIONS TO clean.txt ────────────────────────────────────────────

def apply_to_clean_txt(cases, path: Path):
    text = path.read_text(encoding="utf-8")
    applied = 0
    skipped = 0
    log_lines = []

    for case in cases:
        m_phrase = case["m_phrase"]
        q_phrase = case["q_phrase"]

        if not m_phrase.strip() or not q_phrase.strip():
            skipped += 1
            log_lines.append(f"SKIP (empty phrase)  spread {case['spread']} of {case['pdf']}")
            continue

        count = text.count(m_phrase)
        if count != 1:
            skipped += 1
            log_lines.append(
                f"SKIP (found {count}×)  {case['pdf']} spread {case['spread']}  "
                f"M={repr(m_phrase[:60])}"
            )
            continue

        text = text.replace(m_phrase, q_phrase, 1)
        applied += 1
        log_lines.append(
            f"APPLY  {case['pdf']} spread {case['spread']}  p{case['pages']}  "
            f"{repr(m_phrase[:50])} → {repr(q_phrase[:50])}"
        )

    if not DRY_RUN:
        path.write_text(text, encoding="utf-8")

    return applied, skipped, log_lines


# ── APPLY CORRECTIONS TO JSON ─────────────────────────────────────────────────

def apply_to_json(cases, path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    page_index = {p["page_number"]: i for i, p in enumerate(data["pages"])}

    applied = 0
    skipped = 0
    log_lines = []

    for case in cases:
        m_phrase = case["m_phrase"]
        q_phrase = case["q_phrase"]
        pages    = case["pages"]

        if not m_phrase.strip() or not q_phrase.strip():
            continue

        target_blocks = []
        for pn in pages:
            if pn not in page_index:
                continue
            page_obj = data["pages"][page_index[pn]]
            for block in page_obj.get("content_blocks", []):
                if m_phrase in block.get("text", ""):
                    target_blocks.append(block)

        if len(target_blocks) != 1:
            skipped += 1
            log_lines.append(
                f"SKIP JSON (found in {len(target_blocks)} blocks)  "
                f"{case['pdf']} spread {case['spread']}  M={repr(m_phrase[:50])}"
            )
            continue

        target_blocks[0]["text"] = target_blocks[0]["text"].replace(m_phrase, q_phrase, 1)
        applied += 1
        log_lines.append(
            f"APPLY JSON  {case['pdf']} spread {case['spread']}  "
            f"{repr(m_phrase[:50])} → {repr(q_phrase[:50])}"
        )

    if not DRY_RUN:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return applied, skipped, log_lines


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if DRY_RUN:
        print("DRY RUN — no files will be modified.\n")

    print("Loading spreads and Claude pages …")
    qwen_spreads    = load_spreads(QWEN_DIR, "qwen")
    mistral_spreads = load_spreads(MISTRAL_DIR, "mistral")
    claude_pages    = load_claude_pages(CLAUDE_FILE)
    print(f"  Q: {len(qwen_spreads)} spreads  M: {len(mistral_spreads)} spreads  C: {len(claude_pages)} pages")

    print("Finding Q=C≠M cases …")
    cases = find_cqm_cases(qwen_spreads, mistral_spreads, claude_pages)
    print(f"  {len(cases):,} cases found")

    print("Applying corrections to men_of_maize_clean.txt …")
    txt_applied, txt_skipped, txt_log = apply_to_clean_txt(cases, MISTRAL_FILE)
    print(f"  Applied: {txt_applied}   Skipped: {txt_skipped}")

    print("Applying corrections to men_of_maize_structured.json …")
    json_applied, json_skipped, json_log = apply_to_json(cases, JSON_FILE)
    print(f"  Applied: {json_applied}   Skipped: {json_skipped}")

    log = [
        "Q=C≠M Auto-Correction Log (Mistral base)",
        f"Cases found: {len(cases)}",
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

    print(f"\nDone. {txt_applied} corrections applied to clean.txt, {json_applied} to JSON.")
    print("Next: re-run 12_linebreak_hyphen.py and 13_punct_formatting.py, then 09 and 10.")


if __name__ == "__main__":
    main()
