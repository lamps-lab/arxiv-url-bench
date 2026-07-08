#!/bin/bash

#SBATCH -c 32
#SBATCH -p high-gpu-mem
#SBATCH --gres gpu:1
#SBATCH --output=logs/arxiv_vlm_qwen_%j.out

enable_lmod
module load container_env pytorch-gpu/2.7.1

export CUDA_HOME=/cm/shared/applications/cuda-toolkit/12.6.0/
export XLA_FLAGS=--xla_gpu_cuda_data_dir=$CUDA_HOME

crun.pytorch-gpu -p ~/envs/vlm_qwen python scripts/benchmark_200/arxiv_vlm_url_extractor_qwen.py --device='cuda'