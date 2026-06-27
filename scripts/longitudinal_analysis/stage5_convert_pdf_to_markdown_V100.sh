#!/bin/bash

#SBATCH -c 8
#SBATCH -p gpu
#SBATCH --gres gpu:1
#SBATCH --time=7-00:00:00
#SBATCH --output=/data/la_360k_sample/intermediate_results/logs/v100_%A_%a.out

# ── 40-Worker Array Control ─────────────────────────────────────
# Launches 40 distinct jobs simultaneously. Each job automatically 
# claims its own individual GPU allocation.
# Worker IDs 0 to 39
#SBATCH --array=0-39%10   # 40 total tasks, but maximum 10 active concurrently

export TQDM_DISABLE=1
export SLURM_ARRAY_TASK_COUNT=80         # Manually force the script to know there are 80 total workers!

# Initialize runtime container engine paths
enable_lmod
module load container_env pytorch-gpu/2.5.1

# Point to deep learning drivers
export CUDA_HOME=/cm/shared/applications/cuda-toolkit/12.4.0/
export XLA_FLAGS=--xla_gpu_cuda_data_dir=$CUDA_HOME

# Ensure logs directory exists
mkdir -p /data/la_360k_sample/intermediate_results/logs

# Execute parsing script inside target isolated env
crun -p ~/envs/r_004_marker python /scripts/longitudinal_analysis/stage5_convert_pdf_to_markdown.py