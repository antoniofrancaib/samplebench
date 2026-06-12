# SampleBench — human-preference ↔ metric correlation

> **Simulated votes** (latent quality from an independent fluency prior, not from any metric). Swap for the real Supabase table to rerun verbatim.

- votes: **14,000** (13,267 decisive) over **9** models
- metrics: canonical lm-bench paper metrics (suite `owt_L1024_paper`)
- BT recovery of simulated truth: Spearman ρ = **1.000** (95% CI 0.983–1.000)

## 1. Recovered human score (Bradley–Terry, Elo scale)

| model | human Elo (95% CI) | true |
|---|---|---|
| OWT train data | 1680 (1669–1693) | 1700 |
| AR OWT | 1606 (1595–1617) | 1620 |
| FLM 1024-NFE | 1544 (1532–1554) | 1545 |
| Duo OWT 1024-NFE | 1526 (1515–1536) | 1530 |
| SEDD OWT 1024-NFE | 1503 (1491–1515) | 1515 |
| MDLM OWT 1024-NFE | 1499 (1487–1510) | 1500 |
| FMLM 32-NFE | 1464 (1453–1474) | 1465 |
| FMLM 4-NFE | 1376 (1363–1387) | 1380 |
| FMLM 1-NFE | 1303 (1292–1315) | 1300 |

## 2. Which metric ranks models like humans? (model-level)

Spearman ρ / Kendall τ between human Elo and each canonical metric, ranked by |ρ|.

| metric | n | ρ (95% CI) | τ | orientation |
|---|---|---|---|---|
| EnergyDist | 9 | -0.900 (-0.90,-0.88) | -0.833 | lower=better |
| GradMoment | 9 | -0.833 (-0.85,-0.83) | -0.667 | lower=better |
| FMTyp-p | 9 | +0.817 (+0.78,+0.82) | +0.722 | higher=better |
| MAUVE | 9 | +0.783 (+0.77,+0.78) | +0.667 | higher=better |
| gen-PPL | 9 | -0.750 (-0.82,-0.75) | -0.667 | lower=better |
| Rep-4 | 9 | +0.746 (+0.75,+0.78) | +0.583 | lower=better |
| Rep-3 | 9 | +0.700 (+0.70,+0.75) | +0.556 | lower=better |
| H (nats) | 9 | +0.517 (+0.40,+0.52) | +0.333 | higher=better |
| Rep-2 | 9 | +0.317 (+0.32,+0.42) | +0.278 | lower=better |
| Rep-1 | 9 | -0.250 (-0.25,-0.13) | -0.167 | lower=better |

## 3. Does the metric pick the human winner? (per-battle)

Each side scored by its model-level metric; accuracy = fraction of decisive battles matching the human pick.

| metric | acc | n |
|---|---|---|
| EnergyDist | 0.671 | 13,267 |
| GradMoment | 0.666 | 13,267 |
| FMTyp-p | 0.662 | 13,267 |
| MAUVE | 0.660 | 13,267 |
| gen-PPL | 0.655 | 13,267 |
| H (nats) | 0.577 | 13,267 |
| Rep-1 | 0.520 | 13,267 |
| Rep-2 | 0.422 | 13,267 |
| Rep-3 | 0.349 | 13,267 |
| Rep-4 | 0.331 | 12,150 |

## 4. Learned combiner (logistic on metric deltas)

Over 13,267 fully-scored battles — 5-fold CV: accuracy **0.679** ± 0.005, AUC **0.736** ± 0.007.

| metric | weight |
|---|---|
| Rep-2 | -0.984 |
| FMTyp-p | +0.609 |
| H (nats) | -0.595 |
| gen-PPL | -0.545 |
| Rep-3 | +0.513 |
| Rep-4 | +0.467 |
| EnergyDist | +0.433 |
| GradMoment | -0.383 |
| Rep-1 | -0.115 |
| MAUVE | -0.109 |

## Takeaways

- Best single model-level metric: **EnergyDist** (|ρ| = 0.90, lower=better).
- Best single per-battle discriminator: **EnergyDist** (acc = 0.67).
- A logistic blend of the paper metrics reaches **0.68** accuracy / **0.74** AUC.
- Metrics are model-level (corpus-first, as in lm-bench); per-sample gen_ppl/rep would enable finer sample-level analysis if the runners are extended to dump per-sample scores.

