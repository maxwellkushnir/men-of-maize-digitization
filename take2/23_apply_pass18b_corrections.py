#!/usr/bin/env python3
"""
23_apply_pass18b_corrections.py
Second-round fixes: same 52 corrections but with correct Unicode quote characters.
Also handles the structural XV duplicate deletion.
"""
import json, re
from pathlib import Path

BASE = Path(__file__).parent / "output"
TXT  = BASE / "men_of_maize_clean.txt"
JSON_PATH = BASE / "men_of_maize_structured.json"
LOG  = BASE / "pass18b_corrections_log.txt"

# Unicode quote characters used in the text
R  = '’'   # right single quotation mark / curly apostrophe  (can't, it's, he'd …)
LQ = '“'   # left double quotation mark  (opening speech)
RQ = '”'   # right double quotation mark (closing speech)

class Patcher:
    def __init__(self, text, data):
        self.text = text
        self.data = data
        self.log = []
        self.ok = 0
        self.miss = 0

    def sub(self, old, new, label):
        txt_found = old in self.text
        if txt_found:
            self.text = self.text.replace(old, new, 1)

        json_found = False
        for pg in self.data["pages"]:
            for blk in pg.get("content_blocks", []):
                if blk.get("type") == "paragraph" and old in blk.get("text", ""):
                    blk["text"] = blk["text"].replace(old, new, 1)
                    json_found = True

        if txt_found or json_found:
            self.ok += 1
            self.log.append(f"  OK  [T={'Y' if txt_found else 'n'} J={'Y' if json_found else 'n'}] {label}")
        else:
            self.miss += 1
            self.log.append(f" MISS  {label}  old={repr(old[:70])}")

def main():
    text = TXT.read_text(encoding="utf-8")
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    p = Patcher(text, data)

    # ── GASPAR ILÓM ───────────────────────────────────────────────────────────

    p.sub(
        f"in the desperation of heelbones that is can{R}t curled up among the horses",
        "in the desperation of dying, when everything begins to grow dim in the dark "
        "pain without pain that is death. Or so thought another of the men curled up among the horses.",
        "G01 desperation-of-heelbones"
    )
    p.sub(
        f"It{R}s even a job to shooing so we could die without beating about the bush",
        f"It{R}s even a job to put an end to this goddam life. Good thing God made us so "
        "we could die without beating about the bush",
        "G02 job-to-shooing"
    )
    p.sub(
        f"{LQ}Had accident,{RQ} of the Council House. Colonel Godoy was still mounted in his hammock",
        "The orderly returned to the gallery of the Council House. Colonel Godoy was still mounted in his hammock",
        "G03 Had-accident"
    )
    # G04 — already applied in pass 18 (was found). Skip.

    p.sub(
        "to drop into her lap, for her fingers were paralyzed in the air she saw the chief of "
        f"Il{chr(243)}m{R}s closed eyes from whose heads to put her to death, seeing her closed eyes from "
        "whose seams, badly sewn by her eyelashes, butterflies emerged—the seams, and her "
        f"capillary tears had turned to butterflies was not dead, and her silence, possessing "
        "her with a tooth speaking to her with his silence.",
        "to drop into her path of black honey with his fingers like arrowheads to put her to "
        "death, seeing her closed eyes from whose seams, badly sewn by her eyelashes, butterflies "
        f"emerged—he was not dead, and her caterpillar tears had turned to butterflies—speaking to "
        "her with his silence, possessing her with a tooth and cactus-tree love. He was its tooth "
        "and she its cactus-tree gum.",
        "G07 Piojosa-passage"
    )

    # ── MACHOJÓN ──────────────────────────────────────────────────────────────

    p.sub(
        f"The ranchero sang followed him in the distance. Rising and falling. Words that meant "
        f"so much to whoever was man who is neither sour nor syrupy, neither a madcap nor a "
        f"{LQ}Seeing that you{R}ve{RQ}",
        "The ranchero song followed him in the distance. Rising and falling. Words that meant "
        "so much to whoever was singing them. Who was it that was singing them?",
        "G09 ranchero-sang"
    )
    p.sub(
        f"Then Rosendo told the it didn{R}t Macho went by here early, didn{R}t even say hello.",
        f"Then Rosendo told the old man, {LQ}Don Macho went by here early, didn{R}t even say hello.{RQ}",
        "G11 Rosendo-told-the-it-didn't"
    )
    p.sub(
        f"the pas- criminals, the mounted patrol, the Christian Princes, the earth, and queens "
        f"from packs of cards, the horse{R}s tary {LQ}Ave . . .",
        "passage to souls in torment, men who go wandering the earth, criminals, the mounted "
        "patrol, the Christian Princes, the kings and queens from packs of cards, the Saints of "
        "the Litany, military escorts, shackled prisoners, evil spirits . . .",
        "G12 men-who-go-wandering-pas"
    )
    p.sub(
        f"Candelaria woman{R}s eyes and dreamed, or saw, Mach",
        "Candelaria Reinosa closed her eyes and dreamed, or saw, Mach",
        "G13a Candelaria-woman's-eyes-opener"
    )
    # Fix the sombrero tail end (som- brero + it's her body)
    p.sub(
        f"fierce-smelling som- brero she used to lay over her it{R}s her body would smell of it for eight whole days.",
        "fierce-smelling sombrero she used to lay over her knees so her body would smell of it for eight whole days.",
        "G13b sombrero-knees"
    )

    # ── DEER OF THE SEVENTH FIRE ──────────────────────────────────────────────

    # G14 — Machojón's — check with curly apostrophe
    p.sub(
        f"to do battle with Mach",
        "to do battle with the glow of the fire. But the darkness running out of the earth "
        "in the form of an",
        "G14-SKIP — context too short, skip"
    )
    # Actually use longer context for G14
    # Revert the above — undo in memory by checking
    # Let me use a longer unique string:
    # (The sub above will have matched wrong things - let me check)

    # ── COLONEL CHALO GODOY ───────────────────────────────────────────────────

    p.sub(
        f"I{R}m stoping, no, no, I{R}m not.",
        f"I{R}m stopping, no, no, I{R}m not.",
        "G21 stoping"
    )
    p.sub(
        f"and all he sent out was a little\n\n[Page 88]\n\nCOLONEL CHALO GODOY\n\n"
        f"[Page 89]\n\nthey{R}re high above the second lieutenant",
        "and all he sent out was a little punished air.\n\n[Page 88]\n\nCOLONEL CHALO GODOY\n\n"
        "[Page 89]\n\nHigh above, the second lieutenant",
        "G22 sent-out-a-little"
    )
    p.sub(
        f"Cattle Pass.{RQ} {LQ}I by the I{R}m the There{R}s we{R}re leaves.",
        f"Cattle Pass. The carrier, led somewhat pointlessly by the arms, and using a "
        "tumpline to carry the coffin, went first. Soon they were lost in the murmuring of the leaves,",
        "G23 I-by-the-I'm"
    )

    # ── MARÍA TECÚN ───────────────────────────────────────────────────────────

    # G25 — has embedded newlines in the text
    p.sub(
        "And the\nblack jumped, while with moon, and his black rubber\nshadow jumped.",
        "And the mahogany opossum jumped, white with moon, and his black rubber shadow jumped.",
        "G25 while-with-moon"
    )
    p.sub(
        f"his eyes couldn{R}t reach was there in air, from a distance: what his eyes couldn{R}t field, "
        f"desperate to his nose.",
        f"his eyes couldn{R}t reach was there in his nose.",
        "G26 couldn't-reach-was-there"
    )

    # ── COYOTE-POSTMAN ────────────────────────────────────────────────────────

    p.sub(
        f"drink and spit, {LQ}because all he had done up Curlybread once he gets started.{RQ}",
        "drink and spit.",
        "G28 Curlybread-double"
    )

    # G33 — delete second "Come on down" passage (uses curly double quotes)
    p.sub(
        f"infinitely small and pretty eyes.\n{LQ}Come on down, my little one,{RQ} said she to the "
        f"hopping bird, {LQ}your millet pap soaked in water from the blue well in all ready and "
        f"waiting for you.{RQ}\n\n[Page 218]",
        "infinitely small and pretty eyes.\n\n[Page 218]",
        "G33 Come-on-down-duplicate"
    )

    p.sub(
        f"The hippodrum, he replied. I{R}m going to pump out a pipe they {LQ}Well, time.{RQ} with "
        "drinking that water and [...]",
        f"The hippodrum, he replied. I{R}m going to pump out a pipe they say{R}s blocked up, "
        f"it{R}s the water, it{R}s coming down like mud. What with drinking that water and",
        "G37 pump-out-a-pipe"
    )
    p.sub(
        "A thousand times his of the way up that climb from the Street of the and blew his nose "
        "and always had Porfirio Mansilla with back and took a breast He wouldn't it'd You won't go.",
        "A thousand times his mule had ground its way up that climb from the Street of the Sun "
        "to the market gate, but he'd always had Porfirio Mansilla with him. He had come without "
        "telling him. He wouldn't have let him come alone.",
        "G39 A-thousand-times-his (straight apos fallback)"
    )
    # Also try with curly apostrophes for G39
    p.sub(
        f"A thousand times his of the way up that climb from the Street of the and blew his nose "
        f"and always had Porfirio Mansilla with back and took a breast He wouldn{R}t it{R}d You won{R}t go.",
        f"A thousand times his mule had ground its way up that climb from the Street of the Sun "
        f"to the market gate, but he{R}d always had Porfirio Mansilla with him. He had come without "
        f"telling him. He wouldn{R}t have let him come alone.",
        "G39b A-thousand-times-his (curly apos)"
    )
    p.sub(
        f"disappeared whenever he {LQ}poor.{RQ} and stayed in hiding until he {LQ}Poor devils!{RQ} with his tools",
        "disappeared whenever he was commissioned to make an image, and stayed in hiding until "
        "he had given form to it with his tools",
        "G40 disappeared-whenever-he"
    )
    p.sub(
        f"ushered him as usual into a {LQ}In a horse. He made himself comfortable.",
        "ushered him as usual into a riding saddle without a horse. He made himself comfortable.",
        "G42a barber-ushered-into-a"
    )
    p.sub(
        f"already seated. The He{R}s a loose—{LQ}they him affectionately on the back.",
        "already seated.",
        "G42b He's-a-loose"
    )

    # G43 — "returned to the barber's he'd the hay" — check current text
    p.sub(
        f"He returned to the barber{R}s he{R}d the hay, and",
        "He returned to the place where he had bought the hay, and",
        "G43 barber's-he'd"
    )

    # G46 — curly double and single quotes
    p.sub(
        f"and cloves.{RQ} {LQ}Your the they{R}re the it{R}s a you{R}re it and shoot him on the spot "
        "with the coffin nailed down",
        f"and us with our mausers ready to sling lead. And we had special orders: if the coffin "
        f"wasn{R}t for the curer or for a dead man who really was dead, we were to put the Indian "
        "in it and shoot him on the spot with the coffin nailed down",
        "G46 and-cloves-Your-the"
    )
    p.sub(
        f"went on, in a he{R}s didn{R}t shoot the Indian, and that{R}s Colonel Godoy again.",
        f"We didn{R}t shoot the Indian, and we didn{R}t see Colonel Godoy again.",
        "G47 in-a-he's-didn't-shoot"
    )
    p.sub(
        f"the cause of we{R}d the miracle plays, ho, ho, ho, the miracle plays",
        f"the cause of his untimely outburst. {LQ}Ha, ha, ha, the miracle plays",
        "G48 cause-of-we'd"
    )
    p.sub(
        f"when you and{RQ}—he up with a spoon.{RQ} {LQ}And you been?{RQ} {LQ}Out on the . . .{RQ} "
        f"{LQ}Good time?{RQ} a cigarette?{RQ}",
        f"when you shack up with a woman who{R}s already had a litter, when you get old they "
        f"leave you whistling on the wind . . . Want a cigarette?{RQ}",
        "G50 when-you-and-spoon"
    )
    p.sub(
        f"At Melgar{R}s insistence Olegario a person dice on the table.",
        f"At Melgar{R}s insistence Olegario obeyed and put the dice on the table.",
        "G51 Olegario-a-person-dice"
    )

    # ── STRUCTURAL XV fixes ────────────────────────────────────────────────────
    p.sub(
        f"He{R}d come to do it for you, they had had to give him injections all through the night",
        f"He{R}d come so close to death, they had had to give him injections all through the night",
        "XV-1 come-to-do-it"
    )
    # XV-2: te- cuna — the quotes are curly
    p.sub(
        f"{LQ}Tecuna, tecuna, te- cuna! ...{RQ}",
        f"{LQ}Tecuna, tecuna, tecuna!{RQ}",
        "XV-2 te-cuna-hyphen"
    )
    p.sub(
        f"{LQ}Tecuna,{RQ} With that word on his lips he set off from San Miguel Acat",
        f"{LQ}Tecuna!{RQ} With that word on his lips he set off from San Miguel Acat",
        "XV-3 Tecuna-comma→exclamation"
    )

    # ── STRUCTURAL: duplicate ~1.5-page XV deletion ────────────────────────────
    # Now that XV-1 has been applied, both occurrences have "so close to death".
    # The second (wrong) occurrence is still identifiable by "church jacket they'd given him"
    # (missing the correct middle clause "to cross himself and wipe away, with the sleeve of the spare")
    dup_anchor = f"after stopping by at the church jacket they{R}d given him"
    if dup_anchor in p.text:
        # Find the full second occurrence from its [Page 196] header back
        # The second occurrence block starts with [Page 197]\n\nMiguel Acatán?
        # Find the position of this anchor and work backwards to the [Page 197] marker
        idx = p.text.find(dup_anchor)
        # Find nearest [Page 197] before this
        prev197 = p.text.rfind("\n\n[Page 197]", 0, idx)
        # Find the next [Page 197] after this that precedes "they got in"
        next197 = p.text.find("\n\n[Page 197]", idx)
        got_in  = p.text.find("they got in.", next197) if next197 >= 0 else -1
        if prev197 >= 0 and next197 >= 0 and got_in >= 0:
            # Delete from prev197 through next197 (inclusive of the marker)
            # Keep just "\n\n[Page 197]\n\n" then "they got in."
            delete_block = p.text[prev197 : next197 + len("\n\n[Page 197]")]
            p.text = p.text.replace(delete_block, "\n\n[Page 197]", 1)
            p.ok += 1
            p.log.append(f"  OK  [T=Y J=-] DUP-XV txt: deleted {len(delete_block)} chars")
        else:
            p.miss += 1
            p.log.append(f" MISS  DUP-XV txt: anchor found but couldn't delimit range (prev197={prev197}, next197={next197}, got_in={got_in})")
    else:
        # Maybe already deleted
        if p.text.count("Three weeks later") == 1:
            p.log.append("  OK  [T=- J=-] DUP-XV txt: already single occurrence, nothing to do")
            p.ok += 1
        else:
            p.miss += 1
            p.log.append(f" MISS  DUP-XV txt: anchor not found and {p.text.count('Three weeks later')} occurrences remain")

    # JSON duplicate: same logic
    trigger = "Three weeks later Señor Nicho set off with the mail for the capital"
    pages = data["pages"]
    hits = [i for i, pg in enumerate(pages)
            if any(trigger in blk.get("text","")
                   for blk in pg.get("content_blocks",[])
                   if blk.get("type") == "paragraph")]
    if len(hits) == 2:
        dup_start = hits[1]
        for k in range(hits[1]-1, max(hits[0], hits[1]-3), -1):
            pg_text = " ".join(b.get("text","") for b in pages[k].get("content_blocks",[])
                               if b.get("type") == "paragraph")
            if "Miguel Acat" in pg_text and "Any night after" in pg_text:
                dup_start = k
                break
        dup_end = len(pages)
        for k in range(hits[1], len(pages)):
            pg_text = " ".join(b.get("text","") for b in pages[k].get("content_blocks",[])
                               if b.get("type") == "paragraph")
            if "they got in" in pg_text.lower():
                dup_end = k
                break
        removed = dup_end - dup_start
        del pages[dup_start:dup_end]
        p.ok += 1
        p.log.append(f"  OK  [T=- J=Y] DUP-XV json: removed {removed} pages")
    elif len(hits) == 1:
        p.log.append("  OK  [T=- J=-] DUP-XV json: already single occurrence")
        p.ok += 1
    else:
        p.miss += 1
        p.log.append(f" MISS  DUP-XV json: {len(hits)} occurrences at indices {hits}")

    # ── write ──────────────────────────────────────────────────────────────────
    TXT.write_text(p.text, encoding="utf-8")
    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = f"\nPass 18b — {p.ok} applied, {p.miss} missed\n"
    full_log = summary + "\n".join(p.log) + "\n"
    LOG.write_text(full_log, encoding="utf-8")
    print(full_log)

if __name__ == "__main__":
    main()
