# bench/ — data + analysis layer

Turns the **lm-bench** OWT corpus into the artifacts this repo needs: a curated
blind-A/B sample pool for the web UI, an intrinsic-metrics table, and a
human-preference ↔ metric correlation study. Everything here is **generated and
regenerable** — the lm-bench manifests are the single source of truth; never
hand-edit the outputs.

## Layout

```
bench/
  scripts/
    lmbench_common.py      shared paths, config, helpers
    ingest.py              lm-bench → registry + curated K-per-model pool
    compute_metrics.py     curated pool → per-sample + per-model metrics
    build_frontend_data.py curated pool → ../src/data.js (8 real models)
    simulate_votes.py      SIMULATED human votes (Elo/Bradley–Terry)  ⚠ not real data
    correlate.py           votes + metrics → analysis/report.md
  registry/
    checkpoints.json       one row per checkpoint (metadata only — no weights)
    suites.json            per-suite model list w/ manifest summaries
  samples/<suite>/<model>/ curated samples.jsonl + manifest.json  (committed)
  metrics/
    metrics.jsonl          per curated sample
    metrics_by_model.json  per-model means + js_to_human (MAUVE-style)
  analysis/
    report.md              the correlation study (committed)
    sim_truth.json         simulated ground-truth qualities (committed)
    sim_votes.jsonl        simulated votes (git-ignored — regenerate)
```

## Run it

```bash
python3 bench/scripts/ingest.py            # 1. curate pool + registry
python3 bench/scripts/compute_metrics.py   # 2. metrics
python3 bench/scripts/build_frontend_data.py  # 3. regenerate src/data.js
python3 bench/scripts/simulate_votes.py    # 4. (demo) fake the collected votes
python3 bench/scripts/correlate.py         # 5. correlation report
```
Only numpy is required. Steps 1–3 are real; 4–5 are the demonstration that runs
verbatim on real votes once they are collected.

## What's real vs simulated

- **Real:** the sample texts (genuine generations from the OWT checkpoints), the
  registry, and every intrinsic metric (`unigram_entropy`, `distinct_n`,
  `rep_4gram`, `zipf_coef`, `js_to_human`, …). `gen_ppl`/`entropy` are real only
  where the corpus already carries them (flm/fmlm); the rest need a GPU backfill.
- **Simulated:** the human votes. Each model gets a latent quality from an
  independent fluency prior (real text > AR > high-NFE diffusion > low-NFE >
  naive controls), and votes are drawn from a Bradley–Terry/Elo model with rater
  noise, ties, and both-bad outcomes. The latent prior is **not** derived from
  any metric, so the metric↔human correlations are not circular.

## The study (see analysis/report.md)

1. **Bradley–Terry** fit on the pairwise votes → per-model human Elo + bootstrap
   CIs (recovers the planted ranking at ρ ≈ 1.0, validating the machinery).
2. **Model level** — Spearman/Kendall of human Elo vs each model-mean metric.
   `gen_ppl` and `js_to_human` (MAUVE-style distance to human text) correlate
   most strongly (lower = better).
3. **Sample level** — pairwise accuracy: does the metric's preferred side match
   the human pick?
4. **Learned combiner** — logistic regression on metric deltas; a blend beats any
   single metric (~0.71 acc / 0.78 AUC in the demo).

## Next: wire real collection

The web UI already POSTs votes to Supabase (`sample_votes`). To make the study
run on real data with one query, the schema should expose a join-ready view:

- `samples(sample_id PK, model_id, suite_id, text, token_len)` ← from `metrics.jsonl`
- `metrics(sample_id, metric_name, value)` ← long form, easy to add MAUVE later
- `votes(...)` ← already collected (battle_id, choice, left/right sample+model, …)
- view `vote_features` joining each vote to left/right metric deltas + `human_pick`

Then `correlate.py` points at the exported `votes` table instead of
`sim_votes.jsonl` and the rest is unchanged.
