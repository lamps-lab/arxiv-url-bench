#!/bin/bash
#SBATCH --job-name=latexml_200
#SBATCH --output=logs/slurm_latexml.out
#SBATCH --error=logs/slurm_latexml.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=1-00:00:00
#SBATCH --mem=4G

# Ensure logs directory exists
mkdir -p logs

# Environment Setup
enable_lmod
module load container_env python3/2023.2-py310 

# Run the python script
python3 convert_latex_to_html.py