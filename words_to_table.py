#!/usr/bin/env python3
"""
words_to_table.py - Rebuild a table from a word-level OCR CSV made by photo_to_csv.py.

photo_to_csv.py records where each word sits on the photo (left/top/width/height).
This script uses those positions to put the words back into rows and columns, so
a photo of a table becomes a proper grid CSV you can open in Excel.

How it works:
  1. Words whose vertical spans overlap are put in the same row.
  2. Column boundaries are found where no word crosses a vertical strip of the
     image (the white gutters between columns).
  3. Each word is dropped into its row/column cell; words sharing a cell are
     joined with a space.

Usage:
    python words_to_table.py IMG_5794.csv                 # writes IMG_5794_table.csv
    python words_to_table.py IMG_5794.csv -o table.csv
    python words_to_table.py IMG_5794.csv --show          # also print the grid
    python words_to_table.py IMG_5794.csv --min-gap 40    # wider gutters only (fewer columns)
    python words_to_table.py IMG_5794.csv --min-gap 10    # narrower gutters (more columns)
    python words_to_table.py IMG_5794.csv --min-conf 50   # ignore shaky words first
"""

import argparse
import csv
import sys
from pathlib import Path


def load_words(path, min_conf):
    words = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        needed = {"text", "left", "top", "width", "height"}
        if not needed.issubset(reader.fieldnames or []):
            sys.exit(f"{path} is not a word-level CSV from photo_to_csv.py "
                     f"(needs columns {sorted(needed)}). Re-run photo_to_csv.py without --lines.")
        for r in reader:
            if float(r.get("confidence", 100)) < min_conf:
                continue
            left, top = int(r["left"]), int(r["top"])
            w, h = int(r["width"]), int(r["height"])
            words.append({
                "text": r["text"], "left": left, "top": top,
                "right": left + w, "bottom": top + h,
                "cx": left + w / 2, "cy": top + h / 2,
                "h": h,
            })
    return words


def group_rows(words, overlap=0.5):
    """Sort by vertical centre; start a new row when a word doesn't overlap the current row band."""
    rows = []
    for w in sorted(words, key=lambda w: w["cy"]):
        if rows:
            row = rows[-1]
            band_top = min(x["top"] for x in row)
            band_bot = max(x["bottom"] for x in row)
            shared = min(band_bot, w["bottom"]) - max(band_top, w["top"])
            if shared >= overlap * min(w["h"], band_bot - band_top):
                row.append(w)
                continue
        rows.append([w])
    for row in rows:
        row.sort(key=lambda w: w["left"])
    return rows


def find_column_edges(words, min_gap):
    """Return x positions of gutters: vertical strips at least min_gap wide that no word crosses."""
    spans = sorted((w["left"], w["right"]) for w in words)
    edges = []
    cur_l, cur_r = spans[0]
    for l, r in spans[1:]:
        if l - cur_r >= min_gap:          # a gutter between cur_r and l
            edges.append((cur_r + l) / 2)
            cur_l, cur_r = l, r
        else:
            cur_r = max(cur_r, r)
    return edges


def column_of(cx, edges):
    for i, e in enumerate(edges):
        if cx < e:
            return i
    return len(edges)


def build_grid(rows, edges):
    ncols = len(edges) + 1
    grid = []
    for row in rows:
        cells = [[] for _ in range(ncols)]
        for w in row:
            cells[column_of(w["cx"], edges)].append(w["text"])
        grid.append([" ".join(c) for c in cells])
    return grid


def print_grid(grid):
    widths = [max(len(r[c]) for r in grid) for c in range(len(grid[0]))]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(sep)
    for r in grid:
        print("| " + " | ".join(cell.ljust(w) for cell, w in zip(r, widths)) + " |")
    print(sep)


def main():
    ap = argparse.ArgumentParser(description="Turn a word-level OCR CSV into a table grid CSV.")
    ap.add_argument("csv", help="word CSV produced by photo_to_csv.py")
    ap.add_argument("-o", "--output", help="output CSV (default: <name>_table.csv)")
    ap.add_argument("--min-gap", type=float, default=None,
                    help="min horizontal white space (px) that counts as a column gutter. "
                         "Default: 1.2 x median word height")
    ap.add_argument("--min-conf", type=float, default=0, help="drop words below this OCR confidence")
    ap.add_argument("--show", action="store_true", help="print the grid to the terminal")
    args = ap.parse_args()

    words = load_words(args.csv, args.min_conf)
    if not words:
        sys.exit("no words found")

    heights = sorted(w["h"] for w in words)
    median_h = heights[len(heights) // 2]
    min_gap = args.min_gap if args.min_gap is not None else 1.2 * median_h

    rows = group_rows(words)
    edges = find_column_edges(words, min_gap)
    grid = build_grid(rows, edges)

    output = Path(args.output) if args.output else Path(args.csv).with_name(Path(args.csv).stem + "_table.csv")
    with open(output, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(grid)

    print(f"{len(rows)} rows x {len(edges) + 1} columns (gutter >= {min_gap:.0f}px) -> {output}",
          file=sys.stderr)
    if args.show:
        print_grid(grid)


if __name__ == "__main__":
    main()
