#!/usr/bin/env python3
import os
import time
import traceback
from pathlib import Path

import torch

# ── Configuration ────────────────────────────────────────────────
PDF_INPUT_DIR = Path("/data/200_sample/raw_files/pdf")
MD_OUTPUT_DIR = Path("/data/200_sample/raw_files/markdown")
RESUME        = True

# ── Device selection (automatic) ─────────────────────────────────
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"torch      : {torch.__version__}")
    print(f"device     : {DEVICE}")
    if DEVICE == "cuda":
        print(f"GPU        : {torch.cuda.get_device_name(0)}")
    print("=" * 60)

    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered

    os.makedirs(MD_OUTPUT_DIR, exist_ok=True)

    # Ignore checkpoint files
    pdf_files = sorted(
        p for p in Path(PDF_INPUT_DIR).rglob("*.pdf")
        if "checkpoint" not in p.name.lower()
    )

    print(f"\nFound {len(pdf_files)} PDF(s)")

    # Load models once
    print("\nLoading models...")
    converter = PdfConverter(artifact_dict=create_model_dict())
    print("Ready.\n")

    failed = []
    t_start = time.perf_counter()

    for i, pdf_path in enumerate(pdf_files, 1):
        md_path = Path(MD_OUTPUT_DIR) / (pdf_path.stem + ".md")

        if RESUME and md_path.exists():
            print(f"[{i}/{len(pdf_files)}] SKIP: {pdf_path.name}")
            continue

        print(f"[{i}/{len(pdf_files)}] Converting: {pdf_path.name}", end=" ")

        try:
            t0 = time.perf_counter()
            rendered = converter(str(pdf_path))
            md_text, _, _ = text_from_rendered(rendered)
            md_path.write_text(md_text, encoding="utf-8")
            print(f"→ {time.perf_counter() - t0:.1f}s")
        except Exception:
            print("→ FAILED")
            traceback.print_exc()
            failed.append(str(pdf_path))

    print("\nDone.")
    print(f"Failed: {len(failed)}")
    print(f"Time: {time.perf_counter() - t_start:.1f}s")


if __name__ == "__main__":
    main()

