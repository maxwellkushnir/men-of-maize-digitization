# PDF Generation Log — Men of Maize

**Stage:** Post-transcription — PDF build attempt  
**Date:** May 2026

---

## Context

With all 174 spreads transcribed and the assembly complete (214 pages, 0 gaps), the next step was generating the final PDF using `03_build_pdf.py` (WeasyPrint).

---

## Environment Decision: Google Colab

Local Mac build was blocked — `brew install pango` (required by WeasyPrint) needs ~10 GB free disk space, which the machine doesn't have.

Two options were considered:

**Friend's Mac** — cleanest path. macOS has Baskerville built in at the exact path the script expects. Zero code changes needed.

**Google Colab** — free, no disk issue, runs Linux. One complication: Baskerville is a macOS system font and isn't available on Linux. Fix: copy `Baskerville.ttc` from `/System/Library/Fonts/Supplemental/` on the Mac and upload it to Colab alongside the script. A one-line change to `03_build_pdf.py` makes it check for a local `Baskerville.ttc` before falling back to the macOS system path.

Went with Colab.

---

## Colab Setup

Dependencies already present on Colab's Linux image:
- `libpango-1.0-0` and `libpangocairo-1.0-0` — already installed
- `weasyprint 68.1` — installed via pip
- `PyMuPDF 1.27.2` — installed via pip

Files uploaded to `/content/` and moved into the expected directory structure:
- `/content/take2/03_build_pdf.py`
- `/content/take2/Baskerville.ttc`
- `/content/take2/output/men_of_maize_structured.json`
- `/content/1.pdf`

Build ran successfully and produced `men_of_maize.pdf` (1.7 MB).

---

## Issues Found in Output PDF

Visual inspection of the generated PDF revealed the following problems:

### 1. Page count is ~3× too high
The PDF has **652 pages**. The original book is ~350–400 pages. The assembly script groups content by detected `[Page N]` markers in the raw transcription, but many spreads only produced one marker for a two-page spread. This means both pages' content was packed into a single JSON page entry, which then overflows to 2–3 PDF pages each.

### 2. Short lines are centered instead of left-aligned
The last line of every justified paragraph (e.g., a line ending mid-sentence like "plains." or "God, sweet Lord of Mercy . . . !") appears centered rather than flush left. This is a WeasyPrint 68.1 behavior with `text-align: justify` — the `text-align-last: left` CSS property was added to the script but had no effect.

### 3. Hyphenation artifacts in source text
Words that were split across line-ends in the original print book were transcribed with a space before the hyphen (e.g., "disap- peared", "tim- bers", "godfa- thered"). These artifacts were not caught by the assembly cleanup and appear as broken words in the PDF.

### 4. Embedded page numbers appearing as content
The original book's printed page numbers (e.g., "37") were transcribed as plain text and appear between sentences in the body copy. They were not stripped during assembly because the cleanup only recognizes `[Page N]`-formatted markers, not bare Arabic numerals in the text flow.

### 5. Running headers not rendering
The `@page` margin box rules for running headers ("MEN OF MAIZE" on left pages, chapter name on right pages) do not appear in the output. WeasyPrint may not be applying the named page rules as expected given the current HTML structure.

---

## Colab Run 2 (May 2026)

Code fixes applied before this run:
- `02_assemble.py`: hyphenation dehyphenation, bare page number stripping (113 stripped), cross-page paragraph joining (58 joins)
- `03_build_pdf.py`: removed per-page `<div class="body-page">` wrappers; applied `page: body-page` to `#body-start`; moved `text-align: justify` + `text-align-last: left` onto `p` directly

**Result:** 650 pages, 1.3 MB. Headers still absent.

### New findings

**Root cause of 650-page count identified:** `02_assemble.py` was producing 104 chapter heading blocks instead of 7. Chapter names appear as running headers at the top of each original book page (e.g., "GASPAR ILÓM" printed at the top of every page in that chapter). `match_chapter()` runs before `is_running_header_noise()` in the line parser, so these running headers are parsed as chapter headings rather than discarded as noise. Each `h2.chapter-heading` has `page-break-before: right` in the CSS, generating ~97 spurious forced page breaks.

**Fix applied:** Post-processing pass in `02_assemble.py` after `sorted_pages` is built — keeps only the first occurrence of each chapter slug, removes all subsequent duplicates. Result: 7 chapter headings (one per chapter), at pages 15, 22, 51, 71, 103, 163, 329.

**Left-align confirmed working.**

**Headers still not working** — will diagnose after page count is confirmed fixed.

---

## Colab Run 3 (May 2026)

Code fixes applied before this run:
- `02_assemble.py`: removed duplicate chapter headings — 104 → 7 (running headers in original book were being parsed as chapter headings; each `h2` has `page-break-before: right`, creating ~97 spurious forced breaks)
- `03_build_pdf.py`: stripped `@page body-page:left` and `@page body-page:right` margin box rules (hypothesis: these are causing WeasyPrint to shrink effective text area); added `lang="en"` to `<html>` for proper hyphenation; fixed cover PDF path lookup to also check script directory (so uploading `1.pdf` alongside the script works in Colab)

**Diagnostic run before proceeding** — used PyMuPDF in Colab to inspect the 504-page PDF:

```
Total pages: 504
Page size: 5.50" × 8.50"  ← correct, not a sizing issue

Word count distribution:
  0–9 words:   33 pages
  10–49 words: 29 pages
  50–99 words:  1 page
  100–199 words: 66 pages
  200+ words:  375 pages

Pages whose text starts with a chapter/book name: 84
Near-blank pages (<5 words): 33
Page 50 (thin): "He ran out, this wasn't his rancho..." — ends mid-sentence, 35 words
```

**Finding 1: Running headers ARE rendering.** The 84 pages whose text starts with a chapter/book name are right-hand pages where PyMuPDF captured the margin-box running header text ("COYOTE-POSTMAN", "MEN OF MAIZE", etc.) as the first text on the page. WeasyPrint did render them — user didn't notice because they're 8pt in the top margin area above the main text block. The header CSS works.

**Finding 2: Root cause of page count identified.** 75,327 body words ÷ ~300 words/page = ~251 pages of expected content. 251 × 2 = 502 ≈ 504. WeasyPrint is treating `@page body-page:left` and `@page body-page:right` as two separate named page types rather than left/right variants of one type. Every page flip forces a break because the "named page changed." This doubles the count. The 33 near-blank and 29 thin (10–49 word) pages are the wasted transition pages inserted at each left→right and right→left switch.

**Fix applied for Run 3:** Removed `@page body-page:left` and `@page body-page:right` rules entirely. Kept a simple `@page body-page` with size and margins only. Also fixed cover PDF path lookup (checks script directory too), added `lang="en" xml:lang="en"` to `<html>` for proper hyphenation.

**Expected result:** Page count drops from 504 to ~280–320. Running headers will need a different approach — the WeasyPrint-compatible pattern is `@page :left` / `@page :right` without named pages, which avoids the doubling bug. To be implemented after page count is confirmed fixed.

**Result: 504 pages — identical to Run 2. Removing `:left/:right` rules had zero effect on page count.** The doubling hypothesis was wrong. However, pages starting with chapter names dropped from 84 → 80, confirming the margin boxes are gone. The 504-page count comes from something else.

**New finding:** The culprit is now suspected to be `#body-start { page: body-page; }`. WeasyPrint's named-page handling on a block element appears to mis-paginate the content. This was NOT tested in Run 3 (only the `:left/:right` rules were removed, not the named page assignment itself).

---

## Colab Run 4 (May 2026)

Fix: Removed all named-page CSS entirely — `@page body-page`, `@page front-matter-page`, `page: body-page` on `#body-start`, `page: front-matter-page` on `.front-matter`. Only `@page cover-page` retained (cover is a special full-bleed case). All body content now flows through the default `@page` rule. Cover page still uses `page: cover-page`.

**What we know going into Run 4:**

- Page size confirmed correct (5.5×8.5) ✓
- Content confirmed correct (75,327 words, 7 chapters, right structure) ✓
- `@page body-page:left` / `:right` ruled out — removing them had zero effect
- 504 ÷ ~251 expected pages ≈ exactly 2.0 — content fits ~250 pages but we get double
- The near-perfect doubling points to `#body-start { page: body-page; }` as the culprit — WeasyPrint may be laying out the named-page element's contents twice or creating extra page contexts internally
- Run 4 removes ALL named-page CSS (except cover) to test this hypothesis

**Expected:** Page count drops from 504 to ~300–350.

**Result:** 506 pages, 1.2 MB. Named-page removal had zero effect — hypothesis disproved.

### Root cause identified (post-run diagnosis)

Local PyMuPDF analysis of `men_of_maize-5.pdf` (the Run 4 output) revealed the true problem:

**The front_matter had 928 blocks / 43,602 words of actual chapter content — not just title pages.**

Root cause chain:
1. `06_mistral_ocr.py` recovered 49 blocked spreads, writing their content into the raw `.txt` files without `[Page N]` markers (Mistral doesn't use the Claude transcription format).
2. In `02_assemble.py`, any content before the first `[Page N]` marker in a spread goes to `orphan_blocks`, which go to `front_matter_blocks`.
3. Since Mistral output has NO `[Page N]` markers, ALL 49 Mistral spreads + 9 other no-marker spreads (65 total) went entirely into `front_matter_blocks` instead of `pages_by_num`.
4. Result: 43,602 words of body text (including 59 chapter heading h2 elements) in the "front matter" section.
5. Each `h2.chapter-heading` has `page-break-before: right` → 59 forced page breaks in the front matter alone → bloated page count.

**Expected PDF content (75,327 body words) vs actual HTML content (75,327 body + 43,602 front matter = 118,929 words total).** The body was MISSING 58 spreads of content (those 58 spreads were in the wrong section).

---

## Code Fixes Applied (May 2026) — for Run 5

### `02_assemble.py` changes

1. **Orphan spread → inferred page** (the core fix): instead of routing no-marker spreads to `front_matter_blocks`, they now get assigned an inferred page number based on the last known page from the same PDF (`last_page_by_pdf`). Each orphan spread becomes a real page in `pages_by_num`.

2. **True front matter preserved**: Spreads from `2-25.pdf` that come BEFORE its first `[Page N]` marker (spreads 1–7: title page, copyright, TOC) still go to `front_matter_blocks`. Everything else is body content.

3. **Markdown `#` header stripping**: Mistral OCR uses `#` prefixes for running headers (e.g., `# MEN OF MAIZE`). These are now stripped before processing, so they're correctly discarded by the existing running-header noise filter.

4. **Image description filtering**: Physical page descriptions from OCR (e.g., `[Page (left side - blank except for reversed text showing through)]`, `[The left page appears blank...]`) are now discarded.

5. **Fuzzy running-header matching**: `is_running_header_noise()` now includes a fuzzy match (cutoff 0.80) to catch OCR variants like `MEN OF MAREL`.

### Results after re-assembly

```
Front matter: 1 section, 45 blocks, ~340 words, 0 chapter headings
Body pages:   272 pages, ~118,046 words
Chapter headings: 7 (GASPAR ILÓM at pg 2, MACHOJÓN at pg 22, ...)
Expected PDF: ~393 content pages
```

**Expected Run 5 result:** ~420 pages (393 content + ~27 blank pages from 7 chapter `page-break-before: right` forced breaks).

---

## Colab Run 5 (May 2026)

No code changes — first run with the Round 2 assembly fix in place.

**Result: 418 pages, 1.7 MB.** Page count confirmed fixed. ✅

**PyMuPDF diagnostic findings:**

| Check | Result |
|-------|--------|
| Page size | 5.50" × 8.50" ✅ |
| Cover (p1) | Blank text extraction — image renders correctly ✅ |
| Chapter order | All 7 chapters in correct sequence ✅ |
| Chapter starts on odd pages | All 7 ✅ (p5, p31, p65, p91, p133, p209, p417) |
| Blank recto pages at chapter breaks | p30, p64, p132, p208, p416 ✅ |
| Body word density | ~280–320 words/page ✅ |
| NEEDS_REVIEW gaps | 0 ✅ |
| Running headers | ❌ Not rendering — no margin-box text found at top of any page |

**Root cause of missing running headers:** The `@page :left` / `@page :right` margin box rules were stripped during the Run 2–4 CSS experiments and never restored. WeasyPrint is not placing "MEN OF MAIZE" or chapter names in the top margin.

**Minor issues found:**
- `"Pi- ojosa"` hyphenation artifact on p10 (split-word not caught by dehyphenation regex)
- Library rubber-stamp text in front matter (p3): "BERGENFIELD FREE PUBLIC LIBRARY", "FREE PUBLIC LIBRARY BENSENVILLE, IL"
- CONTENTS page (p4) incomplete — only 3 of 7 chapters listed
- p131 has 11 words only (orphaned sentence near chapter boundary)

**Fix for Run 6:** Add correct `@page :left` / `@page :right` CSS with `string-set` / `string()` margin boxes to `03_build_pdf.py`.

---

## Colab Run 6 (May 2026)

Fix applied: Added `@page :left` / `@page :right` margin box rules to `03_build_pdf.py`. Cover page rules updated to suppress headers (`content: none` on all margin boxes).

**Result: 418 pages, 1.7 MB. Running headers confirmed working.** ✅

PyMuPDF diagnostic:

| Check | Result |
|-------|--------|
| Page count | 418 ✅ |
| Running headers | ✅ Odd pages: chapter name at y=26pt; Even pages: "MEN OF MAIZE" at y=26pt |
| Page numbers | ✅ Present at bottom of every page |

**Remaining issues (minor):**
- `"Pi- ojosa"` hyphenation artifact on p10 — fix in `02_assemble.py`
- Library stamps in front matter (p3) — manual patch in raw txt
- Incomplete CONTENTS page (p4) — manual patch in raw txt
- Body font (11pt) reported as feeling large — standard trade paperback is 10–11pt; will test at 10pt

---

## Colab Run 7 (May 2026)

Fixes applied:
- `02_assemble.py`: intra-page hyphen join fix ("Pi-" + "ojosa" across running header — stripped trailing hyphen in join); CONTENTS TOC fix (skipped `match_chapter()` and `is_running_header_noise()` for front matter spreads so TOC entries aren't eaten); library stamps removed from `2-25.pdf_raw.txt` (Bergenfield and Bensenville library rubber stamps)
- `03_build_pdf.py`: font size 11pt → 10pt, line-height 1.45 → 1.4

**Result: 338 pages, 1.6 MB.** (`men_of_maize-8.pdf`)

| Check | Result |
|-------|--------|
| Page count | 338 ✅ (expected ~380, slightly compact at 10pt/1.4) |
| Running headers | ✅ working (Baskerville, y=26pt) |
| Blank recto pages at chapter breaks | ✅ still present (p30, p64, p108, p132, p170) |
| Word density | ~395 words/page ✅ |
| Pi-ojosa artifact | ✅ fixed |
| Library stamps | ✅ removed |
| CONTENTS | ✅ all 7 chapters now present |

---

## Colab Run 8 (May 2026)

Fixes applied to `03_build_pdf.py`:
- Blank recto pages removed (`page-break-before: right` removed from `h2.chapter-heading`)
- Line-height 1.4 → 1.15
- Ornament images added (`ornament_break.png`, `ornament_fancy.png`), auto-cropped via PIL at runtime
- `ornament_fancy` before chapter headings; `ornament_break` before section numbers (Roman numerals); `ornament_break` image as section-break divider (replaces ◆)
- Copperplate font added for chapter headings and running headers
- Background colour `#ccc1b0` (parchment) on `@page` and `body`

**Result: 273 pages, 1.6 MB.** (`men_of_maize-9.pdf`)

| Check | Result |
|-------|--------|
| Page count | 273 ✅ (no blank chapter-break pages) |
| Running headers | ✅ Copperplate, correct alternation |
| Blank pages | ✅ None (only cover p1) |
| Word density | ⚠️ 450+ words/page — very dense, 1.15 line-height too tight |
| Ornaments | ✅ Rendering (to be confirmed visually) |
| Background | ✅ #ccc1b0 parchment |

**Remaining issue:** 1.15 line-height produces ~450 words/page — cramped. Consider 1.3 for Run 9.

---

## Colab Run 9 (May 2026)

Fixes applied to `03_build_pdf.py`:
- Line-height 1.15 → 1.3
- `page-break-before: right` restored on `h2.chapter-heading` (removed in Run 8 to kill blank pages, but 4 of 7 chapters landed on even/left pages as a result)
- Chapter heading font 13pt → 15pt (felt small at 13pt)

**Result: 317 pages, 1.7 MB.** (`men_of_maize-10.pdf`)

| Check | Result |
|-------|--------|
| Page count | 317 ✅ |
| Page size | 5.50" × 8.50" ✅ |
| All 7 chapters on odd (right) pages | ✅ (p5, p25, p51, p71, p103, p161, p317) |
| Blank recto pages at chapter breaks | ✅ 8 blank pages (1 per chapter, where needed) |
| Running headers | ✅ Copperplate, correct alternation |
| Word density | ✅ ~381 words/page |
| Ornaments | ✅ |
| Background | ✅ #ccc1b0 parchment |

**Current state:** PDF is structurally correct and typographically clean. No known layout issues outstanding.

**Next step:** Robustness check — run `04_compare.py` (independent re-transcription via Mistral/DeepSeek to flag content errors in the assembled text).

---

## Colab Run 10 (May 2026)

Fix applied to `03_build_pdf.py`:
- Chapter heading font 13pt → 15pt

**Result: 317 pages, 1.7 MB.** (`men_of_maize-12.pdf` — user ran an intermediate unlisted build between -10 and -12)

| Check | Result |
|-------|--------|
| Page count | 317 ✅ |
| All 7 chapters on odd pages | ✅ (p5, p25, p71, p103, p161, p317 detected; DEER title too long to extract as single block at 15pt — wraps to two lines, visually present) |
| Word density | ~381 words/page ✅ |

**Remaining:** Chapter headings still feel small — bumping to 17pt for next run.

---

## Colab Run 11 (May 2026)

Fix applied to `03_build_pdf.py`:
- Chapter heading font 15pt → 17pt

**Result: 317 pages, 1.7 MB.** (`men_of_maize-13.pdf`)

| Check | Result |
|-------|--------|
| Page count | 317 ✅ |
| All chapters on odd pages | ✅ (p5, p25, p71, p103, p161, p317 + DEER wraps across lines) |
| Word density | ~381 words/page ✅ |

**Current state:** PDF typesetting complete. Moving on to robustness check (workshopping approach).

---

## Colab Run 12 (June 2026)

No script changes — first build from the fully corrected Mistral base with all passes applied.

**New in this build vs PDF-13:**
- All correction passes applied (Rules 1, 2a, 2b, 2c + GPT-5.5 vision passes)
- 43 high-severity uncertain pages marked with `※` at start of first paragraph
- Appendix at back listing all 43 uncertain passages with Qwen / Mistral / base readings

**Result: 272 pages, 1.7 MB.** (`men_of_maize-14.pdf`)

| Check | Result |
|-------|--------|
| Page count | 272 |
| Build errors | None |
| Needs-review spreads | 0 |
| Size | 1.7 MB |

**Note on page count drop (317 → 272):** 45 fewer pages than PDF-13. Likely caused by the text corrections compacting content slightly and/or the uncertainty appendix not adding as much as the removed content saves. To be verified during visual review.

**Next:** User to visually review PDF-14 checklist (cover, headers, ornaments, ※ markers, appendix).

---

## Colab Runs 13–17 (PDFs 14–17, June 2026-06-01)

PDF-15 through PDF-17 were incremental fixes built locally and verified with `review_pdf.py`. Each addressed cross-check issues found during visual review (deduplication, OCR corrections, author bio garble, epilogue trailing ellipsis, etc.). Fully documented in `robustness_checks.md` under the PDF-17 cross-check section.

---

## Colab Run 18 — PDF-18 (2026-06-09)

**Purpose:** Apply 52 source-confirmed text corrections (Pass 18).

All 52 garbled passages identified by scanning PDF-17, then cross-checked against 4 raw sources (Qwen, Mistral, OpenAI, Claude base). Applied via scripts `22_apply_pass18_corrections.py` + `23_apply_pass18b_corrections.py`. Also deleted duplicate ~1.5-page Section XV in Coyote-Postman.

| Check | Result |
|-------|--------|
| Pages | ~270 |
| Build errors | None |
| Key fix | 52 garbled passages corrected; 1 structural duplicate deleted |

---

## Colab Run 19 — PDF-19 (2026-06-09)

**Purpose:** New layout (metadata page, linked TOC, EB Garamond) + GASPAR ILÓM manual transcription.

**Script changes in `03_build_pdf.py`:**
- Added `metadata_page_html()` — page 2 with Guatemala/Buenos Aires dates + author bio
- Added `toc_page_html()` — single-page linked TOC (all chapters hyperlinked)
- `render_cover_b64()` updated to handle PNG input (`1.png`)
- Body font switched to EB Garamond (auto-detected at `/usr/share/fonts/truetype/ebgaramond/`)
- Font size 10pt → 11pt, margins narrowed to widen text area ~10%
- Ornaments swapped: `ornament_fancy.png` ↔ `ornament_break.png`

**JSON changes:**
- Pages 1–14 replaced with clean manual transcription (script `24_insert_gaspar_transcription.py`)
- Epilogue trimmed: Guatemala dates + garbled pages 337+ removed
- Front matter cleared (replaced by hardcoded HTML in build script)
- Total pages: 272 → 265 after restructure

**Colab install cell required:**
```
apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0
apt-get install -y fonts-ebgaramond
pip install weasyprint PyMuPDF pillow -q
```

| Check | Result |
|-------|--------|
| Pages | ~385 |
| Build errors | None |
| Font | EB Garamond (confirmed loaded) |
| TOC | Single page, linked |

---

## Colab Run 20 — PDF-20 FINAL (2026-06-09)

**Purpose:** Fix 417 mid-sentence paragraph splits.

530 paragraph blocks in the JSON started with lowercase letters — all were mid-sentence continuations from Mistral's spread-boundary transcription, incorrectly stored as separate `<p>` blocks. One-pass merge applied to JSON (script inline, backup as `men_of_maize_structured_PREMERGE.json`).

No script changes to `03_build_pdf.py`. JSON uploaded to Colab, same three cells.

| Check | Result |
|-------|--------|
| Pages | ~385 |
| Build errors | None |
| Paragraph merges | 417 applied |
| Status | **FINAL — ready to publish** |

**Remaining known imperfections (accepted):**
- `[illegible]` placeholders at book pp. 52, 226, 314 (original photos needed)
- ~20 page-boundary duplicate passages (review tool flags them; not visible to reader)

---

## Colab Run 21 — PDF-21 (2026-06-11, pending)

**Purpose:** Two cosmetic fixes found during publication review.

**Script changes in `03_build_pdf.py`:**
- `_TOC_ENTRIES` displayed page numbers corrected from original print page numbers to actual PDF page positions: 1→5, 23→29, 49→57, 71→79, 103→113, 163→177, 329→355. Anchors unchanged — links still jump correctly.
- New closing page at the very end of the document: blank page (uses existing `blank-page` named page, so no running headers or page number) with `ornament_fancy.png` centered (`.closing-page`, padding-top 3.2in). Marks the formal end of the book.
- **EB Garamond detection hardened.** First Run 21 attempt (2026-06-12) silently fell back to DejaVu: Colab's updated runtime image installs `fonts-ebgaramond` outside the hardcoded paths, so the build printed `Body font: Baskerville (system fallback)` — that PDF was discarded. Script now searches all of `/usr/share/fonts` for `EBGaramond*Regular*` (prefers 12pt optical size, skips SC variants) before falling back. **Always verify the build prints `Body font: EB Garamond (found)`.**

**No JSON changes.** Upload `take2/03_build_pdf.py` + `take2/output/men_of_maize_structured.json` (+ `1.png`, ornament PNGs, `Copperplate.ttc`) to Colab; same three cells as Runs 19–20, install cell unchanged.

**Note:** Publicly the iteration count stays "twenty" (Max's call) — stat cards and blog unchanged.

**Run 21 outcome (2026-06-12):** Built successfully on second attempt (font fix). Output saved as `men_of_maize-FINAL.pdf` (346 pages). Max then found two TOC numbers still wrong: Coyote-Postman 177→175, Epilogue 355→345. Fixed **without rebuilding** via local PyMuPDF surgery: redacted the two spans, rewrote the numbers using the PDF's own embedded EB Garamond (right-aligned, same baseline/size/color), restored the two click-links removed by redaction (14/14 links verified). Result: **`men_of_maize-FINAL-tocfix.pdf` — the publication file.** `_TOC_ENTRIES` in the script updated to 175/345 for future builds.
