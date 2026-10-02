#!/usr/bin/env python3
"""
photo_to_csv.py - Extract text (words and numbers) from a photo and save it to a CSV.

Uses Tesseract OCR via pytesseract. Each recognised word becomes one CSV row with
its position on the image, OCR confidence, and whether it looks like a number.

Requirements:
    pip install pytesseract pillow
    pip install pillow-heif        # only needed for iPhone .HEIC photos
    Tesseract engine:  apt install tesseract-ocr   (Debian/Ubuntu)
                       brew install tesseract      (macOS)
                       https://github.com/UB-Mannheim/tesseract/wiki (Windows)

Usage:
    python photo_to_csv.py photo.jpg                     # writes photo.csv
    python photo_to_csv.py photo.jpg -o out.csv          # choose output file
    python photo_to_csv.py *.jpg -o all.csv              # several photos, one CSV
    python photo_to_csv.py photo.jpg --lines             # one row per line instead of per word
    python photo_to_csv.py photo.jpg --min-conf 60       # drop low-confidence words
    python photo_to_csv.py photo.jpg --lang eng+fra      # other Tesseract languages
    python photo_to_csv.py table.jpg --psm 6             # better for tables/receipts

To rebuild a photographed table as a grid, feed the output to words_to_table.py.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
    import pytesseract
except ImportError:
    sys.exit("Missing dependencies. Run:  pip install pytesseract pillow")

# Optional: iPhone HEIC/HEIF photos.  pip install pillow-heif
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_OK = True
except ImportError:
    HEIF_OK = False

# Matches integers, decimals, thousands separators, percentages, currency.
NUMBER_RE = re.compile(r"^[\$€£]?[-+]?\d[\d,]*(\.\d+)?%?$")

WORD_FIELDS = [
    "source", "page", "block", "paragraph", "line", "word_num",
    "text", "is_number", "numeric_value", "confidence",
    "left", "top", "width", "height",
]
LINE_FIELDS = ["source", "page", "block", "paragraph", "line", "text", "avg_confidence"]


def parse_number(text):
    """Return a float if text looks numeric, else None."""
    if not NUMBER_RE.match(text):
        return None
    cleaned = text.replace(",", "").replace("$", "").replace("€", "").replace("£", "").rstrip("%")
    try:
        return float(cleaned)
    except ValueError:
        return None


def preprocess(image, scale=2):
    """Light cleanup that usually helps OCR on photos: grayscale, autocontrast, upscale."""
    img = ImageOps.exif_transpose(image)  # respect phone-camera rotation
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    return img


def ocr_words(path, lang="eng", min_conf=0, no_preprocess=False, psm=3):
    """Run OCR and return a list of word-level dicts."""
    if Path(path).suffix.lower() in (".heic", ".heif") and not HEIF_OK:
        sys.exit(f"{path} is a HEIC photo. Install the decoder with the same Python "
                 f"you run this script with:\n    {sys.executable} -m pip install pillow-heif")
    with Image.open(path) as im:
        img = im.copy() if no_preprocess else preprocess(im)

    data = pytesseract.image_to_data(img, lang=lang, config=f"--psm {psm}",
                                     output_type=pytesseract.Output.DICT)
    rows = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = float(data["conf"][i])
        if not text or conf < 0 or conf < min_conf:
            continue
        value = parse_number(text)
        rows.append({
            "source": Path(path).name,
            "page": data["page_num"][i],
            "block": data["block_num"][i],
            "paragraph": data["par_num"][i],
            "line": data["line_num"][i],
            "word_num": data["word_num"][i],
            "text": text,
            "is_number": value is not None,
            "numeric_value": "" if value is None else value,
            "confidence": round(conf, 1),
            "left": data["left"][i],
            "top": data["top"][i],
            "width": data["width"][i],
            "height": data["height"][i],
        })
    return rows


def group_lines(word_rows):
    """Collapse word rows into one row per line of text."""
    lines = {}
    for w in word_rows:
        key = (w["source"], w["page"], w["block"], w["paragraph"], w["line"])
        lines.setdefault(key, []).append(w)
    out = []
    for key, words in lines.items():
        words.sort(key=lambda w: w["word_num"])
        out.append({
            "source": key[0], "page": key[1], "block": key[2],
            "paragraph": key[3], "line": key[4],
            "text": " ".join(w["text"] for w in words),
            "avg_confidence": round(sum(w["confidence"] for w in words) / len(words), 1),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="OCR a photo and save the words/numbers to CSV.")
    ap.add_argument("images", nargs="+", help="photo file(s): jpg, png, tiff, bmp, webp ...")
    ap.add_argument("-o", "--output", help="CSV path (default: <first image name>.csv)")
    ap.add_argument("--lang", default="eng", help="Tesseract language(s), e.g. eng or eng+deu")
    ap.add_argument("--min-conf", type=float, default=0, help="drop words below this confidence (0-100)")
    ap.add_argument("--lines", action="store_true", help="one row per text line instead of per word")
    ap.add_argument("--no-preprocess", action="store_true", help="feed the raw image to Tesseract")
    ap.add_argument("--psm", type=int, default=3,
                    help="Tesseract page segmentation mode. 3 = auto (default), "
                         "6 = single uniform block, best for tables and receipts")
    args = ap.parse_args()

    output = Path(args.output) if args.output else Path(args.images[0]).with_suffix(".csv")

    all_rows = []
    for img_path in args.images:
        if not Path(img_path).is_file():
            print(f"skipping {img_path}: not found", file=sys.stderr)
            continue
        try:
            rows = ocr_words(img_path, args.lang, args.min_conf, args.no_preprocess, args.psm)
        except pytesseract.TesseractNotFoundError:
            sys.exit("Tesseract engine not found. Install it (see header of this script) "
                     "or set pytesseract.pytesseract.tesseract_cmd to its path.")
        print(f"{img_path}: {len(rows)} words", file=sys.stderr)
        all_rows.extend(rows)

    if args.lines:
        all_rows = group_lines(all_rows)
        fields = LINE_FIELDS
    else:
        fields = WORD_FIELDS

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"wrote {len(all_rows)} rows to {output}", file=sys.stderr)


if __name__ == "__main__":
    main()
