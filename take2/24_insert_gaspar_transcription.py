#!/usr/bin/env python3
"""
24_insert_gaspar_transcription.py
Replace garbled JSON pages 1-14 with the manually-transcribed GASPAR ILÓM Chapter I text.

Source: "Part I Chapter 1 transcribed.txt" (one flat text, ornament breaks marked)
Target: men_of_maize_structured.json pages 1-14
"""
import json, shutil, re
from pathlib import Path

BASE       = Path(__file__).parent
TRANSCRIPT = BASE.parent / "Part I Chapter 1 transcribed.txt"
JSON_PATH  = BASE / "output" / "men_of_maize_structured.json"
TXT_PATH   = BASE / "output" / "men_of_maize_clean.txt"

def parse_transcript(path: Path) -> list:
    """
    Parse the transcript file into a list of content blocks.
    Recognises:
      #Small ornament break#   → section_break
      #Big ornament break...#  → section_break
      Blank lines              → paragraph separator
      Everything else          → paragraph text
    Prepends the chapter heading and section number.
    """
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    blocks = [
        {"type": "chapter_heading", "text": "GASPAR ILÓM"},
        {"type": "section_number",  "text": "I"},
    ]

    para_buf = []

    def flush():
        t = " ".join(para_buf).strip()
        if t:
            blocks.append({"type": "paragraph", "text": t})
        para_buf.clear()

    for line in lines:
        stripped = line.strip()
        if re.match(r'#Small ornament break#', stripped, re.IGNORECASE):
            flush()
            blocks.append({"type": "section_break"})
        elif re.match(r'#Big ornament break', stripped, re.IGNORECASE):
            flush()
            blocks.append({"type": "section_break"})
            # Section II follows — add heading and the missing opener paragraph
            blocks.append({"type": "section_number", "text": "II"})
            blocks.append({"type": "paragraph", "text": (
                "The sun let down its hair. The summer was received in the domain of "
                "the chieftain of Ilóm with comb honey rubbed on the branches of the "
                "fruit trees, so the fruit would be sweet; with headdresses of immortelles "
                "on the heads of the women, so the women would be fertile; and with dead "
                "raccoons hanging from the doors of the ranchos, so the men would be potent."
            )})
        elif stripped == "":
            flush()
        else:
            para_buf.append(stripped)

    flush()
    return blocks


def split_at_section_break(blocks: list) -> tuple[list, list]:
    """Split block list at the first section_break into two groups."""
    for i, b in enumerate(blocks):
        if b["type"] == "section_break":
            return blocks[:i+1], blocks[i+1:]
    return blocks, []


def main():
    shutil.copy(JSON_PATH, JSON_PATH.with_name("men_of_maize_structured_PREPASS18d.json"))

    data   = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    blocks = parse_transcript(TRANSCRIPT)

    # Split transcript into two logical page groups at the first section_break
    part1, part2 = split_at_section_break(blocks)

    # Build two replacement page entries
    new_page_1 = {"page_number": 1,  "content_blocks": part1, "_source": "manual-transcription"}
    new_page_7 = {"page_number": 7,  "content_blocks": part2, "_source": "manual-transcription"}

    # Remove old pages 1-14 from JSON
    old_count = len([p for p in data["pages"] if p["page_number"] <= 14])
    data["pages"] = [p for p in data["pages"] if p["page_number"] > 14]

    # Insert new pages at the front
    data["pages"] = [new_page_1, new_page_7] + data["pages"]

    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Report
    print(f"Removed {old_count} old pages (1-14)")
    print(f"Inserted 2 new pages from transcription")
    print(f"  Page 1 : {len(part1)} blocks  (Section I up to first ornament break)")
    print(f"  Page 7 : {len(part2)} blocks  (Section I cont. + ornament break + Section II opener)")
    print(f"Total pages now: {len(data['pages'])}")
    print()
    print("Block types in page 1:")
    for b in part1:
        print(f"  [{b['type']}] {repr(b.get('text','')[:70])}")
    print()
    print("First 5 blocks of page 7:")
    for b in part2[:5]:
        print(f"  [{b['type']}] {repr(b.get('text','')[:70])}")
    print()
    print("First block of (old) page 15:")
    p15 = next((p for p in data["pages"] if p["page_number"] == 15), None)
    if p15:
        print(f"  [{p15['content_blocks'][0]['type']}] {repr(p15['content_blocks'][0].get('text','')[:80])}")

if __name__ == "__main__":
    main()
