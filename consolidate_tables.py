#!/usr/bin/env python3
"""
consolidate_tables.py - Merge every cleaned table in a folder into one CSV.

Reads all *_clean.csv files (made by clean_table.py / photos_to_tables.sh) in a folder
and writes a single table:

  * Columns are matched by header name, so tables whose columns are in a different
    order, or that have an extra column, still line up. Header names are compared
    case-insensitively, ignoring spaces and punctuation.
  * A file whose first row is data rather than a header (no header was detected)
    is matched to the most common header with the same number of columns.
  * Rows that appear in more than one photo (overlapping screenshots) are kept once.
  * A "source" column says which photo each row came from (drop it with --no-source).

Usage:
    python consolidate_tables.py datatable                     # writes datatable/consolidated.csv
    python consolidate_tables.py datatable -o all.csv
    python consolidate_tables.py datatable --keep-duplicates
    python consolidate_tables.py datatable --sort timestamp    # sort by a column
    python consolidate_tables.py datatable --pattern "*.csv"   # use other files
"""

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path


def norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_header(row):
    """A header row has text but no cell that is mostly digits."""
    cells = [c for c in row if c.strip()]
    if not cells:
        return False
    def numeric(c):
        digits = sum(ch.isdigit() for ch in c)
        return digits >= max(1, len(c.replace(" ", "")) // 2)
    return not any(numeric(c) for c in cells)


def read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
    if not rows:
        return None, []
    if is_header(rows[0]):
        return [c.strip() for c in rows[0]], rows[1:]
    return None, rows


def sort_key(value):
    v = value.replace(",", "")
    try:
        return (0, float(v), "")
    except ValueError:
        return (1, 0.0, value)


def main():
    ap = argparse.ArgumentParser(description="Merge many cleaned table CSVs into one.")
    ap.add_argument("folder", help="folder holding the *_clean.csv files")
    ap.add_argument("-o", "--output", help="output CSV (default: <folder>/consolidated.csv)")
    ap.add_argument("--pattern", default="*_clean.csv", help="which files to merge (default *_clean.csv)")
    ap.add_argument("--keep-duplicates", action="store_true", help="keep rows repeated across photos")
    ap.add_argument("--no-source", action="store_true", help="leave out the source column")
    ap.add_argument("--sort", help="sort the result by this column name")
    args = ap.parse_args()

    folder = Path(args.folder)
    output = Path(args.output) if args.output else folder / "consolidated.csv"
    files = sorted(p for p in folder.glob(args.pattern) if p.resolve() != output.resolve())
    if not files:
        sys.exit(f"no files matching {args.pattern} in {folder}")

    tables = []
    for p in files:
        header, rows = read(p)
        tables.append((p, header, rows))

    # Most common header per column count, used for files where no header was found.
    by_width = {}
    for width, header in Counter((len(h), tuple(h)) for _, h, _ in tables if h).most_common():
        by_width.setdefault(width[0], list(width[1]))

    # Build the combined column list in first-seen order.
    columns, display = [], {}
    def add_col(name):
        key = norm(name) or name
        if key not in display:
            display[key] = name
            columns.append(key)
        return key

    merged, seen = [], set()
    dupes = 0
    for p, header, rows in tables:
        if header is None:
            width = max(len(r) for r in rows) if rows else 0
            header = by_width.get(width) or [f"col_{i + 1}" for i in range(width)]
            note = "no header, matched by column count"
        else:
            note = ""
        keys = [add_col(h if h else f"col_{i + 1}") for i, h in enumerate(header)]
        source = p.stem.removesuffix("_clean")
        kept = 0
        for r in rows:
            record = {k: (r[i].strip() if i < len(r) else "") for i, k in enumerate(keys)}
            fingerprint = tuple(sorted((k, v) for k, v in record.items() if v))
            if not args.keep_duplicates:
                if fingerprint in seen:
                    dupes += 1
                    continue
                seen.add(fingerprint)
            record["__source"] = source
            merged.append(record)
            kept += 1
        print(f"{p.name}: {kept} rows {('(' + note + ')') if note else ''}", file=sys.stderr)

    if args.sort:
        key = norm(args.sort)
        if key not in display:
            sys.exit(f"--sort column '{args.sort}' not found; columns are: {', '.join(display.values())}")
        merged.sort(key=lambda r: sort_key(r.get(key, "")))

    with open(output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        head = [display[k] for k in columns]
        w.writerow(head if args.no_source else ["source"] + head)
        for r in merged:
            vals = [r.get(k, "") for k in columns]
            w.writerow(vals if args.no_source else [r["__source"]] + vals)

    print(f"merged {len(files)} files: {len(merged)} rows, {len(columns)} columns, "
          f"{dupes} duplicate rows removed -> {output}", file=sys.stderr)


if __name__ == "__main__":
    main()
