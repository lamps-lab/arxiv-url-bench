import os
import re
import json
import time
import fitz  # PyMuPDF
import gc
import multiprocessing as mp

RESULTS_DIR = "/data/la_360k_sample/intermediate_results"

URL_PATTERN = re.compile(r'''(?xi)
    \b(?:
        (?:https?|ftp|file|data|javascript|mailto|tel|git|ssh|magnet)://    
        | www\d{0,3}[.]                                                    
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
            (?:[a-z0-9\u00a1-\uffff][a-z0-9\u00a1-\uffff_-]{0,62})?
            [a-z0-9\u00a1-\uffff]\.
        )*
        (?:[a-z\u00a1-\uffff]{2,}\.?)                                      
    )
    (?::\d{2,5})?                                                          
    (?:[/?#][^\s]*)?                                                       
''')

TRAILING_NOISE = re.compile(r'[.,;:)\]}>"\']$')
SAVE_INTERVAL = 1000  

METADATA_BLOCKLIST = {
    "ns.adobe.com", "adobe.com", "w3.org", "purl.org", "xml.org", "schemas.microsoft.com"
}

def clean_url(u: str) -> str:
    if "'><" in u: u = u.split("'><")[0]
    if '"><' in u: u = u.split('"><')[0]
    if '<' in u: u = u.split('<')[0]
    while TRAILING_NOISE.search(u):
        u = TRAILING_NOISE.sub('', u)
    return u

def is_noise_or_metadata(url: str) -> bool:
    url_lower = url.lower()
    for domain in METADATA_BLOCKLIST:
        if domain in url_lower: return True
    if "xmlns" in url_lower or "/xap/" in url_lower or "/rdf/" in url_lower: return True
    return False

def is_self_ref(url: str, arxiv_id: str) -> bool:
    base = re.sub(r'v\d+$', '', arxiv_id)
    if '/' in base: pat = rf'arxiv\.org/.+/{re.escape(base)}(v\d+)?'
    else: pat = rf'arxiv\.org/(?:abs|pdf|html|ps)/{re.escape(base)}(v\d+)?'
    return bool(re.search(pat, url))

def sanitize_for_regex(text: str) -> str:
    """Strips non-printable binary characters to prevent C-level Regex stack overflows."""
    return re.sub(r'[^\x20-\x7E\t\n\r]', ' ', text)

def extract_urls_from_pdf(pdf_path: str, arxiv_id: str) -> list:
    urls = set()
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            for link in page.get_links():
                uri = link.get("uri", "")
                if uri.startswith("http") or uri.startswith("git"): urls.add(uri)
                    
            text = page.get_text("text")
            for m in URL_PATTERN.finditer(text): urls.add(m.group())
        
        ocgs = doc.get_ocgs()
        if ocgs:
            for name in ocgs.get("ocgs", {}).keys():
                layer_text = doc.get_ocg_content(name)
                if layer_text:
                    for m in URL_PATTERN.finditer(layer_text): urls.add(m.group())
                        
        doc.close()
    except Exception:
        pass 

    # Fallback Binary Scan
    try:
        with open(pdf_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk: break
                chunk_str = chunk.decode("utf-8", errors="ignore")
                safe_str = sanitize_for_regex(chunk_str) 
                for m in URL_PATTERN.finditer(safe_str):
                    urls.add(m.group())
    except Exception:
        pass

    final_urls = set()
    for u in urls:
        if not u: continue
        cleaned = clean_url(u)
        if cleaned and not is_self_ref(cleaned, arxiv_id) and not is_noise_or_metadata(cleaned):
            final_urls.add(cleaned)
        
    return sorted(list(final_urls))

def _worker_process(pdf_path, arxiv_id, out_queue):
    """The isolated worker function that actually touches the dangerous PDF."""
    try:
        res = extract_urls_from_pdf(pdf_path, arxiv_id)
        out_queue.put(("SUCCESS", res))
    except Exception as e:
        out_queue.put(("ERROR", str(e)))

def extract_with_sandbox(pdf_path, arxiv_id, timeout_sec=120):
    """
    Spawns a highly isolated subprocess to parse the PDF. 
    If PyMuPDF segfaults, the subprocess dies safely without killing the main script.
    """
    ctx = mp.get_context('spawn') # 'spawn' ensures a clean memory state for C-libs
    q = ctx.Queue()
    
    p = ctx.Process(target=_worker_process, args=(pdf_path, arxiv_id, q))
    p.start()
    p.join(timeout=timeout_sec)
    
    # 1. Handle infinite hangs (Catastrophic Backtracking)
    if p.is_alive():
        print(f"\n  [TIMEOUT] {arxiv_id} hung for over {timeout_sec}s. Terminating safely.", flush=True)
        p.terminate()
        p.join()
        return []
        
    # 2. Handle the Segfault! (Exit code won't be 0 if it crashed)
    if p.exitcode != 0:
        print(f"\n  [CRASH DETECTED] {arxiv_id} caused a SegFault (Code {p.exitcode}). Skipped safely.", flush=True)
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
    in_file = os.path.join(RESULTS_DIR, "stage1_sampled_ids.json")
    out_file = os.path.join(RESULTS_DIR, "stage2_pdf_textwal_urls.json")
    
    with open(in_file, "r") as f:
        stage1 = json.load(f)

    if os.path.exists(out_file):
        print("Found existing file. Resuming where we left off...", flush=True)
        with open(out_file, "r") as f:
            try: result = json.load(f)
            except json.JSONDecodeError: result = {}
    else:
        result = {}

    start_time = time.perf_counter()
    global_count = 0

    for year, entries in sorted(stage1.items(), key=lambda x: int(x[0])):
        if year not in result: result[year] = {}
            
        print(f"\n--- Running: Year {year} ({len(entries)} entries) ---", flush=True)
        
        for i, entry in enumerate(entries):
            aid, pdf_path = entry["arxiv_id"], entry["pdf_path"]
            
            if aid in result[year]: continue
            
            print(f"  -> Parsing {aid}...", end='\r', flush=True) 
            
            # Use the Sandboxed extractor!
            urls = extract_with_sandbox(pdf_path, aid)
            
            result[year][aid] = {
                "pdf_path": pdf_path,
                "urls": urls,
                "num_urls": len(urls)
            }
            
            global_count += 1
            
            if global_count % 250 == 0:
                print(f"  [{year}] {i + 1}/{len(entries)} completed.", flush=True)
                gc.collect() 

            if global_count % SAVE_INTERVAL == 0:
                print(f"  [Autosave] Writing state checkpoint to {out_file}...", flush=True)
                with open(out_file, "w") as f:
                    json.dump(result, f, indent=2)
                    
        with open(out_file, "w") as f:
            json.dump(result, f, indent=2)

    end_time = time.perf_counter()
    print(f"\n✓ Finished processing. Results saved to: {out_file}", flush=True)
    print(f"Total time elapsed: {end_time - start_time:.2f} seconds.", flush=True)

if __name__ == "__main__":
    # Required for safe multiprocessing behavior on Linux clusters
    mp.set_start_method('spawn', force=True) 
    main()