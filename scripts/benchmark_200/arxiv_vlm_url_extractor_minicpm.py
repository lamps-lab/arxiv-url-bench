"""
R004_IMLS_OADS__
|
arxiv_vlm_url_extractor_minicpm.py 
Created on Wed Nov 19 22:46:39 2025
@author: Lemos

"stage" JSON :
    {arxiv_id: {"filename": ..., "url_count": ..., "urls": [...]}}
"""


import re
import sys
import json
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoModel, AutoTokenizer

torch.cuda.empty_cache()
torch.cuda.ipc_collect()

# =========
# CONFIG
# =========
ROOT_DIR     = Path("data/200_sample")
BASE_DIR     = ROOT_DIR / "raw_files"
PNG_DIR       = BASE_DIR / "vlm_png"      # <arxiv_id>/page_001.png ... shared across all 3 VLMs
OUTPUT_FOLDER = BASE_DIR / "vlm_minicpm"      # one JSON per paper 
INTER_DIR    = ROOT_DIR / "intermediate_results"  # aggregated stage_*.json
STAGE_JSON    = INTER_DIR / "stage_vlm_minicpm_urls.json"
LOCAL_MODEL_DIR = "VLMs/MiniCPM-o-2_6"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
INTER_DIR.mkdir(parents=True, exist_ok=True)

# Needed so transformers can find MiniCPM's custom modeling code.
sys.path.insert(0, str(Path(LOCAL_MODEL_DIR).resolve()))
print("sys.path[0]:", sys.path[0])

PROMPT = """
You are an expert URL extractor. Your task is to identify all URLs in the provided page image.

Rules:
1. Only output URLs. Do NOT include any extra text or commentary.
2. Each URL must be on a separate line.
3. Include URLs in headers, footers, tables, or broken across multiple lines.
4. Reconstruct any URLs broken across lines.
5. Ignore all other text on the page.
6. Do not summarize or explain anything.

Output example:
https://example.com/page
http://domain.org/path?query
www.site.net/index.html
"""

# Strict URL regex
URL_RE = re.compile(
    r"\b(?:https?://|www\.)[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
    re.IGNORECASE
)


# ======================================================
# LOAD MODEL & TOKENIZER FROM LOCAL PATH
# ======================================================
print("Loading MiniCPM-O model from local path...")
model = AutoModel.from_pretrained(
    LOCAL_MODEL_DIR,
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
    init_vision=True,
    init_audio=False,
    init_tts=False
)
model = model.to(DEVICE).eval()
model.init_tts()

tokenizer = AutoTokenizer.from_pretrained(LOCAL_MODEL_DIR, trust_remote_code=True)
print("Model and tokenizer loaded.")


# ======================================================
# PAPER DISCOVERY  (replaces the old PDF-folder listing)
# ======================================================
def get_arxiv_ids(png_dir: Path = PNG_DIR) -> list:
    return sorted(p.name for p in png_dir.iterdir() if p.is_dir())


def get_page_images(arxiv_id: str, png_dir: Path = PNG_DIR) -> list:
    return sorted((png_dir / arxiv_id).glob("page_*.png"))


# ======================================================
# URL EXTRACTION FROM ONE IMAGE
# ======================================================
def extract_urls_from_image(image):
    msgs = [{"role": "user", "content": PROMPT}]
    res = model.chat(
        image=image,
        msgs=msgs,
        context=None,
        tokenizer=tokenizer,
        sampling=False,
        temperature=0.0
    )
    return res


def clean_urls(text):
    urls = []
    for u in URL_RE.findall(text):
        u = u.strip().rstrip(".,;:!?) ]")
        u = u.replace(" ", "")
        # Remove mistakes like '11.http'
        if not re.match(r"^\d+\.", u):
            urls.append(u)
    return list(set(urls))


# ======================================================
# PROCESS ONE PAPER 
# ======================================================
def process_paper(arxiv_id):
    print(f"\nProcessing paper: {arxiv_id}")
    page_paths = get_page_images(arxiv_id)

    all_urls = []
    pages_data = []
    for idx, page_path in enumerate(page_paths):
        print(f"  Page {idx + 1}/{len(page_paths)}")
        image = Image.open(page_path).convert("RGB")
        text = extract_urls_from_image(image)
        urls = clean_urls(text)
        all_urls.extend(urls)
        pages_data.append({"page": idx + 1, "urls": urls})

    urls = list(set(all_urls))
    return {
        "arxiv_id": arxiv_id,
        "filename": f"{arxiv_id}.pdf",
        "urls": urls,
        "url_count": len(urls),
        "pages": pages_data,
    }


# ======================================================
# MAIN -- process all papers; write per-paper JSON + one aggregated stage JSON
# ======================================================
if __name__ == "__main__":
    arxiv_ids = get_arxiv_ids()
    print(f"Found {len(arxiv_ids)} papers under {PNG_DIR}")

    # Resume support: delete stage_vlm_minicpm_urls.json for a clean re-run.
    stage_results = {}
    if STAGE_JSON.exists():
        with open(STAGE_JSON) as f:
            stage_results = json.load(f)
        print(f"Resuming -- {len(stage_results)} papers already completed.")

    for idx, arxiv_id in enumerate(arxiv_ids, 1):
        out_path = OUTPUT_FOLDER / f"{arxiv_id}.json"
        if arxiv_id in stage_results and out_path.exists():
            print(f"[{idx}/{len(arxiv_ids)}] {arxiv_id}: already done, skipping")
            continue

        print(f"[{idx}/{len(arxiv_ids)}] {arxiv_id}")
        result = process_paper(arxiv_id)

        with open(out_path, "w") as f:
            json.dump(result, f, indent=4)
        print(f"Saved -> {out_path}")

        stage_results[arxiv_id] = {
            "filename": result["filename"],
            "url_count": result["url_count"],
            "urls": result["urls"],
        }
        with open(STAGE_JSON, "w") as f:
            json.dump(stage_results, f, indent=4)

    print(f"\nAll papers processed. {len(stage_results)} papers in {STAGE_JSON}")