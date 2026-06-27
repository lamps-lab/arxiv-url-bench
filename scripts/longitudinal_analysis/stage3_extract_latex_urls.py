import os
import json
import re
import gc
import time
import multiprocessing as mp
from pylatexenc.latex2text import LatexNodes2Text

INPUT_JSON = "/data/la_360k_sample/intermediate_results/stage3b_latex_sources_all.json"
OUTPUT_JSON = "/data/la_360k_sample/intermediate_results/stage3_latex_urls.json"
SAVE_INTERVAL = 250  

# Regex pattern to capture URLs
direct_url_pattern = re.compile(r'''(?xi)
    \b(?:
        (?:https?|ftp|file|data|javascript|mailto|tel|git|ssh|magnet)://
        | www\d{0,3}[.]
        | [a-z0-9.\-]+[.][a-z]{2,4}/
    )
    (?:\S+(?::\S*)?@)?
    (?:
        (?!(?:10|127)(?:\.\d{1,3}){3})
        (?!(?:169\.254|192\.168)(?:\.\d{1,3}){2})
        (?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})
        (?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])
        (?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}
        (?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))
    |
        (?:
            (?:
                [a-z0-9\u00a1-\uffff]
                [a-z0-9\u00a1-\uffff_-]{0,62}
            )?
            [a-z0-9\u00a1-\uffff]\.
        )*
        (?:[a-z\u00a1-\uffff]{2,}\.?)
    )
    (?::\d{2,5})?
    (?:[/?#][^\s]*)?
    \b
''')

def sanitize_for_regex(text: str) -> str:
    """Strips non-printable binary characters to prevent C-level Regex stack overflows."""
    return re.sub(r'[^\x20-\x7E\t\n\r]', ' ', text)

def safe_save_json(data):
    """Save JSON to a temp file first, then replace to prevent corruption on job kill."""
    temp_file = OUTPUT_JSON + ".tmp"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    os.replace(temp_file, OUTPUT_JSON)

def extract_urls_from_folder(base_folder):
    """Walk through the base folder, find all .tex and .bbl files, and extract URLs."""
    extracted_urls = set()
    
    if not os.path.exists(base_folder):
        return list(extracted_urls)

    for root, _, files in os.walk(base_folder):
        for file in files:
            if file.endswith('.tex') or file.endswith('.bbl'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    plain_text = content
                    if file.endswith(".tex"):
                        try:
                            plain_text = LatexNodes2Text().latex_to_text(content)
                        except Exception:
                            # Fallback to raw content if pylatexenc fails on complex macros
                            plain_text = content

                    # Find URLs inside \url{} and \urladdr{}
                    extracted_urls.update(re.findall(r'\\url\{([^}]+)\}', content))
                    extracted_urls.update(re.findall(r'\\urladdr\{([^}]+)\}', content))
                    
                    # Find direct URLs (using sanitized text to prevent regex hangs)
                    safe_plain_text = sanitize_for_regex(plain_text)
                    extracted_urls.update(direct_url_pattern.findall(safe_plain_text))
                
                except Exception:
                    # Catching any rogue read errors safely within the worker
                    pass

    return list(extracted_urls)

def _worker_process(source_path, out_queue):
    """The isolated worker function that touches the dangerous LaTeX parsing."""
    try:
        res = extract_urls_from_folder(source_path)
        out_queue.put(("SUCCESS", res))
    except Exception as e:
        out_queue.put(("ERROR", str(e)))

def extract_with_sandbox(source_path, arxiv_id, timeout_sec=60):
    """
    Spawns a highly isolated subprocess to parse the LaTeX. 
    If pylatexenc hangs, the subprocess is killed safely.
    """
    ctx = mp.get_context('spawn')
    q = ctx.Queue()
    
    p = ctx.Process(target=_worker_process, args=(source_path, q))
    p.start()
    p.join(timeout=timeout_sec)
    
    # 1. Handle infinite hangs (pylatexenc loops)
    if p.is_alive():
        print(f"\n  [TIMEOUT] {arxiv_id} hung for over {timeout_sec}s (likely pylatexenc loop). Terminated.", flush=True)
        p.terminate()
        p.join()
        return []
        
    # 2. Handle memory crashes / Segfaults
    if p.exitcode != 0:
        print(f"\n  [CRASH] {arxiv_id} crashed the worker (Code {p.exitcode}). Skipped.", flush=True)
        return []
        
    # 3. Handle normal execution
    try:
        status, data = q.get_nowait()
        if status == "SUCCESS":
            return data
        return []
    except Exception:
        return []

def main():
    print("Initializing LaTeX URL Extractor...", flush=True)
    
    # 1. Load input schema
    with open(INPUT_JSON, 'r', encoding='utf-8') as f:
        source_data = json.load(f)

    # 2. Load existing output schema if resuming
    result_data = {}
    if os.path.exists(OUTPUT_JSON):
        print("Found existing output file. Resuming...", flush=True)
        with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
            try:
                result_data = json.load(f)
            except json.JSONDecodeError:
                result_data = {}

    # 3. Dynamically build processed_ids directly from the JSON data!
    processed_ids = set()
    for year_data in result_data.values():
        processed_ids.update(year_data.keys())
        
    print(f"Loaded {len(processed_ids)} already processed records from {OUTPUT_JSON}.", flush=True)

    records_processed_this_run = 0
    start_time = time.perf_counter()

    # 4. Iterate through years and IDs
    for year, papers in sorted(source_data.items(), key=lambda x: str(x[0])):
        if year not in result_data:
            result_data[year] = {}

        print(f"\n--- Running: Year {year} ({len(papers)} entries) ---", flush=True)

        for arxiv_id, source_path in papers.items():
            if arxiv_id in processed_ids:
                continue

            print(f"  -> Parsing {arxiv_id}...", end='\r', flush=True)

            urls = extract_with_sandbox(source_path, arxiv_id, timeout_sec=60)

            # Map to desired schema
            result_data[year][arxiv_id] = {
                "latex_source_path": source_path,
                "urls": urls,
                "num_urls": len(urls)
            }

            # Update in-memory set and counters
            processed_ids.add(arxiv_id)
            records_processed_this_run += 1

            # Save periodically
            if records_processed_this_run % SAVE_INTERVAL == 0:
                print(f"  [Autosave] Checkpoint reached. Saving to {OUTPUT_JSON}...", flush=True)
                safe_save_json(result_data)
                gc.collect()

    # Final save when complete
    safe_save_json(result_data)
    end_time = time.perf_counter()
    
    print(f"\n✓ Extraction complete! Results saved to: {OUTPUT_JSON}", flush=True)
    print(f"Total new records processed this run: {records_processed_this_run}")
    print(f"Total time elapsed: {end_time - start_time:.2f} seconds.", flush=True)

if __name__ == "__main__":
    mp.set_start_method('spawn', force=True) 
    main()

