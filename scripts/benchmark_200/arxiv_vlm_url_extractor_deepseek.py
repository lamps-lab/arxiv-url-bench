"""
R004_IMLS_OADS__
|
arxiv_vlm_url_extractor_deepseek.py 
Created on Wed Nov 19 22:46:39 2025
@author: Lemos

"stage" JSON :
    {arxiv_id: {"filename": ..., "url_count": ..., "urls": [...]}}
"""

import re
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM

# DeepSeek imports
from deepseek_vl.models import VLChatProcessor
from deepseek_vl.utils.io import load_pil_images

torch.cuda.empty_cache()
torch.cuda.ipc_collect()

# =========
# CONFIG
# =========
ROOT_DIR     = Path("data/200_sample")
BASE_DIR     = ROOT_DIR / "raw_files"
PNG_DIR       = BASE_DIR / "vlm_png"      # <arxiv_id>/page_001.png ... shared across all 3 VLMs
OUTPUT_FOLDER = BASE_DIR / "vlm_deepseek"      # one JSON per paper 
INTER_DIR    = ROOT_DIR / "intermediate_results"  # aggregated stage_*.json 
STAGE_JSON    = INTER_DIR / "stage_vlm_deepseek_urls.json"
MODEL_FOLDER  = "VLMs/deepseek-vl-7b-chat"

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

URL_STRICT_RE = re.compile(
    r"\b(?:https?://|www\.)[A-Za-z0-9\-._~:/?#[@\]!$&'()*+,;=%]+",
    re.IGNORECASE
)


# ======================================================
# LOAD MODEL
# ======================================================
def load_deepseek_model(local_path):
    print("Loading DeepSeek-VL from:", local_path)

    vl_chat_processor = VLChatProcessor.from_pretrained(local_path)
    tokenizer = vl_chat_processor.tokenizer

    vl_gpt = AutoModelForCausalLM.from_pretrained(
        local_path,
        trust_remote_code=True
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    vl_gpt = vl_gpt.to(dtype).to(device).eval()

    return vl_chat_processor, tokenizer, vl_gpt, device


# ======================================================
# PAPER DISCOVERY  (replaces the old PDF-folder listing)
# ======================================================
def get_arxiv_ids(png_dir: Path = PNG_DIR) -> list:
    return sorted(p.name for p in png_dir.iterdir() if p.is_dir())


def get_page_images(arxiv_id: str, png_dir: Path = PNG_DIR) -> list:
    return sorted((png_dir / arxiv_id).glob("page_*.png"))


# ======================================================
# EXTRACT URLS FROM ONE IMAGE
# ======================================================
def deepseek_extract_urls(vl_chat_processor, tokenizer, vl_gpt, device, image_path):
    conversation = [
        {
            "role": "User",
            "content": "<image_placeholder>\n" + PROMPT.strip(),
            "images": [str(image_path)],
        },
        {"role": "Assistant", "content": ""}
    ]

    pil_images = load_pil_images(conversation)

    prepare_inputs = vl_chat_processor(
        conversations=conversation,
        images=pil_images,
        force_batchify=True
    ).to(device)

    inputs_embeds = vl_gpt.prepare_inputs_embeds(**prepare_inputs)

    outputs = vl_gpt.language_model.generate(
        inputs_embeds=inputs_embeds,
        attention_mask=prepare_inputs.attention_mask,
        pad_token_id=tokenizer.eos_token_id,
        bos_token_id=tokenizer.bos_token_id,
        eos_token_id=tokenizer.eos_token_id,
        max_new_tokens=1024,
        do_sample=False,
    )

    text = tokenizer.decode(outputs[0].cpu().tolist(), skip_special_tokens=True)

    # Extract one URL per line
    urls = [u.strip() for u in text.split("\n") if u.strip()]

    # Clean/filter
    cleaned_urls = []
    for u in urls:
        u = u.strip(".,;:!?) ]")
        u = u.replace(" ", "")

        m = URL_STRICT_RE.search(u)
        if not m:
            continue  # skip junk

        url = m.group(0).rstrip(".,;:!?) ]")
        cleaned_urls.append(url)

    return cleaned_urls


# ======================================================
# PROCESS ONE PAPER 
# ======================================================
def process_paper(arxiv_id, vl_chat_processor, tokenizer, vl_gpt, device):
    print(f"\nProcessing: {arxiv_id}")
    page_paths = get_page_images(arxiv_id)

    results = []
    all_urls = []
    for idx, page_path in enumerate(page_paths):
        print(f" Page {idx + 1}/{len(page_paths)}")
        urls = deepseek_extract_urls(vl_chat_processor, tokenizer, vl_gpt, device, page_path)
        results.append({"page": idx + 1, "urls": urls})
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
    vl_chat_processor, tokenizer, vl_gpt, device = load_deepseek_model(MODEL_FOLDER)

    arxiv_ids = get_arxiv_ids()
    print(f"Found {len(arxiv_ids)} papers under {PNG_DIR}")

    # Resume support: delete stage_vlm_deepseek_urls.json for a clean re-run.
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

        print(f"\n=== [{idx}/{len(arxiv_ids)}] {arxiv_id} ===")
        data = process_paper(arxiv_id, vl_chat_processor, tokenizer, vl_gpt, device)

        with open(out_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"Saved -> {out_path}")

        stage_results[arxiv_id] = {
            "filename": data["filename"],
            "url_count": data["url_count"],
            "urls": data["urls"],
        }
        with open(STAGE_JSON, "w") as f:
            json.dump(stage_results, f, indent=4)

    print(f"\nAll papers processed. {len(stage_results)} papers in {STAGE_JSON}")

