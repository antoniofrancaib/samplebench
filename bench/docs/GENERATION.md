# SampleBench v2 — Generation Choices and Rationale

## Study design

SampleBench v2 is a **pure diffusion-vs-diffusion** human preference study.
All 28 generators use the same OWT-trained base architecture (DIT, ~170 M params) evaluated
on OpenWebText, varying only the **sampler family** and **number of function evaluations (NFE)**.
This isolates the question: *given equal compute budget, which diffusion/flow sampler
produces text that humans prefer?*

AR models and naive baselines are excluded from the v2 voting pool — including them
would let raters use coherence as a confound (AR wins trivially at high NFE), obscuring
the within-diffusion NFE signal we care about.

---

## Model families

| Family | Algorithm | Sampler type | OWT checkpoint |
|---|---|---|---|
| MDLM | absorbing diffusion + score entropy | ancestral / predictor-corrector | kuleshov-group/mdlm-owt (HF) |
| SEDD | score entropy discrete diffusion | ancestral | louaaron/sedd-medium (HF) |
| FLM | flow matching LM | Euler ODE | david3684/flm (GitHub) |
| FMLM | flow matching LM (distilled) | Euler ODE | david3684/flm (GitHub) |
| DUO base | diffusion with uniform-to-data | ancestral | s-sahoo/duo (GitHub) |
| DUO distilled | DUO + distillation | Euler ODE | s-sahoo/duo (GitHub) |

MDLM, SEDD, and DUO base are classic discrete diffusion models.
FLM and FMLM are flow-matching models; FMLM is the distilled version of FLM.
DUO distilled is the distilled version of DUO base.

---

## NFE sweep design

The NFE grid was chosen to span three orders of magnitude:

| Family | NFE values | Rationale |
|---|---|---|
| MDLM | 8, 32, 128, 512, 1024 | Full sweep; known to benefit from many steps |
| SEDD | 8, 32, 128, 512, 1024 | Same as MDLM for direct comparison |
| FLM | 8, 32, 128, 512, 1024 | Flow matching; efficiency peaks at moderate NFE |
| FMLM | 1, 4, 8, 16, 32 | Distilled model: designed to work at 1–32 NFE |
| DUO base | 8, 32, 128, 512, 1024 | Same sweep as MDLM/SEDD |
| DUO distilled | 8, 16, 32 | Distilled: meaningful range is 8–32 |

Low end (8 NFE) tests whether distillation closes the quality gap.
High end (512/1024 NFE) tests asymptotic quality of the base models.

---

## Fixed controls

To isolate NFE as the variable:

- **Seed**: fixed at 1 for all jobs.
- **Sequence length**: 1024 GPT-2 tokens for all samples.
- **Data split**: OWT validation (`openwebtext-split`).
- **EMA weights**: used for all models (`eval.disable_ema=false`).
- **Display window**: ~256-token excerpt shown to voters (length confound control,
  implemented in `bench/pipeline/build_frontend.py`).
- **Batch randomization**: voter sees pairs drawn uniformly at random from the pool;
  neither model ID nor NFE is disclosed.

---

## Backend

All generators use the `flm-hydra` backend, which invokes
`third_party/flm/main.py` via Hydra. The generate_corpus.py wrapper in lm-bench
translates the lm-bench checkpoint registry entry into the correct Hydra overrides.

Key override mapping:

| lm-bench field | Hydra override |
|---|---|
| `generation.algo` | `algo=<algo>` |
| `generation.nfe` | `sampling.steps=<nfe>` |
| `generation.eval_batch_size` | `loader.eval_batch_size=<n>` |
| checkpoint path (symlink resolved) | `eval.checkpoint_path=<abs_path>` |

Symlinks under `checkpoints/owt/` resolve to `checkpoints/raw/local_pc/*.ckpt`
(local copies downloaded from the sources listed above).

---

## Cluster

- Partition: `h100` (H100 NVL, sm_90, CUDA 13.0 forward-compatible with driver 595)
- Node exclusion: `--exclude=H100Azure04` (broken module system, exit 127)
- QOS: `normal` (max 4 concurrent GPUs)
- venv: `$LM_BENCH_VENV`
- Wall time: 12 h (sufficient for all NFE levels)

The RTX PRO 6000 Blackwell (`gpu` partition) cannot initialize CUDA 13.0 (`cudaErrorUnknown`
on `_cuda_init()`), so all generation uses the H100 partition exclusively.

---

## Reproducibility

To regenerate from scratch:

```bash
cd ~/lm-bench

# Smoke test (8 samples, FMLM 1-NFE)
sbatch --partition=h100 --exclude=H100Azure04 \
  --export=SUITE_CONFIG=configs/sample_suites/owt_L1024_diffusion_v2_debug.yaml,\
MODEL_ID=owt_v2_fmlm_1_nfe,SAMPLES_ROOT=results/samples/v2,\
LM_BENCH_GENERATE_PYTHON=$LM_BENCH_VENV/bin/python \
  workflows/slurm/generate.sbatch

# Full fan-out (28 jobs)
for MODEL_ID in <...28 IDs...>; do
  sbatch --partition=h100 --exclude=H100Azure04 \
    --export=SUITE_CONFIG=configs/sample_suites/owt_L1024_diffusion_v2.yaml,\
MODEL_ID=${MODEL_ID},SAMPLES_ROOT=results/samples/v2,\
LM_BENCH_GENERATE_PYTHON=$LM_BENCH_VENV/bin/python \
    workflows/slurm/generate.sbatch
done
```

See `bench/SAMPLES.md` for the full ID list and checkpoint provenance.
