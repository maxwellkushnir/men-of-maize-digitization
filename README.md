# Men of Maize — Digitization Pipeline

This repo is the pipeline that turned 175 photographs of a then-out-of-print novel — *Men of Maize* by Miguel Ángel Asturias (1975 Delacorte edition, translated by Gerald Martin), photographed in 2020 when no other English edition existed — into a fully typeset, ~300-page PDF. Four AI models transcribed and cross-checked each other, automated rules adjudicated their disagreements, and the result went through twenty PDF builds before it was done.

**Blog post:** [Men of Maize — Building Diplomacy](https://buildingdiplomacy.substack.com/p/men-of-maize) · **PDF download:** [Google Drive](https://drive.google.com/file/d/16l0jQDiBAeTZIVikmtTjvXyOhxkVmShq/view?usp=sharing)

| **4** | **20** | **175** |
|:---:|:---:|:---:|
| AI models used | PDF passes | Photographed spreads |

---

## How it actually happened

### 1. Photograph and transcribe

The source was 175 photographed book spreads, stored as six PDFs. [`01_transcribe.py`](take2/01_transcribe.py) sent each spread to Claude's vision API and captured about 70% of the book on the first full run. The script includes soft-refusal detection and retry-with-fallback-prompt logic, and is resume-safe — all of which turned out to be necessary.

### 2. The content-filter problem

The other 30% failed in an unexpected way: hard API errors — `Output blocked by content filtering policy`. A Nobel laureate's 1949 novel was being flagged, spread by spread, as unsafe content. The blocking was nondeterministic: a spread that failed one day would pass the next, and benign pages blocked while genuinely violent ones sailed through.

Re-running the failures ([`05_retry_needs_review.py`](take2/05_retry_needs_review.py)) recovered some. The final 49 blocked spreads were recovered by a dedicated OCR model ([`06_mistral_ocr.py`](take2/06_mistral_ocr.py)) — all 49 in a single batch call, zero refusals, under ten cents.

### 3. Trust, but verify: the three-way cross-check

A complete transcription is not necessarily an accurate one. So two more models — Qwen ([`07_qwen_transcribe.py`](take2/07_qwen_transcribe.py)) and Mistral Large 3 ([`08_mistral_transcribe.py`](take2/08_mistral_transcribe.py)) — independently re-transcribed all 175 spreads from scratch, *blind*, without ever seeing the first transcription. [`09_three_way_compare.py`](take2/09_three_way_compare.py) scored the three versions against each other.

The two independent models agreed with each other on **94–97% of the text** across the whole book. The comparison also produced the project's biggest course correction: Mistral's transcription was systematically the most reliable, so the base text was swapped from Claude's version to Mistral's ([`14_build_mistral_base.py`](take2/14_build_mistral_base.py)), with alignment failures resolved by [`15b_check_fallback_blocks.py`](take2/15b_check_fallback_blocks.py) and [`16_fallback_mistral_reread.py`](take2/16_fallback_mistral_reread.py).

### 4. Adjudicating the disagreements

The remaining few percent — thousands of divergent spans, queued for review by [`10_divergence_review.py`](take2/10_divergence_review.py) — were settled by rules, in escalating order:

- **Majority wins.** Where two models agreed and one didn't, take the majority reading ([`11_apply_qm_corrections.py`](take2/11_apply_qm_corrections.py), [`15_apply_cq_corrections.py`](take2/15_apply_cq_corrections.py), [`17_apply_mc_corrections.py`](take2/17_apply_mc_corrections.py)).
- **Dismiss the cosmetic.** Differences that were just line-break hyphens or quote/ellipsis style were detected and dropped ([`12_linebreak_hyphen.py`](take2/12_linebreak_hyphen.py), [`13_punct_formatting.py`](take2/13_punct_formatting.py)).
- **Call a tiebreaker.** Where all three models disagreed, a fourth model (GPT) examined the original photographs and voted ([`18_text_adjudication.py`](take2/18_text_adjudication.py)) and re-transcribed the affected spreads from scratch ([`19_openai_transcribe.py`](take2/19_openai_transcribe.py)). Tellingly, the adjudicator was confident on only 6 of 580 contested spans — the rest were genuinely hard.
- **Look with human eyes.** The last few hundred ambiguous passages were settled manually against the photographs ([`22_apply_pass18_corrections.py`](take2/22_apply_pass18_corrections.py), [`23_apply_pass18b_corrections.py`](take2/23_apply_pass18b_corrections.py)), and the opening chapter was re-transcribed entirely by hand ([`24_insert_gaspar_transcription.py`](take2/24_insert_gaspar_transcription.py)).

What couldn't be fully verified isn't hidden: [`21_mark_uncertainties.py`](take2/21_mark_uncertainties.py) marks the remaining uncertain passages with a ※ in the PDF margin, with an appendix at the back showing each model's reading.

### 5. Making it a book again

[`02_assemble.py`](take2/02_assemble.py) turns the raw transcriptions into clean, structured text; [`03_build_pdf.py`](take2/03_build_pdf.py) typesets it with WeasyPrint (run in Google Colab) — EB Garamond at trade-paperback size, running headers, ornamental section breaks, a linked table of contents, and a cover.

The PDF was rebuilt **twenty times**. The first build came out at 652 pages (phantom blank pages, duplicated headings, four hundred paragraphs split mid-sentence at photo boundaries); the final one is ~300. That gap is what the iterations fixed.

---

## Map of the repo

**Scripts** (`take2/`), in four clusters:

| Cluster | Scripts |
|---------|---------|
| Read the photographs | `01` (Claude) · `06` (Mistral OCR) · `07` (Qwen) · `08` (Mistral Large 3) · `19` (GPT) |
| Cross-check & adjudicate | `04`–`05`, `09`–`21` — comparison, review queues, majority-vote rules, tiebreakers, dedup, uncertainty marking |
| Manual correction passes | `22`–`24` |
| Assemble & typeset | `02` (assembly) · `03` (PDF build, Colab) |

**Working documents** — the unpolished, complete record:

| File | What it's good for |
|------|--------------------|
| `first_draft_pass.md` | The full project history: every attempt, failure, and decision in order |
| `robustness_checks.md` | The QA methodology and agreement scores |
| `pdf_generation_log.md` | Run-by-run logs of all twenty Colab PDF builds |
| `t1_vs_t2_divergences.md` | All 788 word-level divergences between the first two transcription attempts |
| `blog_notes.md` | Raw notes for the blog post |

## What's *not* here

The book itself. *Men of Maize* is under copyright, so the photographs, the transcribed text, and the finished PDF are all excluded from this repo. What's shared is the pipeline and the record of how it was built.

Since this project began, the book has returned to print: Penguin Classics reissued Gerald Martin's translation in September 2024, in paperback and ebook, with a foreword by Héctor Tobar. If you want to own the book, buy that edition.

## If you want to dig deeper

The working documents above were written for the project, not for an audience — they're session logs. The intended way to explore this repo: clone it and ask your own Claude Code to walk you through it.

## A note on authorship

This README and the project's working documents were written by Claude Code — directed, reviewed, and corrected throughout by Maxwell Kushnir, the project's author.
