# SampleBench — human-preference ↔ metric correlation

> **Simulated votes** (latent quality from an independent fluency prior, not from any metric). Swap for the real Supabase table to rerun verbatim.

- votes: **20,000** (18,333 decisive) over **37** models
- metrics: canonical lm-bench paper metrics (suite `owt_L1024_paper`)
- BT recovery of simulated truth: Spearman ρ = **0.976** (95% CI 0.951–0.981)

## 1. Recovered human score (Bradley–Terry, Elo scale)

| model | human Elo (95% CI) | true |
|---|---|---|
| OWT train data | 1721 (1699–1741) | 1700 |
| AR OWT | 1660 (1639–1684) | 1620 |
| FLM 1024-NFE | 1584 (1564–1602) | 1548 |
| Duo OWT 1024-NFE | 1581 (1561–1600) | 1530 |
| FLM 1024-NFE | 1575 (1557–1596) | 1545 |
| FLM 512-NFE | 1564 (1545–1586) | 1530 |
| DUO Base 1024-NFE | 1551 (1532–1572) | 1525 |
| SEDD OWT 1024-NFE | 1544 (1523–1562) | 1515 |
| MDLM 1024-NFE | 1544 (1524–1563) | 1512 |
| DUO Base 512-NFE | 1544 (1522–1562) | 1500 |
| SEDD 512-NFE | 1537 (1521–1555) | 1495 |
| MDLM OWT 1024-NFE | 1536 (1517–1554) | 1500 |
| FLM 128-NFE | 1536 (1514–1555) | 1505 |
| SEDD 1024-NFE | 1529 (1510–1554) | 1518 |
| MDLM 512-NFE | 1525 (1505–1544) | 1490 |
| FMLM 32-NFE | 1523 (1500–1543) | 1480 |
| DUO Distilled 16-NFE | 1501 (1481–1522) | 1465 |
| DUO Base 128-NFE | 1495 (1474–1512) | 1455 |
| SEDD 128-NFE | 1494 (1476–1512) | 1450 |
| DUO Distilled 32-NFE | 1491 (1472–1510) | 1485 |
| FMLM 8-NFE | 1485 (1464–1510) | 1440 |
| FLM 32-NFE | 1484 (1457–1505) | 1472 |
| MDLM 128-NFE | 1482 (1461–1502) | 1445 |
| FMLM 32-NFE | 1481 (1460–1500) | 1465 |
| FMLM 16-NFE | 1481 (1461–1502) | 1460 |
| FLM 8-NFE | 1465 (1442–1483) | 1432 |
| DUO Base 32-NFE | 1462 (1442–1482) | 1420 |
| MDLM 32-NFE | 1446 (1427–1465) | 1408 |
| DUO Distilled 8-NFE | 1440 (1417–1460) | 1428 |
| DUO Base 8-NFE | 1433 (1411–1454) | 1380 |
| SEDD 32-NFE | 1432 (1414–1449) | 1415 |
| FMLM 4-NFE | 1425 (1403–1444) | 1395 |
| FMLM 4-NFE | 1418 (1398–1437) | 1380 |
| SEDD 8-NFE | 1405 (1385–1427) | 1375 |
| MDLM 8-NFE | 1400 (1377–1421) | 1368 |
| FMLM 1-NFE | 1396 (1376–1416) | 1340 |
| FMLM 1-NFE | 1332 (1310–1355) | 1300 |

## 2. Which metric ranks models like humans? (model-level)

Spearman ρ / Kendall τ between human Elo and each canonical metric, ranked by |ρ|.

| metric | n | ρ (95% CI) | τ | orientation |
|---|---|---|---|---|
| EnergyDist | 9 | -0.950 (-0.95,-0.88) | -0.889 | lower=better |
| FMTyp-p | 9 | +0.867 (+0.78,+0.87) | +0.778 | higher=better |
| GradMoment | 9 | -0.850 (-0.87,-0.83) | -0.722 | lower=better |
| MAUVE | 9 | +0.817 (+0.77,+0.82) | +0.722 | higher=better |
| Rep-4 | 9 | +0.780 (+0.75,+0.81) | +0.639 | lower=better |
| gen-PPL | 9 | -0.733 (-0.82,-0.73) | -0.611 | lower=better |
| Rep-3 | 9 | +0.733 (+0.70,+0.78) | +0.611 | lower=better |
| H (nats) | 9 | +0.533 (+0.40,+0.53) | +0.389 | higher=better |
| Rep-1 | 9 | -0.283 (-0.28,-0.13) | -0.222 | lower=better |
| Rep-2 | 9 | +0.267 (+0.27,+0.42) | +0.222 | lower=better |

## 3. Does the metric pick the human winner? (per-battle)

Each side scored by its model-level metric; accuracy = fraction of decisive battles matching the human pick.

| metric | acc | n |
|---|---|---|
| GradMoment | 0.669 | 1,024 |
| EnergyDist | 0.668 | 1,024 |
| FMTyp-p | 0.660 | 1,024 |
| MAUVE | 0.657 | 1,024 |
| gen-PPL | 0.656 | 1,024 |
| H (nats) | 0.586 | 1,024 |
| Rep-1 | 0.536 | 1,024 |
| Rep-2 | 0.412 | 1,024 |
| Rep-3 | 0.353 | 1,024 |
| Rep-4 | 0.332 | 938 |

## 4. Learned combiner (logistic on metric deltas)

Over 1,024 fully-scored battles — 5-fold CV: accuracy **0.657** ± 0.018, AUC **0.723** ± 0.017.

| metric | weight |
|---|---|
| Rep-2 | -0.759 |
| gen-PPL | -0.730 |
| Rep-4 | +0.430 |
| H (nats) | -0.325 |
| Rep-3 | +0.279 |
| EnergyDist | -0.130 |
| Rep-1 | -0.061 |
| GradMoment | -0.053 |
| FMTyp-p | +0.044 |
| MAUVE | +0.024 |

## Takeaways

- Best single model-level metric: **EnergyDist** (|ρ| = 0.95, lower=better).
- Best single per-battle discriminator: **GradMoment** (acc = 0.67).
- A logistic blend of the paper metrics reaches **0.66** accuracy / **0.72** AUC.
- Metrics are model-level (corpus-first, as in lm-bench); per-sample gen_ppl/rep would enable finer sample-level analysis if the runners are extended to dump per-sample scores.

