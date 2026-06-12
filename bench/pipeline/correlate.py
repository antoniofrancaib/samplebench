#!/usr/bin/env python3
"""Correlate human preference (votes) with the canonical lm-bench metrics.

Reads everything from samplebench.db:
  1. Bradley–Terry fit on the votes -> per-model human Elo (+ bootstrap CIs),
     written back to model_human_scores. If sim_truth is present (simulated
     votes), checks the fit recovers the planted ranking.
  2. Model level: Spearman/Kendall of human Elo vs each canonical metric
     (gen-PPL, MAUVE, GradMoment, EnergyDist, FMTyp-p, H, Rep-1..4), ranked by |ρ|.
  3. Per-battle: using each side's model-level metric, does it pick the human
     winner? -> pairwise accuracy per metric.
  4. Learned combiner: logistic regression on metric deltas (left - right) over
     fully-scored battles; 5-fold CV accuracy/AUC + standardized weights.

Writes bench/analysis/report.md.
Run:  python3 bench/pipeline/correlate.py   (after build_db + a vote loader)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ANALYSIS_DIR, connect  # noqa: E402


# ── stats (numpy/stdlib only) ────────────────────────────────────────────
def _rank(a):
    a = np.asarray(a, float)
    order = a.argsort()
    r = np.empty(len(a)); r[order] = np.arange(len(a))
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
    pos, neg = (labels == 1).sum(), (labels == 0).sum()
    if pos == 0 or neg == 0:
        return float("nan")
    r = _rank(scores)
    return float((r[labels == 1].sum() - pos * (pos - 1) / 2) / (pos * neg))


def bt_fit(win, games, iters=200):
    n = len(win); p = np.ones(n)
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
    win = np.zeros(n); games = np.zeros((n, n))
    for li, ri, ch in zip(left, right, choice):
        if ch == "left":
            win[li] += 1; games[li, ri] += 1; games[ri, li] += 1
        elif ch == "right":
            win[ri] += 1; games[li, ri] += 1; games[ri, li] += 1
        elif ch == "tie":
            win[li] += 0.5; win[ri] += 0.5; games[li, ri] += 1; games[ri, li] += 1
    return win, games


def logreg(X, y, l2=1.0, lr=0.3, iters=4000):
    Xb = np.hstack([np.ones((len(X), 1)), X]); w = np.zeros(Xb.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xb @ w))
        g = Xb.T @ (p - y) / len(y); g[1:] += l2 * w[1:] / len(y)
        w -= lr * g
    return w


def predict(w, X):
    return 1 / (1 + np.exp(-(np.hstack([np.ones((len(X), 1)), X]) @ w)))


# ── main ─────────────────────────────────────────────────────────────────
def main() -> None:
    con = connect()
    suite = con.execute(
        "SELECT suite_id FROM metrics GROUP BY suite_id "
        "ORDER BY COUNT(*) DESC LIMIT 1").fetchone()[0]

    votes = con.execute(
        "SELECT left_model_id, right_model_id, choice, left_sample_id, right_sample_id "
        "FROM votes").fetchall()
    if not votes:
        print("no votes in DB — run simulate_votes.py or pull_votes.py first")
        return

    labels = {r["model_id"]: r["label"]
              for r in con.execute("SELECT DISTINCT model_id, label FROM models")}
    meta = {r["metric"]: (r["label"], bool(r["higher_is_better"]))
            for r in con.execute("SELECT metric, label, higher_is_better FROM metric_meta")}
    mv = {}  # model_id -> {metric: value}
    for r in con.execute("SELECT model_id, metric, value FROM metrics"):
        mv.setdefault(r["model_id"], {})[r["metric"]] = r["value"]
    truth = {r["model_id"]: r["quality"]
             for r in con.execute("SELECT model_id, quality FROM sim_truth")}

    models = sorted({v["left_model_id"] for v in votes} | {v["right_model_id"] for v in votes})
    idx = {m: i for i, m in enumerate(models)}
    n = len(models)
    left = np.array([idx[v["left_model_id"]] for v in votes])
    right = np.array([idx[v["right_model_id"]] for v in votes])
    choice = np.array([v["choice"] for v in votes])

    # 1. Human Elo + bootstrap CI -----------------------------------------
    win, games = tally(left, right, choice, n)
    human = bt_fit(win, games)
    rng = np.random.default_rng(0)
    B = 300
    boot = np.zeros((B, n))
    for b in range(B):
        s = rng.integers(0, len(votes), len(votes))
        wb, gb = tally(left[s], right[s], choice[s], n)
        boot[b] = bt_fit(wb, gb, iters=120)
    lo, hi = np.percentile(boot, [2.5, 97.5], axis=0)

    nvotes_per = np.zeros(n)
    for li, ri in zip(left, right):
        nvotes_per[li] += 1; nvotes_per[ri] += 1
    con.execute("DELETE FROM model_human_scores")
    con.executemany(
        "INSERT INTO model_human_scores VALUES (?,?,?,?,?,?)",
        [(suite, m, float(human[idx[m]]), float(lo[idx[m]]), float(hi[idx[m]]),
          int(nvotes_per[idx[m]])) for m in models])
    con.commit()

    recov = None
    if truth:
        tv = np.array([truth.get(m, np.nan) for m in models])
        ok = ~np.isnan(tv)
        recov = spearman(human[ok], tv[ok])
        recov_ci = np.percentile(
            [spearman(boot[b][ok], tv[ok]) for b in range(B)], [2.5, 97.5])

    # Fully-scored models (carry every metric) — compare all metrics on this set.
    all_metrics = list(meta.keys())
    fully = [m for m in models if all(mt in mv.get(m, {}) for mt in all_metrics)]
    dense = [mt for mt in all_metrics if all(mt in mv.get(m, {}) for m in fully)]
    scored = set(fully)

    # 2. Model-level correlations (over the common fully-scored set) -------
    model_rows = []
    for met in all_metrics:
        ai = [i for i, m in enumerate(models) if m in scored and met in mv.get(m, {})]
        if len(ai) < 3:
            continue
        ai = np.array(ai)
        vals = np.array([mv[models[i]][met] for i in ai])
        rho, tau = spearman(human[ai], vals), kendall_tau(human[ai], vals)
        brho = np.array([spearman(boot[b][ai], vals) for b in range(B)])
        model_rows.append({
            "metric": met, "label": meta[met][0], "rho": rho, "tau": tau, "n": len(ai),
            "lo": float(np.percentile(brho, 2.5)), "hi": float(np.percentile(brho, 97.5)),
            "dir": "higher=better" if meta[met][1] else "lower=better",
        })
    model_rows.sort(key=lambda r: -abs(r["rho"]))

    # 3 & 4. Per-battle using model-level metrics --------------------------
    dec = [(idx[v["left_model_id"]], idx[v["right_model_id"]], v["choice"]) for v in votes
           if v["choice"] in ("left", "right")]
    sample_rows = []
    for met in all_metrics:
        higher = meta[met][1]
        nz = ok_ct = 0
        for li, ri, ch in dec:
            lm, rm = models[li], models[ri]
            if met not in mv.get(lm, {}) or met not in mv.get(rm, {}):
                continue
            dv = mv[lm][met] - mv[rm][met]
            if dv == 0:
                continue
            pred_left = (dv > 0) if higher else (dv < 0)
            nz += 1
            ok_ct += int(pred_left == (ch == "left"))
        if nz:
            sample_rows.append({"metric": met, "label": meta[met][0],
                                "acc": ok_ct / nz, "n": nz})
    sample_rows.sort(key=lambda r: -r["acc"])

    # Combiner over fully-scored battles (both models carry every metric).
    X, y = [], []
    for v in votes:
        if v["choice"] not in ("left", "right"):
            continue
        lm, rm = v["left_model_id"], v["right_model_id"]
        if lm not in scored or rm not in scored:
            continue
        X.append([mv[lm][m] - mv[rm][m] for m in dense])
        y.append(1.0 if v["choice"] == "left" else 0.0)
    X, y = np.array(X, float), np.array(y, float)
    combiner = None
    if len(X) > 200:
        Xs = X / (X.std(0) + 1e-9)
        folds = np.array_split(rng.permutation(len(Xs)), 5)
        accs, aucs = [], []
        for f in folds:
            te = np.zeros(len(Xs), bool); te[f] = True
            w = logreg(Xs[~te], y[~te]); p = predict(w, Xs[te])
            accs.append(np.mean((p > 0.5) == (y[te] > 0.5)))
            aucs.append(auc(p, y[te].astype(int)))
        wf = logreg(Xs, y)
        combiner = {
            "acc": float(np.mean(accs)), "acc_sd": float(np.std(accs)),
            "auc": float(np.mean(aucs)), "auc_sd": float(np.std(aucs)),
            "n": len(X), "dense": dense,
            "coefs": sorted(zip(dense, wf[1:]), key=lambda t: -abs(t[1])),
        }
    con.close()

    # ── report ────────────────────────────────────────────────────────────
    o = ["# SampleBench — human-preference ↔ metric correlation\n"]
    if truth:
        o.append("> **Simulated votes** (latent quality from an independent fluency "
                 "prior, not from any metric). Swap for the real Supabase table to "
                 "rerun verbatim.\n")
    o.append(f"- votes: **{len(votes):,}** ({len(dec):,} decisive) over **{n}** models")
    o.append(f"- metrics: canonical lm-bench paper metrics (suite `{suite}`)")
    if recov is not None:
        o.append(f"- BT recovery of simulated truth: Spearman ρ = **{recov:.3f}** "
                 f"(95% CI {recov_ci[0]:.3f}–{recov_ci[1]:.3f})")
    o.append("\n## 1. Recovered human score (Bradley–Terry, Elo scale)\n")
    o.append("| model | human Elo (95% CI) |" + (" true |" if truth else ""))
    o.append("|---|---|" + ("---|" if truth else ""))
    for m in sorted(models, key=lambda m: -human[idx[m]]):
        i = idx[m]
        t = f" {truth[m]:.0f} |" if truth and m in truth else (" — |" if truth else "")
        o.append(f"| {labels.get(m, m)} | {human[i]:.0f} ({lo[i]:.0f}–{hi[i]:.0f}) |{t}")

    o.append("\n## 2. Which metric ranks models like humans? (model-level)\n")
    o.append("Spearman ρ / Kendall τ between human Elo and each canonical metric, "
             "ranked by |ρ|.\n")
    o.append("| metric | n | ρ (95% CI) | τ | orientation |")
    o.append("|---|---|---|---|---|")
    for r in model_rows:
        o.append(f"| {r['label']} | {r['n']} | {r['rho']:+.3f} "
                 f"({r['lo']:+.2f},{r['hi']:+.2f}) | {r['tau']:+.3f} | {r['dir']} |")

    o.append("\n## 3. Does the metric pick the human winner? (per-battle)\n")
    o.append("Each side scored by its model-level metric; accuracy = fraction of "
             "decisive battles matching the human pick.\n")
    o.append("| metric | acc | n |")
    o.append("|---|---|---|")
    for r in sample_rows:
        o.append(f"| {r['label']} | {r['acc']:.3f} | {r['n']:,} |")

    if combiner:
        o.append("\n## 4. Learned combiner (logistic on metric deltas)\n")
        o.append(f"Over {combiner['n']:,} fully-scored battles — 5-fold CV: accuracy "
                 f"**{combiner['acc']:.3f}** ± {combiner['acc_sd']:.3f}, AUC "
                 f"**{combiner['auc']:.3f}** ± {combiner['auc_sd']:.3f}.\n")
        o.append("| metric | weight |")
        o.append("|---|---|")
        for m, c in combiner["coefs"]:
            o.append(f"| {meta[m][0]} | {c:+.3f} |")

    o.append("\n## Takeaways\n")
    if model_rows:
        b = model_rows[0]
        o.append(f"- Best single model-level metric: **{b['label']}** "
                 f"(|ρ| = {abs(b['rho']):.2f}, {b['dir']}).")
    if sample_rows:
        o.append(f"- Best single per-battle discriminator: **{sample_rows[0]['label']}** "
                 f"(acc = {sample_rows[0]['acc']:.2f}).")
    if combiner:
        o.append(f"- A logistic blend of the paper metrics reaches "
                 f"**{combiner['acc']:.2f}** accuracy / **{combiner['auc']:.2f}** AUC.")
    o.append("- Metrics are model-level (corpus-first, as in lm-bench); per-sample "
             "gen_ppl/rep would enable finer sample-level analysis if the runners "
             "are extended to dump per-sample scores.\n")

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    (ANALYSIS_DIR / "report.md").write_text("\n".join(o) + "\n", encoding="utf-8")

    print(f"BT over {len(votes)} votes, {n} models"
          + (f"  (recovery ρ={recov:.3f})" if recov is not None else ""))
    print("\nmodel-level |ρ| ranking (human vs canonical metric):")
    for r in model_rows:
        print(f"  {r['label']:12s} n={r['n']:2d}  ρ={r['rho']:+.3f}  τ={r['tau']:+.3f}  {r['dir']}")
    if combiner:
        print(f"\ncombiner: acc={combiner['acc']:.3f} auc={combiner['auc']:.3f} "
              f"(n={combiner['n']}, {len(dense)} metrics)")
    print(f"\nwrote {ANALYSIS_DIR / 'report.md'}")


if __name__ == "__main__":
    main()
