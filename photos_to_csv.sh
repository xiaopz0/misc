#!/usr/bin/env bash
# photos_to_csv.sh - OCR every photo in a folder into CSV files.
#
# Usage:
#   ./photos_to_csv.sh                 # photos in the current folder
#   ./photos_to_csv.sh ~/Pictures/scan # photos in another folder
#   ./photos_to_csv.sh . --lines       # extra flags are passed to photo_to_csv.py
#
# Output:
#   one <photo>.csv next to each photo, plus all_photos.csv combining them all.
#   Photos that already have a .csv are skipped (delete the .csv to redo one).

set -euo pipefail

dir="${1:-.}"
shift || true                      # remaining args go to photo_to_csv.py
script="$(dirname "$0")/photo_to_csv.py"

if [[ ! -f "$script" ]]; then
    echo "photo_to_csv.py must sit in the same folder as this script" >&2
    exit 1
fi

shopt -s nullglob nocaseglob
photos=("$dir"/*.heic "$dir"/*.heif "$dir"/*.jpg "$dir"/*.jpeg "$dir"/*.png "$dir"/*.tif "$dir"/*.tiff "$dir"/*.webp "$dir"/*.bmp)
shopt -u nocaseglob

if (( ${#photos[@]} == 0 )); then
    echo "no photos found in $dir" >&2
    exit 1
fi

echo "found ${#photos[@]} photos in $dir"

done_n=0; skip_n=0; fail_n=0
for photo in "${photos[@]}"; do
    csv="${photo%.*}.csv"
    if [[ -f "$csv" ]]; then
        skip_n=$((skip_n + 1))
        continue
    fi
    if python "$script" "$photo" -o "$csv" "$@"; then
        done_n=$((done_n + 1))
    else
        echo "FAILED: $photo" >&2
        fail_n=$((fail_n + 1))
    fi
done

# Combine every per-photo CSV into one file (header written once).
combined="$dir/all_photos.csv"
first=1
for photo in "${photos[@]}"; do
    csv="${photo%.*}.csv"
    [[ -f "$csv" ]] || continue
    if (( first )); then
        cat "$csv" > "$combined"; first=0
    else
        tail -n +2 "$csv" >> "$combined"
    fi
done

echo "done: $done_n converted, $skip_n already had a csv, $fail_n failed"
echo "combined file: $combined"
