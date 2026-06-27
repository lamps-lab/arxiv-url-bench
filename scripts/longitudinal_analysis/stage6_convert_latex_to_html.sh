#!/bin/bash
#SBATCH --job-name=latexml_bulk
#SBATCH --output=logs/slurm_%A_%a.out
#SBATCH --error=logs/slurm_%A_%a.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=7-00:00:00
#SBATCH --mem=4G
#SBATCH --array=1-1000%100

# Environment Setup
enable_lmod
module load container_env python3/2023.2-py310 

MANIFEST="todo_manifest.txt"
TOTAL_LINES=$(wc -l < "$MANIFEST")

STRIDE=467 

START_LINE=$(( (SLURM_ARRAY_TASK_ID - 1) * STRIDE + 1 ))
END_LINE=$(( START_LINE + STRIDE - 1 ))

if [ "$START_LINE" -gt "$TOTAL_LINES" ]; then
    exit 0
fi

chmod +x stage6_convert_latex_to_html.py

sed -n "${START_LINE},${END_LINE}p" "$MANIFEST" | while read -r REL_PATH; do
    [ -z "$REL_PATH" ] && continue
    
    # RUN NATIVELY: Apptainer is fully visible here!
    python3 stage6_convert_latex_to_html.py "$REL_PATH"
done