# Model Evals

Metric runners are corpus-first. They read manifest-backed text corpora from
`results/samples/...` and write reports to `results/metrics/...`.

Maintained paper metrics:

- `gen_ppl`: generative perplexity and empirical unigram entropy.
- `mauve`: distributional overlap in a neural representation.
- `grad_moment`: gradient-moment distance under a fixed GPT-2 scorer.
- `energy_mmd`: energy-distance style comparison over handcrafted text features.
- `htesting`: FMTyp-p and related hypothesis-testing diagnostics.
- `rep4`: Rep-n within-sample repetition, configured for Rep-1/2/3/4.

Each corpus directory contains:

```text
manifest.json
samples.jsonl
```

Example:

```bash
PYTHONPATH=src python -m lm_bench.cli eval \
  --metric energy_mmd \
  --suite configs/sample_suites/lm1b_L128_paper.yaml \
  --reference-corpus results/samples/lm1b/lm1b_L128_paper/lm1b_data_train/manifest.json
```

Generation belongs upstream; metric code only consumes materialized corpora.
