## Dataset Download

The datasets and intermediate artifacts used in the longitudinal analysis are distributed separately because of their size. Download the complete **`arxiv-mini-corpus`** from Hugging Face:

**Hugging Face:**
https://huggingface.co/datasets/dblind-data/arxiv-url-bench-hf/tree/main/arxiv-mini-corpus

After downloading, place the contents under the repository's `data/` directory so that the directory structure matches the following:

```text id="fbgvkj"
data/
├── la_360k_sample/
│   ├── arxiv_extracted_urls_5_formats_360k.json   # REQUIRED: only file needed to reproduce Figure 7
│   │
│   ├── intermediate_results/                      # Optional: preprocessing artifacts
│   │   ├── stage1_sampled_ids.json
│   │   ├── stage2_pdf_textwal_urls.json
│   │   ├── stage3_latex_urls.json
│   │   ├── stage4_xml_grobid_urls_new.json
│   │   ├── stage5_markdown_urls.json
│   │   ├── stage6_html_urls_new.json
│   │   └── arxiv_360k_common_ids_longitudinal_analysis.json
│   │
│   └── raw_files/                                # Optional: required only to rerun preprocessing
│       ├── pdf/
│       ├── textwal/
│       ├── html/
│       ├── xml/
│       ├── latex/
│       └── markdown/
│
└── 200_sample/
```

Only `la_360k_sample/arxiv_extracted_urls_5_formats_360k.json` is required to reproduce the final visualization. The remaining files are provided for transparency and to enable rerunning the preprocessing pipeline from scratch.
