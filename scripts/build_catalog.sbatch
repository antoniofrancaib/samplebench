#!/bin/bash
#SBATCH --job-name=samplebench-catalog
#SBATCH --partition=gpu
#SBATCH --qos=debug
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=/mnt/storage01/home/afranca/samplebench/catalog_build_%j.log
#SBATCH --error=/mnt/storage01/home/afranca/samplebench/catalog_build_%j.log

set -euo pipefail

SOURCE_ROOT=/mnt/storage01/home/afranca/dLMbench/data/samples
REPO_ROOT=/mnt/storage01/home/afranca/samplebench
COMMIT=${SAMPLEBENCH_SOURCE_COMMIT:?SAMPLEBENCH_SOURCE_COMMIT is required}
JOB_ROOT=/scratch/afranca/samplebench-catalog-${SLURM_JOB_ID}
RESULT_ARCHIVE=${REPO_ROOT}/catalog_release_${SLURM_JOB_ID}.tar.gz
STALE_JOB_ROOT=${SAMPLEBENCH_STALE_JOB_ROOT:-}

cleanup() {
  case "${JOB_ROOT}" in
    /scratch/afranca/samplebench-catalog-[0-9]*) rm -rf "${JOB_ROOT}" ;;
    *) echo "refusing unsafe cleanup path: ${JOB_ROOT}" >&2; exit 2 ;;
  esac
}
trap cleanup EXIT

test "$(hostname -s)" != login01
test "$(hostname -s)" != login02
if [ -n "${STALE_JOB_ROOT}" ]; then
  test "${STALE_JOB_ROOT}" = /scratch/afranca/samplebench-catalog-155975
  rm -rf "${STALE_JOB_ROOT}"
  test ! -e "${STALE_JOB_ROOT}"
fi
test ! -e "${JOB_ROOT}"
mkdir -p "${JOB_ROOT}/source" "${JOB_ROOT}/canonical" "${JOB_ROOT}/output"
git -C "${REPO_ROOT}" show "${COMMIT}:scripts/build_catalog.py" > "${JOB_ROOT}/source/build_catalog.py"
git -C "${REPO_ROOT}" show "${COMMIT}:scripts/arm-evidence-r5.json" > "${JOB_ROOT}/source/arm-evidence-r5.json"
cp -R --no-preserve=mode,ownership,timestamps "${SOURCE_ROOT}/." "${JOB_ROOT}/canonical/"
/usr/bin/python3 "${JOB_ROOT}/source/build_catalog.py" \
  --source "${JOB_ROOT}/canonical" \
  --evidence "${JOB_ROOT}/source/arm-evidence-r5.json" \
  --output "${JOB_ROOT}/output" \
  --server-output "${JOB_ROOT}/output/catalog.js"
tar -C "${JOB_ROOT}/output" -czf "${JOB_ROOT}/catalog-release.tar.gz" data.js data-public.js data-release.json catalog.js
cp "${JOB_ROOT}/catalog-release.tar.gz" "${RESULT_ARCHIVE}"
sha256sum "${RESULT_ARCHIVE}"
cleanup
trap - EXIT
