"""
pdf_layout_classifier_and_sampler.py
=======================

Script that traverses arXiv year-month PDF folders (e.g. "9201", "9202", ..., "1512") and draws a stratified random sample of papers for each year in the range 1992-2015.

For every year it selects:
    - 50 single-column papers
    - 50 double-column papers
    - 30 ETDs (long, single-column theses/dissertations)
    - 30 scanned / image-based papers

Classification heuristics (first page of each PDF):
    - Scanned:        very little extractable text + a large embedded image
                       covering most of the page (text-coverage heuristic).
    - Layout:         single vs. two columns, inferred from the horizontal
                       gaps between text-block x-coordinates (page-geometry
                       heuristic).
    - ETD:            single-column layout with a high page count.
    - Single column:  single-column layout with a modest page count.
    - Double column:  two-column layout with a modest page count.

A PDF is assigned to the FIRST matching category in this priority order:
    scanned > etd > single_column > double_column
Anything that fits none of these buckets, or that fails to open, is skipped (and logged).

Sampling is randomized (with a fixed seed, for reproducibility) by shuffling the pooled list of PDFs for each year (across all 12 of its month folders) before classifying, then filling each category's quota in that randomized order and stopping early once every quota for the year is met.

Assuming the input directory contains the year-month folders for each year (e.g. "arxiv-pdf/9201", "arxiv-pdf/9202", ..., "arxiv-pdf/1512"), each folder holding PDFs directly.

Requirements
------------
    pip install pymupdf
"""

import os
import csv
import shutil
import random

try:
    import fitz  # PyMuPDF
except ImportError as exc:
    raise ImportError(
        "This script requires PyMuPDF. Install it with: pip install pymupdf"
    ) from exc


# ---------
# CONFIG
# ---------

# Assuming the input directory contains the year-month folders for each
# year (e.g. "9201", "9202", ..., "1512"), each containing PDFs directly.
ROOT_FOLDER = "arxiv-pdf"

# Where selected files / lists / the classification log get written.
OUTPUT_DIR = "arxiv-sample-set-b"

START_YEAR = 1992
END_YEAR = 2015  # inclusive

REQUIRED_SC_PAPER_COUNT = 50       # single-column
REQUIRED_DC_PAPER_COUNT = 50       # double-column
REQUIRED_ETD_PAPER_COUNT = 30      # ETDs
REQUIRED_SCANNED_PAPER_COUNT = 30  # scanned / image-based

RANDOM_SEED = 42

# If True, copy each selected PDF into a per-category subfolder under
# OUTPUT_DIR (in addition to writing its path to the *.txt list files).
COPY_FILES = True

# --- Classification thresholds -------------------------------------------
COLUMN_GAP_THRESHOLD = 50          # pt gap between block x-coords -> two columns
SINGLE_COL_MAX_PAGES = 20          # single-column "regular paper" upper bound
DOUBLE_COL_MAX_PAGES = 15          # double-column "regular paper" upper bound
ETD_MIN_PAGES = 30                 # single-column doc at/above this length -> ETD
SCANNED_TEXT_CHAR_THRESHOLD = 50   # fewer extractable chars than this on page 1 ...
SCANNED_IMAGE_AREA_RATIO = 0.5     # ... plus an image covering this much of the page -> scanned


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def build_month_folders(year):
    """Return the 12 YYMM folder names for a given year (arXiv convention)."""
    yy = f"{year % 100:02d}"
    return [f"{yy}{month:02d}" for month in range(1, 13)]


def is_scanned(page):
    """Heuristic: little/no extractable text + a large embedded image."""
    text = page.get_text().strip()
    if len(text) >= SCANNED_TEXT_CHAR_THRESHOLD:
        return False

    images = page.get_images(full=True)
    if not images:
        return False

    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return True  # can't measure area, but text coverage was already very low

    for img in images:
        xref = img[0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            rects = []
        for rect in rects:
            img_area = rect.width * rect.height
            if (img_area / page_area) >= SCANNED_IMAGE_AREA_RATIO:
                return True

    # Very low text but no single dominant image found — still treat as
    # scanned, since a text-coverage of near zero is itself the key signal.
    return True


def detect_column_layout(page):
    """Detects whether a page is single- or two-column via block x-gaps."""
    blocks = page.get_text("blocks")
    x_coords = sorted({round(b[0]) for b in blocks if (b[2] - b[0]) > 5 and (b[3] - b[1]) > 5})

    if len(x_coords) < 2:
        return "single"

    gaps = [x_coords[i + 1] - x_coords[i] for i in range(len(x_coords) - 1)]
    return "double" if any(g > COLUMN_GAP_THRESHOLD for g in gaps) else "single"


def classify_pdf(pdf_path):
    """
    Classify a single PDF.

    Returns (category, status) where:
        status   is "ok" (classified into a target category),
                 "no_match" (opened fine but fits no target bucket), or
                 "error" (could not be opened / read).
        category is one of "scanned", "etd", "single_column",
                 "double_column", or None.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None, "error"

    try:
        if doc.page_count == 0:
            return None, "no_match"

        page = doc[0]

        if is_scanned(page):
            return "scanned", "ok"

        layout = detect_column_layout(page)
        num_pages = doc.page_count

        if layout == "single" and num_pages >= ETD_MIN_PAGES:
            return "etd", "ok"
        if layout == "single" and num_pages <= SINGLE_COL_MAX_PAGES:
            return "single_column", "ok"
        if layout == "double" and num_pages <= DOUBLE_COL_MAX_PAGES:
            return "double_column", "ok"

        return None, "no_match"
    except Exception:
        return None, "error"
    finally:
        doc.close()


# --------------------------------------------------------------------------
# Core processing
# --------------------------------------------------------------------------

def process_year(year, list_writers, csv_writer, category_dirs, rng):
    """Pool all PDFs across a year's 12 month folders, then randomly sample
    into the four category quotas for that year."""
    month_folders = build_month_folders(year)

    all_pdfs = []
    any_folder_found = False
    for mf in month_folders:
        folder_path = os.path.join(ROOT_FOLDER, mf)
        if not os.path.isdir(folder_path):
            continue
        any_folder_found = True
        pdfs_here = [
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.lower().endswith(".pdf")
        ]
        print(f"  [{mf}] found {len(pdfs_here)} PDFs")
        all_pdfs.extend(pdfs_here)

    if not any_folder_found:
        print(f"  No month folders found for year {year}, skipping.")
        return None

    rng.shuffle(all_pdfs)  

    quotas = {
        "single_column": REQUIRED_SC_PAPER_COUNT,
        "double_column": REQUIRED_DC_PAPER_COUNT,
        "etd": REQUIRED_ETD_PAPER_COUNT,
        "scanned": REQUIRED_SCANNED_PAPER_COUNT,
    }
    counts = {k: 0 for k in quotas}
    n_processed = n_errors = n_no_match = 0

    for pdf_path in all_pdfs:
        if all(counts[k] >= quotas[k] for k in quotas):
            break  # every quota for this year has been filled

        category, status = classify_pdf(pdf_path)
        n_processed += 1

        if status == "error":
            n_errors += 1
            continue
        if status == "no_match" or category is None:
            n_no_match += 1
            continue

        selected = counts[category] < quotas[category]
        if selected:
            counts[category] += 1
            list_writers[category].write(pdf_path + "\n")
            if COPY_FILES:
                shutil.copy(pdf_path, category_dirs[category])

        month_folder = os.path.basename(os.path.dirname(pdf_path))
        csv_writer.writerow([year, month_folder, pdf_path, category, selected])

    print(
        f"  Year {year}: processed {n_processed} PDFs "
        f"({n_errors} errors, {n_no_match} unmatched)"
    )
    print(
        f"  Selected -> single: {counts['single_column']}/{quotas['single_column']}, "
        f"double: {counts['double_column']}/{quotas['double_column']}, "
        f"etd: {counts['etd']}/{quotas['etd']}, "
        f"scanned: {counts['scanned']}/{quotas['scanned']}"
    )
    return counts


def main():
    rng = random.Random(RANDOM_SEED)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    category_dirs = {
        "single_column": os.path.join(OUTPUT_DIR, "single_column_papers"),
        "double_column": os.path.join(OUTPUT_DIR, "double_column_papers"),
        "etd": os.path.join(OUTPUT_DIR, "etd_papers"),
        "scanned": os.path.join(OUTPUT_DIR, "scanned_papers"),
    }
    if COPY_FILES:
        for d in category_dirs.values():
            os.makedirs(d, exist_ok=True)

    list_paths = {
        "single_column": os.path.join(OUTPUT_DIR, "single_column.txt"),
        "double_column": os.path.join(OUTPUT_DIR, "double_column.txt"),
        "etd": os.path.join(OUTPUT_DIR, "etd.txt"),
        "scanned": os.path.join(OUTPUT_DIR, "scanned.txt"),
    }
    list_writers = {cat: open(path, "w") for cat, path in list_paths.items()}

    csv_path = os.path.join(OUTPUT_DIR, "classification_log.csv")
    csv_file = open(csv_path, "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["year", "month_folder", "file_path", "category", "selected"])

    grand_totals = {"single_column": 0, "double_column": 0, "etd": 0, "scanned": 0}

    for year in range(START_YEAR, END_YEAR + 1):
        print(f"\n=== Processing year {year} ===")
        counts = process_year(year, list_writers, csv_writer, category_dirs, rng)
        if counts:
            for k in grand_totals:
                grand_totals[k] += counts[k]

    for f in list_writers.values():
        f.close()
    csv_file.close()

    print("\n=== Done ===")
    print(f"Grand totals across {START_YEAR}-{END_YEAR}: {grand_totals}")
    print(f"Selected file lists written under: {OUTPUT_DIR}/*.txt")
    print(f"Full per-file classification log written to: {csv_path}")


if __name__ == "__main__":
    main()