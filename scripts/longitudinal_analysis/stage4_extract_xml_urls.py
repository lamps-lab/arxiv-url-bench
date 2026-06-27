import csv
import json
import os
from lxml import etree

# Define the TEI namespace
NSMAP = {'tei': 'http://www.tei-c.org/ns/1.0'}

# File configurations
CSV_FILE = '/data/la_360k_sample/intermediate_results/stage4_grobid_xml_master_summary.csv'  
JSON_OUTPUT_FILE = '/data/la_360k_sample/intermediate_results/stage4_xml_grobid_urls.json'
SAVE_INTERVAL = 250  

def extract_urls_from_tei(xml_file):
    if not isinstance(xml_file, str) or not os.path.exists(xml_file) or os.path.getsize(xml_file) == 0:
        return []
    
    # Define the URL to be ignored
    GROBID_URL = "https://github.com/kermitt2/grobid"
    
    try:
        tree = etree.parse(xml_file)
        root = tree.getroot()
        
        elements_with_target = root.xpath("//*[@target]", namespaces=NSMAP)
        
        extracted_data = []
        for elem in elements_with_target:
            url = elem.get("target")
            # Added check to exclude the specific Grobid URL
            if (url and 
                "tei" not in url.lower() and 
                not url.startswith("#") and 
                url.strip().lower() != GROBID_URL.lower()):
                
                extracted_data.append(url)
                
        return list(set(extracted_data))
    except Exception as e:
        print(f"Error parsing {xml_file}: {e}")
        return []

def get_year_from_arxiv_id(arxiv_id):
    """
    Extracts the year, correctly handling modern arXiv naming formats 
    (e.g., ensuring prefix '2001' is categorized as year 2020).
    """
    if '/' in arxiv_id:
        # Old format: supr-con/9502001
        yymm = arxiv_id.split('/')[-1][:4]
    else:
        # New format: 2001.00001
        yymm = arxiv_id.split('.')[0]
        
    yy = int(yymm[:2])
    return str(1900 + yy if yy > 50 else 2000 + yy)

def safe_save_checkpoint(result_data: dict):
    """Atomically save the JSON to prevent corruption on abrupt runtime kills."""
    temp_json = f"{JSON_OUTPUT_FILE}.tmp"
    with open(temp_json, 'w', encoding='utf-8') as jf:
        json.dump(result_data, jf, indent=4)
    os.replace(temp_json, JSON_OUTPUT_FILE)

def main():
    # 1. Load existing JSON state if resuming
    result = {}
    if os.path.exists(JSON_OUTPUT_FILE):
        with open(JSON_OUTPUT_FILE, 'r', encoding='utf-8') as f:
            try:
                result = json.load(f)
                print(f"Loaded existing output file: {JSON_OUTPUT_FILE}")
            except json.JSONDecodeError:
                print("Warning: Existing JSON is empty or malformed. Starting fresh dictionary.")

    # 2. Build the processed tracking cache dynamically from the saved file keys!
    processed_ids = set()
    for year_data in result.values():
        processed_ids.update(year_data.keys())
    print(f"Found {len(processed_ids)} already processed records directly in JSON output. Resuming...")

    # 3. Stream CSV line-by-line (Memory Efficient)
    with open(CSV_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        batch_count = 0
        total_processed_this_run = 0
        
        for row in reader:
            arxiv_id = row['arxiv_id']
            
            # Use output JSON data structure as your single source of truth
            if arxiv_id in processed_ids:
                continue
                
            xml_path = row['target_xml_path']
            source_path = row['source_pdf_path'] 
            
            # Extract
            urls = extract_urls_from_tei(xml_path)
            year = get_year_from_arxiv_id(arxiv_id)
            
            # Populate dictionary
            if year not in result:
                result[year] = {}
                
            result[year][arxiv_id] = {
                "xml_path ": xml_path, 
                "urls": urls,
                "num_urls": len(urls)
            }
            
            processed_ids.add(arxiv_id)
            batch_count += 1
            total_processed_this_run += 1
            
            # 4. Save state periodically
            if batch_count >= SAVE_INTERVAL:
                safe_save_checkpoint(result)
                batch_count = 0
                print(f"Progress saved. Total processed this run: {total_processed_this_run} records.")

        # 5. Final save for any remaining records in the last batch
        if batch_count > 0:
            safe_save_checkpoint(result)
            
        print(f"Processing complete. Total records processed this run: {total_processed_this_run}")

if __name__ == "__main__":
    main()