#!/bin/bash
# Validate one immutable SampleBench release snapshot on an on-premises node.
# The snapshot and all runtime dependencies stay in job-local scratch.
# No GPU is requested because this is a CPU-only control-plane job.
#SBATCH --job-name=samplebench-r6-verify
#SBATCH --partition=gpu
#SBATCH --qos=debug
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=/mnt/storage01/home/afranca/samplebench/release_verify_%j.log
#SBATCH --error=/mnt/storage01/home/afranca/samplebench/release_verify_%j.log

set -euo pipefail

REPO_ROOT=/mnt/storage01/home/afranca/samplebench
COMMIT=${SAMPLEBENCH_SOURCE_COMMIT:?SAMPLEBENCH_SOURCE_COMMIT is required}
JOB_ROOT=/scratch/afranca/samplebench-r6-verify-${SLURM_JOB_ID}

cleanup() {
  case "${JOB_ROOT}" in
    /scratch/afranca/samplebench-r6-verify-[0-9]*) rm -rf "${JOB_ROOT}" ;;
    *) echo "refusing unsafe cleanup path: ${JOB_ROOT}" >&2; exit 2 ;;
  esac
}
trap cleanup EXIT

test "$(hostname -s)" != login01
test "$(hostname -s)" != login02
test ! -e "${JOB_ROOT}"
mkdir -p "${JOB_ROOT}/repo" "${JOB_ROOT}/npm-cache" "${JOB_ROOT}/playwright"

# Stage precisely the reviewed commit before invoking Node, npm, or a browser.
git -C "${REPO_ROOT}" archive --format=tar "${COMMIT}" | tar -x -C "${JOB_ROOT}/repo"
cd "${JOB_ROOT}/repo"
export CI=1
export NPM_CONFIG_CACHE="${JOB_ROOT}/npm-cache"
export PLAYWRIGHT_BROWSERS_PATH="${JOB_ROOT}/playwright"

node --version
npm --version
npm ci --no-audit --no-fund
npx --no-install playwright install chromium
npm test
npm run build
npm run test:browser
