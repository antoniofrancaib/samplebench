#!/usr/bin/env bash
#SBATCH --job-name=samplebench-gen
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=12:00:00
#SBATCH --partition=gpu
#SBATCH --qos=normal
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --gres=gpu:1

set -euo pipefail

module load python/3.12.12

: "${SUITE_CONFIG:?set SUITE_CONFIG}"
: "${CHECKPOINTS_CONFIG:=data/configs/checkpoints.yaml}"
: "${MODEL_ID:?set MODEL_ID}"
: "${SAMPLES_ROOT:=data/samples}"
: "${LM_BENCH_GENERATE_PYTHON:=python3}"
export LM_BENCH_GENERATE_PYTHON
: "${LM_BENCH_CLI_PYTHON:=${LM_BENCH_GENERATE_PYTHON}}"

cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
mkdir -p slurm/logs

# Resolve SUITE_CONFIG name → file path if not already a path
if [[ "${SUITE_CONFIG}" != */* && "${SUITE_CONFIG}" != *.yaml ]]; then
    SUITE_CONFIG="data/configs/suites/${SUITE_CONFIG}.yaml"
fi

PYTHONPATH=engine "${LM_BENCH_CLI_PYTHON}" -m lm_bench.cli generate \
  --checkpoints "${CHECKPOINTS_CONFIG}" \
  --suite "${SUITE_CONFIG}" \
  --models "${MODEL_ID}" \
  --output-root "${SAMPLES_ROOT}"
