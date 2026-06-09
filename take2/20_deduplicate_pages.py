"""
Men of Maize — Stage 20: Cross-page deduplication.

Two deduplication passes:

  Pass 1 — Boundary overlap (simple):
    The tail of page N overlaps with the head of page N+1 at position ≈0.
    Solution: trim the matching words from the start of page N+1.

  Pass 2 — Interior overlap (complex):
    Content from somewhere in page N reappears somewhere in page N+1.
    Solution: find matching paragraph blocks in page N+1 and remove them.

Usage:
    python3 20_deduplicate_pages.py [--dry-run]
"""

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
JSON_PATH  = OUTPUT_DIR / "men_of_maize_structured.json"
BACKUP     = OUTPUT_DIR / "men_of_maize_structured_PREDEDUP.json"

DRY_RUN = "--dry-run" in sys.argv

# Pass 1 thresholds
P1_MIN_WORDS    = 5
P1_MAX_HEAD_POS = 80    # match can start up to 80 words into page B
P1_MIN_RATIO    = 0.30

# Pass 2 thresholds (block-level)
P2_MIN_BLOCK_WORDS = 15   # ignore short blocks
P2_MIN_SIM         = 0.72  # block must be 72% similar to a block in a recent page

# How many preceding pages to check for block-level duplicates
P2_LOOKBACK = 3


def tokenise(text: str) -> list[str]:
    return re.findall(r"[a-zA-ZÀ-ÿ''-]+", text.lower())


def blocks_text(blocks: list) -> str:
    return " ".join(b.get("text", "") for b in blocks if b.get("type") == "paragraph")


def block_sim(a: str, b: str) -> float:
    wa, wb = set(tokenise(a)), set(tokenise(b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


# ── PASS 1 ────────────────────────────────────────────────────────────────────

def find_boundary_overlap(tail_words: list, head_words: list) -> tuple[int, int]:
    """Return (head_start, match_len) for boundary-style duplicates."""
    tail_sample = tail_words[-400:]   # look at more of the tail
    head_sample = head_words[:400:]

    sm = SequenceMatcher(None, tail_sample, head_sample, autojunk=False)
    best = (0, 0, 0)
    for a, b, size in sm.get_matching_blocks():
        if size < P1_MIN_WORDS:
            continue
        if b > P1_MAX_HEAD_POS:
            continue
        if a + size < len(tail_sample) - 120:   # match must reach within 120 of tail end
            continue
        if size > best[2]:
            best = (a, b, size)
    return best[1], best[2]   # head_start, match_len


def trim_from_word(blocks: list, word_offset: int, n_words: int) -> list:
    """Remove n_words starting at word_offset from the block list."""
    result  = []
    current = 0
    end_pos = word_offset + n_words

    for blk in blocks:
        if blk.get("type") != "paragraph":
            result.append(blk)
            continue
        words = blk["text"].split()
        blk_start = current
        blk_end   = current + len(words)
        current   = blk_end

        if blk_end <= word_offset or blk_start >= end_pos:
            # Outside the removal zone — keep entirely
            result.append(blk)
        elif blk_start < word_offset and blk_end > end_pos:
            # Removal zone is interior to this block
            kept = words[:word_offset - blk_start] + words[end_pos - blk_start:]
            if kept:
                result.append({**blk, "text": " ".join(kept)})
        elif blk_start < word_offset:
            # Block spans start of removal zone — keep left part
            kept = words[:word_offset - blk_start]
            if kept:
                result.append({**blk, "text": " ".join(kept)})
        elif blk_end > end_pos:
            # Block spans end of removal zone — keep right part
            kept = words[end_pos - blk_start:]
            if kept:
                result.append({**blk, "text": " ".join(kept)})
        # else: entirely within removal zone — drop

    return result


# ── PASS 2 ────────────────────────────────────────────────────────────────────

def find_duplicate_blocks(prior_blocks_list: list[list], pg_b_blocks: list) -> list[int]:
    """Return indices (in pg_b_blocks) of paragraph blocks that duplicate content from any prior page."""
    prior_texts = [
        b.get("text", "")
        for prior in prior_blocks_list
        for b in prior
        if b.get("type") == "paragraph"
    ]
    dup_indices = []

    for j, blk in enumerate(pg_b_blocks):
        if blk.get("type") != "paragraph":
            continue
        btext = blk.get("text", "")
        if len(tokenise(btext)) < P2_MIN_BLOCK_WORDS:
            continue
        for atext in prior_texts:
            if block_sim(atext, btext) >= P2_MIN_SIM:
                dup_indices.append(j)
                break

    return dup_indices


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    data  = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    pages = data["pages"]

    log_lines = []
    p1_count  = 0
    p2_count  = 0

    for i in range(len(pages) - 1):
        pg_a = pages[i]
        pg_b = pages[i + 1]

        tail_w = tokenise(blocks_text(pg_a["content_blocks"]))
        head_w = tokenise(blocks_text(pg_b["content_blocks"]))

        if not tail_w or not head_w:
            continue

        # ── Pass 1: boundary overlap ──────────────────────────────────────────
        head_start, match_len = find_boundary_overlap(tail_w, head_w)

        if match_len >= P1_MIN_WORDS:
            ratio = match_len / min(len(tail_w[-200:]), len(head_w[:200]))
            if ratio >= P1_MIN_RATIO:
                excerpt = " ".join(head_w[head_start:head_start+6])
                log_lines.append(
                    f"[P1] p{pg_a['page_number']}→p{pg_b['page_number']}: "
                    f"remove {match_len} words at head+{head_start}  '{excerpt}'"
                )
                if not DRY_RUN:
                    pg_b["content_blocks"] = trim_from_word(
                        pg_b["content_blocks"], head_start, match_len
                    )
                p1_count += 1
                continue   # skip pass 2 for this pair

        # ── Pass 2: interior block-level duplicates ───────────────────────────
        prior = [pages[max(0, i - k)]["content_blocks"] for k in range(1, P2_LOOKBACK + 1)]
        dup_idx = find_duplicate_blocks(prior, pg_b["content_blocks"])
        if dup_idx:
            excerpts = [pg_b["content_blocks"][j].get("text","")[:40] for j in dup_idx[:2]]
            log_lines.append(
                f"[P2] p{pg_a['page_number']}→p{pg_b['page_number']}: "
                f"remove {len(dup_idx)} block(s)  '{excerpts[0]}…'"
            )
            if not DRY_RUN:
                keep = [blk for j, blk in enumerate(pg_b["content_blocks"]) if j not in set(dup_idx)]
                pg_b["content_blocks"] = keep
            p2_count += 1

    tag = "(DRY RUN) " if DRY_RUN else ""
    print(f"Deduplication {tag}— {len(log_lines)} overlaps found")
    print(f"  Pass 1 (boundary): {p1_count}")
    print(f"  Pass 2 (block):    {p2_count}")
    print()
    for line in log_lines:
        print(f"  {line}")

    if not DRY_RUN and log_lines:
        if not BACKUP.exists():
            import shutil
            shutil.copy(JSON_PATH, BACKUP)
            print(f"\nBackup: {BACKUP.name}")
        JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved:  {JSON_PATH.name}")
    elif DRY_RUN:
        print("\n(No files modified — re-run without --dry-run to apply)")


if __name__ == "__main__":
    main()
