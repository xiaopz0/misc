#!/usr/bin/env python3
"""
clean_table.py - Extract just the data table from an OCR'd screenshot/photo and repair OCR errors.

Input is the word-level CSV from photo_to_csv.py (<photo>.csv). The script:

  1. Groups words into rows by their position on the image.
  2. Finds the data block: the longest run of rows with a similar number of words.
     Window titles, menus, shell prompts and footers are dropped. The row just
     above the block is kept as the header when it fits the columns.
  3. Works out column boundaries from the data rows ONLY, so a long title line
     spanning the whole image cannot hide the gaps between columns.
  4. Re-joins timestamps that landed in a date cell and a time cell.
  5. Fixes OCR character confusions in cells that are mostly digits:
     @ © O o Q D -> 0,  l I | ! -> 1,  S -> 5,  B -> 8,  Z -> 2,  ':' or ',' as decimal point.

Usage:
    python clean_table.py IMG_5794.csv                 # writes IMG_5794_clean.csv
    python clean_table.py IMG_5794.csv --show          # also print the result
    python clean_table.py IMG_5794.csv --rows 4:20     # force which rows (0-based, end excl.)
    python clean_table.py IMG_5794.csv --min-gap 30    # column gutter width in px (see words_to_table.py)
    python clean_table.py IMG_5794.csv --no-header     # row above the data is not a header
    python clean_table.py IMG_5794.csv --no-fix        # keep raw OCR text

Needs words_to_table.py in the same folder.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from words_to_table import load_words, group_rows, find_column_edges, build_grid  # noqa: E402

DATE_RE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$|^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}$")
TIME_RE = re.compile(r"^\d{1,2}[:.]\d{2}([:.]\d{2})?(\.\d+)?$")

LOOKALIKES = "@©OoQD°l|I!iSsBZzG"
DIGIT_FIX = str.maketrans({
    "@": "0", "©": "0", "O": "0", "o": "0", "Q": "0", "D": "0", "°": "0",
    "l": "1", "I": "1", "|": "1", "!": "1", "i": "1",
    "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6",
})
NUMERIC_CHARS = set("0123456789.,:-+%$ " + LOOKALIKES)


def fix_token(tok):
    """Repair digit confusions in one token if it is mostly numeric."""
    if not tok or not all(c in NUMERIC_CHARS for c in tok):
        return tok                        # a real word, leave it alone
    if not any(c.isdigit() for c in tok):
        return tok                        # e.g. a bare "-" or "O" with no digits around
    t = tok.translate(DIGIT_FIX)
    if DATE_RE.match(t) or TIME_RE.match(t):
        return t
    t = re.sub(r"^([-+]?\d+)[:,](\d{2})$", r"\1.\2", t)     # 12:50 / 12,50 -> 12.50
    t = re.sub(r"^([-+]?\d+)\.$", r"\1.0", t)               # 12.  -> 12.0
    t = re.sub(r"^([-+]?)\.(\d+)$", r"\g<1>0.\2", t)        # .5   -> 0.5
    return t


def fix_cell(text):
    return " ".join(fix_token(tok) for tok in text.split())


def find_data_block(rows, tolerance=1):
    """Longest run of consecutive rows whose word count stays within `tolerance` of the first."""
    counts = [len(r) for r in rows]
    best = (0, 0)
    i = 0
    while i < len(rows):
        if counts[i] < 2:
            i += 1
            continue
        j, target = i, counts[i]
        while j < len(rows) and counts[j] >= 2 and abs(counts[j] - target) <= tolerance:
            j += 1
        if j - i > best[1] - best[0]:
            best = (i, j)
        i = j
    # Trim leading/trailing rows that do not match the block's dominant word count
    # (a header or footer line that happened to be within tolerance).
    start, end = best
    if end - start >= 3:
        block = counts[start:end]
        mode = max(set(block), key=block.count)
        while end - start > 2 and counts[start] != mode:
            start += 1
        while end - start > 2 and counts[end - 1] != mode:
            end -= 1
    return start, end


def fix_decimal_colons(grid):
    """In a column that is mostly decimals, '12:50' is 12.50, not a time."""
    if not grid:
        return grid
    for c in range(len(grid[0])):
        col = [r[c] for r in grid if r[c]]
        decimals = sum(bool(re.fullmatch(r"[-+]?\d+\.\d+", v)) for v in col)
        if col and decimals >= 0.5 * len(col):
            for r in grid:
                r[c] = re.sub(r"^([-+]?\d+):(\d{2})$", r"\1.\2", r[c])
    return grid


def header_fits(header_row, edges, ncols):
    """A header row is usable if its words each sit in a column and no two share one."""
    from words_to_table import column_of
    cols = [column_of(w["cx"], edges) for w in header_row]
    return len(set(cols)) >= max(2, ncols - 1)


def merge_split_timestamps(grid, header):
    if not grid:
        return grid, header
    c = 0
    while c < len(grid[0]) - 1:
        pairs = [(r[c], r[c + 1]) for r in grid if r[c]]
        if pairs and sum(bool(DATE_RE.match(a) and TIME_RE.match(b)) for a, b in pairs) >= 0.6 * len(pairs):
            for r in grid:
                r[c] = (r[c] + " " + r[c + 1]).strip()
                del r[c + 1]
            if header:
                a, b = header[c], header[c + 1]
                header[c] = a if not b or b.lower() in a.lower() else (a + " " + b).strip()
                del header[c + 1]
        else:
            c += 1
    return grid, header


def drop_empty_columns(grid, header):
    keep = [c for c in range(len(grid[0])) if any(r[c] for r in grid)]
    grid = [[r[c] for c in keep] for r in grid]
    if header:
        header = [header[c] for c in keep]
    return grid, header


def main():
    ap = argparse.ArgumentParser(description="Extract the clean data table from an OCR word CSV.")
    ap.add_argument("csv", help="word CSV from photo_to_csv.py (not the _table.csv)")
    ap.add_argument("-o", "--output", help="output CSV (default: <name>_clean.csv)")
    ap.add_argument("--rows", help="row range to keep, e.g. 4:20 (0-based, end exclusive); skips auto-detect")
    ap.add_argument("--min-gap", type=float, help="column gutter width in px (default 1.2 x median word height)")
    ap.add_argument("--min-conf", type=float, default=0, help="drop words below this OCR confidence")
    ap.add_argument("--no-header", action="store_true")
    ap.add_argument("--no-fix", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    words = load_words(args.csv, args.min_conf)
    if not words:
        sys.exit("no words found")
    rows = group_rows(words)

    if args.rows:
        a, b = args.rows.split(":")
        start, end = int(a or 0), int(b or len(rows))
    else:
        start, end = find_data_block(rows)
        if end - start < 2:
            sys.exit("could not find a data block; use --rows START:END")
    data_rows = rows[start:end]

    data_words = [w for r in data_rows for w in r]
    heights = sorted(w["h"] for w in data_words)
    min_gap = args.min_gap if args.min_gap is not None else 1.2 * heights[len(heights) // 2]
    edges = find_column_edges(data_words, min_gap)

    header = None
    if not args.no_header and start > 0 and header_fits(rows[start - 1], edges, len(edges) + 1):
        header = build_grid([rows[start - 1]], edges)[0]
    grid = build_grid(data_rows, edges)

    grid, header = drop_empty_columns(grid, header)
    if not args.no_fix:
        grid = [[fix_cell(c) for c in r] for r in grid]
        grid = fix_decimal_colons(grid)
    grid, header = merge_split_timestamps(grid, header)

    out_rows = ([header] if header else []) + grid
    output = Path(args.output) if args.output else Path(args.csv).with_name(Path(args.csv).stem + "_clean.csv")
    with open(output, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out_rows)

    print(f"kept rows {start}:{end} of {len(rows)} ({'header + ' if header else ''}{len(grid)} data rows, "
          f"{len(grid[0])} columns, gutter >= {min_gap:.0f}px) -> {output}", file=sys.stderr)
    if args.show:
        widths = [max(len(r[c]) for r in out_rows) for c in range(len(out_rows[0]))]
        for r in out_rows:
            print(" | ".join(c.ljust(w) for c, w in zip(r, widths)))


if __name__ == "__main__":
    main()
