# Robustness Checks — Men of Maize

## Document Reading Order

| # | File | Read when |
|---|------|-----------|
| 1 | `robustness_checks.md` ← **this file** | Always — current state, next step, all QA results |
| 2 | `first_draft_pass.md` | Need project history or context on a past decision |
| 3 | `pdf_generation_log.md` | Debugging a Colab PDF build |
| 4 | `t1_vs_t2_divergences.md` | Verifying a specific passage against the original T1 transcription |

---

## Key Facts About the Original Book

- **Title:** *Men of Maize* by Miguel Ángel Asturias (1975 Delacorte/Seymour Lawrence, trans. Gerald Martin)
- **Chapters:** GASPAR ILÓM · MACHOJÓN · THE DEER OF THE SEVENTH FIRE · COLONEL CHALO GODOY · MARÍA TECÚN · COYOTE-POSTMAN · EPILOGUE
- **Typography:** Baskerville serif, small caps chapter headings, page numbers at bottom outer corners
- **Running headers:** "MEN OF MAIZE" on left pages · current chapter name on right pages
- **Section breaks:** small ornamental square (◆) between sections within a chapter
- **Total spreads:** 175 across 6 source PDFs
- **Source PDFs:** `1.pdf` (cover), `2-25.pdf`, `26-55.pdf`, `56-75.pdf`, `76-107.pdf`, `108-.pdf`
- **PDF build:** always runs in Google Colab (WeasyPrint + pango) — do not attempt locally

---

**Purpose:** Verify that the assembled text (`men_of_maize_clean.txt`) is accurate before publishing the PDF.  
**Current PDF:** `take2/PDFs/men_of_maize-14.pdf` (272 pages, all corrections applied, ※ markers + appendix)

---

## ▶ RESUME HERE (next session)

**PDF-14 built (2026-06-01). 272 pages, 1.7 MB. All correction passes applied.**

- ✅ Task A (fallback blocks): 215/215 resolved
- ✅ Rule 1 (`15_apply_cq_corrections.py`): 193 JSON / 95 txt Q=C≠M corrections applied
- ✅ Rule 2a (`12_linebreak_hyphen.py`): 19 JSON fixes, 297 linebreak spans dismissed
- ✅ Rule 2b (`13_punct_formatting.py`): 325 JSON fixes, 2,384 formatting spans dismissed
- ✅ Rule 2c (`17_apply_mc_corrections.py`): 392 txt / 596 JSON single-word Q=C_orig≠M corrections + 2 manual fixes (adorms→adorns, ortiroot→orrisroot)
- ✅ Script 18 (`18_text_adjudication.py`): GPT-5.5 vision adjudication → 3 txt / 3 JSON corrections
- ✅ Script 19 (`19_openai_transcribe.py`): GPT-5.5 re-transcription → 79 txt / 60 JSON corrections
- ✅ PDF-14 built: 272 pages, 1.7 MB, 0 errors, saved as `take2/PDFs/men_of_maize-14.pdf`

**▶ NEXT SESSION — start here:**
Build PDF-18 in Colab (upload updated `03_build_pdf.py` + `men_of_maize_structured.json`). After that, supply manual text for GASPAR ILÓM opening (2-25.pdf pp. 1–14, PDF pp. 5–35) — paste into chat → write replacement script → rebuild as PDF-19.

**JSON state after PDF-17 cross-check fixes (2026-06-01):**
- Author bio fixed (was garbled with "solitude of lead" injected mid-sentence)
- Epilogue trailing ellipsis restored; "Poppa-Possun" → "Poppa-Possum"
- "with, out copying" → "without copying"; duplicate "you you" fixed
- All OCR corrections applied (honeycombs, beatified, Jasmíne, Señor Nicho, jigged, roseapples, doeskin, tamale soup, vendors, bat's wing)
- Deduplication passes run (22 overlaps removed total)
- "Eugrope" confirmed correct — all three sources agree, do NOT change

**Remaining known issues:**
- GASPAR ILÓM (PDF pp. 5–35): duplicates, fragments, garbles — replace with manual text
- ~20 remaining duplicates throughout the book (automated dedup reached its limit)
- "[illegible]" placeholders at book pp. 52, 226, 314 — need original photos

**Known uncertainties (for next iteration):**
- 43 pages with `※` markers — high-severity Q≠M≠C spans, no model majority
- GASPAR ILÓM opening (2-25.pdf pp. 1–14) — most problematic section; user to supply manually
- Uncertainty index: `take2/output/uncertainty_index.json`
- Interactive review tool: `take2/output/unresolved_spans_report.html`

---

**▶ BASE SWAP — Steps 1 & 2 COMPLETE (2026-05-26):**  
`take2/14_build_mistral_base.py` ran in 1.2 seconds. Results:
- `men_of_maize_clean.txt` rebuilt from Mistral (118,401 words; target 118,116 ✓)
- `men_of_maize_structured.json` transplanted: **1,650/1,865 paragraph blocks (88.5%) replaced with Mistral text**
- 215 blocks kept Claude text (fallback): mostly short dialogue lines and pages 2–14 (GASPAR ILÓM opening, where Mistral didn't number the spreads)
- Full fallback log: `take2/output/mistral_base_transplant_log.txt`
- Backups preserved: `men_of_maize_clean_CLAUDE_BASE.txt`, `men_of_maize_structured_CLAUDE_BASE.json`

**▶ FALLBACK BLOCK QWEN CHECK COMPLETE (2026-05-26):**  
`take2/15b_check_fallback_blocks.py` ran. Results for the 215 `_base_fallback` blocks:
- 107 verified (Qwen agrees with Claude — no change)
- 40 corrected (Qwen has a different reading — Claude text replaced with Qwen's)
  - Genuine OCR corrections: "sleeps it" → "sees all" (p2), "curse" → "cure" (p14), "blizzard's" → "buzzard's" (p173), garbled p201 text fixed, "musi-cians" → "musicians" (p14), etc.
- 68 unverified (low confidence or line-break hyphen artifacts in Qwen — kept Claude text)
- Full log: `take2/output/fallback_qwen_check_log.txt`

---

**▶ FALLBACK BLOCK FULL RESOLUTION — COMPLETE (2026-05-26)**

All 215 `_base_fallback` blocks are now resolved. Three scripts + one manual review pass:

| Stage | Script | Blocks | Method |
|---|---|---|---|
| Qwen verified (no change) | `15b_check_fallback_blocks.py` | 107 | Qwen confirmed Claude's text |
| Qwen corrected | `15b_check_fallback_blocks.py` | 40 | Qwen's reading applied (genuine OCR fixes) |
| Mistral re-read recovered | `16_fallback_mistral_reread.py` | 38 | Fuzzy paragraph match on existing Mistral raw data — no API calls |
| Garbled codes blanked | `15b` + `16` | 8 | `5609`, `SE06 05990-01551m`, `SECS`, `SEDS 4 1930-01` + others |
| Corpus-confirmed short blocks | inline | 6 | `Mango.`, `Yes.`×2, `No.`, `1899-1974`, `Poppa-possum.` |
| Direct corrections | inline | 2 | `Stupid horse` sentence (Q+M both had correct text); `Poppa-posum` spelling |
| **Manual PDF review** | `fallback_review2.html` | **19** | User opened PDFs, verified/corrected each block |
| **Total** | | **215/215** | ✓ |

Key manual corrections from PDF review:
- p2: "serpent" (not "snake" or "script"), "lakes" restored, "he could feel" (not "had curled itself around")
- p50: "Be good if the curer came back today…who slipped the cricket in our Nana's belly" (Claude misread)
- p52: "Calistro, Calistro…" (not "Calitro")
- p62: "I brought you some yucca flowers as well." (entirely different sentence from Claude's garbled version)
- p66: "Maybe this'll bring you round!" (not "jump you round")
- p82: "Glimmering beeeEEEast! Beastly beeeEEEast!" (phonetic shout corrected)
- p84: "Maaa-cho! Maaa-cho!" (not "Masa-cho")
- p154: "On credit . . ." "Free drinks died, and credit's dead."
- p222 ×3: "María TecúúúÚÚÚn . . . María TecúúúÚÚÚn!" (phonetic cry corrected, all 3 instances)
- p224: "He met a train of oxcarts. The carters were sprawled…" (opening fragment fixed)
- p259: "It was all kept very quiet, just like it will be when you come out and surprise us all, Canducha." (garbled middle fixed; name corrected to Canducha)
- p73, p50 ("Where are the others?"): deleted (not in book at that position)

Fallback block work is done. No `_qwen_unverified` or `_mistral_unresolved` flags remain in the JSON.

**Logs:** `take2/output/fallback_qwen_check_log.txt`, `take2/output/fallback_mistral_reread_log.txt`  
**Review form used:** `take2/output/fallback_review2.html`

---

---

**▶ ALL CORRECTION PASSES COMPLETE (2026-05-29)**

Full correction pass history (Mistral base → all rules → GPT-5.5 vision):

| Pass | Script | Result |
|------|--------|--------|
| Rule 1: Q=C≠M | `15_apply_cq_corrections.py` | 193 JSON / 95 txt corrections |
| Rule 2a: line-break hyphens | `12_linebreak_hyphen.py` | 19 JSON fixes, 297 spans dismissed |
| Rule 2b: quote/ellipsis style | `13_punct_formatting.py` | 325 JSON fixes, 2,384 spans dismissed |
| Rule 2c: single-word Q=C_orig≠M | `17_apply_mc_corrections.py` | 392 txt / 596 JSON + 2 manual fixes |
| GPT-5.5 vision adjudication | `18_text_adjudication.py` | 3 txt / 3 JSON corrections (580 spans, 574 uncertain) |
| GPT-5.5 vision re-transcription | `19_openai_transcribe.py` | 79 txt / 60 JSON corrections (102 spreads) |

**Final scores after all passes (2026-05-29):**

| Pages | Base vs Qwen | Base vs Mistral | Qwen vs Mistral |
|-------|-------------|-----------------|-----------------|
| 1–50   | 90.6% | 93.2% | 95.8% |
| 51–100 | 90.6% | 94.0% | 95.0% |
| 101–150| 89.5% | 93.3% | 95.2% |
| 151–200| 86.1% | 91.7% | 94.4% |
| 201–250| 87.7% | 92.3% | 94.5% |
| 251–300| 90.2% | 92.8% | 96.6% |
| 301–337| 86.0% | 87.7% | 97.0% |

**Q≠M span queue breakdown (final — from last `10_divergence_review.py` run, 2026-05-29):**
- Total spans: 4,245
- Q≠M≠C (all three differ): **515** (down from 582 before GPT-5.5 passes)
- Q=C≠M: 434
- M=C≠Q: 863
- Q≠M (C n/a): 2,431

**Key output files:**
- `take2/output/men_of_maize_clean.txt` — assembled text, all corrections applied ✓
- `take2/output/men_of_maize_structured.json` — structured JSON, all corrections applied ✓
- `take2/output/divergence_review.html` — Q≠M review queue (515 Q≠M≠C spans, manually reviewable)
- `take2/output/openai_raw/` — raw GPT-5.5 re-transcription output (per-PDF .txt files)
- `take2/output/openai_corrections_log.txt` — Script 19 corrections log
- `take2/output/text_adjudication_log.txt` — Script 18 adjudication log
- `take2/output/cq_corrections_log.txt` — Rule 1 correction log
- `take2/output/linebreak_corrections_log.txt` — Rule 2a log
- `take2/output/punct_formatting_log.txt` — Rule 2b log

---

## Check 2 — Take 1 vs Take 2 Diff (DONE)

**Method:** Run `04_compare.py` locally. Diffs Take 1 (~70% coverage, ~95k words) against the assembled Take 2 text page by page. No API needed.

**Run:** 2026-05-25

```bash
cd "Raw Data (to use)/take2"
python3 04_compare.py
# output: take2/output/comparison_report.html
```

**Raw numbers:**
| Metric | Count |
|--------|-------|
| T1 pages | 251 |
| T2 pages | 272 |
| Pages compared (both present) | 214 |
| Good match (≥92%) | 28 (13%) |
| Minor divergence (70–92%) | 107 |
| Significant divergence (<70%) | 79 |
| T1-only pages | 21 |
| T2-only pages (Mistral-recovered, no T1) | 42 |

### Why the 13% "good match" rate is misleading

The low rate is mostly a **page boundary misalignment artefact**, not content errors. Both T1 and T2 use actual book page numbers (`[Page N]`), but the two model runs drew the boundary at slightly different points within each spread — so T1's "page 52" and T2's "page 52" contain the same chapter passage but different slices of it. The per-page diff scores low even when the content is essentially the same text.

A spot-check confirms this: T1 page 25 and T2 page 25 have Jaccard similarity 0.65, but only because the segment boundaries don't align — the words themselves are the same novel chapter.

Additional noise: T1 consistently uses `Gaspar` (no accent) while T2 uses `Gáspár` (accented throughout). The byte-level string comparison treats every character-name occurrence as a mismatch.

### Genuine findings

**1. One confirmed word-level transcription error caught:**
- T1 (line 250): `"His half-burned hands clawed at the ground"`
- T2 (line 56 of clean.txt): `"His half-buried hands clawed at the ground"`
- **T2 is correct.** Gaspar is pressing his drunk hands into the earth — no fire is present in this scene. T1 misread "buried" as "burned".

**2. Accent inconsistency — T1 uses `Gaspar Ilóm`, T2 uses `Gáspár Ilóm`.**  
T2 is likely correct (matches the published translation's spelling). This difference inflates the divergence counts throughout the comparison.

**3. T1's 21 pages not in T2** — these are spreads that were blocked by Claude's content filter in Take 2 and recovered by Mistral OCR. Mistral's output was assigned inferred page numbers, which may not exactly match the book's real page numbers, so some T1 pages have no corresponding T2 page in the comparison.

**4. T2's 42 pages not in T1** — Mistral-recovered spreads from the section that failed in both Take 1 and Take 2 (mainly `108-.pdf` / COYOTE-POSTMAN). No T1 equivalent exists, so these pages are unverified by Check 2.

### Content-level pass (04b_content_compare.py) — 2026-05-25

A second pass stripped all page structure, normalised accents, and diffed the full body text as a single word sequence. This avoids the page-boundary misalignment problem entirely.

**Results:**
- T1 body tokens: 91,769 — T2 body tokens: 118,005
- Total divergences (content words only, coverage gaps excluded): **788**
- All 788 fall within the first ~30% of the book — beyond that, T1's gaps mean no meaningful alignment is possible

**Sample of genuine errors found (both directions):**

| ~Pos | T1 | T2 | Verdict |
|------|----|----|---------|
| 1% | serpent | script | T1 likely correct ("serpent of six hundred thousand coils") |
| 1% | steeple | sleeps | T2 correct |
| 1% | twisted slashetes | freshly sharpened machetes | T2 correct (T1 badly misread) |
| 1% | burned (×2) | buried (×2) | T2 correct (confirmed) |
| 1% | decompose | decapitate | T2 correct |
| 1% | cactus | a gourd | T2 correct |
| 1% | heavy | hoary | T2 likely correct |
| 1% | flittermouse | fittermouse | T1 correct (flittermouse = archaic for bat) |
| 2% | rib cage | image | ambiguous — needs original photo |
| 2% | cure | curse | T2 likely correct |
| 2% | buzzards should | yellow rabbits | significant semantic difference, needs photo |

**Divergence log:** All 788 entries recorded in `t1_vs_t2_divergences.md` (grouped by ~10% book position buckets, with context). Use as a lookup during Check 1 to flag where independent models should arbitrate.

### Verdict

T2 is more accurate than T1 on balance — T1 has more gross misreads (e.g. "twisted slashetes" for "machetes", "steeple" for "sleeps"). T2 has at least one confirmed error ("script" for "serpent"). The ~30% of the book beyond T1's coverage is entirely unverified by Check 2. **The divergence log is the key output — use it during Check 1.**

---

## Check 1 — Independent Blind Re-transcription (DONE)

**Method:** Re-transcribed all 174 spreads from scratch using two models fully independent of the Claude pipeline. Compared word-level agreement against the assembled `men_of_maize_clean.txt` in ~50-page buckets via `SequenceMatcher`.

**Models:**
- **Qwen** (`qwen3-vl-plus`, DashScope US endpoint, OpenAI-compatible SDK)
- **Mistral** (`mistral-large-2512` / Mistral Large 3, fresh blind run — NOT reusing `06_mistral_ocr.py`)

**Scripts (2026-05-25):**
- `take2/07_qwen_transcribe.py` — Qwen transcription → `output/qwen_raw/`
- `take2/08_mistral_transcribe.py` — Mistral Large 3 transcription → `output/mistral_raw/`
- `take2/09_three_way_compare.py` — Bucketed three-way comparison → `output/three_way_report.html`

**Transcription runs:** 2026-05-25 — both completed 174/174 spreads, zero API errors.

| Model | Spreads | Total words |
|-------|---------|-------------|
| Claude (assembled) | — | 117,832 |
| Qwen3-VL-Plus | 174/174 | 119,462 |
| Mistral Large 3 (`mistral-large-2512`) | 174/174 | 118,116 |

**Three-way comparison results (final — `mistral-large-2512`):**

| Pages (Claude ref.) | Claude vs Qwen | Claude vs Mistral | Qwen vs Mistral |
|---------------------|---------------|-------------------|-----------------|
| 1–50   | 90.7% | 90.6% | **95.8%** |
| 51–100 | 86.7% | 87.3% | **95.0%** |
| 101–150| 92.0% | 90.5% | **95.2%** |
| 151–200| 87.7% | 87.2% | **94.6%** |
| 201–250| 87.3% | 88.0% | **94.6%** |
| 251–300| 93.2% | 94.3% | **96.6%** |
| 301–337| 96.5% | 95.8% | **97.0%** |

**0 buckets flagged below 80%.**

### Development note: pixtral-large-latest was tested and rejected

During development, an earlier version of `08_mistral_transcribe.py` used `pixtral-large-latest`. That model was deprecated by Mistral on 2026-02-27 and had a known repetition-loop bug — it would enter a generation loop, repeating the same phrase 5–15× before continuing, inflating its word count to ~129k and corrupting the output. Those test outputs were identified and discarded. **The script was updated to `mistral-large-2512` before the actual production run.**

The `output/mistral_raw/` files (confirmed by the `# Model: mistral-large-2512` header in each file) are clean. Apparent repetitions in the output (e.g. `"Gaspar Ilóm is letting them…"` appearing three times) are verified as legitimate literary anaphora in the source text, not model artifacts.

**Both independent transcriptions — Qwen and Mistral Large 3 — are reliable.** The three-way comparison is fully valid.

### Why Claude scores lower than Q vs M

The meaningful pattern in the results table is not that any model is broken — it is that **Qwen and Mistral agree with each other more than either agrees with Claude**:

- Qwen vs Mistral: 94–97% (two independent models, different APIs, different architectures)
- Claude vs Qwen / Claude vs Mistral: 87–96%

This gap (87–96% vs 94–97%) is the signal that Claude's transcription diverges more from the independent sources than they diverge from each other. Manual review confirmed real Claude errors — e.g. scanning the line below accidentally, reading "burned" for "buried", misreading "machetes" as "twisted slashetes". Claude is the base text but the least reliable transcriber of the three.

### Results summary

- **Qwen vs Mistral: 94–97%** across all 7 buckets — the two independent models agree strongly
- **Claude vs Qwen: 87–96%**, **Claude vs Mistral: 87–95%** — Claude is consistent with both
- **Zero buckets below 80%**
- **4,392 divergent spans** between Qwen and Mistral (8,350 Qwen words / 6,675 Mistral words, ~5–7% of total)

These 4,392 spans are positions where the two independent models disagree and the correct reading cannot be determined by comparison alone. The goal is to reduce this manual review queue as far as possible before resorting to photo checks.

---

## Reducing the Manual Review Queue

**Rule 1 — Q=M≠C: auto-correct (no photo needed)**

Where Qwen and Mistral agree but Claude differs, trust Q/M and correct Claude automatically. Both independent models saw the original photograph and reached the same reading — Claude is the outlier.

Script: `take2/11_apply_qm_corrections.py`
- 1,382 Q=M≠C cases found
- **249 corrections applied to `men_of_maize_clean.txt`**
- **949 corrections applied to `men_of_maize_structured.json`**
- 1,133 skipped (phrase appeared 0 or 2+ times in the page text — too ambiguous for auto-replace)
- Full log: `take2/output/qm_corrections_log.txt`
- Example caught: Claude said "fittermouse", Q and M both said "flittermouse" (archaic word for bat — Q/M correct)

**Rule 2a — Line-break hyphen artifacts: dismiss from queue (no photo needed)**

Many Q≠M spans are not real word disagreements — one model faithfully transcribed a line-break hyphen from the printed page (e.g. `Lis- ten`, `misfor- tune`, `planta- tions`) while the other silently joined the word. After collapsing the hyphen-space, Q and M agree on the word content.

Logic (all four conditions must hold):
1. The divergence is between Q and M (Claude's reading is ignored for the rule, though if Claude also agrees that's a bonus)
2. One or both spans contain the pattern `word- word` (hyphen followed by a space mid-word)
3. After collapsing all such patterns, the word content of Q and M match (punctuation stripped, case-insensitive)
4. Therefore: the joined form is correct — both models agree once the formatting artifact is removed

Key nuance: if a span has both a line-break word AND a punctuation difference (e.g. `musician. "Lis- ten,` vs `musician, "Listen,`), only the word part is resolved (`Listen`); the punctuation difference (period vs comma) remains. These spans are counted as partially resolved — they stay in the queue for the punctuation check but the word itself is confirmed correct.

Note on Claude's text: Claude never transcribed the split forms (it always joined words as normal prose), so 0 corrections were needed in `men_of_maize_clean.txt` or the JSON. The benefit of this rule is purely span-count reduction in the review queue.

Script: `take2/12_linebreak_hyphen.py`
- **297 linebreak-resolvable Q≠M spans identified** (out of 4,245)
- 162 individual split-word instances found across those spans
- 0 corrections applied to Claude's text (Claude already had the joined form or a different reading)
- Full log: `take2/output/linebreak_corrections_log.txt`
- Example: Q `planta- tions,` vs M `plantations,` → correct word is `plantations`. Claude already had `plantations`. Span dismissed.

**▶ Span count after Rule 2a: 4,245 − 297 = 3,948 remaining**

---

**Rule 2b — Quote / ellipsis / dash style: dismiss and defer to Qwen**

Where the ONLY difference between Q and M is a formatting convention — not word content — defer to Qwen's style and apply it to Claude's text.

Qwen's preferred styles (detected from raw output):
- Quotes: curly (`"` `"` `'` `'`) — Qwen uses 2,759 curly apostrophes vs Mistral's mix
- Ellipsis: spaced (`. . .`) — Qwen uses 350 spaced vs Mistral's 277 plain `...`
- Dashes: em dash (`—`) — both models use em dash; no pure dash-style spans found

Logic: after normalising all three dimensions to a canonical form, if Q == M, the span is formatting-only and is dismissed. Qwen's un-normalised version is applied to Claude's text.

Script: `take2/13_punct_formatting.py`
- **2,384 formatting-only Q≠M spans dismissed**
  - 2,224 quote-style only, 115 ellipsis-style only, 48 quote+ellipsis combo
- **910 corrections applied to `men_of_maize_clean.txt`**
- **1,210 corrections applied to `men_of_maize_structured.json`**
- 1,726 skipped (Claude's text not found at that position, or found 0/2+ times)
- Full log: `take2/output/punct_formatting_log.txt`
- Example: Q `"Gaspar` (curly double quote) vs M `"Gaspar` (straight) → Claude text updated to curly. Q `. . .` vs M `...` → Claude updated to spaced form.

**▶ Span count after Rule 2b: 3,948 − 2,384 = 1,564 remaining**

---

**All automated rules complete.** Remaining 515 Q≠M≠C spans are genuinely ambiguous — no model has a majority reading. Manual review via `divergence_review.html` is the only remaining option.

**Review document:** `take2/output/divergence_review.html` — all Q≠M spans with Qwen, Mistral, and Claude readings side by side.

**Current status:** All rules (1, 2a, 2b, 2c) + GPT-5.5 vision passes applied. **515 Q≠M≠C spans remain — manual review or accept as-is before PDF build.**
