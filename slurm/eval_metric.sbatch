#!/usr/bin/env bash
#SBATCH --job-name=samplebench-eval
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:1

set -euo pipefail

: "${METRIC:?set METRIC}"
: "${SUITE_CONFIG:?set SUITE_CONFIG}"
: "${METRICS_CONFIG:=data/configs/metrics.yaml}"
: "${MODELS:=all}"
: "${SAMPLES_ROOT:=data/samples}"
: "${METRICS_ROOT:=data/metrics}"

cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
mkdir -p slurm/logs

module load python/3.12.12
source /mnt/nfs/vol8t/home/afranca/venvs/lm-bench-cu130/bin/activate

REFERENCE_ARGS=()
if [[ -n "${REFERENCE_CORPUS:-}" ]]; then
  REFERENCE_ARGS=(--reference-corpus "${REFERENCE_CORPUS}")
fi

PYTHONPATH=engine python3 -m lm_bench.cli eval \
  --metric "${METRIC}" \
  --suite "${SUITE_CONFIG}" \
  --metrics-config "${METRICS_CONFIG}" \
  --samples-root "${SAMPLES_ROOT}" \
  --output-root "${METRICS_ROOT}" \
  --models ${MODELS//,/ } \
  "${REFERENCE_ARGS[@]}" \
  "$@"
