# SampleBench — human-preference ↔ metric correlation

> **Simulated human votes.** Latent per-model quality came from an independent fluency prior, *not* from any metric below; votes were drawn from a Bradley–Terry/Elo model with rater noise, ties and both-bad outcomes. Numbers illustrate the pipeline, not real opinion.

- votes: **14,000** (13,115 decisive) over **13** models, 280 voters

- BT recovery of simulated truth: Spearman ρ = **1.000** (95% CI 0.978–1.000) — the fit reconstructs the planted ranking.


## 1. Recovered human score (Bradley–Terry, Elo scale)

| model | human Elo (95% CI) | true (sim) |
|---|---|---|
| owt_data_train | 1752 (1733–1772) | 1700 |
| owt_ar_base | 1679 (1664–1697) | 1620 |
| owt_flm_1024_nfe | 1619 (1605–1634) | 1545 |
| owt_duo_base_1024_nfe | 1590 (1575–1605) | 1530 |
| owt_sedd_1024_nfe | 1580 (1563–1594) | 1515 |
| owt_mdlm_1024_nfe | 1578 (1565–1593) | 1500 |
| owt_fmlm_32_nfe | 1544 (1528–1558) | 1465 |
| owt_mirror_5000 | 1501 (1486–1514) | 1430 |
| owt_fmlm_4_nfe | 1450 (1435–1467) | 1380 |
| owt_phrase_bank_5000 | 1431 (1417–1448) | 1360 |
| owt_fmlm_1_nfe | 1372 (1357–1389) | 1300 |
| owt_topk_iid_k64 | 1251 (1231–1269) | 1160 |
| owt_periodic_k_400 | 1153 (1130–1175) | 1100 |

## 2. Which metric ranks models like humans? (model-level)

Spearman ρ / Kendall τ between human Elo and each model-mean metric (n = 13 models), ranked by |ρ|.

| metric | n models | ρ (95% CI) | τ | orientation |
|---|---|---|---|---|
| gen_ppl | 4 | -0.800 (-0.80,-0.80) | -0.667 | lower=better |
| js_to_human | 13 | -0.709 (-0.74,-0.69) | -0.538 | lower=better |
| distinct_1 | 13 | +0.621 (+0.55,+0.64) | +0.436 | higher=better |
| char_len | 13 | +0.615 (+0.57,+0.64) | +0.436 | higher=better |
| unigram_entropy | 13 | +0.297 (+0.25,+0.31) | +0.256 | higher=better |
| distinct_2 | 13 | +0.291 (+0.24,+0.31) | +0.205 | higher=better |
| zipf_coef | 13 | -0.044 (-0.06,+0.03) | -0.026 | higher=better |
| rep_4gram | 13 | +0.006 (+0.01,+0.04) | +0.013 | lower=better |
| entropy | 4 | +0.000 (+0.00,+0.00) | +0.000 | higher=better |

## 3. Does the metric pick the human winner? (sample-level)

Pairwise accuracy: fraction of decisive battles where the metric's preferred side matches the human pick (0.5 = chance).

| metric | pairwise acc | direction | n |
|---|---|---|---|
| js_to_human | 0.674 | lower=better | 13,115 |
| distinct_1 | 0.622 | higher=better | 13,112 |
| char_len | 0.617 | higher=better | 13,108 |
| distinct_2 | 0.596 | higher=better | 13,110 |
| word_count | 0.562 | higher=better | 13,044 |
| rep_4gram | 0.554 | lower=better | 10,855 |
| unigram_entropy | 0.545 | higher=better | 13,114 |
| zipf_coef | 0.514 | higher=better | 13,113 |

## 4. Learned combiner (logistic on metric deltas)

5-fold CV: accuracy **0.712** ± 0.009, AUC **0.784** ± 0.009. Standardized weights (sign = direction, |·| = importance):

| metric | weight |
|---|---|
| zipf_coef | +1.453 |
| distinct_1 | +1.006 |
| js_to_human | -0.988 |
| distinct_2 | -0.827 |
| word_count | -0.673 |
| char_len | +0.620 |
| unigram_entropy | +0.571 |
| rep_4gram | +0.151 |

## Takeaways

- Best *single* model-level metric: **gen_ppl** (|ρ| = 0.80, lower=better).
- Best single sample-level discriminator: **js_to_human** (acc = 0.67).
- A simple logistic blend reaches **0.71** pairwise accuracy — a learned composite beats any one metric.
- Swap the simulated votes for the real Supabase table to rerun this verbatim; add real `gen_ppl`/MAUVE once the corpus is scored on GPU.

