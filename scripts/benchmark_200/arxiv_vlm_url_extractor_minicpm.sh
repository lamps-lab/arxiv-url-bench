#!/bin/bash

#SBATCH -c 32
#SBATCH -p high-gpu-mem
#SBATCH --gres gpu:1
#SBATCH --output=arxiv_vlm_url_extractor_minicpm.out

enable_lmod
module load container_env pytorch-gpu/2.5.1

export CUDA_HOME=/cm/shared/applications/cuda-toolkit/12.4.0/
export XLA_FLAGS=--xla_gpu_cuda_data_dir=$CUDA_HOME

crun.pytorch-gpu -p ~/envs/vlm_minicpm python arxiv_vlm_url_extractor_minicpm.py --device='cuda'