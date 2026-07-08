"""
R004_IMLS_OADS__
|
arxiv_vlm_url_extractor_qwen.py
Created on Wed Nov 19 22:46:39 2025
@author: Lemos

"stage" JSON :
    {arxiv_id: {"filename": ..., "url_count": ..., "urls": [...]}}
"""

import json
from pathlib import Path

import torch
from PIL import Image
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor, BitsAndBytesConfig

torch.cuda.empty_cache()
torch.cuda.ipc_collect()

# ======================================================
# CONFIG
# ======================================================
ROOT_DIR     = Path("data/200_sample")
BASE_DIR     = ROOT_DIR / "raw_files"
PNG_DIR       = BASE_DIR / "vlm_png"      # <arxiv_id>/page_001.png ... shared across all 3 VLMs
OUTPUT_FOLDER = BASE_DIR / "vlm_qwen"      # one JSON per paper (unchanged behavior)
INTER_DIR    = ROOT_DIR / "intermediate_results"  # aggregated stage_*.json lives here
STAGE_JSON    = INTER_DIR / "stage_vlm_qwen_urls.json"
MODEL_FOLDER  = "VLMs/qwen2_vl"

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
INTER_DIR.mkdir(parents=True, exist_ok=True)

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


# ======================================================
# PAPER DISCOVERY  (replaces the old PDF-folder listing)
# ======================================================
def get_arxiv_ids(png_dir: Path = PNG_DIR) -> list:
    """Every subfolder of PNG_DIR is one paper's rendered pages."""
    return sorted(p.name for p in png_dir.iterdir() if p.is_dir())


def get_page_images(arxiv_id: str, png_dir: Path = PNG_DIR) -> list:
    return sorted((png_dir / arxiv_id).glob("page_*.png"))


def extract_qwen_assistant_lines(text):
    if "Assistant:" in text:
        assistant = text.split("Assistant:")[-1]
    elif "assistant:" in text:
        assistant = text.split("assistant:")[-1]
    elif "assistant" in text:
        assistant = text.split("assistant")[-1]
    elif "<|assistant|>" in text:
        assistant = text.split("<|assistant|>")[-1]
    else:
        assistant = text  # fallback

    lines = [line.strip() for line in assistant.split("\n")]
    lines = [l for l in lines if l]
    return lines


# ======================================================
# LOAD MODEL
# ======================================================
def load_qwen():
    bnb_config = BitsAndBytesConfig(load_in_8bit=True)

    model = Qwen2VLForConditionalGeneration.from_pretrained(
        MODEL_FOLDER,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.float16,
        trust_remote_code=True
    )

    processor = AutoProcessor.from_pretrained(
        MODEL_FOLDER,
        trust_remote_code=True
    )
    return model, processor


# ======================================================
# RUN MODEL ON ONE IMAGE (unchanged chat template logic)
# ======================================================
def extract_urls_from_image(model, processor, image):
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": PROMPT},
            ],
        }
    ]

    text_input = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    inputs = processor(
        text=text_input,
        images=image,
        return_tensors="pt"
    ).to(model.device)

    output_ids = model.generate(
        **inputs,
        max_new_tokens=1000
    )

    text = processor.batch_decode(
        output_ids,
        skip_special_tokens=True
    )[0]

    return extract_qwen_assistant_lines(text)


# ======================================================
# PROCESS ONE PAPER  (now reads pre-rendered PNGs, not the PDF)
# ======================================================
def process_paper(arxiv_id, model, processor):
    print(f"\nProcessing {arxiv_id}")
    page_paths = get_page_images(arxiv_id)

    results = []
    all_urls = []
    for i, page_path in enumerate(page_paths):
        print(f" Page {i + 1}/{len(page_paths)}")
        image = Image.open(page_path).convert("RGB")
        urls = extract_urls_from_image(model, processor, image)
        results.append({"page": i + 1, "urls": urls})
        all_urls.extend(urls)

    urls = list(set(all_urls))
    return {
        "arxiv_id": arxiv_id,
        "filename": f"{arxiv_id}.pdf",
        "pages": results,
        "urls": urls,
        "url_count": len(urls),
    }


# ======================================================
# MAIN -- process all papers; write per-paper JSON + one aggregated stage JSON
# ======================================================
if __name__ == "__main__":
    model, processor = load_qwen()

    arxiv_ids = get_arxiv_ids()
    print(f"Found {len(arxiv_ids)} papers under {PNG_DIR}")

    # Resume support: a 200-paper GPU job can get killed by a wall-time
    # limit, so reload whatever's already been written and skip it.
    # Delete stage_vlm_qwen_urls.json if you want a clean full re-run.
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
        data = process_paper(arxiv_id, model, processor)

        with open(out_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"  Saved -> {out_path}")

        stage_results[arxiv_id] = {
            "filename": data["filename"],
            "url_count": data["url_count"],
            "urls": data["urls"],
        }

        # Persist the aggregate after every paper so progress is never
        # lost if the job is killed / hits a wall-time limit.
        with open(STAGE_JSON, "w") as f:
            json.dump(stage_results, f, indent=4)

    print(f"\nDone. {len(stage_results)} papers in {STAGE_JSON}")