# SampleBench — human-preference ↔ metric correlation

> **Simulated votes** (latent quality from an independent fluency prior, not from any metric). Swap for the real Supabase table to rerun verbatim.

- votes: **20,000** (17,978 decisive) over **28** models
- metrics: canonical lm-bench paper metrics (suite `owt_L1024_diffusion_v2`)
- BT recovery of simulated truth: Spearman ρ = **0.986** (95% CI 0.953–0.985)

## 1. Recovered human score (Bradley–Terry, Elo scale)

| model | human Elo (95% CI) | true |
|---|---|---|
| FLM 1024-NFE | 1601 (1583–1618) | 1548 |
| FLM 512-NFE | 1578 (1558–1594) | 1530 |
| DUO Base 1024-NFE | 1571 (1554–1588) | 1525 |
| MDLM 1024-NFE | 1566 (1551–1582) | 1512 |
| SEDD 1024-NFE | 1563 (1543–1579) | 1518 |
| DUO Base 512-NFE | 1553 (1536–1567) | 1500 |
| MDLM 512-NFE | 1545 (1529–1563) | 1490 |
| SEDD 512-NFE | 1533 (1517–1551) | 1495 |
| FLM 128-NFE | 1532 (1512–1550) | 1505 |
| FLM 32-NFE | 1530 (1514–1546) | 1472 |
| FMLM 32-NFE | 1523 (1506–1539) | 1480 |
| DUO Distilled 32-NFE | 1518 (1499–1534) | 1485 |
| DUO Distilled 16-NFE | 1515 (1499–1532) | 1465 |
| DUO Base 128-NFE | 1499 (1482–1514) | 1455 |
| FMLM 16-NFE | 1489 (1471–1507) | 1460 |
| FMLM 8-NFE | 1486 (1471–1501) | 1440 |
| MDLM 128-NFE | 1483 (1466–1499) | 1445 |
| FLM 8-NFE | 1478 (1461–1493) | 1432 |
| DUO Distilled 8-NFE | 1476 (1458–1493) | 1428 |
| SEDD 128-NFE | 1474 (1458–1491) | 1450 |
| DUO Base 32-NFE | 1466 (1450–1483) | 1420 |
| MDLM 32-NFE | 1460 (1443–1477) | 1408 |
| SEDD 32-NFE | 1453 (1436–1471) | 1415 |
| FMLM 4-NFE | 1452 (1436–1469) | 1395 |
| DUO Base 8-NFE | 1426 (1408–1444) | 1380 |
| SEDD 8-NFE | 1420 (1403–1438) | 1375 |
| MDLM 8-NFE | 1411 (1394–1430) | 1368 |
| FMLM 1-NFE | 1402 (1384–1420) | 1340 |

## 2. Which metric ranks models like humans? (model-level)

Spearman ρ / Kendall τ between human Elo and each canonical metric, ranked by |ρ|.

| metric | n | ρ (95% CI) | τ | orientation |
|---|---|---|---|---|
| gen-PPL | 28 | -0.660 (-0.70,-0.60) | -0.513 | lower=better |
| Rep-3 | 28 | +0.653 (+0.58,+0.70) | +0.497 | lower=better |
| Rep-4 | 28 | +0.553 (+0.48,+0.61) | +0.431 | lower=better |
| EnergyDist | 28 | -0.494 (-0.56,-0.43) | -0.349 | lower=better |
| MAUVE | 28 | +0.441 (+0.37,+0.52) | +0.307 | higher=better |
| GradMoment | 28 | -0.426 (-0.50,-0.36) | -0.302 | lower=better |
| Rep-2 | 28 | +0.420 (+0.35,+0.48) | +0.331 | lower=better |
| Rep-1 | 28 | +0.373 (+0.31,+0.43) | +0.286 | lower=better |
| H (nats) | 28 | -0.350 (-0.41,-0.28) | -0.275 | higher=better |
| FMTyp-p | 28 | +0.345 (+0.28,+0.42) | +0.222 | higher=better |

## 3. Does the metric pick the human winner? (per-battle)

Each side scored by its model-level metric; accuracy = fraction of decisive battles matching the human pick.

| metric | acc | n |
|---|---|---|
| gen-PPL | 0.563 | 17,978 |
| EnergyDist | 0.547 | 17,978 |
| MAUVE | 0.542 | 17,978 |
| GradMoment | 0.541 | 17,978 |
| FMTyp-p | 0.534 | 17,978 |
| H (nats) | 0.469 | 17,978 |
| Rep-1 | 0.466 | 17,978 |
| Rep-2 | 0.461 | 17,921 |
| Rep-4 | 0.448 | 16,591 |
| Rep-3 | 0.439 | 17,785 |

## 4. Learned combiner (logistic on metric deltas)

Over 17,978 fully-scored battles — 5-fold CV: accuracy **0.579** ± 0.007, AUC **0.608** ± 0.010.

| metric | weight |
|---|---|
| Rep-1 | -0.740 |
| Rep-3 | +0.658 |
| FMTyp-p | -0.609 |
| Rep-4 | -0.494 |
| gen-PPL | -0.488 |
| H (nats) | -0.406 |
| EnergyDist | -0.263 |
| GradMoment | -0.217 |
| Rep-2 | +0.117 |
| MAUVE | +0.110 |

## Takeaways

- Best single model-level metric: **gen-PPL** (|ρ| = 0.66, lower=better).
- Best single per-battle discriminator: **gen-PPL** (acc = 0.56).
- A logistic blend of the paper metrics reaches **0.58** accuracy / **0.61** AUC.
- Metrics are model-level (corpus-first, as in lm-bench); per-sample gen_ppl/rep would enable finer sample-level analysis if the runners are extended to dump per-sample scores.

