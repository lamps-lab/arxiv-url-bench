#!/usr/bin/env python3
import os
import sys
import subprocess
import json
from pathlib import Path

# --- Configuration ---
TIMEOUT_SECONDS = 20  
APPTAINER_IMG = "latexml.sif"
SRC_ROOT = Path("/data/200_sample/raw_files/latex")
DEST_ROOT = Path("/data/200_sample/raw_files/html")
LOG_DIR = Path("/data/200_sample/intermediate_results/latexml/logs")
ERROR_LOG = LOG_DIR / "latexml_errors.log"

LOG_DIR.mkdir(parents=True, exist_ok=True)


def find_main_tex(folder_path):
    """Finds the primary .tex file by evaluating file traits."""
    tex_files = list(Path(folder_path).glob("*.tex"))
    if not tex_files:
        return None
    if len(tex_files) == 1:
        return tex_files[0]

    candidates = []
    for tf in tex_files:
        try:

            content = tf.read_text(errors="ignore")
            if "\\documentclass" in content or "\\begin{document}" in content:
                weight = len(content)
                candidates.append((weight, tf))
        except Exception:
            continue

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    return max(tex_files, key=lambda f: f.stat().st_size)


def process_paper(folder_path):
    arxiv_id = folder_path.name
    
    # Dest path: /data/200_sample/raw_files/html/0705.1689/0705.1689.html
    dest_folder = DEST_ROOT / arxiv_id
    dest_file = dest_folder / f"{arxiv_id}.html"
    meta_success_file = dest_folder / "success.json"

    # Skip if already done
    if dest_file.exists() and meta_success_file.exists():
        return

    main_tex = find_main_tex(folder_path)
    if not main_tex:
        with open(ERROR_LOG, "a") as f:
            f.write(f"{arxiv_id} : Missing .tex source files\n")
        return

    dest_folder.mkdir(parents=True, exist_ok=True)

    cmd = [
        "apptainer", "exec", APPTAINER_IMG,
        "latexmlc", str(main_tex), f"--dest={dest_file}"
    ]

    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=TIMEOUT_SECONDS
        )

        if result.returncode == 0 and dest_file.exists():
            valid_arxiv_id = arxiv_id.replace("_", "/", 1) if "_" in arxiv_id else arxiv_id
            
            with open(meta_success_file, "w") as f:
                json.dump({"arxiv_id": valid_arxiv_id, "html_path": str(dest_file.resolve())}, f)
        else:
            with open(ERROR_LOG, "a") as f:
                f.write(f"{arxiv_id} : Exited with code {result.returncode}\n")

    except subprocess.TimeoutExpired:
        with open(ERROR_LOG, "a") as f:
            f.write(f"{arxiv_id} : Timed out after {TIMEOUT_SECONDS}s\n")
    except Exception as e:
        with open(ERROR_LOG, "a") as f:
            f.write(f"{arxiv_id} : Runtime exception - {str(e)}\n")

if __name__ == "__main__":
    if not SRC_ROOT.exists():
        print(f"Error: Source directory {SRC_ROOT} does not exist.")
        sys.exit(1)

    # Automatically find all subfolders inside SRC_ROOT
    folders = [f for f in SRC_ROOT.iterdir() if f.is_dir()]
    
    print(f"Found {len(folders)} paper folders. Starting conversion...")
    
    for i, folder in enumerate(folders, 1):
        print(f"Processing {i}/{len(folders)}: {folder.name}")
        process_paper(folder)
        
    print("Done!")