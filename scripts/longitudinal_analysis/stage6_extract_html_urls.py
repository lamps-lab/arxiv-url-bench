import json
import os
import re
from bs4 import BeautifulSoup

# --- Configuration ---
INPUT_JSONL = "/data/la_360k_sample/intermediate_results/stage6_latexml_success.jsonl"
OUTPUT_JSON = "/data/la_360k_sample/intermediate_results/stage6_html_urls_new.json"
BATCH_SIZE = 250  

def get_year_from_arxiv_id(arxiv_id):
    """Extracts the publication year from old and new arXiv IDs."""
    # Match new format (e.g., 2104.12345 -> 2021)
    new_match = re.match(r'^(\d{2})\d{2}\.', arxiv_id)
    if new_match:
        yy = int(new_match.group(1))
        return str(2000 + yy)
    
    # Match old format (e.g., hep-ph/0104289 -> 2001, math/9901001 -> 1999)
    old_match = re.search(r'/(\d{2})\d{2}\d{3}$', arxiv_id)
    if old_match:
        yy = int(old_match.group(1))
        return str(1900 + yy if yy >= 91 else 2000 + yy)
        
    return "unknown_year"

def extract_urls_with_context(html_file, file_id):
    if not os.path.exists(html_file):
        return []

    try:
        with open(html_file, 'r', encoding='utf-8') as file:
            html_content = file.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        page_content = soup.find('div', class_='ltx_page_content')

        extracted_data = set()
        if page_content:
            for a_tag in page_content.find_all('a', href=True):
                url = a_tag['href']
                
                # Escape the file_id so regex doesn't misinterpret characters like '.' or '/'
                safe_file_id = re.escape(file_id)
                
                # Skip self-referencing URLs and URLs with fragments
                if re.search(rf"(arxiv\.org/(abs|pdf|html)/{safe_file_id})", url) or '#' in url:
                    continue
                    
                extracted_data.add(url)

        return list(extracted_data)

    except Exception as e:
        print(f"Error processing {file_id}: {e}")
        return []

def safe_save_checkpoint(result_data: dict):
    """Atomically save the JSON to prevent corruption on abrupt runtime kills."""
    tmp_json = OUTPUT_JSON + ".tmp"
    with open(tmp_json, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, indent=4)
    os.replace(tmp_json, OUTPUT_JSON)

def main():
    # 1. Load existing output JSON to maintain state and recover safely
    result_data = {}
    if os.path.exists(OUTPUT_JSON):
        print(f"Loading existing output JSON to resume: {OUTPUT_JSON}")
        with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
            try:
                result_data = json.load(f)
            except json.JSONDecodeError:
                print("Warning: Existing JSON could not be parsed. Initializing empty state.")

    # 2. Build the processed tracking cache dynamically from the saved file keys!
    processed_ids = set()
    for year_data in result_data.values():
        processed_ids.update(year_data.keys())
    print(f"Found {len(processed_ids)} already processed records directly in JSON output. Resuming...")

    records_processed_in_batch = 0
    total_processed_this_run = 0

    # 3. Process the JSONL line by line to save memory
    with open(INPUT_JSONL, 'r', encoding='utf-8') as infile:
         
        for line in infile:
            if not line.strip():
                continue
                
            record = json.loads(line)
            arxiv_id = record['arxiv_id']
            html_path = record['html_path']

            # Use the output JSON file as your single source of truth
            if arxiv_id in processed_ids:
                continue

            # Execution
            urls = extract_urls_with_context(html_path, arxiv_id)
            year = get_year_from_arxiv_id(arxiv_id)

            if year not in result_data:
                result_data[year] = {}

            result_data[year][arxiv_id] = {
                "html_path": html_path,
                "urls": urls,
                "num_urls": len(urls)
            }

            # Update state variables in memory
            processed_ids.add(arxiv_id)
            records_processed_in_batch += 1
            total_processed_this_run += 1

            # 4. Save to JSON atomically in intervals
            if records_processed_in_batch >= BATCH_SIZE:
                safe_save_checkpoint(result_data)
                records_processed_in_batch = 0
                print(f"Batch saved. Total processed this run: {total_processed_this_run}")

    # Final save to catch any remaining records under the batch size limit
    if records_processed_in_batch > 0:
        safe_save_checkpoint(result_data)
        print("Final batch saved. Processing complete.")

if __name__ == "__main__":
    main()
