## Dataset Download

The datasets and intermediate artifacts used in the longitudinal analysis are distributed separately because of their size. Download the complete **`arxiv-mini-corpus`** from Hugging Face:

**Hugging Face:**
https://huggingface.co/datasets/rochanaro/hf-arxiv-url-bench/tree/main/arxiv-mini-corpus

After downloading, place the contents under the repository's `data/` directory so that the directory structure matches the following:

```text
data/
├── la_360k_sample/
│   ├── arxiv_extracted_urls_5_formats_360k.json        # REQUIRED: only file needed to reproduce Figure 7
│   │
│   ├── intermediate_results/                           # Optional: preprocessing artifacts, for transparency
│   │   ├── stage1_sampled_ids.json
│   │   ├── stage2_pdf_textwal_urls.json
│   │   ├── stage3_latex_urls.json
│   │   ├── stage3b_latex_sources_all.json
│   │   ├── stage4_xml_grobid_urls.json
│   │   ├── stage4_grobid_xml_master_summary.csv
│   │   ├── stage5_markdown_urls.json
│   │   ├── stage5_markdown_marker_success.json
│   │   ├── stage6_html_urls.json
│   │   ├── stage6_latexml_success.jsonl
│   │   └── longitudinal_analysis_common_360k_arxiv_ids.json
│   │
│   └── raw_files/                                      # Optional: required only to rerun preprocessing (~560 GB total)
│       ├── pdf/          # from pdf.tar.gz
│       ├── latex/        # from latex.tar.gz
│       ├── html/         # from html.tar.gz
│       ├── xml/          # from xml.tar.gz
│       ├── markdown/     # from markdown.tar.gz
│       └── textwal/      # from textwal.tar.gz
│
└── 200_sample/
```

Only `la_360k_sample/arxiv_extracted_urls_5_formats_360k.json` is required to reproduce the final visualization — jump to the **"Reproducing Figure 7: Temporal Distribution of Extracted URLs from arXiv Papers (1992–2024)"** section of `4_arxiv_urls_longitudinal_analysis.ipynb`. The `intermediate_results/` files document each stage of the preprocessing pipeline for transparency and reproducibility; the six `*.tar.gz` archives (unpacked into `raw_files/` above) are only needed if you want to rerun that pipeline from the original PDFs.

This corpus is a 364,744-paper common pool (all six formats successfully produced) drawn from an initial stratified sample of PDFs spanning 1992–2024, capped at 15,000 papers/year.