#!/usr/bin/env python3
"""
22_apply_pass18_corrections.py
Apply 52 source-confirmed text corrections + structural duplicate fix.
"""
import json, shutil
from pathlib import Path

BASE = Path(__file__).parent / "output"
TXT  = BASE / "men_of_maize_clean.txt"
JSON_PATH = BASE / "men_of_maize_structured.json"
LOG  = BASE / "pass18_corrections_log.txt"

def backup(p):
    dst = p.with_name(p.stem + "_PREPASS18" + p.suffix)
    if not dst.exists():
        shutil.copy(p, dst)
        print(f"Backed up → {dst.name}")

# ── helpers ──────────────────────────────────────────────────────────────────

class Patcher:
    def __init__(self, text, data):
        self.text = text
        self.data = data
        self.log = []
        self.ok = 0
        self.miss = 0

    def sub(self, old, new, label):
        """Replace in txt and in every JSON paragraph block."""
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
            status = f"TXT={'Y' if txt_found else 'n'} JSN={'Y' if json_found else 'n'}"
            self.log.append(f"  OK  [{status}] {label}")
        else:
            self.miss += 1
            self.log.append(f" MISS         {label}  →  {repr(old[:70])}")

def main():
    backup(TXT); backup(JSON_PATH)
    text = TXT.read_text(encoding="utf-8")
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    p = Patcher(text, data)

    # ─── GASPAR ILÓM ──────────────────────────────────────────────────────────

    p.sub(
        "in the desperation of heelbones that is can't curled up among the horses",
        "in the desperation of dying, when everything begins to grow dim in the dark "
        "pain without pain that is death. Or so thought another of the men curled up among the horses.",
        "G01 desperation-of-heelbones"
    )
    p.sub(
        "It's even a job to shooing so we could die without beating about the bush",
        "It's even a job to put an end to this goddam life. Good thing God made us so "
        "we could die without beating about the bush",
        "G02 job-to-shooing"
    )
    p.sub(
        '"Had accident," of the Council House. Colonel Godoy was still mounted in his hammock',
        "The orderly returned to the gallery of the Council House. Colonel Godoy was still mounted in his hammock",
        "G03 Had-accident"
    )
    p.sub(
        '"You," crazy." "Go the apothecary\'s, and tell them to be here tonight."',
        '"You," Godoy ordered the soldier, "go find me those musicians who came about '
        'the serenade and tell them to be here tonight."',
        "G04 You-crazy-Go-apothecary"
    )
    p.sub(
        "jiggeded in and out of the darkness",
        "jiggled in and out of the darkness",
        "G05 jiggeded"
    )
    p.sub(
        "to guide the stars in the winter. The firefly wizards be sure there would be guiding stars. The firefly wizards,",
        "to be sure there would be guiding stars in the winter. The firefly wizards,",
        "G06 firefly-wizards-be-sure"
    )
    p.sub(
        "to drop into her lap, for her fingers were paralyzed in the air she saw the chief of "
        "Ilóm's closed eyes from whose heads to put her to death, seeing her closed eyes from "
        "whose seams, badly sewn by her eyelashes, butterflies emerged—the seams, and her "
        "capillary tears had turned to butterflies was not dead, and her silence, possessing "
        "her with a tooth speaking to her with his silence.",
        "to drop into her path of black honey with his fingers like arrowheads to put her to "
        "death, seeing her closed eyes from whose seams, badly sewn by her eyelashes, butterflies "
        "emerged—he was not dead, and her caterpillar tears had turned to butterflies—speaking to "
        "her with his silence, possessing her with a tooth and cactus-tree love. He was its tooth "
        "and she its cactus-tree gum.",
        "G07 Piojosa-passage"
    )

    # ─── MACHOJÓN ─────────────────────────────────────────────────────────────

    p.sub(
        "go figure out place to plant his seed",
        "go some other place to plant his seed",
        "G08 go-figure-out-place"
    )
    p.sub(
        'The ranchero sang followed him in the distance. Rising and falling. Words that meant '
        'so much to whoever was man who is neither sour nor syrupy, neither a madcap nor a '
        '"Seeing that you\'ve"',
        "The ranchero song followed him in the distance. Rising and falling. Words that meant "
        "so much to whoever was singing them. Who was it that was singing them?",
        "G09 ranchero-sang"
    )
    p.sub(
        "you haven't go by?",
        "you seen him go by?",
        "G10 haven't-go-by"
    )
    p.sub(
        "Then Rosendo told the it didn't Macho went by here early, didn't even say hello.",
        'Then Rosendo told the old man, "Don Macho went by here early, didn\'t even say hello."',
        "G11 Rosendo-told-the-it-didn't"
    )
    p.sub(
        'to give "Yes, men who go wandering the pas- criminals, the mounted patrol, the Christian '
        'Princes, the earth, and queens from packs of cards, the horse\'s tary "Ave . . .',
        "to give passage to souls in torment, men who go wandering the earth, criminals, the "
        "mounted patrol, the Christian Princes, the kings and queens from packs of cards, the "
        "Saints of the Litany, military escorts, shackled prisoners, evil spirits . . .",
        "G12 men-who-go-wandering-pas"
    )
    p.sub(
        "Candelaria woman's eyes and dreamed, or saw, Machojón riding down from the mountain "
        "gullies where the fires were, on his unbroken stallion, with soda water and cheese "
        "tortillas in his saddlebags, and that fierce-smelling som- brero she used to lay over "
        "her it's her body would smell of it for eight whole days.",
        "Candelaria Reinosa closed her eyes and dreamed, or saw, Machojón riding down from the "
        "mountain gullies where the fires were, on his unbroken stallion, with soda water and "
        "cheese tortillas in his saddlebags, and that fierce-smelling sombrero she used to lay "
        "over her knees so her body would smell of it for eight whole days.",
        "G13 Candelaria-woman's-eyes"
    )

    # ─── DEER OF THE SEVENTH FIRE ─────────────────────────────────────────────

    p.sub(
        "to do battle with Machojón's the fire.",
        "to do battle with the glow of the fire.",
        "G14 Machojón's-the-fire"
    )
    p.sub(
        "returned to brighten her gaze with the over the eyes of the sick woman to pass his "
        "open hands light of the stars.",
        "returned to pass his open hands over the eyes of the sick woman to brighten her gaze "
        "with the light of the stars.",
        "G15 pass-his-open-hands"
    )
    p.sub(
        "And as he stuffed his arm down his fingers under his armpit.\nHis brother Uperto came "
        "upon him, on his way hidden there, his brother Uperto came upon him, on his way back "
        "from looking at the dead man's scar",
        "He spat bitterly as he wiped his fingers under his armpit. And as he stuffed his arm "
        "down a hole in the ground, groping for the bottom to leave his gun hidden there, his "
        "brother Uperto came upon him, on his way back from looking at the dead man's scar",
        "G16-17 stuffed-arm-brother-Uperto"
    )

    # ─── COLONEL CHALO GODOY ──────────────────────────────────────────────────

    p.sub(
        "As Colonel Godoy felt someone then a bullet he turned his head",
        "As Colonel Godoy felt someone jarring on his tail he turned his head",
        "G18 felt-someone-then-a-bullet"
    )
    p.sub("the sallion started bucking", "the stallion started bucking", "G19 sallion")
    p.sub(
        "The sonorous bloodlost of his laughter could not be heard",
        "The sonorous bellows of his laughter could not be heard",
        "G20 bloodlost"
    )
    p.sub("I'm stoping, no, no, I'm not.", "I'm stopping, no, no, I'm not.", "G21 stoping")
    p.sub(
        "and all he sent out was a little\n\n[Page 88]\n\nCOLONEL CHALO GODOY\n\n"
        "[Page 89]\n\nthey're high above the second lieutenant",
        "and all he sent out was a little punished air.\n\n[Page 88]\n\nCOLONEL CHALO GODOY\n\n"
        "[Page 89]\n\nHigh above, the second lieutenant",
        "G22 sent-out-a-little"
    )
    p.sub(
        'toward the Cattle Pass." "I by the I\'m the There\'s we\'re leaves.',
        "toward the Cattle Pass. The carrier, led somewhat pointlessly by the arms, and using "
        "a tumpline to carry the coffin, went first. Soon they were lost in the murmuring of the leaves,",
        "G23 I-by-the-I'm"
    )
    p.sub(
        "He had swallowed one of the dried dry, dry skin was the color of ash, black eyes the color of coal.",
        "He had swallowed one of the devil's hairs. That was part of the agreement. And he had "
        "turned dry, dry skin the color of ash, black eyes the color of coal.",
        "G24 devil's-hairs"
    )

    # ─── MARÍA TECÚN ──────────────────────────────────────────────────────────

    p.sub(
        "And the black jumped, while with moon, and his black rubber shadow jumped.",
        "And the mahogany opossum jumped, white with moon, and his black rubber shadow jumped.",
        "G25 while-with-moon"
    )
    p.sub(
        "He could never tell how it was things became materialized in the air, explained how it "
        "was his eyes couldn't reach was there in air, from a distance: what his eyes couldn't "
        "field, desperate to his nose.",
        "He could never have explained how it was things became materialized in the air, from a "
        "distance: what his eyes couldn't reach was there in his nose.",
        "G26 couldn't-reach-was-there"
    )
    p.sub(
        "we must make time so the full heat of the cash I had.",
        "we must make time so the full heat of the sun won't catch us on the road, I've already "
        "given you all the cash I had.",
        "G27 full-heat-of-the-cash"
    )

    # ─── COYOTE-POSTMAN ───────────────────────────────────────────────────────

    p.sub(
        "because all he had done up until then was drink and spit, 'because all he had done up "
        "Curlybread once he gets started.'",
        "because all he had done up until then was drink and spit.",
        "G28 Curlybread-double"
    )
    p.sub("The dog painting, Señor Nicho", "The dog panting, Señor Nicho", "G29 dog-painting")
    p.sub("followed by Jasmínc.", "followed by Jasmine.", "G30 Jasmínc")
    p.sub("Senior Nicho will be starting out", "Señor Nicho will be starting out", "G31 Senior-Nicho")
    p.sub(
        "they carry its reflection. That something and carry it along, they carry its reflection of Miguelita.",
        "they carry its reflection. That man and the sewing machine are the reflection of Miguelita.",
        "G32 That-something-and-carry"
    )
    # G33 — delete the short duplicate "Come on down" passage (keep the full first one)
    p.sub(
        'looked again at the tropical with its delicate plumage and infinitely small and pretty eyes.\n'
        '"Come on down, my little one," said she to the hopping bird, "your millet pap soaked in '
        'water from the blue well in all ready and waiting for you."\n\n[Page 218]',
        "looked again at the tropical with its delicate plumage and infinitely small and pretty "
        "eyes.\n\n[Page 218]",
        "G33 Come-on-down-duplicate"
    )
    p.sub("couned in her image", "coined in her image", "G34 couned")
    p.sub(
        "Christening late? But wedding occasions are celebrated with chocolate chocolate. All great "
        "occasions Baby Jesus was making with breadcrumbs when the Jew came",
        "Christening chocolate. All great occasions are celebrated with chocolate and bird-cake. "
        "The little birds Baby Jesus was making with breadcrumbs when the Jew came",
        "G35 chocolate-chocolate"
    )
    p.sub(
        "He heard it. a bird, on to his hat, which the wind was intent on turning into a bird, "
        "spurred the mule forward and was soon well lost in his yesterdays? that his being, when "
        "he came to himself, who kept on going in the region around the peak.",
        "He shook his head—so many foolish thoughts—and harnessed himself with the hat cord "
        "again, he was having to hold on to his hat, which the wind was intent on turning into a "
        "bird, spurred the mule forward and was soon well beyond that small settlement which, now "
        "that he came to think about it, was the only sign of human life in the region around the peak.",
        "G36 He-heard-it-a-bird"
    )
    p.sub(
        'The hippodrum, he replied. I\'m going to pump out a pipe they "Well, time." with '
        'drinking that water and [...]',
        "The hippodrum, he replied. I'm going to pump out a pipe they say's blocked up, it's "
        "the water, it's coming down like mud. What with drinking that water and",
        "G37 pump-out-a-pipe"
    )
    p.sub(
        "she pulled it round to the front before the first great shriek she put on her back and "
        "took a breast with the shawl she used to carry it on her back. Fauna could sell white "
        "full of milk out from under her shift. Fauna retorted: coffee, too, said another of yours",
        "she pulled it round to the front before the first great shriek, and took a breast full "
        "of milk out from under her shift. Fauna could sell white coffee, too, said another of "
        "the three musicians",
        "G38 Fauna-sell-white"
    )
    p.sub(
        "A thousand times his of the way up that climb from the Street of the and blew his nose "
        "and always had Porfirio Mansilla with back and took a breast He wouldn't it'd You won't go.",
        "A thousand times his mule had ground its way up that climb from the Street of the Sun "
        "to the market gate, but he'd always had Porfirio Mansilla with him. He had come without "
        "telling him. He wouldn't have let him come alone.",
        "G39 A-thousand-times-his"
    )
    p.sub(
        'disappeared whenever he "poor." and stayed in hiding until he "Poor devils!" with his tools',
        "disappeared whenever he was commissioned to make an image, and stayed in hiding until "
        "he had given form to it with his tools",
        "G40 disappeared-whenever-he"
    )
    p.sub(
        "wrapped in sedentary went into the workshop",
        "wrapped in a sheet. All three went into the workshop",
        "G41 wrapped-in-sedentary"
    )
    p.sub(
        'The barber ushered him as usual into a "In a horse. He made himself comfortable.',
        "The barber ushered him as usual into a riding saddle without a horse. He made himself comfortable.",
        "G42a barber-ushered-into-a"
    )
    p.sub(
        'already seated. The He\'s a loose—"they him affectionately on the back.',
        "already seated.",
        "G42b He's-a-loose"
    )
    p.sub(
        "He returned to the barber's he'd the hay, and",
        "He returned to the place where he had bought the hay, and",
        "G43 barber's-he'd-the-hay"
    )
    p.sub(
        "all wandering up and down the passageways every- they were lost",
        "all wandering up and down the passageways as if they were lost",
        "G44 passageways-every"
    )
    p.sub(
        "but he was hearthstones, of one of them, Ramos",
        "but he was none too fond of one of them, Ramos",
        "G45 hearthstones-Ramos"
    )
    p.sub(
        'and cloves." "Your the they\'re the it\'s a you\'re it and shoot him on the spot with '
        'the coffin nailed down',
        "and us with our mausers ready to sling lead. And we had special orders: if the coffin "
        "wasn't for the curer or for a dead man who really was dead, we were to put the Indian "
        "in it and shoot him on the spot with the coffin nailed down",
        "G46 and-cloves-Your-the"
    )
    p.sub(
        "but in a he's didn't shoot the Indian, and that's Colonel Godoy again.",
        "We didn't shoot the Indian, and we didn't see Colonel Godoy again.",
        "G47 in-a-he's-didn't-shoot"
    )
    p.sub(
        "as he tried to explain the cause of we'd the miracle plays, ho, ho, ho, the miracle plays",
        'as he tried to explain the cause of his untimely outburst. "Ha, ha, ha, the miracle plays',
        "G48 cause-of-we'd"
    )
    p.sub(
        "with the passing of ma- chete you listening, Hilario?",
        "with the passing of the years—Are you listening, Hilario?",
        "G49 passing-of-ma-chete"
    )
    p.sub(
        'when you and"—he up with a spoon." "And you been?" "Out on the . . ." "Good time?" a cigarette?"',
        "when you shack up with a woman who's already had a litter, when you get old they leave "
        'you whistling on the wind . . . Want a cigarette?"',
        "G50 when-you-and-spoon"
    )
    p.sub(
        "At Melgar's insistence Olegario a person dice on the table.",
        "At Melgar's insistence Olegario obeyed and put the dice on the table.",
        "G51 Olegario-a-person-dice"
    )
    p.sub(
        "But just as COYOTE-POSTMAN to the ground with the stump of his missing arm",
        "But just as Olegario put them down the one-arm swept them to the ground with the "
        "stump of his missing arm",
        "G52 COYOTE-POSTMAN-injected"
    )

    # ─── STRUCTURAL: fix garbles within the FIRST (kept) occurrence of XV ─────

    p.sub(
        "He'd come to do it for you, they had had to give him injections all through the night",
        "He'd come so close to death, they had had to give him injections all through the night",
        "XV-1 come-to-do-it-for-you"
    )
    p.sub('"Tecuna, tecuna, te- cuna! ..."', '"Tecuna, tecuna, tecuna!"', "XV-2 te-cuna-hyphen")
    p.sub(
        '"Tecuna," With that word on his lips he set off from San Miguel Acatán',
        '"Tecuna!" With that word on his lips he set off from San Miguel Acatán',
        "XV-3 Tecuna-comma"
    )
    p.sub(
        "will hear someone sew- ing at a machine. It is Miguelita.",
        "will hear someone sewing at a machine. It is Miguelita.",
        "XV-4 sew-ing-hyphen"
    )

    # ─── STRUCTURAL: delete the duplicate ~1.5-page second occurrence of XV ───
    # The second occurrence is uniquely identified by its garbled postmaster line
    # "rather than ever" (first occurrence has "fatter than ever").
    # In txt: delete from second [Page 197] marker through second [Page 197] marker.

    DUP_START = (
        "\n\n[Page 197]\n\n"
        "Miguel Acatán? Any night after the twelve chimes of the Town Hall clock, if you stop "
        "and listen, you will hear someone sewing at a machine. It is Miguelita.\n\n"
        "[Page 196]\n\nXV\n\n"
        "Three weeks later Señor Nicho set off with the mail for the capital, purged of all "
        "earthly cares. He'd come so close to death, they had had to give him injections all "
        "through the night after his celebration, injections of camphor, they couldn't find the "
        "right antidote, camphorated oil, to be exact, and then they gave him a sound flogging "
        "which left him aching still. He had to set off with the clothes he was wearing, white "
        "no longer but rather the color of the dunghill because when, accompanied by a soldier, "
        "he went back home to collect his things, he found that thieves had taken everything he "
        'owned. So hardhearted was his woman, not even his going to prison had made her come back: '
        '"Tecuna, tecuna, tecuna!"\n\n'
        '"Tecuna!" With that word on his lips he set off from San Miguel Acatán, shaky, jittery, '
        "after stopping by at the church jacket they'd given him, the saliva which the postmaster, "
        'rather than ever, sprayed in his face as he gave him a final warning. "You\'ll have to '
        "look after yourself now there's no one else to do it for you, now the tecuna has left you "
        "short-eared. I'll send a soldier to look the rancho over from time to time. Did you lock "
        "it? Did you bar it? Did you sell the hogs, them two hogs you had, and the chickens? Take "
        'your dog with you, dog\'s better\'n a woman!"\n\n'
        "The postman didn't get a chance to explain to that tub of lard who was always spitting as "
        "he spoke that he was wearing all he now possessed, that while he was away, first sick, "
        "then arrested, they robbed him of everything, everything he had.\n\n"
        '"Weighs a bit," he muttered, as he went out of the post office, lifting the mailbags to '
        "test their weight, two large canvas sacks and a smaller briefcase with the official "
        "documents.\n\n"
        '"You\'re a sly one, you are," the postmaster snorted. "You get your smart remarks in. '
        "Of course it's heavy, but that can't be helped, that's how loads are, and you've only "
        "yourself to blame, when these stinking monkeys who call themselves citizen know it's "
        "Señor Nicho taking the mail, they clog up the letter box in the mailing office.\"\n\n"
        "San Miguel Acatán was left behind. He couldn't wait to be off, to get away, among the "
        "spires of eucalyptus trees which cut off lighting and thunderbolts, like the sword of "
        "the Archangel beneath whose golden shoe the devil's head lies crushed; the tufts of "
        "sweet-smelling pines, providers of good turpentine; and the green mass of other trees.\n\n"
        "San Miguel Acatán was lost in a gleam of porcelain beneath the morning sun: porcelain "
        "of its roofs, white porcelain of its houses, old porcelain of the church. And Señor "
        "Nicho was left alone on the shaded road with his dog, skinny, undernourished, meager, "
        "ears cropped because it got distemper as a pup and they'd had to bleed it, eyes golden "
        "brown, white-haired with black spots on its front paws.\n\n"
        '"What was it you said? She left you asleep? You didn\'t hear her go? You had no idea"'
        "—the dog wagged its tail—\"Ah, Jasmine . . .\"—referred to directly by name, the dog "
        "danced round him—\"Quiet, don't go running on ahead and give me the slip, we're in a "
        "hurry.\"\n\n"
        "It was a long day over roads swollen with rain till the earth looked like the peel of a "
        "water-sodden potato, and the rivulets played like live animals, everywhere, leaping, "
        "running, their activity in contrast with the two travelers who by late afternoon were "
        "worn out, ready to drop, in a village of twenty houses where the postman always stop "
        "the night. It was dark before they arrived, but there were still lights in the ranchos "
        "when\n\n[Page 197]"
    )
    DUP_REPLACE = "\n\n[Page 197]"

    txt = p.text
    if DUP_START in txt:
        txt = txt.replace(DUP_START, DUP_REPLACE, 1)
        p.ok += 1
        p.log.append("  OK  [TXT=Y JSN=-] DUP-XV delete-second-occurrence (~1.5 pages)")
    else:
        p.miss += 1
        p.log.append("  MISS         DUP-XV second occurrence not found verbatim — check manually")
    p.text = txt

    # JSON structural fix: remove pages containing the duplicate XV content.
    # Identify by finding two pages with "Three weeks later Señor Nicho" — delete the second group.
    trigger = "Three weeks later Señor Nicho set off with the mail for the capital"
    pages = data["pages"]
    hits = [i for i, pg in enumerate(pages)
            if any(trigger in blk.get("text","")
                   for blk in pg.get("content_blocks",[])
                   if blk.get("type") == "paragraph")]
    if len(hits) == 2:
        # Delete all pages from hits[1] back to (and including) any page immediately
        # before it that contains "Miguel Acatán? Any night"
        del_start = hits[1]
        # peek back for the "Miguel Acatán?" page
        for k in range(hits[1]-1, max(hits[0], hits[1]-3), -1):
            pg_text = " ".join(b.get("text","") for b in pages[k].get("content_blocks",[])
                               if b.get("type") == "paragraph")
            if "Miguel Acatán?" in pg_text and "Any night after" in pg_text:
                del_start = k
                break
        # Find where duplicate ends: first page AFTER hits[1] containing "they got in"
        del_end = len(pages)
        for k in range(hits[1], len(pages)):
            pg_text = " ".join(b.get("text","") for b in pages[k].get("content_blocks",[])
                               if b.get("type") == "paragraph")
            if "they got in" in pg_text.lower():
                del_end = k  # keep this page (it's the real continuation)
                break
        removed = del_end - del_start
        del pages[del_start:del_end]
        p.ok += 1
        p.log.append(f"  OK  [TXT=- JSN=Y] DUP-XV json: removed {removed} pages "
                     f"(indices {del_start}–{del_end-1})")
    elif len(hits) == 1:
        p.log.append("  OK  [TXT=- JSN=-] DUP-XV json: only 1 occurrence found, nothing to delete")
    else:
        p.miss += 1
        p.log.append(f"  MISS         DUP-XV json: found {len(hits)} trigger pages at {hits}")

    # ── write ──────────────────────────────────────────────────────────────────
    TXT.write_text(p.text, encoding="utf-8")
    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = (
        f"\nPass 18 complete — {p.ok} applied, {p.miss} missed\n"
        f"  txt → {TXT.name}\n"
        f"  json → {JSON_PATH.name}\n"
        f"  log → {LOG.name}\n"
    )
    full_log = summary + "\n".join(p.log) + "\n"
    LOG.write_text(full_log, encoding="utf-8")
    print(full_log)


if __name__ == "__main__":
    main()
