#!/usr/bin/env bash
# photos_to_tables.sh - Re-OCR every photo in a folder in table mode and rebuild each as a grid CSV.
#
# For each photo it ALWAYS re-runs OCR (existing CSVs are overwritten) and writes:
#   <photo>.csv          word-level OCR (text, position, confidence)
#   <photo>_table.csv    the table rebuilt as a grid, one cell per column
#
# Usage:
#   ./photos_to_tables.sh                     # photos in the current folder
#   ./photos_to_tables.sh ~/Pictures/tables   # another folder
#   ./photos_to_tables.sh . --min-gap 40      # extra flags go to words_to_table.py
#
# Needs photo_to_csv.py and words_to_table.py in the same folder as this script.

set -euo pipefail

dir="${1:-.}"
shift || true
here="$(dirname "$0")"
ocr="$here/photo_to_csv.py"
tbl="$here/words_to_table.py"

for f in "$ocr" "$tbl"; do
    [[ -f "$f" ]] || { echo "missing $f" >&2; exit 1; }
done

shopt -s nullglob nocaseglob
photos=("$dir"/*.heic "$dir"/*.heif "$dir"/*.jpg "$dir"/*.jpeg "$dir"/*.png "$dir"/*.tif "$dir"/*.tiff "$dir"/*.webp "$dir"/*.bmp)
shopt -u nocaseglob

(( ${#photos[@]} )) || { echo "no photos found in $dir" >&2; exit 1; }
echo "found ${#photos[@]} photos in $dir"

ok=0; fail=0
for photo in "${photos[@]}"; do
    base="${photo%.*}"
    echo "--- $(basename "$photo")"
    if python "$ocr" "$photo" --psm 6 -o "$base.csv" \
       && python "$tbl" "$base.csv" -o "${base}_table.csv" "$@"; then
        ok=$((ok + 1))
    else
        echo "FAILED: $photo" >&2
        fail=$((fail + 1))
    fi
done

echo "done: $ok tables written, $fail failed"
