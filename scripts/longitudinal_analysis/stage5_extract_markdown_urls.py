import json
import os
import re

# ── Configuration ─────────────────────────────────────────────────
INPUT_JSON = "/data/la_360k_sample/intermediate_results/stage5_markdown_marker_success.json"
OUTPUT_JSON = "/data/la_360k_sample/intermediate_results/stage5_markdown_urls.json"
SAVE_INTERVAL = 250 

# ── URL patterns ──────────────────────────────────────────────────
MD_LINK_RE = re.compile(r'!?\[(?:[^\[\]]*)\]\((https?://[^\s)]+)\)', re.IGNORECASE)
HTML_ATTR_RE = re.compile(r'(?:href|src|action|data-href|data-src)\s*=\s*["\']?(https?://[^\s"\' <>)]+)["\']?', re.IGNORECASE)
BARE_URL_RE = re.compile(r'(?<![(["\'])https?://(?:[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]+)', re.IGNORECASE)
DIRECT_URL_RE = re.compile(r'''(?xi)
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

def extract_urls(md_text: str) -> list[str]:
    """Run all four patterns and return a sorted, deduplicated URL list."""
    raw: set[str] = set()
    raw.update(MD_LINK_RE.findall(md_text))
    raw.update(HTML_ATTR_RE.findall(md_text))
    raw.update(BARE_URL_RE.findall(md_text))
    raw.update(DIRECT_URL_RE.findall(md_text))

    cleaned = set()
    for url in raw:
        url = re.sub(r'[.,;:!?\)\]\}\'\'\"]+$', '', url)
        if url:
            cleaned.add(url)
    return sorted(cleaned)

def safe_save_checkpoint(result_data: dict):
    """Atomically save the JSON to prevent corruption on abrupt runtime kills."""
    tmp_json = OUTPUT_JSON + ".tmp"
    with open(tmp_json, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, indent=4)
    os.replace(tmp_json, OUTPUT_JSON)

def main():
    print(f"Loading input JSON: {INPUT_JSON}")
    with open(INPUT_JSON, 'r', encoding='utf-8') as f:
        source_data = json.load(f)

    # 1. Load existing output JSON structure if resuming
    result_data = {}
    if os.path.exists(OUTPUT_JSON):
        print(f"Loading existing output JSON to resume: {OUTPUT_JSON}")
        with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
            try:
                result_data = json.load(f)
            except json.JSONDecodeError:
                result_data = {}

    # 2. Build the processed tracking cache dynamically from the saved file keys!
    processed_ids = set()
    for year_data in result_data.values():
        processed_ids.update(year_data.keys())
    print(f"Loaded {len(processed_ids)} already processed IDs directly from output JSON.")

    processed_in_this_run = 0

    try:
        for year, papers in sorted(source_data.items(), key=lambda x: str(x[0])):
            if year not in result_data:
                result_data[year] = {}

            for paper in papers:
                arxiv_id = paper.get("arxiv_id")
                markdown_path = paper.get("markdown_path")

                if not arxiv_id or not markdown_path:
                    continue
                
                # Skip if already captured in our output JSON source of truth
                if arxiv_id in processed_ids:
                    continue

                urls = []
                if os.path.exists(markdown_path):
                    try:
                        with open(markdown_path, 'r', encoding='utf-8') as mf:
                            md_text = mf.read()
                            urls = extract_urls(md_text)
                    except Exception as e:
                        print(f"Error reading {markdown_path}: {e}")
                else:
                    print(f"Warning: File not found -> {markdown_path}")

                # Populate schema structure
                result_data[year][arxiv_id] = {
                    "markdown_path": markdown_path,
                    "urls": urls,
                    "num_urls": len(urls)
                }

                processed_ids.add(arxiv_id)
                processed_in_this_run += 1

                # Save checkpoint atomically based on interval
                if processed_in_this_run % SAVE_INTERVAL == 0:
                    safe_save_checkpoint(result_data)
                    print(f"Checkpoint saved. Total processed this run: {processed_in_this_run}")

    except KeyboardInterrupt:
        print("\nProcess interrupted via keyboard. Executing safe save...")

    except Exception as e:
        print(f"\nUnexpected error encountered: {e}. Executing safe save...")

    finally:
        # Final cleanup pass save
        safe_save_checkpoint(result_data)
        print(f"Process ended. Newly processed markdown files in this run: {processed_in_this_run}")

if __name__ == "__main__":
    main()
