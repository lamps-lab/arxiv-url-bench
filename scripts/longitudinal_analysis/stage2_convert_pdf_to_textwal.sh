#!/bin/bash
#SBATCH --job-name=pdf_text_bulk
#SBATCH --output=/data/la_360k_sample/intermediate_results/logs_textwal/slurm_%A_%a.out
#SBATCH --error=/data/la_360k_sample/intermediate_results/logs_textwal/slurm_%A_%a.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=7-00:00:00
#SBATCH --mem=4G
#SBATCH --array=1-1000%100

# Environment Setup 
enable_lmod
module load container_env

MANIFEST="/data/la_360k_sample/intermediate_results/pdf_manifest.txt"
TOTAL_LINES=$(wc -l < "$MANIFEST")

# Stride logic automatically sizing data chunks per task array index
STRIDE=468 

START_LINE=$(( (SLURM_ARRAY_TASK_ID - 1) * STRIDE + 1 ))
END_LINE=$(( START_LINE + STRIDE - 1 ))

if [ "$START_LINE" -gt "$TOTAL_LINES" ]; then
    exit 0
fi

chmod +x stage1_convert_pdf_to_textwal.py

# Slice manifest lines and distribute to the worker process
sed -n "${START_LINE},${END_LINE}p" "$MANIFEST" | while read -r LINE; do
    [ -z "$LINE" ] && continue
    
    # Parse out delimited fields
    YEAR=$(echo "$LINE" | cut -d'|' -f1)
    ARXIV_ID=$(echo "$LINE" | cut -d'|' -f2)
    PDF_PATH=$(echo "$LINE" | cut -d'|' -f3)
    
    # RUN VIA CONTAINER ENVIRONMENT: Using crun ensures PyMuPDF (fitz) is available
    crun -p ~/envs/r_004 python stage1_convert_pdf_to_textwal.py "$YEAR" "$ARXIV_ID" "$PDF_PATH"
done