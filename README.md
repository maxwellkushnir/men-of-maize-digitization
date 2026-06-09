# Men of Maize — Digitization Project

A pipeline to digitize *Men of Maize* by Miguel Ángel Asturias (1975 Delacorte/Seymour Lawrence, trans. Gerald Martin) from 175 photographed book spreads into a polished, downloadable PDF.

**Blog post:** *(link coming)*

---

| **4** | **18** | **95%** |
|:---:|:---:|:---:|
| AI models used | PDF passes | Agreement between independent models |

---

## What's in this repo

- **Pipeline scripts** (`take2/`) — numbered 01–21, covering every step from raw image to finished PDF
- **Project docs** — methodology, QA results, run logs, and divergence analysis
- **Blog notes** — raw notes for the accompanying blog post

## Pipeline overview

| Script | What it does |
|--------|-------------|
| `01_transcribe.py` | Claude vision API transcription of 175 spreads |
| `02_assemble.py` | Clean and structure raw output |
| `03_build_pdf.py` | Typeset to PDF — runs in Google Colab |
| `06_mistral_ocr.py` | Mistral OCR fallback for content-filtered spreads |
| `07_qwen_transcribe.py` | Qwen blind re-transcription (174/174 spreads) |
| `08_mistral_transcribe.py` | Mistral Large 3 blind re-transcription (174/174 spreads) |
| `09_three_way_compare.py` | Three-way bucketed comparison |
| `10_divergence_review.py` | HTML review queue of disagreements |
| `11_apply_qm_corrections.py` | Auto-correct where Qwen and Mistral agree against Claude |
| `12_linebreak_hyphen.py` | Dismiss line-break hyphen formatting artifacts |
| `13_punct_formatting.py` | Defer quote/ellipsis style differences to Qwen |
| `14_build_mistral_base.py` | Swap base text from Claude to Mistral |
| `15_apply_cq_corrections.py` | Apply Q=C≠M corrections against Mistral base |
| `15b_check_fallback_blocks.py` | Qwen-verify fallback blocks |
| `16_fallback_mistral_reread.py` | Recover unverified blocks from Mistral raw output |
| `17_apply_mc_corrections.py` | Single-word Q=C_orig≠M corrections |
| `18_text_adjudication.py` | GPT vision adjudication of ambiguous spans |
| `19_openai_transcribe.py` | GPT full re-transcription of affected spreads |
| `20_deduplicate_pages.py` | Cross-page deduplication |
| `21_mark_uncertainties.py` | Mark uncertain pages in JSON for ※ flagging in PDF |

## Project docs

| File | Contents |
|------|----------|
| `robustness_checks.md` | Current state, QA results, next steps — read this first |
| `first_draft_pass.md` | Full project history and technical decisions |
| `pdf_generation_log.md` | Colab run logs |
| `t1_vs_t2_divergences.md` | 788 word-level divergences between Take 1 and Take 2 |

---

> **Status:** One final PDF pass remaining before publication.
