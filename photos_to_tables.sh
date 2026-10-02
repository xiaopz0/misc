#!/usr/bin/env bash
# photos_to_tables.sh - OCR every photo in a folder and extract the data table from each.
#
# For each photo it ALWAYS re-runs OCR (existing CSVs are overwritten) and writes:
#   <photo>.csv           word-level OCR (text, position, confidence)
#   <photo>_table.csv     everything on the image rebuilt as a grid
#   <photo>_clean.csv     just the data table: chrome removed, OCR digit errors fixed
# and finally:
#   all_tables_clean.csv  every _clean.csv stacked, with a leading "source" column
#
# Usage:
#   ./photos_to_tables.sh                     # photos in the current folder
#   ./photos_to_tables.sh ~/Pictures/tables   # another folder
#   ./photos_to_tables.sh . --min-fill 0.3    # extra flags go to clean_table.py
#
# Row selection is lenient by default (--all --min-fill 0.4): it keeps every row that
# fills 40% of the columns, so stray chrome lines are easier to delete by hand than
# missing data rows are to recover. Pass your own --min-fill or --rows to override.
#
# Needs photo_to_csv.py, words_to_table.py and clean_table.py in the same folder as this script.

set -euo pipefail

dir="${1:-.}"
shift || true
here="$(dirname "$0")"
ocr="$here/photo_to_csv.py"
tbl="$here/words_to_table.py"
cln="$here/clean_table.py"

for f in "$ocr" "$tbl" "$cln"; do
    [[ -f "$f" ]] || { echo "missing $f" >&2; exit 1; }
done

# Default clean_table.py flags; anything the user passes is appended and wins.
clean_flags=(--all --min-fill 0.4)

shopt -s nullglob nocaseglob
photos=("$dir"/*.heic "$dir"/*.heif "$dir"/*.jpg "$dir"/*.jpeg "$dir"/*.png "$dir"/*.tif "$dir"/*.tiff "$dir"/*.webp "$dir"/*.bmp)
shopt -u nocaseglob

(( ${#photos[@]} )) || { echo "no photos found in $dir" >&2; exit 1; }
echo "found ${#photos[@]} photos in $dir"

ok=0; fail=0
cleaned=()
for photo in "${photos[@]}"; do
    base="${photo%.*}"
    echo "--- $(basename "$photo")"
    if python "$ocr" "$photo" --psm 6 -o "$base.csv" \
       && python "$tbl" "$base.csv" -o "${base}_table.csv" \
       && python "$cln" "$base.csv" -o "${base}_clean.csv" "${clean_flags[@]}" "$@"; then
        ok=$((ok + 1))
        cleaned+=("${base}_clean.csv")
    else
        echo "FAILED: $photo" >&2
        fail=$((fail + 1))
    fi
done

# Stack every clean table into one file, tagging each row with the photo it came from.
combined="$dir/all_tables_clean.csv"
if (( ${#cleaned[@]} )); then
    python - "$combined" "${cleaned[@]}" <<'EOF'
import csv, sys
from pathlib import Path
out, files = sys.argv[1], sys.argv[2:]
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    header_done = False
    for path in files:
        src = Path(path).stem.removesuffix("_clean")
        with open(path, newline="", encoding="utf-8") as g:
            rows = list(csv.reader(g))
        if not rows:
            continue
        if not header_done:
            w.writerow(["source"] + rows[0]); header_done = True
        for r in rows[1:]:
            w.writerow([src] + r)
EOF
    echo "combined file: $combined"
fi

echo "done: $ok tables written, $fail failed"
