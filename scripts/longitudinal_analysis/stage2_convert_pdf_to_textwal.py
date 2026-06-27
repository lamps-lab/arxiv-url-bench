#!/usr/bin/env python3
import os
import sys
import json
import fitz  # PyMuPDF

RESULTS_DIR = "/data/la_360k_sample/intermediate_results/"
TEXT_OUTPUT_DIR = os.path.join("/data/la_360k_sample/raw_files", "textwal")
LOG_DIR = os.path.join(RESULTS_DIR, "logs_textwal")

# Ensure directories exist
os.makedirs(TEXT_OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
ERROR_LOG = os.path.join(LOG_DIR, "pdf_extraction_errors.log")

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts standard text, annotations, and optional content layers."""
    text_content = []
    doc = fitz.open(pdf_path)
    
    # 1. Standard text & Annotations
    for page in doc:
        text = page.get_text("text")
        if text.strip():
            text_content.append(text)
        
        for annot in page.annots():
            info = annot.info
            if info and "content" in info and info["content"].strip():
                text_content.append(f"\n--- [Annotation] ---\n{info['content']}")

    # 2. Document-level Optional Content Groups (OCG Layers)
    ocgs = doc.get_ocgs()
    if ocgs:
        for name in ocgs.get("ocgs", {}).keys():
            layer_text = doc.get_ocg_content(name)
            if layer_text.strip():
                text_content.append(f"\n--- [Layer: {name}] ---\n{layer_text}")
                
    doc.close()
    return "\n".join(text_content)

def process_single_paper(year, arxiv_id, pdf_path):
    safe_aid = arxiv_id.replace('/', '_')
    
    # Target files
    txt_filepath = os.path.join(TEXT_OUTPUT_DIR, f"{safe_aid}.txt")
    meta_success_file = os.path.join(TEXT_OUTPUT_DIR, f"{safe_aid}.json")
    
    # Resumability check
    if os.path.exists(txt_filepath) and os.path.exists(meta_success_file):
        return

    try:
        extracted_text = extract_text_from_pdf(pdf_path)
        
        # Save raw text
        with open(txt_filepath, "w", encoding="utf-8") as txt_file:
            txt_file.write(extracted_text)
            
        # Write clean isolated metadata metadata record (No core locking)
        log_entry = {
            "year": year,
            "arxiv_id": arxiv_id,
            "text_path": os.path.abspath(txt_filepath)
        }
        with open(meta_success_file, "w") as f:
            json.dump(log_entry, f)

    except Exception as e:
        with open(ERROR_LOG, "a") as err_f:
            err_f.write(f"{arxiv_id} : Runtime exception - {str(e)}\n")
        # Clean up partial creations if failure occurred
        if os.path.exists(txt_filepath): os.path.unlink(txt_filepath)
        if os.path.exists(meta_success_file): os.path.unlink(meta_success_file)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: extract_pdf_worker.py <year> <arxiv_id> <pdf_path>")
        sys.exit(1)
        
    process_single_paper(sys.argv[1], sys.argv[2], sys.argv[3])