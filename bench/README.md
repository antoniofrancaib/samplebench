# bench/ — data + analysis layer

Consumes the **lm-bench** evaluation harness (the source of truth for checkpoints,
generated samples, and the paper metrics) and turns it into a queryable database,
the web UI's sample pool, and a human-preference ↔ metric correlation study.
Nothing here recomputes metrics with home-grown proxies — it ingests lm-bench's
canonical outputs and keeps a pinned copy of the eval code to re-verify them.

## Two repos, two roles

```
~/lm-bench  (COMPUTE — GPU, source of truth)        samplebench/bench  (SERVE + COLLECT + ANALYZE)
checkpoints.yaml ─generate─► samples ─eval─► final_metrics ─┐
                                  │                          │ sync.py
                                  └────────► (curated)  ──► samplebench.db ◄── Supabase votes
                                                                  │
                                                    build_frontend.py → src/data.js
                                                    correlate.py      → analysis/report.md
                                                    reverify.py        (vendored evals vs DB)
```

The Vercel web build only ever touches `src/data.js`; no Python/GPU runs there.

## Layout

```
bench/
  evals/            pinned snapshot of lm-bench/model_evals (re-verify; GPU for some)
                    PROVENANCE.txt records the lm-bench commit
  db/
    schema.sql      checkpoints, suites, models, samples, metric_meta, metrics,
                    votes, sim_truth, model_human_scores (+ vote_metric_deltas view)
    samplebench.db  built artifact (git-ignored; `make db`)
  pipeline/
    common.py       shared paths/config/canonical-metric map/DB helpers
    sync.py         ~/lm-bench → registry snapshot + curated sample pool (+ lm-bench SHA)
    build_db.py     snapshot → samplebench.db static tables
    simulate_votes.py  Bradley–Terry votes → DB        ⚠ simulated, until real votes
    pull_votes.py   Supabase votes → DB                 (real collection)
    build_frontend.py  DB → ../src/data.js
    correlate.py    DB → analysis/report.md
    reverify.py     re-run a vendored metric, diff vs DB
  registry/         synced checkpoints.yaml, suite configs, metrics.csv, provenance.json
  samples/          curated per-model pool (snapshot)
  analysis/report.md
  requirements-eval.txt   heavy deps for bench/evals (GPU) — NOT the web app
  Makefile
```

## Run it

```bash
make refresh        # sync → db → simulate votes → frontend → correlate (demo)
make refresh-real   # same but pulls real votes from Supabase instead of simulating
make reverify       # re-run vendored rep4 on the corpus, assert it matches the DB
```

## Canonical metrics (same as lm-bench)

Ingested per-model from `results/metrics/final_metrics/report/owt_final_table.csv`:
`gen_ppl, entropy_nats (H), mauve, grad_moment, energy_dist, fmtyp_p, rep1..rep4`.
These are **corpus/model-level** (lm-bench is corpus-first), so the human↔metric
correlation is primarily model-level. `gen_ppl`, `mauve`, `grad_moment` need a
GPU (gpt2-large scorer); `energy_mmd`, `htesting`, `rep4` are CPU.

## Re-verification

`reverify.py` re-runs the **vendored** runner on the full lm-bench corpus and
diffs against the DB values (which came from lm-bench's published table). CPU
metrics (rep4/energy_mmd/htesting) run anywhere; GPU metrics need
`requirements-eval.txt` + CUDA. A pass proves the snapshot reproduces the
numbers we serve. Example: `make reverify` → 36/36 rep4 values match (Δ≈0).

## The regeneration lifecycle

When you research new checkpoints:

```
# in ~/lm-bench (GPU): edit checkpoints.yaml + workflow models, then
lm-bench generate --workflow configs/workflows/<suite>.yaml
lm-bench eval     --workflow configs/workflows/<suite>.yaml
# in samplebench:
make refresh        # picks up new samples + metrics, rebuilds DB/frontend/report
```

New checkpoints flow through with zero hand-editing; provenance.json stamps the
lm-bench commit every artifact was built from.

## What's simulated vs real

- **Real:** checkpoints, sample texts, every canonical metric, the vendored eval
  code, and the DB schema/joins.
- **Simulated (until votes accrue):** the human votes. `simulate_votes.py` draws
  per-model quality from an independent fluency prior (not from any metric, so the
  correlations aren't circular) and samples a Bradley–Terry/Elo model. Swap in
  `make refresh-real` once `pull_votes.py` has Supabase credentials.

## Wiring real collection

The web UI already POSTs votes to Supabase (`src/main.jsx`). Set
`VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` and run `make refresh-real`;
`correlate.py` then runs on real votes byte-for-byte the same as on simulated ones.
Per-sample analysis would need the lm-bench `gen_ppl`/`rep4` runners extended to
dump per-sample scores (today they emit corpus aggregates only).
