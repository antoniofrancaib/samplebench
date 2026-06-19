#!/usr/bin/env python3
"""Simulate a realistic batch of human A/B votes and load them into samplebench.db.

============================  SIMULATED DATA  ============================
Stand-in for "suppose the website collected a good amount of votes", so the
correlation pipeline runs end-to-end before real data exists. Each model gets a
latent quality from an INDEPENDENT fluency prior (NOT from any metric), so the
downstream metric↔human correlations are not circular. Votes are drawn from a
Bradley–Terry/Elo model with rater noise, ties and both-bad outcomes.

Supports both study versions:
  v1 — 8 diffusion models + AR + data ceiling anchor (owt_L1024_paper)
  v2 — 28 pure diffusion generators across 6 families × NFE sweep
       (owt_L1024_diffusion_v2); TRUE_QUALITY_V2 is a plausible NFE-prior only.

The TRUE_QUALITY dicts cover both studies; only models with curated samples in
the DB are voted on, so v1/v2 are naturally isolated.

Run:  python3 bench/pipeline/simulate_votes.py   (after build_db.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import connect  # noqa: E402

N_VOTES = 20000
N_VOTERS = 400
SEED = 7
RATER_NOISE = 45.0   # per-vote gaussian noise on the quality gap (Elo points)

# v1 study (8 served models + data ceiling anchor)
TRUE_QUALITY_V1 = {
    "owt_data_train":        1700,   # real human OWT text — ceiling anchor
    "owt_ar_base":           1620,   # autoregressive — most coherent model
    "owt_flm_1024_nfe":      1545,
    "owt_duo_base_1024_nfe": 1530,
    "owt_sedd_1024_nfe":     1515,
    "owt_mdlm_1024_nfe":     1500,
    "owt_fmlm_32_nfe":       1465,
    "owt_fmlm_4_nfe":        1380,
    "owt_fmlm_1_nfe":        1300,   # single NFE — weakest real model
}

# v2 study: pure diffusion-vs-diffusion, 28 generators.
# Quality prior: high-NFE flow > high-NFE ancestral; distilled competitive in range.
# NOT derived from any metric — just a plausible fluency prior for pipeline testing.
TRUE_QUALITY_V2 = {
    "owt_v2_flm_1024_nfe":          1548,
    "owt_v2_flm_512_nfe":           1530,
    "owt_v2_duo_base_1024_nfe":     1525,
    "owt_v2_sedd_1024_nfe":         1518,
    "owt_v2_mdlm_1024_nfe":         1512,
    "owt_v2_flm_128_nfe":           1505,
    "owt_v2_duo_base_512_nfe":      1500,
    "owt_v2_sedd_512_nfe":          1495,
    "owt_v2_mdlm_512_nfe":          1490,
    "owt_v2_duo_distilled_32_nfe":  1485,
    "owt_v2_fmlm_32_nfe":           1480,
    "owt_v2_flm_32_nfe":            1472,
    "owt_v2_duo_distilled_16_nfe":  1465,
    "owt_v2_fmlm_16_nfe":           1460,
    "owt_v2_duo_base_128_nfe":      1455,
    "owt_v2_sedd_128_nfe":          1450,
    "owt_v2_mdlm_128_nfe":          1445,
    "owt_v2_fmlm_8_nfe":            1440,
    "owt_v2_flm_8_nfe":             1432,
    "owt_v2_duo_distilled_8_nfe":   1428,
    "owt_v2_duo_base_32_nfe":       1420,
    "owt_v2_sedd_32_nfe":           1415,
    "owt_v2_mdlm_32_nfe":           1408,
    "owt_v2_fmlm_4_nfe":            1395,
    "owt_v2_duo_base_8_nfe":        1380,
    "owt_v2_sedd_8_nfe":            1375,
    "owt_v2_mdlm_8_nfe":            1368,
    "owt_v2_fmlm_1_nfe":            1340,   # 1-NFE: weakest
}

TRUE_QUALITY = {**TRUE_QUALITY_V1, **TRUE_QUALITY_V2}


def main() -> None:
    rng = np.random.default_rng(SEED)
    con = connect()

    # Sample ids per model from the curated pool; map each model to its suite.
    sample_ids = {m: [] for m in TRUE_QUALITY}
    suite_of = {}
    for r in con.execute("SELECT sample_id, model_id, suite_id FROM samples"):
        if r["model_id"] in sample_ids:
            sample_ids[r["model_id"]].append(r["sample_id"])
            suite_of[r["model_id"]] = r["suite_id"]
    models = [m for m in TRUE_QUALITY if sample_ids[m]]
    missing = [m for m in TRUE_QUALITY if not sample_ids[m]]
    if missing:
        print(f"  warning: no curated samples for {missing} — skipped")

    voters = [f"sim-voter-{i:04d}" for i in range(N_VOTERS)]
    voter_tie_bias = {v: float(rng.uniform(0.6, 1.4)) for v in voters}

    rows = []
    counts = {"left": 0, "right": 0, "tie": 0, "both_bad": 0}
    for n in range(N_VOTES):
        a, b = rng.choice(len(models), size=2, replace=False)
        ma, mb = models[a], models[b]
        sa = str(rng.choice(sample_ids[ma]))
        sb = str(rng.choice(sample_ids[mb]))
        qa, qb = TRUE_QUALITY[ma], TRUE_QUALITY[mb]
        voter = voters[int(rng.integers(N_VOTERS))]

        dq = (qa - qb) + rng.normal(0, RATER_NOISE)
        p_a = 1.0 / (1.0 + 10 ** (-dq / 400.0))
        best = max(qa, qb)
        p_both_bad = 0.16 / (1.0 + np.exp((best - 1420) / 45.0))
        p_tie = 0.10 * np.exp(-abs(qa - qb) / 130.0) * voter_tie_bias[voter]
        r = rng.random()
        if r < p_both_bad:
            choice = "both_bad"
        elif r < p_both_bad + p_tie:
            choice = "tie"
        else:
            choice = "left" if rng.random() < p_a else "right"
        counts[choice] += 1

        winner = ma if choice == "left" else mb if choice == "right" else None
        loser = mb if choice == "left" else ma if choice == "right" else None
        rt = int(abs(rng.normal(4200 if choice in ("left", "right") else 6800, 1500))) + 500
        is_v2 = ma.startswith("owt_v2_")
        av = "samplebench-sim/elo-v2" if is_v2 else "samplebench-sim/elo-v1"
        rows.append((f"sim-{n:06d}", voter, f"{sa}__{sb}", choice, winner, loser,
                     ma, mb, sa, sb, rt, av, 1))

    con.execute("DELETE FROM votes WHERE is_simulated = 1")
    con.executemany(
        "INSERT OR REPLACE INTO votes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.execute("DELETE FROM sim_truth")
    con.executemany("INSERT INTO sim_truth VALUES (?, ?)",
                    [(m, TRUE_QUALITY[m]) for m in models])
    con.commit()
    con.close()

    print(f"simulated {len(rows)} votes over {len(models)} models, {N_VOTERS} voters")
    for k, v in counts.items():
        print(f"  {k:9s} {v:6d}  ({100*v/len(rows):4.1f}%)")


if __name__ == "__main__":
    main()
