#!/usr/bin/env python3
"""Simulate a realistic batch of human A/B votes for the deployed models.

============================  SIMULATED DATA  ============================
This does NOT use real human feedback. It stands in for "suppose the website
collected a good amount of votes", so the correlation pipeline can be exercised
end-to-end. Each model is given a latent human-quality score from an INDEPENDENT
prior (domain knowledge about fluency: real/AR text > high-NFE diffusion >
low-NFE / degenerate), NOT from any computed metric — so the downstream
metric↔human correlations are not circular. Votes are drawn from a
Bradley–Terry/Elo model over those latent scores, with rater noise, ties, and
"both bad" outcomes. Output mimics the Supabase `votes` row shape.
=========================================================================

Run:  python3 bench/scripts/simulate_votes.py   (after ingest + compute_metrics)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lmbench_common import (  # noqa: E402
    ANALYSIS_DIR, METRICS_DIR, SAMPLES_DIR, SUITES,
    iter_model_dirs, read_jsonl, write_json, write_jsonl,
)

N_VOTES = 14000
N_VOTERS = 280
SEED = 7
RATER_NOISE = 45.0   # per-vote gaussian noise on the quality gap (Elo points)

# Latent human quality (Elo scale), set from a prior over fluency — independent
# of any computed text metric. The 8 deployed models are joined by hidden
# ANCHOR systems standard in human-eval leaderboards: the real OWT text
# (ceiling) and the naive control samplers (floor). The web UI still shows only
# the real models; anchors give the metrics real dynamic range for the study.
TRUE_QUALITY = {
    "owt_data_train":        1700,   # real human OWT text — ceiling anchor
    "owt_ar_base":           1620,   # autoregressive — most coherent model
    "owt_flm_1024_nfe":      1545,
    "owt_duo_base_1024_nfe": 1530,
    "owt_sedd_1024_nfe":     1515,
    "owt_mdlm_1024_nfe":     1500,
    "owt_fmlm_32_nfe":       1465,
    "owt_mirror_5000":       1430,   # naive: copies real chunks, repetitive
    "owt_fmlm_4_nfe":        1380,
    "owt_phrase_bank_5000":  1360,   # naive: stitched real phrases
    "owt_fmlm_1_nfe":        1300,   # single NFE — weakest real model
    "owt_topk_iid_k64":      1160,   # naive: i.i.d. top-k — gibberish
    "owt_periodic_k_400":    1100,   # naive: periodic repetition — floor anchor
}


def simulated_model_ids() -> list[str]:
    ids = []
    for suite in SUITES:
        for model_id, _ in iter_model_dirs(suite, root=SAMPLES_DIR):
            if model_id in TRUE_QUALITY:
                ids.append(model_id)
    return ids


def main() -> None:
    rng = np.random.default_rng(SEED)
    models = simulated_model_ids()
    assert set(models) == set(TRUE_QUALITY), set(TRUE_QUALITY) ^ set(models)

    # Sample ids per model (from the curated pool that has per-sample metrics).
    sample_ids = {m: [] for m in models}
    for rec in read_jsonl(METRICS_DIR / "metrics.jsonl"):
        if rec["model_id"] in sample_ids:
            sample_ids[rec["model_id"]].append(rec["sample_id"])

    voters = [f"sim-voter-{i:04d}" for i in range(N_VOTERS)]
    # Small persistent per-voter bias toward "decisiveness" (some raters tie more).
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
        p_a = 1.0 / (1.0 + 10 ** (-dq / 400.0))      # Elo win prob for A

        best = max(qa, qb)
        # Both-bad rises when even the better sample is weak; tie when close.
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
        # Decisive votes are answered faster (lower response time).
        rt = int(abs(rng.normal(4200 if choice in ("left", "right") else 6800, 1500))) + 500

        rows.append({
            "simulated": True,
            "session_id": voter,
            "battle_id": f"{sa}__{sb}",
            "choice": choice,
            "winner_model_id": winner,
            "loser_model_id": loser,
            "left_model_id": ma, "right_model_id": mb,
            "left_sample_id": sa, "right_sample_id": sb,
            "response_time_ms": rt,
            "app_version": "samplebench-sim/elo-v1",
            "vote_number": n + 1,
        })

    write_jsonl(ANALYSIS_DIR / "sim_votes.jsonl", rows)
    write_json(ANALYSIS_DIR / "sim_truth.json", {
        "note": "SIMULATED ground-truth latent quality (Elo scale); independent "
                "of computed metrics. Used only to validate recovery.",
        "n_votes": N_VOTES, "n_voters": N_VOTERS, "seed": SEED,
        "true_quality": TRUE_QUALITY,
    })

    print(f"simulated {len(rows)} votes over {len(models)} models, {N_VOTERS} voters")
    tot = len(rows)
    for k, v in counts.items():
        print(f"  {k:9s} {v:6d}  ({100*v/tot:4.1f}%)")


if __name__ == "__main__":
    main()
