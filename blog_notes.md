# Blog Notes — Men of Maize

## Stat cards (top of blog)

| 4 | 18 | 95% |
|---|----|----|
| AI models used | PDF passes | Agreement rate between independent models |

---

## Why the book is interesting

- The tension between the indigenous Mayan worldview — where maize is sacred, literally the substance humans are made of — and the Spanish/colonial mindset that treats it as a cash crop. That conflict is the whole engine of the book.
- Asturias won the Nobel Prize in 1967, partly for this kind of work — the magical realism he pioneered (he was doing it before García Márquez made it famous) comes directly from taking Mayan cosmology seriously as a narrative mode, not as folklore or decoration.
- There's something relevant about *why it's hard to find* — a Nobel laureate's major work, essentially unavailable. That connects back to the project itself.

---

## Technical details

- Started with 175 photographs of book spreads (the book is out of print / hard to find)
- Fed each photo to an AI vision model (Claude) to transcribe the text
- Then ran two completely independent re-transcriptions using two other models (Qwen and Mistral Large 3) — blind, without seeing the Claude output — to get a three-way cross-check
- After comparing all three, swapped the base text from Claude's version to Mistral's, because the comparison revealed Mistral was more reliable overall — so the final text isn't Claude's transcription with corrections on top, it's Mistral's
- Designed automated rules to adjudicate disagreements: where two models agree and one doesn't, trust the majority; dismiss differences that are just punctuation style or line-break formatting artifacts
- For the genuinely ambiguous remaining cases, used yet another model (GPT) to look at the original photos and cast a tiebreaker vote
- Some blocks still couldn't be resolved automatically and required manual review — actually opening the original photographs and reading them by eye to settle disagreements
- The two independent models agreed with each other at 94–97% across the whole book, giving a measure of confidence in the final text
- Typeset the final text into a proper book PDF (Baskerville font, trade paperback dimensions, running headers, ornamental section breaks) using a tool called WeasyPrint running in Google Colab
- The whole process was deeply iterative — the text went through more than a dozen automated correction passes, and the PDF was rebuilt 17 times as fixes were applied, each iteration catching something the previous one missed
- End result: ~300-page PDF of a novel that had never been digitized
