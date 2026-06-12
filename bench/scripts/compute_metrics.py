#!/usr/bin/env python3
"""Compute intrinsic quality/diversity metrics over the curated sample pool.

Per-sample metrics (text-only, fully reproducible, no GPU):
  char_len, word_count, unigram_entropy, distinct_1, distinct_2,
  rep_4gram (degeneration), zipf_coef, type_token_ratio
Carried through where the corpus already has them:
  gen_ppl, entropy  (raw_generative_ppl / raw_entropy; None when not yet scored)

Per-model aggregates add a distribution-distance to human OWT text:
  js_to_human  (Jensen–Shannon divergence of unigram dist vs owt_data_train)
This is a dependency-free stand-in for MAUVE (lower = closer to human text).

Outputs:
  bench/metrics/metrics.jsonl        one row per curated sample
  bench/metrics/metrics_by_model.json  per-model means + corpus-level metrics

Run:  python3 bench/scripts/compute_metrics.py   (after ingest.py)
"""
from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lmbench_common import (  # noqa: E402
    METRICS_DIR, REFERENCE_MODEL, SAMPLES_DIR, SUITES, iter_model_dirs,
    read_jsonl, tokenize, write_json, write_jsonl,
)


def _ngrams(tokens, n):
    return list(zip(*[tokens[i:] for i in range(n)])) if len(tokens) >= n else []


def _shannon(counts) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def _zipf_coef(counts) -> float:
    """Slope of log(freq) vs log(rank); ~1 for natural language."""
    freqs = sorted(counts.values(), reverse=True)
    if len(freqs) < 5:
        return float("nan")
    xs = [math.log(i + 1) for i in range(len(freqs))]
    ys = [math.log(f) for f in freqs]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    var = sum((x - mx) ** 2 for x in xs)
    if var == 0:
        return float("nan")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var
    return -slope


def sample_metrics(text: str) -> dict:
    toks = tokenize(text)
    n = len(toks)
    uni = Counter(toks)
    bi = Counter(_ngrams(toks, 2))
    four = _ngrams(toks, 4)
    four_seen, four_rep = set(), 0
    for g in four:
        if g in four_seen:
            four_rep += 1
        four_seen.add(g)
    return {
        "char_len": len(text),
        "word_count": n,
        "unigram_entropy": round(_shannon(uni), 4),
        "distinct_1": round(len(uni) / n, 4) if n else 0.0,
        "distinct_2": round(len(bi) / max(1, n - 1), 4) if n > 1 else 0.0,
        "rep_4gram": round(four_rep / len(four), 4) if four else 0.0,
        "zipf_coef": round(_zipf_coef(uni), 4),
        "type_token_ratio": round(len(uni) / n, 4) if n else 0.0,
    }


def _clean_metric(v):
    """0.0 / None in the raw corpus means 'not scored yet', not a real zero."""
    return v if (v is not None and v != 0.0) else None


def js_divergence(p: Counter, q: Counter) -> float:
    vocab = set(p) | set(q)
    tp, tq = sum(p.values()), sum(q.values())
    if tp == 0 or tq == 0:
        return float("nan")
    js = 0.0
    for w in vocab:
        pi, qi = p.get(w, 0) / tp, q.get(w, 0) / tq
        mi = 0.5 * (pi + qi)
        if pi > 0:
            js += 0.5 * pi * math.log2(pi / mi)
        if qi > 0:
            js += 0.5 * qi * math.log2(qi / mi)
    return js


def main() -> None:
    per_sample = []
    model_tokens: dict[str, Counter] = {}
    model_meta: dict[str, dict] = {}

    for suite in SUITES:
        for model_id, _ in iter_model_dirs(suite, root=SAMPLES_DIR):
            corpus = Counter()
            rows = list(read_jsonl(SAMPLES_DIR / suite / model_id / "samples.jsonl"))
            for rec in rows:
                m = sample_metrics(rec["text"])
                corpus.update(tokenize(rec["text"]))
                per_sample.append({
                    "sample_id": rec["sample_id"],
                    "model_id": model_id,
                    "suite_id": suite,
                    "gen_ppl": _clean_metric(rec.get("raw_generative_ppl")),
                    "entropy": _clean_metric(rec.get("raw_entropy")),
                    **m,
                })
            model_tokens[model_id] = corpus
            model_meta[model_id] = {"suite": suite, "n": len(rows)}

    # Per-model aggregates.
    ref = model_tokens.get(REFERENCE_MODEL, Counter())
    by_model = {}
    metric_keys = ["unigram_entropy", "distinct_1", "distinct_2", "rep_4gram",
                   "zipf_coef", "type_token_ratio", "char_len", "word_count",
                   "gen_ppl", "entropy"]
    for model_id, meta in model_meta.items():
        rows = [r for r in per_sample if r["model_id"] == model_id]
        agg = {}
        for k in metric_keys:
            vals = [r[k] for r in rows if r.get(k) is not None
                    and not (isinstance(r[k], float) and math.isnan(r[k]))]
            agg[k] = round(sum(vals) / len(vals), 4) if vals else None
        agg["js_to_human"] = round(js_divergence(model_tokens[model_id], ref), 5) \
            if model_id != REFERENCE_MODEL else 0.0
        by_model[model_id] = {**meta, "metrics": agg}

    write_jsonl(METRICS_DIR / "metrics.jsonl", per_sample)
    write_json(METRICS_DIR / "metrics_by_model.json", {
        "reference_model": REFERENCE_MODEL,
        "note": "gen_ppl/entropy are None where the corpus has not been scored "
                "(only flm/fmlm carry real values); js_to_human is a MAUVE-style "
                "distribution distance to human OWT text (lower = closer).",
        "by_model": by_model,
    })

    print(f"per-sample metrics: {len(per_sample)} rows")
    print(f"{'model':28s}{'uni_H':>7}{'dist2':>7}{'rep4g':>7}{'zipf':>7}"
          f"{'js_hum':>8}{'gen_ppl':>9}")
    for mid, info in by_model.items():
        m = info["metrics"]
        gp = f"{m['gen_ppl']:.1f}" if m["gen_ppl"] is not None else "  --"
        print(f"{mid:28s}{m['unigram_entropy']:7.2f}{m['distinct_2']:7.3f}"
              f"{m['rep_4gram']:7.3f}{m['zipf_coef']:7.2f}{m['js_to_human']:8.3f}{gp:>9}")


if __name__ == "__main__":
    main()
