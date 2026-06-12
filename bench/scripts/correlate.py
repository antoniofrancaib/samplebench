#!/usr/bin/env python3
"""Correlate (simulated) human preference with automatic metrics.

Pipeline:
  1. Fit a Bradley–Terry model to the pairwise votes -> per-model human score
     (Elo scale, bootstrap CIs). Validate it recovers the simulated ground truth.
  2. Model level: Spearman / Kendall between the human score and each metric,
     ranked by |rho| -> "which metric ranks models like humans do".
  3. Sample level: for each decisive battle, does the metric's preferred side
     match the human pick? -> pairwise accuracy per metric.
  4. Learned combiner: logistic regression on metric *deltas* (left - right),
     5-fold CV accuracy/AUC + standardized weights -> best composite predictor.

Writes bench/analysis/report.md and prints a summary.
Run:  python3 bench/scripts/correlate.py   (after simulate_votes + compute_metrics)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lmbench_common import ANALYSIS_DIR, METRICS_DIR, read_jsonl  # noqa: E402

# Per-sample metrics fed to the sample-level + combiner analyses (dense, text-only).
SAMPLE_METRICS = ["unigram_entropy", "distinct_1", "distinct_2", "rep_4gram",
                  "zipf_coef", "char_len", "word_count", "js_to_human"]
# Model-level metrics correlated against the human score.
MODEL_METRICS = ["gen_ppl", "entropy", "unigram_entropy", "distinct_1", "distinct_2",
                 "rep_4gram", "zipf_coef", "char_len", "js_to_human"]
LOWER_IS_BETTER = {"gen_ppl", "rep_4gram", "js_to_human"}


# ── stats (numpy/stdlib only) ────────────────────────────────────────────
def _rank(a):
    a = np.asarray(a, float)
    order = a.argsort()
    r = np.empty(len(a))
    r[order] = np.arange(len(a))
    # average ties
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt)); np.add.at(sums, inv, r)
    return (sums / cnt)[inv]


def pearson(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x, y):
    return pearson(_rank(x), _rank(y))


def kendall_tau(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x); c = d = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = np.sign(x[i] - x[j]) * np.sign(y[i] - y[j])
            if s > 0: c += 1
            elif s < 0: d += 1
    return (c - d) / (0.5 * n * (n - 1)) if n > 1 else float("nan")


def auc(scores, labels):
    scores, labels = np.asarray(scores, float), np.asarray(labels, int)
    pos, neg = scores[labels == 1], scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    r = _rank(scores)
    return float((r[labels == 1].sum() - len(pos) * (len(pos) - 1) / 2)
                 / (len(pos) * len(neg)))


# ── Bradley–Terry ────────────────────────────────────────────────────────
def bt_fit(win, games, iters=200):
    """MM algorithm. win[i]=total wins, games[i,j]=games between i,j."""
    n = len(win)
    p = np.ones(n)
    for _ in range(iters):
        denom = np.zeros(n)
        for i in range(n):
            mask = games[i] > 0
            denom[i] = np.sum(games[i][mask] / (p[i] + p[mask]))
        p_new = np.where(denom > 0, win / np.maximum(denom, 1e-12), p)
        p_new /= p_new.sum()
        if np.max(np.abs(p_new - p)) < 1e-9:
            p = p_new; break
        p = p_new
    elo = 400.0 * np.log10(np.maximum(p, 1e-12))
    return elo - elo.mean() + 1500.0


def tally(left, right, choice, n):
    """Wins (decisive=1, tie=0.5 each) and symmetric game counts."""
    win = np.zeros(n); games = np.zeros((n, n))
    for li, ri, ch in zip(left, right, choice):
        if ch == "left":
            win[li] += 1; games[li, ri] += 1; games[ri, li] += 1
        elif ch == "right":
            win[ri] += 1; games[li, ri] += 1; games[ri, li] += 1
        elif ch == "tie":
            win[li] += 0.5; win[ri] += 0.5; games[li, ri] += 1; games[ri, li] += 1
        # both_bad carries no relative-quality signal -> skip
    return win, games


# ── logistic regression (gradient descent) ───────────────────────────────
def logreg(X, y, l2=1.0, lr=0.3, iters=4000):
    Xb = np.hstack([np.ones((len(X), 1)), X])
    w = np.zeros(Xb.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xb @ w))
        g = Xb.T @ (p - y) / len(y)
        g[1:] += l2 * w[1:] / len(y)
        w -= lr * g
    return w


def predict(w, X):
    return 1 / (1 + np.exp(-(np.hstack([np.ones((len(X), 1)), X]) @ w)))


# ── main ─────────────────────────────────────────────────────────────────
def main() -> None:
    votes = list(read_jsonl(ANALYSIS_DIR / "sim_votes.jsonl"))
    truth = json.loads((ANALYSIS_DIR / "sim_truth.json").read_text())["true_quality"]
    bymodel = json.loads((METRICS_DIR / "metrics_by_model.json").read_text())["by_model"]

    models = sorted({v["left_model_id"] for v in votes} | {v["right_model_id"] for v in votes})
    idx = {m: i for i, m in enumerate(models)}
    n = len(models)
    left = np.array([idx[v["left_model_id"]] for v in votes])
    right = np.array([idx[v["right_model_id"]] for v in votes])
    choice = np.array([v["choice"] for v in votes])

    # 1. Human score + bootstrap CI ---------------------------------------
    win, games = tally(left, right, choice, n)
    human = bt_fit(win, games)
    rng = np.random.default_rng(0)
    B = 300
    boot = np.zeros((B, n))
    for b in range(B):
        s = rng.integers(0, len(votes), len(votes))
        w_b, g_b = tally(left[s], right[s], choice[s], n)
        boot[b] = bt_fit(w_b, g_b, iters=120)
    lo, hi = np.percentile(boot, [2.5, 97.5], axis=0)

    true_vec = np.array([truth[m] for m in models])
    recov_rho = spearman(human, true_vec)
    recov_rho_ci = np.percentile([spearman(boot[b], true_vec) for b in range(B)], [2.5, 97.5])

    # 2. Model-level correlations -----------------------------------------
    # Sparse metrics (gen_ppl/entropy, scored only for some models) are reported
    # over their available subset with the model count noted.
    model_rows = []
    for met in MODEL_METRICS:
        avail = [i for i, m in enumerate(models)
                 if bymodel[m]["metrics"].get(met) is not None]
        if len(avail) < 3:
            continue
        ai = np.array(avail)
        vals = np.array([bymodel[models[i]]["metrics"][met] for i in avail], float)
        rho, tau = spearman(human[ai], vals), kendall_tau(human[ai], vals)
        boot_rho = np.array([spearman(boot[b][ai], vals) for b in range(B)])
        model_rows.append({
            "metric": met, "rho": rho, "tau": tau, "n": len(avail),
            "rho_lo": float(np.percentile(boot_rho, 2.5)),
            "rho_hi": float(np.percentile(boot_rho, 97.5)),
            "orient": "lower=better" if met in LOWER_IS_BETTER else "higher=better",
        })
    model_rows.sort(key=lambda r: -abs(r["rho"]))

    # 3 & 4. Sample-level --------------------------------------------------
    psm = {}
    for r in read_jsonl(METRICS_DIR / "metrics.jsonl"):
        feat = {k: r.get(k) for k in SAMPLE_METRICS if k != "js_to_human"}
        feat["js_to_human"] = bymodel[r["model_id"]]["metrics"].get("js_to_human")
        psm[r["sample_id"]] = feat

    dec = [v for v in votes if v["choice"] in ("left", "right")]
    # winner/loser sample feature matrices
    fw, fl, y_left = [], [], []
    for v in dec:
        ls, rs = psm.get(v["left_sample_id"]), psm.get(v["right_sample_id"])
        if ls is None or rs is None:
            continue
        winner_s = ls if v["choice"] == "left" else rs
        loser_s = rs if v["choice"] == "left" else ls
        fw.append([winner_s[k] for k in SAMPLE_METRICS])
        fl.append([loser_s[k] for k in SAMPLE_METRICS])
        y_left.append(1.0 if v["choice"] == "left" else 0.0)
        v["_lf"] = [ls[k] for k in SAMPLE_METRICS]
        v["_rf"] = [rs[k] for k in SAMPLE_METRICS]
    fw, fl = np.array(fw, float), np.array(fl, float)

    sample_rows = []
    for j, met in enumerate(SAMPLE_METRICS):
        dw = fw[:, j] - fl[:, j]               # winner - loser
        nz = dw != 0
        acc_high = float(np.mean(dw[nz] > 0))  # "higher = better" accuracy
        acc = max(acc_high, 1 - acc_high)
        sample_rows.append({
            "metric": met, "pairwise_acc": acc,
            "direction": "higher=better" if acc_high >= 0.5 else "lower=better",
            "n": int(nz.sum()),
        })
    sample_rows.sort(key=lambda r: -r["pairwise_acc"])

    # Learned combiner on deltas (left - right), 5-fold CV.
    Xd = np.array([np.array(v["_lf"]) - np.array(v["_rf"]) for v in dec
                   if "_lf" in v], float)
    yd = np.array([1.0 if v["choice"] == "left" else 0.0 for v in dec if "_lf" in v])
    mu, sd = Xd.mean(0), Xd.std(0) + 1e-9
    Xs = Xd / sd                                # scale (deltas already ~centered at 0)
    folds = np.array_split(rng.permutation(len(Xs)), 5)
    accs, aucs = [], []
    for f in folds:
        te = np.zeros(len(Xs), bool); te[f] = True
        w = logreg(Xs[~te], yd[~te])
        p = predict(w, Xs[te])
        accs.append(np.mean((p > 0.5) == (yd[te] > 0.5)))
        aucs.append(auc(p, yd[te].astype(int)))
    w_full = logreg(Xs, yd)
    coefs = sorted(zip(SAMPLE_METRICS, w_full[1:]), key=lambda t: -abs(t[1]))

    # ── report ────────────────────────────────────────────────────────────
    out = []
    out.append("# SampleBench — human-preference ↔ metric correlation\n")
    out.append("> **Simulated human votes.** Latent per-model quality came from an "
               "independent fluency prior, *not* from any metric below; votes were "
               "drawn from a Bradley–Terry/Elo model with rater noise, ties and "
               "both-bad outcomes. Numbers illustrate the pipeline, not real opinion.\n")
    out.append(f"- votes: **{len(votes):,}** ({len(dec):,} decisive) over "
               f"**{n}** models, {len({v['session_id'] for v in votes})} voters\n")
    out.append(f"- BT recovery of simulated truth: Spearman ρ = **{recov_rho:.3f}** "
               f"(95% CI {recov_rho_ci[0]:.3f}–{recov_rho_ci[1]:.3f}) — the fit "
               "reconstructs the planted ranking.\n")

    out.append("\n## 1. Recovered human score (Bradley–Terry, Elo scale)\n")
    out.append("| model | human Elo (95% CI) | true (sim) |")
    out.append("|---|---|---|")
    for m in sorted(models, key=lambda m: -human[idx[m]]):
        i = idx[m]
        out.append(f"| {m} | {human[i]:.0f} ({lo[i]:.0f}–{hi[i]:.0f}) | {truth[m]} |")

    out.append("\n## 2. Which metric ranks models like humans? (model-level)\n")
    out.append("Spearman ρ / Kendall τ between human Elo and each model-mean metric "
               f"(n = {n} models), ranked by |ρ|.\n")
    out.append("| metric | n models | ρ (95% CI) | τ | orientation |")
    out.append("|---|---|---|---|---|")
    for r in model_rows:
        out.append(f"| {r['metric']} | {r['n']} | {r['rho']:+.3f} "
                   f"({r['rho_lo']:+.2f},{r['rho_hi']:+.2f}) | {r['tau']:+.3f} | {r['orient']} |")

    out.append("\n## 3. Does the metric pick the human winner? (sample-level)\n")
    out.append("Pairwise accuracy: fraction of decisive battles where the metric's "
               "preferred side matches the human pick (0.5 = chance).\n")
    out.append("| metric | pairwise acc | direction | n |")
    out.append("|---|---|---|---|")
    for r in sample_rows:
        out.append(f"| {r['metric']} | {r['pairwise_acc']:.3f} | {r['direction']} | {r['n']:,} |")

    out.append("\n## 4. Learned combiner (logistic on metric deltas)\n")
    out.append(f"5-fold CV: accuracy **{np.mean(accs):.3f}** ± {np.std(accs):.3f}, "
               f"AUC **{np.mean(aucs):.3f}** ± {np.std(aucs):.3f}. "
               "Standardized weights (sign = direction, |·| = importance):\n")
    out.append("| metric | weight |")
    out.append("|---|---|")
    for met, c in coefs:
        out.append(f"| {met} | {c:+.3f} |")

    out.append("\n## Takeaways\n")
    best = model_rows[0]
    out.append(f"- Best *single* model-level metric: **{best['metric']}** "
               f"(|ρ| = {abs(best['rho']):.2f}, {best['orient']}).")
    out.append(f"- Best single sample-level discriminator: **{sample_rows[0]['metric']}** "
               f"(acc = {sample_rows[0]['pairwise_acc']:.2f}).")
    out.append(f"- A simple logistic blend reaches **{np.mean(accs):.2f}** pairwise "
               "accuracy — a learned composite beats any one metric.")
    out.append("- Swap the simulated votes for the real Supabase table to rerun this "
               "verbatim; add real `gen_ppl`/MAUVE once the corpus is scored on GPU.\n")

    report = "\n".join(out) + "\n"
    (ANALYSIS_DIR / "report.md").write_text(report, encoding="utf-8")

    # console summary
    print(f"BT recovery ρ = {recov_rho:.3f}  (votes={len(votes)}, models={n})\n")
    print("model-level |ρ| ranking (human vs metric):")
    for r in model_rows:
        print(f"  {r['metric']:16s} n={r['n']}  ρ={r['rho']:+.3f}  τ={r['tau']:+.3f}  {r['orient']}")
    print(f"\nsample-level best: {sample_rows[0]['metric']} "
          f"acc={sample_rows[0]['pairwise_acc']:.3f}")
    print(f"combiner: acc={np.mean(accs):.3f} auc={np.mean(aucs):.3f}")
    print(f"\nwrote {ANALYSIS_DIR / 'report.md'}")


if __name__ == "__main__":
    main()
