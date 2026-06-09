"""
Men of Maize — Unresolved Q≠M≠C Span Analysis
Interactive HTML report: shows drift analysis + lets you type what you
actually see in the PDF. Corrections saved to localStorage; exportable as JSON.
"""

import re
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict

BASE        = Path(__file__).parent
OUTPUT_DIR  = BASE / "output"
CLAUDE_FILE = OUTPUT_DIR / "men_of_maize_clean.txt"
QWEN_DIR    = OUTPUT_DIR / "qwen_raw"
MISTRAL_DIR = OUTPUT_DIR / "mistral_raw"
HTML_OUT    = OUTPUT_DIR / "unresolved_spans_report.html"

ALL_PDFS = ["2-25.pdf", "26-55.pdf", "56-75.pdf", "76-107.pdf", "108-.pdf"]

CHAPTER_MAP = {
    "2-25.pdf":   "GASPAR ILÓM",
    "26-55.pdf":  "MACHOJÓN / THE DEER OF THE SEVENTH FIRE",
    "56-75.pdf":  "COLONEL CHALO GODOY",
    "76-107.pdf": "MARÍA TECÚN",
    "108-.pdf":   "COYOTE-POSTMAN / EPILOGUE",
}

CONTEXT       = 35    # wide context for each model's reading
PAGE_CTX_WORDS = 120  # words of base text shown as "page context"
DRIFT_MIN_LEN  = 3

HIGH_SEVERITY = {"phrase, major divergence", "different word (single)", "phrase, multiple words differ"}

MARKER_RE = re.compile(
    r'<<< SPREAD_(?:START|END)[^>]*>>>|'
    r'^#.*$|'
    r'^\[Page\s+\d+[^\]]*\]\s*$|'
    r'^\[section break\]\s*$|'
    r'^MEN OF MAIZE\s*$|'
    r'^MIGUEL ÁNGEL ASTURIAS\s*$',
    re.MULTILINE | re.IGNORECASE,
)
PAGE_NUM_RE = re.compile(r'\[Page\s+(\d+)')


# ── TEXT HELPERS ──────────────────────────────────────────────────────────────

def norm(word):
    s = unicodedata.normalize("NFD", word.lower())
    return s.encode("ascii", "ignore").decode("ascii")

def clean_block(text):
    return MARKER_RE.sub(' ', text)

def words_of(text):
    return text.split()

def norm_words(words):
    return [norm(w) for w in words]

def strip_punct(s):
    return re.sub(r"[^\w\s]", "", s, flags=re.UNICODE).strip()

def edit_distance(a, b):
    a, b = a.lower(), b.lower()
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j+1]+1, curr[j]+1, prev[j]+(0 if ca==cb else 1)))
        prev = curr
    return prev[-1]


# ── LOAD DATA ─────────────────────────────────────────────────────────────────

def load_spreads(directory, suffix):
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

def load_claude_pages(path):
    text   = path.read_text(encoding="utf-8")
    pages  = {}
    matches = list(re.finditer(r'^\[Page\s+(\d+)[^\]]*\]', text, re.MULTILINE))
    for i, m in enumerate(matches):
        pn    = int(m.group(1))
        start = m.end()
        end   = matches[i+1].start() if i+1 < len(matches) else len(text)
        pages[pn] = text[start:end].strip()
    return pages


# ── ALIGNMENT ─────────────────────────────────────────────────────────────────

def build_q_to_c(q_norm, c_norm):
    sm = SequenceMatcher(None, q_norm, c_norm, autojunk=False)
    mapping = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
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
    for qi in range(q_i2, min(len(q_to_c) + q_i2, q_i2 + 20)):
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


# ── CLASSIFY / CATEGORISE ─────────────────────────────────────────────────────

def classify(q_span, m_span, c_span):
    qn = norm(q_span)
    mn = norm(m_span)
    cn = norm(c_span) if c_span and c_span != "—" else None
    if cn is None:  return "Q≠M (C n/a)"
    if qn == mn:    return "Q=M"
    if cn == qn:    return "Q=C≠M"
    if cn == mn:    return "M=C≠Q"
    return "Q≠M≠C"

def categorise_span(q, m, c):
    qw = q.split(); mw = m.split()
    if not qw: return "insertion (M only)"
    if not mw: return "deletion (Q only)"
    if len(qw) == 1 and len(mw) == 1:
        a, b = strip_punct(qw[0]), strip_punct(mw[0])
        ed = edit_distance(a, b)
        if ed == 0:    return "punctuation only"
        if ed <= 2:    return "spelling variant (1–2 edits)"
        if norm(a) == norm(b): return "accent/diacritic"
        return "different word (single)"
    if not strip_punct(q) and mw: return "insertion (M phrase)"
    if not strip_punct(m) and qw: return "deletion (Q phrase)"
    if strip_punct(q).lower() == strip_punct(m).lower(): return "punctuation only"
    if norm(q) == norm(m): return "accent/diacritic"
    if len(qw) == len(mw):
        diffs = sum(1 for a, b in zip(qw, mw) if norm(a) != norm(b))
        return "phrase, one word differs" if diffs == 1 else "phrase, multiple words differ"
    return "phrase, minor length diff" if abs(len(qw)-len(mw)) <= 2 else "phrase, major divergence"


# ── DRIFT DETECTION ───────────────────────────────────────────────────────────

def sig_words(text):
    return {norm(strip_punct(w)) for w in text.split() if len(strip_punct(w)) >= DRIFT_MIN_LEN}

def detect_drift(q_span, m_span, q_left, q_right, m_left, m_right):
    q_sig = sig_words(q_span)
    m_sig = sig_words(m_span)
    if not q_sig or not m_sig:
        return None, None, set()
    q_ctx = sig_words(q_left + " " + q_right)
    m_ctx = sig_words(m_left + " " + m_right)
    q_in_m = q_sig & m_ctx
    m_in_q = m_sig & q_ctx
    if q_in_m and not m_in_q:
        label = "M has Q’s word(s) elsewhere in context: “" + ", ".join(sorted(q_in_m)) + "”"
        return label, "Q", q_in_m
    if m_in_q and not q_in_m:
        label = "Q has M’s word(s) elsewhere in context: “" + ", ".join(sorted(m_in_q)) + "”"
        return label, "M", m_in_q
    if q_in_m and m_in_q:
        merged = q_in_m | m_in_q
        label = "Both models show displacement (shared words: " + ", ".join(sorted(merged)) + ")"
        return label, "ambiguous", merged
    return None, None, set()


# ── PAGE CONTEXT (wide base-text excerpt) ─────────────────────────────────────

def get_page_context(page_nums, claude_pages, target_words, window=PAGE_CTX_WORDS):
    """
    Return a wide excerpt from the base text centred on the disputed span.
    Shows up to `window` words total, centred around the first occurrence of
    any target word.
    """
    full = " ".join(claude_pages.get(p, "") for p in sorted(set(page_nums)))
    words = full.split()
    if not words:
        return "", ""

    # Find best anchor: first position where a target word appears
    target_norms = {norm(strip_punct(w)) for w in target_words.split() if len(strip_punct(w)) >= 3}
    anchor = None
    if target_norms:
        for i, w in enumerate(words):
            if norm(strip_punct(w)) in target_norms:
                anchor = i
                break
    if anchor is None:
        anchor = len(words) // 2

    half   = window // 2
    start  = max(0, anchor - half)
    end    = min(len(words), anchor + half)
    before = words[start:anchor]
    after  = words[anchor:end]
    return " ".join(before), " ".join(after)


# ── COLLECT SPANS ─────────────────────────────────────────────────────────────

def collect_qnmc_spans(qwen_spreads, mistral_spreads, claude_pages):
    spans = []
    all_keys = sorted(
        set(qwen_spreads) & set(mistral_spreads),
        key=lambda k: (ALL_PDFS.index(k[0]) if k[0] in ALL_PDFS else 99, k[1])
    )
    for key in all_keys:
        pdf_name, spread_num = key
        q_raw   = clean_block(qwen_spreads[key])
        m_raw   = clean_block(mistral_spreads[key])
        q_words = words_of(q_raw)
        m_words = words_of(m_raw)
        if not q_words or not m_words:
            continue

        pages = ([int(m.group(1)) for m in PAGE_NUM_RE.finditer(qwen_spreads[key])]
                 or [int(m.group(1)) for m in PAGE_NUM_RE.finditer(mistral_spreads[key])])
        page_label = f"pp. {min(pages)}–{max(pages)}" if pages else "p. ?"

        c_text  = " ".join(claude_pages.get(p, "") for p in sorted(set(pages))) if pages else ""
        c_words = words_of(c_text)
        q_to_c  = build_q_to_c(norm_words(q_words), norm_words(c_words)) if c_words else {}

        sm = SequenceMatcher(None, norm_words(q_words), norm_words(m_words), autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            q_span = " ".join(q_words[i1:i2])
            m_span = " ".join(m_words[j1:j2])
            c_span = claude_span_for(i1, i2, q_to_c, c_words)

            if classify(q_span, m_span, c_span) != "Q≠M≠C":
                continue

            q_left  = " ".join(q_words[max(0, i1 - CONTEXT):i1])
            q_right = " ".join(q_words[i2:i2 + CONTEXT])
            m_left  = " ".join(m_words[max(0, j1 - CONTEXT):j1])
            m_right = " ".join(m_words[j2:j2 + CONTEXT])

            cat = categorise_span(q_span, m_span, c_span)
            drift_label, likely_correct, drift_words = detect_drift(
                q_span, m_span, q_left, q_right, m_left, m_right
            )

            # Wide page context from base text, centred on the disputed span
            page_ctx_before, page_ctx_after = get_page_context(
                pages, claude_pages, q_span or m_span
            )

            # Suggested pre-fill for the correction textarea
            if likely_correct == "Q":
                suggestion = q_span
            elif likely_correct == "M":
                suggestion = m_span
            else:
                suggestion = ""

            spans.append({
                "pdf":            pdf_name,
                "spread":         spread_num,
                "pages":          page_label,
                "page_nums":      pages,
                "chapter":        CHAPTER_MAP.get(pdf_name, pdf_name),
                "q_left":         q_left,
                "q_span":         q_span,
                "q_right":        q_right,
                "m_left":         m_left,
                "m_span":         m_span,
                "m_right":        m_right,
                "c_span":         c_span,
                "page_ctx_before":page_ctx_before,
                "page_ctx_after": page_ctx_after,
                "category":       cat,
                "drift_label":    drift_label,
                "likely_correct": likely_correct,
                "drift_words":    drift_words,
                "suggestion":     suggestion,
            })
    return spans


# ── SEVERITY / COLOUR MAPS ────────────────────────────────────────────────────

SEVERITY_ORDER = {
    "phrase, major divergence":     0,
    "different word (single)":      1,
    "phrase, multiple words differ":2,
    "phrase, one word differs":     3,
    "insertion (M only)":           4,
    "insertion (M phrase)":         5,
    "deletion (Q only)":            6,
    "deletion (Q phrase)":          7,
    "phrase, minor length diff":    8,
    "spelling variant (1–2 edits)":9,
    "accent/diacritic":             10,
    "punctuation only":             11,
}

CAT_COLOUR = {
    "phrase, major divergence":     "#b71c1c",
    "different word (single)":      "#c62828",
    "phrase, multiple words differ":"#e53935",
    "phrase, one word differs":     "#ef6c00",
    "insertion (M only)":           "#6a1b9a",
    "insertion (M phrase)":         "#7b1fa2",
    "deletion (Q only)":            "#1565c0",
    "deletion (Q phrase)":          "#1976d2",
    "phrase, minor length diff":    "#f9a825",
    "spelling variant (1–2 edits)":"#558b2f",
    "accent/diacritic":             "#00695c",
    "punctuation only":             "#546e7a",
}


# ── HTML HELPERS ──────────────────────────────────────────────────────────────

def esc(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))

def esc_attr(s):
    return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", " ")

def highlight_drift(text, drift_words):
    if not drift_words:
        return esc(text)
    out = []
    for w in text.split():
        nw = norm(strip_punct(w))
        if nw in drift_words:
            out.append(f'<mark class="drift">{esc(w)}</mark>')
        else:
            out.append(esc(w))
    return " ".join(out)

def reading_block(model_label, model_colour, left, span, right, drift_words, is_likely, span_id, model_key):
    empty   = "<em class='empty'>∅</em>"
    span_html = f'<span class="span-text" style="color:{model_colour}">{esc(span) if span else empty}</span>'
    likely_badge = ' <span class="likely-badge">&#10003; likely correct</span>' if is_likely else ""
    fill_btn = (f'<button class="fill-btn" onclick="fillFrom(\'{span_id}\',\'{esc_attr(span)}\')"'
                f' style="border-color:{model_colour};color:{model_colour}">Use this</button>')
    return f"""
<div class="reading-row">
  <div class="reading-label" style="color:{model_colour}">{model_label}{likely_badge}</div>
  <div class="reading-text">
    <span class="ctx">{highlight_drift(left, drift_words)}</span>
    <span class="gap">[</span>{span_html}<span class="gap">]</span>
    <span class="ctx">{highlight_drift(right, drift_words)}</span>
  </div>
  {fill_btn}
</div>"""


def span_card(i, s, span_id):
    col       = CAT_COLOUR.get(s["category"], "#333")
    cat_badge = f'<span class="cat-badge" style="background:{col}">{esc(s["category"])}</span>'

    # Drift banner
    if s["drift_label"]:
        lc   = s["likely_correct"]
        dc   = {"Q":"#1565c0","M":"#2e7d32","ambiguous":"#e65100"}.get(lc,"#555")
        lctx = {"Q":"Qwen is likely correct at this position",
                "M":"Mistral is likely correct at this position",
                "ambiguous":"Both models show displacement — check original"}.get(lc,"")
        drift_banner = f"""
<div class="drift-banner" style="border-color:{dc}">
  <strong style="color:{dc}">&#9670; Line drift detected:</strong> {esc(s["drift_label"])}<br>
  <span style="color:{dc}">{esc(lctx)}</span>
  <span class="drift-legend">&#x2022; <mark class="drift">highlighted words</mark> = word found in other model’s context</span>
</div>"""
    else:
        drift_banner = '<div class="no-drift-banner">No drift pattern detected — needs photo check against the original spread.</div>'

    dw = s["drift_words"]
    q_likely = s["likely_correct"] == "Q"
    m_likely = s["likely_correct"] == "M"

    q_block = reading_block("Qwen",    "#1565c0", s["q_left"], s["q_span"], s["q_right"], dw, q_likely, span_id, "q")
    m_block = reading_block("Mistral", "#2e7d32", s["m_left"], s["m_span"], s["m_right"], dw, m_likely, span_id, "m")

    c_text  = s["c_span"] if s["c_span"] and s["c_span"] != "—" else "—"
    c_block = f"""
<div class="reading-row">
  <div class="reading-label" style="color:#777">Current base</div>
  <div class="reading-text"><span style="color:#888">{esc(c_text)}</span></div>
  <button class="fill-btn" onclick="fillFrom('{span_id}','{esc_attr(c_text)}')" style="border-color:#999;color:#777">Use this</button>
</div>"""

    # Wide page context from base
    pb = s["page_ctx_before"]
    pa = s["page_ctx_after"]
    page_ctx_html = f"""
<div class="page-ctx-block">
  <div class="page-ctx-label">Base text — full page context ({esc(s["pages"])})</div>
  <div class="page-ctx-text">
    <span class="ctx">{esc(pb)}</span>
    <span class="page-ctx-marker"> [⋯ disputed area ⋯] </span>
    <span class="ctx">{esc(pa)}</span>
  </div>
</div>"""

    # Correction area
    suggestion = s["suggestion"]
    meta = {
        "id": span_id,
        "pdf": s["pdf"],
        "spread": s["spread"],
        "pages": s["pages"],
        "chapter": s["chapter"],
        "q_span": s["q_span"],
        "m_span": s["m_span"],
        "c_span": s["c_span"],
        "category": s["category"],
        "drift": s["drift_label"] or "",
        "likely": s["likely_correct"] or "",
    }
    import json
    meta_json = esc_attr(json.dumps(meta))

    correction_area = f"""
<div class="correction-area">
  <div class="correction-header">
    <span class="correction-label">&#9998; Your correction</span>
    <select class="status-sel" id="status-{span_id}" onchange="save('{span_id}')"
            title="Mark this span's review status">
      <option value="unreviewed">Unreviewed</option>
      <option value="corrected">Corrected</option>
      <option value="keep">Keep current base</option>
      <option value="skip">Skip / not sure</option>
    </select>
  </div>
  <textarea class="correction-input" id="input-{span_id}"
            data-key="{span_id}" data-meta="{meta_json}"
            placeholder="Type what you see in the PDF… (or use a ‘Use this’ button above)"
            oninput="save('{span_id}')">{esc(suggestion)}</textarea>
  <div class="correction-hint">
    Keyboard: Tab to move between spans · Ctrl+Enter to mark as Corrected and jump to next
  </div>
</div>"""

    loc = f'{esc(s["pdf"])} &nbsp;·&nbsp; spread {s["spread"]} &nbsp;·&nbsp; {esc(s["pages"])} &nbsp;·&nbsp; {esc(s["chapter"])}'

    return f"""
<div class="span-card" id="card-{span_id}" data-key="{span_id}">
  <div class="card-header">
    <span class="card-num">#{i}</span>
    {cat_badge}
    <span class="card-loc">{loc}</span>
    <span class="card-status-indicator" id="ind-{span_id}"></span>
  </div>
  {drift_banner}
  <div class="readings-section">
    {q_block}
    {m_block}
    {c_block}
  </div>
  {page_ctx_html}
  {correction_area}
</div>"""


def compact_row(i, s, span_id):
    col  = CAT_COLOUR.get(s["category"], "#333")
    badge = f'<span class="cat-badge" style="background:{col};font-size:10px">{esc(s["category"])}</span>'
    meta = {"id":span_id,"pdf":s["pdf"],"spread":s["spread"],"pages":s["pages"],
            "chapter":s["chapter"],"q_span":s["q_span"],"m_span":s["m_span"],
            "c_span":s["c_span"],"category":s["category"],"drift":"","likely":""}
    import json
    meta_json = esc_attr(json.dumps(meta))
    q_ctx_short = s["q_left"][-50:] + " [" + (s["q_span"] or "∅") + "] " + s["q_right"][:50]
    return f"""<tr id="card-{span_id}" data-key="{span_id}">
  <td style="color:#999;font-size:11px">{i}</td>
  <td style="font-size:11px;white-space:nowrap">{esc(s["pdf"])}<br>s{s["spread"]} {esc(s["pages"])}</td>
  <td style="font-size:11px;color:#777">{esc(s["chapter"])}</td>
  <td style="font-size:11px;color:#1565c0;font-weight:bold">{esc(s["q_span"])}</td>
  <td style="font-size:11px;color:#2e7d32;font-weight:bold">{esc(s["m_span"])}</td>
  <td style="font-size:11px;color:#777">{esc(s["c_span"]) if s["c_span"] not in ("","—","—") else "—"}</td>
  <td style="font-size:11px;color:#666;max-width:250px">{esc(q_ctx_short)}</td>
  <td>{badge}</td>
  <td>
    <select class="status-sel" id="status-{span_id}" onchange="save('{span_id}')" style="font-size:11px">
      <option value="unreviewed">—</option>
      <option value="corrected">Corrected</option>
      <option value="keep">Keep base</option>
      <option value="skip">Skip</option>
    </select>
    <input type="text" id="input-{span_id}" data-key="{span_id}" data-meta="{meta_json}"
           placeholder="correction…" oninput="save('{span_id}')"
           style="font-size:11px;width:120px;margin-left:4px;padding:2px 4px;border:1px solid #ccc;border-radius:2px">
  </td>
</tr>"""


# ── JAVASCRIPT ────────────────────────────────────────────────────────────────

JS = r"""
const STORE_KEY = 'moz_corrections_v1';

function load() {
  return JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
}
function store(data) {
  localStorage.setItem(STORE_KEY, JSON.stringify(data));
}

function save(key) {
  const data   = load();
  const inp    = document.getElementById('input-' + key);
  const status = document.getElementById('status-' + key);
  if (!inp) return;
  data[key] = {
    text:      inp.value,
    status:    status ? status.value : 'corrected',
    timestamp: new Date().toISOString(),
    meta:      inp.dataset.meta ? JSON.parse(inp.dataset.meta) : {}
  };
  store(data);
  updateIndicator(key, data[key].status);
  updateProgress();
}

function fillFrom(key, text) {
  const inp = document.getElementById('input-' + key);
  if (!inp) return;
  inp.value = text;
  save(key);
  inp.focus();
}

function updateIndicator(key, status) {
  const ind = document.getElementById('ind-' + key);
  if (!ind) return;
  const map = {
    'corrected': {text:'Corrected', bg:'#2e7d32'},
    'keep':      {text:'Keep base', bg:'#1565c0'},
    'skip':      {text:'Skip',      bg:'#e65100'},
    'unreviewed':{text:'',          bg:'transparent'},
  };
  const s = map[status] || {text:'', bg:'transparent'};
  ind.textContent  = s.text;
  ind.style.background = s.bg;
  ind.style.display = s.text ? 'inline-block' : 'none';
}

function updateProgress() {
  const data     = load();
  const total    = document.querySelectorAll('[data-key]').length;
  const done     = Object.values(data).filter(v => v.status && v.status !== 'unreviewed').length;
  const corrected= Object.values(data).filter(v => v.status === 'corrected').length;
  const el = document.getElementById('progress-text');
  if (el) el.textContent = done + ' / ' + total + ' reviewed  (' + corrected + ' corrected)';
  const bar = document.getElementById('progress-bar');
  if (bar) bar.style.width = (total ? (100*done/total) : 0).toFixed(0) + '%';
}

function exportJSON() {
  const data = load();
  const out  = Object.values(data)
    .filter(v => v.status && v.status !== 'unreviewed')
    .map(v => ({...v.meta, correction: v.text, status: v.status, saved: v.timestamp}));
  if (!out.length) { alert('No reviewed spans yet.'); return; }
  const blob = new Blob([JSON.stringify(out, null, 2)], {type: 'application/json'});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = 'moz_manual_corrections.json'; a.click();
  URL.revokeObjectURL(url);
}

function exportCSV() {
  const data = load();
  const rows = Object.values(data).filter(v => v.status && v.status !== 'unreviewed');
  if (!rows.length) { alert('No reviewed spans yet.'); return; }
  const cols = ['id','pdf','spread','pages','chapter','q_span','m_span','c_span',
                'category','drift','likely','correction','status','saved'];
  const lines = [cols.join(',')];
  rows.forEach(v => {
    const m = v.meta || {};
    lines.push(cols.map(c => {
      const val = (c === 'correction' ? v.text : c === 'status' ? v.status :
                   c === 'saved' ? v.timestamp : (m[c] ?? ''));
      return '"' + String(val).replace(/"/g, '""') + '"';
    }).join(','));
  });
  const blob = new Blob([lines.join('\n')], {type: 'text/csv'});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a'); a.href=url; a.download='moz_corrections.csv'; a.click();
  URL.revokeObjectURL(url);
}

function clearAll() {
  if (!confirm('Clear ALL saved corrections? This cannot be undone.')) return;
  localStorage.removeItem(STORE_KEY);
  document.querySelectorAll('.correction-input, input[id^="input-"]').forEach(el => el.value = '');
  document.querySelectorAll('.status-sel').forEach(el => el.value = 'unreviewed');
  document.querySelectorAll('.card-status-indicator').forEach(el => {
    el.textContent = ''; el.style.display = 'none';
  });
  updateProgress();
}

// Ctrl+Enter: mark corrected + focus next card
document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    const active = document.activeElement;
    if (!active || !active.classList.contains('correction-input')) return;
    const key = active.dataset.key;
    const sel = document.getElementById('status-' + key);
    if (sel) { sel.value = 'corrected'; save(key); }
    // Move to next textarea
    const all = Array.from(document.querySelectorAll('.correction-input'));
    const idx = all.indexOf(active);
    if (idx >= 0 && idx < all.length - 1) all[idx+1].focus();
    e.preventDefault();
  }
});

window.addEventListener('load', function() {
  const data = load();
  document.querySelectorAll('[data-key]').forEach(el => {
    const key = el.dataset.key;
    if (!data[key]) return;
    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
      el.value = data[key].text || '';
    }
    const sel = document.getElementById('status-' + key);
    if (sel && data[key].status) sel.value = data[key].status;
    updateIndicator(key, data[key].status || 'unreviewed');
  });
  updateProgress();
});
"""

CSS = """
body{font-family:Georgia,serif;font-size:13px;margin:2em auto;max-width:1250px;color:#222;line-height:1.55}
h1{font-size:1.5em;margin-bottom:.2em}
h2{font-size:1.1em;margin-top:2.5em;border-bottom:1px solid #ccc;padding-bottom:4px}
h3{font-size:1em;margin-top:1.5em;color:#555}
p.note{color:#555;font-size:12px;margin:.3em 0 1em}
a{color:#1565c0}

/* progress bar */
#progress-bar-wrap{background:#e0e0e0;border-radius:4px;height:8px;margin:8px 0}
#progress-bar{height:8px;background:#2e7d32;border-radius:4px;width:0%;transition:width .3s}
#progress-text{font-size:12px;color:#555}

/* toolbar */
.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:12px 0}
.toolbar button{padding:6px 14px;border:none;border-radius:4px;cursor:pointer;font-size:12px;font-family:Georgia,serif}
.btn-export{background:#1565c0;color:#fff}
.btn-csv{background:#2e7d32;color:#fff}
.btn-clear{background:#f5f5f5;color:#555;border:1px solid #ccc}

/* span cards */
.span-card{border:1px solid #ddd;border-radius:5px;padding:14px 18px;margin:14px 0;background:#fff}
.span-card:target{border-color:#1565c0;box-shadow:0 0 0 2px #bbdefb}
.card-header{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.card-num{font-size:12px;color:#aaa;min-width:28px}
.card-loc{font-size:11px;color:#777}
.card-status-indicator{padding:2px 8px;border-radius:10px;font-size:11px;color:#fff;display:none;margin-left:auto}
.cat-badge{color:#fff;padding:2px 7px;border-radius:3px;font-size:11px;white-space:nowrap}

/* drift banners */
.drift-banner{margin:8px 0;padding:8px 12px;background:#fff8e1;border-left:3px solid #f9a825;
  border-radius:2px;font-size:12px;line-height:1.6}
.no-drift-banner{margin:8px 0;padding:7px 12px;background:#f5f5f5;border-left:3px solid #bbb;
  border-radius:2px;font-size:12px;color:#777}
.drift-legend{display:block;margin-top:4px;color:#888;font-size:11px}
mark.drift{background:#fff9c4;color:#5d4037;padding:0 2px;border-radius:2px;font-weight:bold}

/* readings */
.readings-section{margin:10px 0}
.reading-row{display:grid;grid-template-columns:90px 1fr auto;align-items:start;
  gap:8px;margin:5px 0;padding:5px 0;border-bottom:1px solid #f0f0f0}
.reading-label{font-size:11px;font-weight:bold;padding-top:2px}
.likely-badge{font-size:10px;background:#2e7d32;color:#fff;padding:1px 5px;
  border-radius:8px;margin-left:4px;font-weight:normal}
.reading-text{font-size:12px;line-height:1.7;word-break:break-word}
.span-text{font-weight:bold;font-size:13px;padding:0 3px}
.ctx{color:#aaa}
.gap{color:#bbb;font-size:11px;padding:0 1px}
.empty{color:#aaa}
.fill-btn{font-size:11px;padding:3px 8px;border:1px solid #ccc;border-radius:3px;
  background:#fff;cursor:pointer;white-space:nowrap;font-family:Georgia,serif}
.fill-btn:hover{background:#f5f5f5}

/* page context block */
.page-ctx-block{margin:10px 0 8px;padding:10px 14px;background:#f9f9f9;
  border:1px solid #e8e8e8;border-radius:3px}
.page-ctx-label{font-size:11px;color:#888;margin-bottom:5px;font-style:italic}
.page-ctx-text{font-size:12px;line-height:1.75;color:#555;word-break:break-word}
.page-ctx-marker{color:#c62828;font-weight:bold;font-size:12px}

/* correction area */
.correction-area{margin-top:12px;padding:12px 14px;background:#f0f7ff;
  border:1px solid #bbdefb;border-radius:4px}
.correction-header{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.correction-label{font-size:12px;font-weight:bold;color:#1565c0}
.status-sel{font-size:12px;padding:3px 6px;border:1px solid #90caf9;border-radius:3px;
  background:#fff;font-family:Georgia,serif;cursor:pointer}
.correction-input{width:100%;box-sizing:border-box;min-height:56px;font-size:13px;
  font-family:Georgia,serif;padding:8px 10px;border:1px solid #90caf9;border-radius:3px;
  background:#fff;resize:vertical;line-height:1.5}
.correction-input:focus{outline:none;border-color:#1565c0;box-shadow:0 0 0 2px #e3f2fd}
.correction-hint{font-size:10px;color:#90a4ae;margin-top:4px}

/* compact table */
table{border-collapse:collapse;width:100%;margin-bottom:1.5em}
th,td{padding:5px 9px;border:1px solid #e0e0e0;vertical-align:top}
th{background:#f5f5f5;font-size:12px;text-align:left}
tr:hover{background:#fafafa}
.toc a{color:#1565c0;text-decoration:none;margin-right:1.5em;font-size:12px}
"""


# ── BUILD HTML ────────────────────────────────────────────────────────────────

def build_html(spans):
    import json as _json

    total = len(spans)
    high  = [s for s in spans if s["category"] in HIGH_SEVERITY]
    other = [s for s in spans if s["category"] not in HIGH_SEVERITY]

    high_sorted = sorted(high, key=lambda s: (
        0 if s["drift_label"] else 1,
        {"Q":0,"M":1,"ambiguous":2,None:3}.get(s["likely_correct"],3),
        ALL_PDFS.index(s["pdf"]) if s["pdf"] in ALL_PDFS else 99,
        s["spread"]
    ))
    other_sorted = sorted(other, key=lambda s: (
        SEVERITY_ORDER.get(s["category"], 99),
        ALL_PDFS.index(s["pdf"]) if s["pdf"] in ALL_PDFS else 99,
        s["spread"]
    ))

    drift_count = sum(1 for s in high if s["drift_label"])
    drift_q     = sum(1 for s in high if s["likely_correct"] == "Q")
    drift_m     = sum(1 for s in high if s["likely_correct"] == "M")
    drift_amb   = sum(1 for s in high if s["likely_correct"] == "ambiguous")
    no_drift    = len(high) - drift_count

    cat_counts = defaultdict(int)
    for s in spans:
        cat_counts[s["category"]] += 1

    cat_rows = ""
    for cat in sorted(cat_counts, key=lambda c: SEVERITY_ORDER.get(c, 99)):
        n   = cat_counts[cat]
        col = CAT_COLOUR.get(cat, "#333")
        pct = 100 * n / total
        bar = f'<div style="width:{pct:.0f}%;height:8px;background:{col};border-radius:2px"></div>'
        star = "&#9733; " if cat in HIGH_SEVERITY else ""
        cat_rows += f'<tr><td><span style="color:{col};font-weight:bold">{star}{esc(cat)}</span></td><td style="text-align:right">{n}</td><td style="text-align:right">{pct:.1f}%</td><td style="width:100px">{bar}</td></tr>\n'

    # Priority cards
    priority_html = ""
    for i, s in enumerate(high_sorted, 1):
        sid = f"{s['pdf'].replace('.','_').replace('-','_')}_s{s['spread']}_{i}"
        priority_html += span_card(i, s, sid)

    # Compact table for other spans
    other_rows = ""
    current_cat = None
    for i, s in enumerate(other_sorted, len(high_sorted) + 1):
        cat = s["category"]
        col = CAT_COLOUR.get(cat, "#333")
        if cat != current_cat:
            current_cat = cat
            n = cat_counts[cat]
            other_rows += f'<tr style="background:#f0f0f0"><td colspan="9" style="padding:8px 10px;font-weight:bold;font-size:13px;color:{col}">{esc(cat)} <span style="font-weight:normal;color:#666">({n} spans)</span></td></tr>\n'
        sid = f"{s['pdf'].replace('.','_').replace('-','_')}_s{s['spread']}_{i}"
        other_rows += compact_row(i, s, sid)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Men of Maize — Unresolved Spans Review</title>
<style>{CSS}</style>
</head>
<body>

<h1>Men of Maize — Unresolved Q≠M≠C Spans</h1>
<p class="note">
  <strong>{total} spans</strong> where Qwen, Mistral, and the current base all disagree.
  Context window: ±{CONTEXT} words per model · {PAGE_CTX_WORDS}-word base-text excerpt per span.
  Corrections auto-saved to browser localStorage.
</p>

<div id="progress-bar-wrap"><div id="progress-bar"></div></div>
<div id="progress-text"></div>

<div class="toolbar">
  <button class="btn-export" onclick="exportJSON()">&#8659; Export JSON</button>
  <button class="btn-csv"    onclick="exportCSV()">&#8659; Export CSV</button>
  <button class="btn-clear"  onclick="clearAll()">&#10005; Clear all</button>
  <span style="font-size:11px;color:#888">
    Ctrl+Enter = mark corrected &amp; jump to next · Tab = move between fields
  </span>
</div>

<div class="toc">
  <a href="#summary">Summary</a>
  <a href="#priority">Priority ({len(high)} spans)</a>
  <a href="#other">Other ({len(other)} spans)</a>
</div>

<h2 id="summary">Summary</h2>
<h3>By category <span style="font-size:11px;color:#888">(&#9733; = shown in Priority section)</span></h3>
<table style="max-width:650px">
<thead><tr><th>Category</th><th style="text-align:right">Count</th><th style="text-align:right">%</th><th>Bar</th></tr></thead>
<tbody>{cat_rows}</tbody>
<tfoot><tr style="font-weight:bold"><td>Total</td><td style="text-align:right">{total}</td><td style="text-align:right">100%</td><td></td></tr></tfoot>
</table>

<h3>Line drift analysis (high-severity spans)</h3>
<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0">
  <span style="padding:6px 14px;border-radius:4px;background:#e8f5e9;border:1px solid #a5d6a7;font-size:13px">
    <strong style="color:#2e7d32">{drift_count}</strong> drift detected
  </span>
  <span style="padding:6px 14px;border-radius:4px;background:#e3f2fd;border:1px solid #90caf9;font-size:13px">
    <strong style="color:#1565c0">{drift_q}</strong> Qwen likely correct
  </span>
  <span style="padding:6px 14px;border-radius:4px;background:#e8f5e9;border:1px solid #a5d6a7;font-size:13px">
    <strong style="color:#2e7d32">{drift_m}</strong> Mistral likely correct
  </span>
  <span style="padding:6px 14px;border-radius:4px;background:#fff8e1;border:1px solid #ffe082;font-size:13px">
    <strong style="color:#e65100">{drift_amb}</strong> ambiguous
  </span>
  <span style="padding:6px 14px;border-radius:4px;background:#fafafa;border:1px solid #ddd;font-size:13px">
    <strong style="color:#555">{no_drift}</strong> needs photo check
  </span>
</div>

<h2 id="priority">Priority Review — {len(high)} high-severity spans</h2>
<p class="note">
  Drift-detected first (most actionable). Highlighted words in context = phrase found
  displaced in the other model. Use <strong>Use this</strong> to pre-fill, or type freely.
  Status and text auto-save to your browser; export when done.
</p>
{priority_html}

<h2 id="other">Other {len(other)} spans</h2>
<p class="note">Lower impact on meaning. Quick status + correction field per row.</p>
<table>
<thead>
<tr><th>#</th><th>Location</th><th>Chapter</th><th style="color:#1565c0">Qwen</th>
<th style="color:#2e7d32">Mistral</th><th>Base</th><th>Context (Qwen)</th><th>Type</th><th>Your correction</th></tr>
</thead>
<tbody>{other_rows}</tbody>
</table>

<script>{JS}</script>
</body>
</html>"""


def main():
    print("Loading data …")
    claude_pages    = load_claude_pages(CLAUDE_FILE)
    qwen_spreads    = load_spreads(QWEN_DIR, "qwen")
    mistral_spreads = load_spreads(MISTRAL_DIR, "mistral")

    print("Collecting Q≠M≠C spans …")
    spans = collect_qnmc_spans(qwen_spreads, mistral_spreads, claude_pages)
    print(f"  {len(spans)} spans found")

    from collections import Counter
    cats  = Counter(s["category"] for s in spans)
    high  = [s for s in spans if s["category"] in HIGH_SEVERITY]
    drift = [s for s in high if s["drift_label"]]

    print(f"\nHigh-severity: {len(high)} spans")
    print(f"  Drift detected: {len(drift)}  ({100*len(drift)//max(len(high),1)}%)")
    print(f"    Qwen likely:    {sum(1 for s in drift if s['likely_correct']=='Q')}")
    print(f"    Mistral likely: {sum(1 for s in drift if s['likely_correct']=='M')}")
    print(f"    Ambiguous:      {sum(1 for s in drift if s['likely_correct']=='ambiguous')}")
    print(f"  No drift (photo): {len(high)-len(drift)}")

    print(f"\nAll categories:")
    for cat in sorted(cats, key=lambda c: SEVERITY_ORDER.get(c, 99)):
        print(f"  {cat:<42} {cats[cat]:>4}")

    print(f"\nWriting {HTML_OUT.name} …")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    HTML_OUT.write_text(build_html(spans), encoding="utf-8")
    print(f"Done: {HTML_OUT}")

    import subprocess
    subprocess.run(["open", str(HTML_OUT)])


if __name__ == "__main__":
    main()
