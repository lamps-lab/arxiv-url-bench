#!/usr/bin/env python3
import os
import sys
import subprocess
import json
import re

from pathlib import Path

# --- Configuration ---
TIMEOUT_SECONDS = 6  # 20 #1200 minutes
APPTAINER_BIN = "/bin/apptainer"
APPTAINER_IMG = "latexml.sif"

SRC_ROOT = Path("/data/la_360k_sample/raw_files/latex")
DEST_ROOT = Path("/data/la_360k_sample/raw_files/html")
LOG_DIR = Path("/data/la_360k_sample/intermediate_results/latexml/logs")

# Ensure log directories exist
LOG_DIR.mkdir(parents=True, exist_ok=True)

ERROR_LOG = LOG_DIR / "stage6_latexml_errors.log"


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


def process_paper(relative_folder_str):
    folder_path = SRC_ROOT / relative_folder_str
    arxiv_id = folder_path.name  # e.g., "hep-ph_0104289" or "0001.12345"
    strata = folder_path.parent.name  # e.g., "0104" or "0001"

    # NEW STRUCTURE: Create a dedicated folder matching the arxiv_id
    # Path: .../arxiv-html/0104/hep-ph_0104289/
    dest_folder = DEST_ROOT / strata / arxiv_id

    # Target file: .../arxiv-html/0104/hep-ph_0104289/hep-ph_0104289.html
    dest_file = dest_folder / f"{arxiv_id}.html"

    # Each paper tracks its own success metadata file locally
    meta_success_file = dest_folder / "success.json"

    # Resumability: Skip if the HTML and metadata files are already completely created
    if dest_file.exists() and meta_success_file.exists():
        return

    # 1. Find the main LaTeX file
    main_tex = find_main_tex(folder_path)
    if not main_tex:
        with open(ERROR_LOG, "a") as f:
            f.write(f"{arxiv_id} : Missing .tex source files\n")
        return

    # Ensure the dedicated output folder exists
    dest_folder.mkdir(parents=True, exist_ok=True)
    
    # --- NEW: Cleanup orphaned files from Slurm hard-kills ---
    if dest_file.exists() and not meta_success_file.exists():
        dest_file.unlink() # Delete the partial/corrupted HTML file
    # ---------------------------------------------------------

    # 2. Build the Apptainer / LaTeXML command
    cmd = [
        "apptainer",
        "exec",
        APPTAINER_IMG,
        "latexmlc",
        str(main_tex),
        f"--dest={str(dest_file)}",
    ]

    # 3. Execute with Timeout Protection
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )

        # Check stderr for specific missing package warnings or generic errors
        stderr_output = result.stderr
        if "File `" in stderr_output and ".sty' not found" in stderr_output:
            missing_sty = re.findall(r"File `([^`]+.sty)' not found", stderr_output)
            with open(ERROR_LOG, "a") as f:
                f.write(f"{arxiv_id} : Missing package dependency {missing_sty}\n")
            # Clean up the empty folder if nothing was generated
            if dest_folder.exists() and not os.listdir(dest_folder):
                dest_folder.rmdir()
            return

        if result.returncode == 0 and dest_file.exists():
            # Convert folder name back to valid arXiv ID structure
            # If it has an underscore (old style like hep-ph_0104289), switch it to a forward slash.
            # If it's new style (like 0001.12345), it stays as-is.
            if "_" in arxiv_id:
                valid_arxiv_id = arxiv_id.replace("_", "/", 1)
            else:
                valid_arxiv_id = arxiv_id

            log_entry = {
                "arxiv_id": valid_arxiv_id,
                "html_path": str(dest_file.resolve()),
            }

            # NO CORE LOCKING: Write cleanly to an isolated private file
            with open(meta_success_file, "w") as f:

                json.dump(log_entry, f)

        else:
            with open(ERROR_LOG, "a") as f:
                f.write(f"{arxiv_id} : LaTeXML exited with code {result.returncode}\n")
            # Cleanup empty directory if conversion failed completely
            if dest_folder.exists() and not os.listdir(dest_folder):
                dest_folder.rmdir()

    except subprocess.TimeoutExpired:
        with open(ERROR_LOG, "a") as f:
            f.write(f"{arxiv_id} : Process timed out after {TIMEOUT_SECONDS}s\n")
        # Clean up any partial files or folders left behind on timeout
        if dest_file.exists():
            dest_file.unlink()
        if dest_folder.exists() and not os.listdir(dest_folder):
            dest_folder.rmdir()

    except Exception as e:
        with open(ERROR_LOG, "a") as f:
            f.write(f"{arxiv_id} : Runtime exception - {str(e)}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: convert_paper.py <relative_subfolder_path>")
        sys.exit(1)
    process_paper(sys.argv[1])