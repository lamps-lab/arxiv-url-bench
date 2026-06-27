import os
import json
import concurrent.futures
import requests
import time

# GROBID server endpoint
GROBID_URL = "http://localhost:8070/api/processFulltextDocument"
GROBID_ALIVE_URL = "http://localhost:8070/api/isalive"

# Input configuration file and global output location
JSON_PATH = "/data/la_360k_sample/intermediate_results/stage1_sampled_ids.json"
OUTPUT_XML_FOLDER = "/data/la_360k_sample/raw_files/xml"
OUTPUT_METADATA_FOLDER = "/data/la_360k_sample/raw_files/xml-metadata"
os.makedirs(OUTPUT_XML_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_METADATA_FOLDER, exist_ok=True)

# Number of parallel threads sending requests to GROBID.
# Keep this at or below the 'concurrency' value in grobid_local.yaml (currently 10).
# With 12 CPUs allocated, 6 is a safe conservative value.
MAX_WORKERS = 6


def wait_for_grobid(max_wait_seconds=120):
    """
    Block until GROBID responds on /api/isalive or timeout is reached.
    This guards against the rare case where the Python script starts before
    the SLURM polling loop has confirmed the server is up.
    """
    print(f"Verifying GROBID is reachable at {GROBID_ALIVE_URL} ...")
    start = time.time()
    while time.time() - start < max_wait_seconds:
        try:
            r = requests.get(GROBID_ALIVE_URL, timeout=5)
            if r.status_code == 200 and r.text.strip().lower() == "true":
                print(f"  GROBID confirmed alive ({int(time.time() - start)}s).")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(5)
    print(f"ERROR: GROBID did not respond within {max_wait_seconds}s. Aborting.")
    return False


def process_single_pdf(item):
    """
    Processes a single PDF item dict, sends it to GROBID, and saves both
    the XML output and a tracking metadata JSON file.
    """
    pdf_path = item.get("pdf_path")
    arxiv_id = item.get("arxiv_id")  # Preserves exact ID e.g. "math/9201285"

    if not pdf_path or not arxiv_id:
        return None

    safe_basename = arxiv_id.replace("/", "_")
    xml_output_path = os.path.join(OUTPUT_XML_FOLDER, f"{safe_basename}.xml")
    meta_output_path = os.path.join(OUTPUT_METADATA_FOLDER, f"{safe_basename}_meta.json")

    # Skip if already fully processed
    if os.path.exists(xml_output_path) and os.path.exists(meta_output_path):
        return f"Skipped (already processed): {arxiv_id}"

    # Skip if source PDF is missing
    if not os.path.exists(pdf_path):
        return f"❌ Missing source PDF: {pdf_path}"

    metadata = {
        "arxiv_id": arxiv_id,
        "source_pdf_path": pdf_path,
        "target_xml_path": xml_output_path,
        "status": "pending",
        "timestamp": ""
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with open(pdf_path, "rb") as f:
                response = requests.post(
                    GROBID_URL,
                    files={"input": f},
                    params={"includeRawCitations": "true"},
                    timeout=120
                )

            if response.status_code == 200:
                with open(xml_output_path, "w", encoding="utf-8") as xml_file:
                    xml_file.write(response.text)

                metadata["status"] = "success"
                metadata["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
                with open(meta_output_path, "w", encoding="utf-8") as meta_file:
                    json.dump(metadata, meta_file, indent=2)

                return f"✅ Converted: {arxiv_id}"

            elif response.status_code == 503:
                # GROBID pool is full — back off and retry
                wait = 5 * (attempt + 1)
                time.sleep(wait)
                continue

            else:
                return f"❌ Server error ({response.status_code}): {arxiv_id}"

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                # Write placeholder files so failed entries are not re-queued
                with open(xml_output_path, "w", encoding="utf-8") as xml_file:
                    xml_file.write("<failed/>\n")

                metadata["status"] = "failed"
                metadata["error"] = str(e)
                metadata["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
                with open(meta_output_path, "w", encoding="utf-8") as meta_file:
                    json.dump(metadata, meta_file, indent=2)

                return f"🚫 Failed after {max_retries} attempts: {arxiv_id} — {e}"

    return f"❌ Exhausted retries (503 backpressure): {arxiv_id}"


def main():
    # Safety check: confirm GROBID is up before flooding it with requests
    if not wait_for_grobid(max_wait_seconds=120):
        raise SystemExit(1)

    print(f"\n📖 Reading job list from {JSON_PATH}...")
    if not os.path.exists(JSON_PATH):
        print(f"Aborting: JSON file not found at {JSON_PATH}")
        return

    with open(JSON_PATH, "r", encoding="utf-8") as jf:
        data = json.load(jf)

    # Flatten Year -> [items] dict into a flat list
    pdf_queue = []
    for year, items in data.items():
        if isinstance(items, list):
            pdf_queue.extend(items)

    total_files = len(pdf_queue)
    print(f"Found {total_files} PDFs to process across all years.")
    print(f"Starting {MAX_WORKERS} parallel workers...\n")

    start_time = time.time()
    completed_count = 0
    success_count = 0
    fail_count = 0
    skip_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for result in executor.map(process_single_pdf, pdf_queue):
            if result is None:
                continue
            completed_count += 1

            if "✅" in result:
                success_count += 1
            elif "Skipped" in result:
                skip_count += 1
            else:
                fail_count += 1

            # Print every 50 completions, or immediately on any non-success
            if completed_count % 50 == 0 or "✅" not in result:
                elapsed = time.time() - start_time
                rate = completed_count / elapsed if elapsed > 0 else 0
                print(f"[{completed_count}/{total_files}] ({rate:.1f}/s) {result}")

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"🎉 Pipeline complete in {elapsed:.1f}s ({elapsed/3600:.2f}h)")
    print(f"   ✅ Converted : {success_count}")
    print(f"   ⏭️  Skipped   : {skip_count}")
    print(f"   ❌ Failed    : {fail_count}")
    print(f"   Total       : {completed_count}/{total_files}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()