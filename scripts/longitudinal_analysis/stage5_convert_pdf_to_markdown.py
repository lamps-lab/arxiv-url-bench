import os
# Force tqdm to deactivate before any dependencies load it
os.environ["TQDM_DISABLE"] = "1"
import json
import time
import sys
import traceback
from pathlib import Path
import torch

# ── Configuration ────────────────────────────────────────────────
INPUT_JSON = "/data/la_360k_sample/intermediate_results/stage1_sampled_ids.json"
MD_OUTPUT_BASE = "/data/la_360k_sample/raw_files/markdown"
TRACKER_DIR = "/data/la_360k_sample/intermediate_results/trackers"
RESUME = True

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Dynamically adapt to whatever scale you set in Slurm
TASK_ID = int(os.environ.get("SLURM_ARRAY_TASK_ID", 0))
NUM_TASKS = int(os.environ.get("SLURM_ARRAY_TASK_COUNT", 1))

Path(TRACKER_DIR).mkdir(parents=True, exist_ok=True)

def load_completed_ids_for_task(task_workload):
    """Scan only relevant year/task files to build local resume history."""
    completed = set()
    task_years = {year for year, _, _ in task_workload}
    
    for year in task_years:
        log_path = Path(TRACKER_DIR) / f"{year}_task_{TASK_ID}.log"
        if log_path.exists():
            try:
                with open(log_path, "r") as f:
                    completed.update([line.strip() for line in f if line.strip()])
            except Exception as e:
                print(f"Warning: Tracking sync error for year {year}: {e}")
    return completed

def log_success_by_year(year, arxiv_id):
    """Isolate logs by year AND task ID to keep disk writes race-condition free."""
    try:
        log_path = Path(TRACKER_DIR) / f"{year}_task_{TASK_ID}.log"
        with open(log_path, "a") as f:
            f.write(f"{arxiv_id}\n")
    except Exception as e:
        print(f"Critical: Failed saving success state for {arxiv_id}: {e}")

def main():
    print("=" * 60)
    print(f"Task ID     : {TASK_ID} / Total Workers: {NUM_TASKS}")
    print(f"Torch Engine: {torch.__version__} | Device: {DEVICE}")
    if DEVICE == "cuda":
        print(f"GPU Hardware: {torch.cuda.get_device_name(0)}")
    print("=" * 60)

    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered

    if not os.path.exists(INPUT_JSON):
        print(f"Critical Error: Cannot locate input mapping JSON at {INPUT_JSON}")
        sys.exit(1)
        
    with open(INPUT_JSON, "r") as f:
        sampled_data = json.load(f)

    # Flatten the dataset sequentially
    all_workload = []
    for year, items in sorted(sampled_data.items()):
        for item in items:
            all_workload.append((year, item["arxiv_id"], item["pdf_path"]))
            
    total_global_files = len(all_workload)
    
    # Fully automated step-slicing (Worker 0 handles index 0, 40, 80...)
    # This automatically balances both old and new years across all 40 workers!
    task_workload = all_workload[TASK_ID::NUM_TASKS]
    total_files = len(task_workload)
    
    print(f"Global Pool Layout: {total_global_files:,} files.")
    print(f"Allocated to Task {TASK_ID}: {total_files:,} files.")

    successful_conversions = load_completed_ids_for_task(task_workload)
    print(f"Resume memory loaded: {len(successful_conversions):,} items already completed.")

    print("\nInitializing Marker Pipeline Models into VRAM...")
    converter = PdfConverter(artifact_dict=create_model_dict())
    print("Pipeline Ready.\n")

    failed_list = []
    t_start = time.perf_counter()

    for idx, (year, arxiv_id, pdf_path_str) in enumerate(task_workload, 1):
        if RESUME and arxiv_id in successful_conversions:
            continue

        pdf_path = Path(pdf_path_str)
        if not pdf_path.exists():
            continue

        year_output_dir = Path(MD_OUTPUT_BASE) / str(year)
        year_output_dir.mkdir(parents=True, exist_ok=True)
        md_path = year_output_dir / f"{pdf_path.stem}.md"

        print(f"[{idx}/{total_files}] [{year}] Converting {pdf_path.name}...", end=" ", flush=True)

        try:
            t0 = time.perf_counter()
            rendered = converter(str(pdf_path))
            md_text, _, _ = text_from_rendered(rendered)
            
            md_path.write_text(md_text, encoding="utf-8")
            log_success_by_year(year, arxiv_id)
            successful_conversions.add(arxiv_id)
            
            print(f"Success! ({time.perf_counter() - t0:.1f}s)")
        except Exception as e:
            print("FAILED")
            traceback.print_exc()
            failed_list.append({"arxiv_id": arxiv_id, "year": year, "error": str(e)})

    print(f"\nTask {TASK_ID} run finalized. Local execution duration: {time.perf_counter() - t_start:.1f}s")

if __name__ == "__main__":
    main()