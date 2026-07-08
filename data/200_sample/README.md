## Dataset Download

The benchmark dataset containing the 200 sampled arXiv papers and the intermediate artifacts (PDFs and corresponding LaTeX source files) can be downloaded from Hugging Face:

https://huggingface.co/datasets/dblind-data/arxiv-url-bench-hf/blob/main/arxiv-200-benchmark/arxiv-url-bench-200-raw-files.tar.gz

After downloading, place the contents under the repository's `data/` directory so that the directory structure matches the following:

```text id="fbgvkj"
data/
└── 200_sample/
    ├── arxiv_extracted_urls_all_formats_200.json   # FINAL combined output
    │
    ├── intermediate_results/                        # one JSON per format
    │   ├── stage_text_urls.json
    │   ├── stage_textwal_pymupdf_urls.json
    │   ├── stage_textwal_pypdf_urls.json
    │   ├── stage_textwal_pdfminer_urls.json
    │   ├── stage_textwalcl_urls.json
    │   ├── stage_html_urls.json
    │   ├── stage_latex_urls.json
    │   ├── stage_xml_grobid_urls.json
    │   ├── stage_vlm_qwen_urls.json
    │   ├── stage_vlm_deepseek_urls.json
    │   ├── stage_vlm_minicpm_urls.json
    │   └── stage_markdown_urls.json
    │
    └── raw_files/
        ├── pdf/             # REQUIRED input: 200 benchmark PDFs (<arxiv_id>.pdf)
        ├── html/            # generated
        ├── latex/           # REQUIRED input: corresponding LaTeX source, one subfolder per paper
        ├── text/            # generated
        ├── textwal/         # generated (pymupdf / pypdf / pdfminer subfolders)
        ├── xml/             # generated (GROBID TEI output)
        ├── markdown/        # generated (Marker output)
        └── vlm_png/         # generated (page images shared by all VLMs)
│
└── la_360k_sample/
```

Only data/200_sample/raw_files/pdf/ and data/200_sample/raw_files/latex/ need to be populated before running this notebook. These directories should contain the 200-paper benchmark downloaded from the Hugging Face repository. All remaining directories and intermediate outputs are created automatically during notebook execution.