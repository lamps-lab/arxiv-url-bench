#!/bin/bash

#SBATCH --job-name=stage1_extract_textwal_urls
#SBATCH -c 2
#SBATCH --mem=32G
#SBATCH --time=144:00:00
#SBATCH --partition=main
#SBATCH --output=/data/la_360k_sample/intermediate_results/stage1_extract_textwal_urls%j.out

# Environment setup
enable_lmod
module load container_env python3/2023.2-py310

# Execute parsing script inside target isolated env
crun -p ~/envs/r_004 python stage1_extract_textwal_urls.py