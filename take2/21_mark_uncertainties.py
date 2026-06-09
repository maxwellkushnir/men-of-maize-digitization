"""
Men of Maize — Mark Uncertain Pages in Structured JSON
Finds all high-severity Q≠M≠C spans, flags the relevant pages in the JSON
with _uncertain=true, and saves an uncertainty_index.json for future reference.

Run this BEFORE building the PDF. Only needs to be run once.
"""

import re
import json
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict

BASE        = Path(__file__).parent
OUTPUT_DIR  = BASE / "output"
CLAUDE_FILE = OUTPUT_DIR / "men_of_maize_clean.txt"
QWEN_DIR    = OUTPUT_DIR / "qwen_raw"
MISTRAL_DIR = OUTPUT_DIR / "mistral_raw"
JSON_FILE   = OUTPUT_DIR / "men_of_maize_structured.json"
INDEX_OUT   = OUTPUT_DIR / "uncertainty_index.json"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]
CHAPTER_MAP = {
    "2-25.pdf":   "GASPAR ILÓM",
    "26-55.pdf":  "MACHOJÓN / THE DEER OF THE SEVENTH FIRE",
    "56-75.pdf":  "COLONEL CHALO GODOY",
    "76-107.pdf": "MARÍA TECÚN",
    "108-.pdf":   "COYOTE-POSTMAN / EPILOGUE",
}

HIGH_SEVERITY = {"phrase, major divergence", "different word (single)", "phrase, multiple words differ"}
CONTEXT = 12

MARKER_RE = re.compile(
    r'<<< SPREAD_(?:START|END)[^>]*>>>|^#.*$|^\[Page\s+\d+[^\]]*\]\s*$|'
    r'^\[section break\]\s*$|^MEN OF MAIZE\s*$|^MIGUEL ÁNGEL ASTURIAS\s*$',
    re.MULTILINE | re.IGNORECASE,
)
PAGE_NUM_RE = re.compile(r'\[Page\s+(\d+)')


def norm(w):
    s = unicodedata.normalize("NFD", w.lower())
    return s.encode("ascii", "ignore").decode("ascii")

def strip_punct(s):
    return re.sub(r"[^\w\s]", "", s, flags=re.UNICODE).strip()

def edit_distance(a, b):
    a, b = a.lower(), b.lower()
    if len(a) > len(b): a, b = b, a
    prev = list(range(len(b)+1))
    for ca in a:
        curr = [prev[0]+1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j+1]+1, curr[j]+1, prev[j]+(0 if ca==cb else 1)))
        prev = curr
    return prev[-1]

def load_spreads(directory, suffix):
    spreads = {}
    block_re = re.compile(
        r'<<< SPREAD_START pdf="([^"]+)" spread="(\d+)"[^>]*>>>(.*?)<<< SPREAD_END >>>',
        re.DOTALL)
    for pdf in ALL_PDFS:
        path = directory / f"{pdf}_{suffix}.txt"
        if not path.exists(): continue
        for m in block_re.finditer(path.read_text(encoding="utf-8")):
            spreads[(m.group(1), int(m.group(2)))] = m.group(3)
    return spreads

def load_claude_pages(path):
    text = path.read_text(encoding="utf-8")
    pages = {}
    matches = list(re.finditer(r'^\[Page\s+(\d+)[^\]]*\]', text, re.MULTILINE))
    for i, m in enumerate(matches):
        pn = int(m.group(1))
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        pages[pn] = text[start:end].strip()
    return pages

def build_q_to_c(qn, cn):
    sm = SequenceMatcher(None, qn, cn, autojunk=False)
    mapping = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for d in range(i2-i1): mapping[i1+d] = j1+d
    return mapping

def claude_span_for(q_i1, q_i2, q_to_c, c_words):
    if not c_words: return "—"
    c_before = next((q_to_c[qi]+1 for qi in range(q_i1-1, max(-1,q_i1-20), -1) if qi in q_to_c), None)
    c_after  = next((q_to_c[qi]   for qi in range(q_i2, min(len(q_to_c)+q_i2, q_i2+20)) if qi in q_to_c), None)
    if c_before is None and c_after is None: return "—"
    if c_before is None: c_before = max(0, c_after-(q_i2-q_i1)-2)
    if c_after  is None: c_after  = min(len(c_words), c_before+(q_i2-q_i1)+2)
    return " ".join(c_words[c_before:c_after]) or "—"

def classify(q, m, c):
    qn = norm(q); mn = norm(m)
    cn = norm(c) if c and c != "—" else None
    if cn is None: return "Q≠M (C n/a)"
    if qn == mn:   return "Q=M"
    if cn == qn:   return "Q=C≠M"
    if cn == mn:   return "M=C≠Q"
    return "Q≠M≠C"

def categorise(q, m):
    qw = q.split(); mw = m.split()
    if not qw: return "insertion (M only)"
    if not mw: return "deletion (Q only)"
    if not strip_punct(q) and mw: return "insertion (M phrase)"
    if not strip_punct(m) and qw: return "deletion (Q phrase)"
    if len(qw)==1 and len(mw)==1:
        a, b = strip_punct(qw[0]), strip_punct(mw[0])
        ed = edit_distance(a, b)
        if ed == 0: return "punctuation only"
        if ed <= 2: return "spelling variant (1–2 edits)"
        if norm(a)==norm(b): return "accent/diacritic"
        return "different word (single)"
    if strip_punct(q).lower()==strip_punct(m).lower(): return "punctuation only"
    if norm(q)==norm(m): return "accent/diacritic"
    if len(qw)==len(mw):
        d = sum(1 for a,b in zip(qw,mw) if norm(a)!=norm(b))
        return "phrase, one word differs" if d==1 else "phrase, multiple words differ"
    return "phrase, minor length diff" if abs(len(qw)-len(mw))<=2 else "phrase, major divergence"


def collect_high_severity_spans(qwen_spreads, mistral_spreads, claude_pages):
    results = []
    all_keys = sorted(set(qwen_spreads) & set(mistral_spreads),
                      key=lambda k: (ALL_PDFS.index(k[0]) if k[0] in ALL_PDFS else 99, k[1]))
    for key in all_keys:
        pdf_name, spread_num = key
        q_raw   = MARKER_RE.sub(' ', qwen_spreads[key])
        m_raw   = MARKER_RE.sub(' ', mistral_spreads[key])
        q_words = q_raw.split(); m_words = m_raw.split()
        if not q_words or not m_words: continue

        pages = ([int(m.group(1)) for m in PAGE_NUM_RE.finditer(qwen_spreads[key])]
                 or [int(m.group(1)) for m in PAGE_NUM_RE.finditer(mistral_spreads[key])])
        if not pages: continue

        c_text  = " ".join(claude_pages.get(p,"") for p in sorted(set(pages)))
        c_words = c_text.split()
        q_to_c  = build_q_to_c([norm(w) for w in q_words], [norm(w) for w in c_words]) if c_words else {}

        sm = SequenceMatcher(None, [norm(w) for w in q_words], [norm(w) for w in m_words], autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal": continue
            q_span = " ".join(q_words[i1:i2])
            m_span = " ".join(m_words[j1:j2])
            c_span = claude_span_for(i1, i2, q_to_c, c_words)
            if classify(q_span, m_span, c_span) != "Q≠M≠C": continue
            cat = categorise(q_span, m_span)
            if cat not in HIGH_SEVERITY: continue

            q_left  = " ".join(q_words[max(0,i1-CONTEXT):i1])
            q_right = " ".join(q_words[i2:i2+CONTEXT])
            results.append({
                "pdf":     pdf_name,
                "spread":  spread_num,
                "pages":   sorted(set(pages)),
                "chapter": CHAPTER_MAP.get(pdf_name, pdf_name),
                "q_span":  q_span,
                "m_span":  m_span,
                "c_span":  c_span,
                "context_left":  q_left,
                "context_right": q_right,
                "category":      cat,
            })
    return results


def main():
    print("Loading data …")
    claude_pages    = load_claude_pages(CLAUDE_FILE)
    qwen_spreads    = load_spreads(QWEN_DIR, "qwen")
    mistral_spreads = load_spreads(MISTRAL_DIR, "mistral")

    print("Collecting high-severity Q≠M≠C spans …")
    spans = collect_high_severity_spans(qwen_spreads, mistral_spreads, claude_pages)
    print(f"  {len(spans)} high-severity spans found")

    # Collect unique page numbers affected
    uncertain_pages = set()
    for s in spans:
        uncertain_pages.update(s["pages"])
    print(f"  Affects {len(uncertain_pages)} book pages: {sorted(uncertain_pages)}")

    # Save uncertainty index
    index = {
        "total_high_severity_spans": len(spans),
        "uncertain_page_numbers":    sorted(uncertain_pages),
        "spans":                     spans,
    }
    INDEX_OUT.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Saved: {INDEX_OUT.name}")

    # Mark pages in structured JSON
    print("Marking pages in structured JSON …")
    structured = json.loads(JSON_FILE.read_text(encoding="utf-8"))

    # Build page_number → span list lookup
    page_to_spans = defaultdict(list)
    for s in spans:
        for pn in s["pages"]:
            page_to_spans[pn].append(s)

    marked = 0
    for page in structured.get("pages", []):
        pn = page.get("page_number")
        if pn in uncertain_pages:
            page["_uncertain"] = True
            page["_uncertain_spans"] = [
                {"q": s["q_span"], "m": s["m_span"], "base": s["c_span"], "cat": s["category"]}
                for s in page_to_spans[pn]
            ]
            marked += 1

    JSON_FILE.write_text(json.dumps(structured, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {marked} pages marked as uncertain in JSON")
    print(f"\nDone. Now run 03_build_pdf.py — uncertain pages will carry a ※ marker.")
    print(f"Uncertainty index saved to: {INDEX_OUT.name}")


if __name__ == "__main__":
    main()
