#!/bin/bash

#SBATCH --job-name=stage3_latex_urls
#SBATCH -c 2
#SBATCH --mem=32G
#SBATCH --time=168:00:00
#SBATCH --partition=main
#SBATCH --output=/data/la_360k_sample/intermediate_results/stage3_latex_urls_%j.out

# Environment setup
enable_lmod
module load container_env python3/2023.2-py310

# Execute parsing script inside target isolated env
crun -p ~/envs/r_004 python stage3_extract_latex_urls.py