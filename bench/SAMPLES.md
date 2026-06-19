# SampleBench v2 — Sample Manifest

Generated 2026-06-17.  
Suite: `owt_L1024_diffusion_v2` · Dataset: OpenWebText · Length: 1 024 tokens · Seed: 1  
Cluster: AITHYRA h100 partition (H100 NVL, sm_90, driver 595) · `--exclude=H100Azure04`  
Venv: `/mnt/nfs/vol8t/home/afranca/venvs/lm-bench-cu130` (PyTorch 2.11.0+cu130)  
Output root: `~/lm-bench/results/samples/v2/`

---

## Generator × NFE grid (28 configurations)

### MDLM — 5 NFE levels
| Model ID | NFE | Checkpoint | Source |
|---|---|---|---|
| `owt_v2_mdlm_8_nfe` | 8 | `checkpoints/owt/mdlm/base/model.ckpt` → `raw/local_pc/mdlm-003.ckpt` (2 716 MB) | [kuleshov-group/mdlm-owt](https://huggingface.co/kuleshov-group/mdlm-owt) |
| `owt_v2_mdlm_32_nfe` | 32 | same | same |
| `owt_v2_mdlm_128_nfe` | 128 | same | same |
| `owt_v2_mdlm_512_nfe` | 512 | same | same |
| `owt_v2_mdlm_1024_nfe` | 1024 | same | same |

### SEDD — 5 NFE levels
| Model ID | NFE | Checkpoint | Source |
|---|---|---|---|
| `owt_v2_sedd_8_nfe` | 8 | `checkpoints/owt/sedd/base/model.ckpt` → `raw/local_pc/sedd-002.ckpt` (2 716 MB) | [louaaron/sedd-medium](https://huggingface.co/louaaron/sedd-medium) |
| `owt_v2_sedd_32_nfe` | 32 | same | same |
| `owt_v2_sedd_128_nfe` | 128 | same | same |
| `owt_v2_sedd_512_nfe` | 512 | same | same |
| `owt_v2_sedd_1024_nfe` | 1024 | same | same |

### FLM (flow LM, base) — 5 NFE levels
| Model ID | NFE | Checkpoint | Source |
|---|---|---|---|
| `owt_v2_flm_8_nfe` | 8 | `checkpoints/owt/flm/base/model.ckpt` → `raw/local_pc/owt_flm-001.ckpt` (4 752 MB) | [david3684/flm](https://github.com/david3684/flm) |
| `owt_v2_flm_32_nfe` | 32 | same | same |
| `owt_v2_flm_128_nfe` | 128 | same | same |
| `owt_v2_flm_512_nfe` | 512 | same | same |
| `owt_v2_flm_1024_nfe` | 1024 | same | same |

### FMLM (distilled) — 5 NFE levels
| Model ID | NFE | Checkpoint | Source |
|---|---|---|---|
| `owt_v2_fmlm_1_nfe` | 1 | `checkpoints/owt/fmlm/distilled/model.ckpt` → `raw/local_pc/owt_fmlm-004.ckpt` (4 753 MB) | [david3684/flm](https://github.com/david3684/flm) |
| `owt_v2_fmlm_4_nfe` | 4 | same | same |
| `owt_v2_fmlm_8_nfe` | 8 | same | same |
| `owt_v2_fmlm_16_nfe` | 16 | same | same |
| `owt_v2_fmlm_32_nfe` | 32 | same | same |

### DUO base — 5 NFE levels
| Model ID | NFE | Checkpoint | Source |
|---|---|---|---|
| `owt_v2_duo_base_8_nfe` | 8 | `checkpoints/owt/duo/base/model.ckpt` → `raw/local_pc/duo-002.ckpt` (2 716 MB) | [s-sahoo/duo](https://github.com/s-sahoo/duo) |
| `owt_v2_duo_base_32_nfe` | 32 | same | same |
| `owt_v2_duo_base_128_nfe` | 128 | same | same |
| `owt_v2_duo_base_512_nfe` | 512 | same | same |
| `owt_v2_duo_base_1024_nfe` | 1024 | same | same |

### DUO distilled — 3 NFE levels
| Model ID | NFE | Checkpoint | Source |
|---|---|---|---|
| `owt_v2_duo_distilled_8_nfe` | 8 | `checkpoints/owt/duo/distilled/model.ckpt` → `raw/local_pc/duo-distilled-001.ckpt` (2 716 MB) | [s-sahoo/duo](https://github.com/s-sahoo/duo) |
| `owt_v2_duo_distilled_16_nfe` | 16 | same | same |
| `owt_v2_duo_distilled_32_nfe` | 32 | same | same |

---

## Sampler configuration

All generators use the `flm-hydra` backend (`third_party/flm/main.py`).

| Parameter | Value | Notes |
|---|---|---|
| `mode` | `sample_eval` | generation only, no perplexity eval |
| `model` | `small` | ~170 M params, DIT backbone |
| `model.length` | 1024 | tokens per sample |
| `data` | `openwebtext-split` | OWT validation split (no contamination) |
| `loader.eval_batch_size` | 16–32 | set per model in checkpoints.yaml |
| `eval.disable_ema` | false | EMA weights used for all models |
| `eval.compute_generative_perplexity` | false | computed offline by bench/pipeline |
| `+wandb.offline` | true | W&B logging suppressed |
| `sampling.gamma` | 1.0 | (FMLM) |

NFE is passed as `sampling.steps=<nfe>` and controls the number of denoising steps.

---

## Output paths

Each generator writes two files:

```
results/samples/v2/owt/owt_L1024_diffusion_v2/<model_id>/
  samples.jsonl    # 1024 rows, one sample per line
  manifest.json    # provenance: model_id, checkpoint, sampler config, seed, counts
```

Smoke-test output (8 samples, debug suite) is in `owt_L1024_diffusion_v2_debug/`.

---

## Job accounting

| Batch | Jobs | Status |
|---|---|---|
| Smoke test | 72080 | COMPLETED (exit 0) |
| Wave 1 (node bug) | 72081–72108 | 72082,72085–72091 FAILED (H100Azure04, exit 127); rest cancelled |
| Wave 2 (--exclude=H100Azure04) | 72081,72083,72084 (running) + 72109–72133 | In flight |

H100Azure04 excluded permanently: `module load` fails on that node (exit 127).
