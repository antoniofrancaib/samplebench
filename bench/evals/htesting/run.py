"""
Hypothesis-testing metrics for text generation evaluation.

Three metrics that ask: "was this sequence drawn from the human distribution?"

NE  — Normalized Energy effect size (batch level, lower is better)
      Reports log10(T_obs / E[T | H0]) where T is the energy distance between the
      generated and reference feature distributions.  T_obs is the observed energy
      distance; E[T | H0] is the mean energy distance under label-permutation, which
      estimates what the test statistic looks like when both groups are drawn from the
      same pool.  The ratio is a dimensionless effect size: 0 means the two batches
      are statistically indistinguishable; large positive values signal a distributional
      gap.  We take log10 for a more linear visual scale.  Lower is better (↓).

FMTyp-p — Full-Mahalanobis Typicality p-value (per-sequence, batch-averaged, higher is better)
      Uses the Mahalanobis distance m²(x) = (x-μ)ᵀ Σ̂⁻¹ (x-μ) where μ and Σ̂ are
      estimated from the reference corpus using the analytical Ledoit-Wolf (2004)
      shrinkage estimator.  No Gaussian assumption is imposed on the null: the null
      distribution of m² is built empirically from the reference sequences themselves,
      so the calibration is fully non-parametric.  For each generated sequence x,
      p(x) = fraction of reference sequences h with m²(h) ≥ m²(x).  High p-value
      means x is no more atypical than a typical reference sequence.  We report the
      mean over generated sequences.  Higher is better (↑).

NHF — Neighbourhood Human Fraction at k (per-sequence, batch-averaged, higher is better)
      For each generated sequence x, find its k nearest neighbours in the pooled set
      (reference ∪ generated), excluding x itself.  Count the fraction that come from
      the reference pool.  Under H0 (generated ∼ reference), the expected fraction is
      n_ref / (n_ref + n_gen - 1) ≈ 0.5 for balanced pools.  No calibration is needed:
      the theoretical baseline is analytic.  Higher means x is embedded in a mixed
      neighbourhood typical of human text; lower means x clusters with other generated
      sequences in a non-human region.  We report the mean over generated sequences.
      Higher is better (↑).

All three metrics use the same entity-discourse text feature representation (33
hand-crafted features, no neural model required) as the existing energy/MMD metric.
NE and NHF use features standardised by the reference statistics (mean 0, std 1 per
feature); FMTyp-p operates on raw features so that the Ledoit-Wolf estimator captures
both scale and correlation information from the reference.

Reference:
  Ledoit, O. & Wolf, M. (2004). A well-conditioned estimator for large-dimensional
  covariance matrices. Journal of Multivariate Analysis, 88(2), 365-411.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402
    add_corpus_args,
    corpus_metadata,
    ensure_out_dir,
    load_corpora,
    load_corpus,
    read_texts,
    write_csv,
    write_json,
    write_report,
)
from text_features import (  # noqa: E402
    ENTITY_DISCOURSE_FEATURE_NAMES,
    entity_discourse_features,
    feature_matrix,
    pairwise_distances,
    standardize_from_ref,
)

# ---------------------------------------------------------------------------
# Ledoit-Wolf shrinkage covariance estimator (numpy-only, analytical formula)
# ---------------------------------------------------------------------------

def ledoit_wolf_cov(X: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    """
    Analytical Ledoit-Wolf (2004) shrinkage covariance estimator.

    Shrinks the sample covariance S towards mu*I where mu = tr(S)/d.
    Optimal shrinkage intensity rho is computed analytically via the
    Oracle Approximating Shrinkage formula (Ledoit & Wolf, 2004, eq. 14).

    Parameters
    ----------
    X : (n, d) array, already mean-centred or not (we centre internally)

    Returns
    -------
    Sigma : (d, d) regularised covariance matrix
    rho   : scalar shrinkage intensity in [0, 1]
    mu_X  : (d,) sample mean (for computing Mahalanobis distances later)
    """
    n, d = X.shape
    mu_X = X.mean(axis=0)
    Xc = X - mu_X                         # (n, d), centred

    # Biased sample covariance (1/n normalisation, matching LW derivation)
    S = (Xc.T @ Xc) / n                  # (d, d)

    # Scalar target: mu * I
    trace_S = np.trace(S)
    mu_scalar = trace_S / d

    # ||S||_F^2 and ||S - mu I||_F^2
    S_frob_sq = float(np.sum(S * S))
    delta_sq = S_frob_sq - trace_S ** 2 / d   # = ||S - mu I||_F^2

    # beta_sq numerator:  sum_k ||z_k||^4 / n  -  ||S||_F^2
    # Derived from: (1/n^2) sum_k ||z_k z_k^T - S||_F^2
    #             = (1/n^2)(sum_k ||z_k||^4 - n ||S||_F^2)
    # Multiply through by n to get b^2 = (sum_k ||z_k||^4/n - ||S||_F^2) / n
    norms_sq = np.sum(Xc * Xc, axis=1)        # (n,), ||z_k||^2
    sum_norms4 = float(np.sum(norms_sq * norms_sq))  # sum_k ||z_k||^4
    beta_sq_num = sum_norms4 / n - S_frob_sq  # numerator * n

    # Optimal rho: min(beta_sq / delta_sq, 1), both scaled by same factor
    if delta_sq < 1e-14:
        rho = 0.0   # S is already a multiple of I; no shrinkage needed
    else:
        rho = float(np.clip(beta_sq_num / (n * delta_sq), 0.0, 1.0))

    Sigma = (1.0 - rho) * S + rho * mu_scalar * np.eye(d)
    return Sigma, rho, mu_X


def mahalanobis_sq(X: np.ndarray, mu: np.ndarray, L: np.ndarray) -> np.ndarray:
    """
    Squared Mahalanobis distance m²(x) = (x-mu)^T Σ^{-1} (x-mu).

    Computed stably via the Cholesky factor L of Σ = L L^T:
        m²(x) = || L^{-1} (x - mu) ||²

    Parameters
    ----------
    X  : (n, d) query points
    mu : (d,)  reference mean
    L  : (d, d) lower-triangular Cholesky factor of Σ

    Returns
    -------
    m2 : (n,) squared Mahalanobis distances
    """
    diff = X - mu                          # (n, d)
    # Solve L y = diff^T for y, then m² = ||y||²
    # np.linalg.solve is O(d^2) per column; with d=33, direct solve is fine
    Y = np.linalg.solve(L, diff.T)        # (d, n)
    return np.sum(Y * Y, axis=0)          # (n,)


# ---------------------------------------------------------------------------
# Metric 1 — NE: Normalised Energy effect size
# ---------------------------------------------------------------------------

def _energy_dist_from_precomputed(D: np.ndarray,
                                   ix: np.ndarray,
                                   iy: np.ndarray) -> float:
    """Energy distance from a precomputed full pairwise distance matrix."""
    Dxy = D[np.ix_(ix, iy)]
    Dxx = D[np.ix_(ix, ix)]
    Dyy = D[np.ix_(iy, iy)]
    # Clip at 0 to avoid floating-point negatives near zero
    return float(max(0.0, 2.0 * Dxy.mean() - Dxx.mean() - Dyy.mean()))


def compute_ne(
    ref_z: np.ndarray,
    gen_z: np.ndarray,
    n_permutations: int,
    seed: int,
    max_n: int,
) -> dict[str, float]:
    """
    Normalised Energy effect size  NE = log10(T_obs / E[T | H0]).

    T_obs  : energy distance between ref_z and gen_z (observed)
    E[T|H0]: mean energy distance under label-permutation on the pooled set,
             estimating the null (both groups from the same distribution)

    Uses equal-size subsamples (min(|ref|, |gen|, max_n)) so the permutation
    null is symmetric and unbiased.

    Returns a dict with 'ne', 'ne_T_obs', 'ne_T_perm_mean', 'ne_T_perm_std'.
    """
    rng = np.random.default_rng(seed)
    n = min(len(ref_z), len(gen_z), max_n)

    # Subsample equally from each side
    idx_r = rng.choice(len(ref_z), size=n, replace=False)
    idx_g = rng.choice(len(gen_z), size=n, replace=False)
    r = ref_z[idx_r]
    g = gen_z[idx_g]

    # Pre-compute full pairwise distance matrix on the pooled set
    pooled = np.vstack([r, g])                    # (2n, d)
    D = pairwise_distances(pooled, pooled)         # (2n, 2n)
    N = 2 * n
    ix_ref = np.arange(n)
    ix_gen = np.arange(n, N)

    T_obs = _energy_dist_from_precomputed(D, ix_ref, ix_gen)

    T_perm = np.empty(n_permutations)
    for i in range(n_permutations):
        perm = rng.permutation(N)
        T_perm[i] = _energy_dist_from_precomputed(D, perm[:n], perm[n:])

    T_perm_mean = float(T_perm.mean())
    T_perm_std  = float(T_perm.std(ddof=1))

    # Effect size: how many times larger is the observed gap than the null expectation?
    # If T_perm_mean == 0 (can only happen with identical point clouds), NE = 0.
    if T_perm_mean < 1e-14:
        ne = 0.0
    else:
        ratio = T_obs / T_perm_mean
        # ratio < 1 can occur due to finite-sample noise; log10 of values < 1 is negative.
        # We do NOT clip: a negative NE correctly indicates the two distributions are
        # even closer than the permutation null expects (the generator is very human-like).
        ne = float(np.log10(max(ratio, 1e-6)))

    # Also compute the permutation p-value for reference (not reported in table,
    # but stored in the JSON for audit purposes)
    pvalue = float(np.mean(T_perm >= T_obs))

    return {
        "ne":             ne,
        "ne_T_obs":       float(T_obs),
        "ne_T_perm_mean": T_perm_mean,
        "ne_T_perm_std":  T_perm_std,
        "ne_pvalue":      pvalue,       # archived; not the primary metric
    }


# ---------------------------------------------------------------------------
# Metric 2 — FMTyp-p: Full-Mahalanobis Typicality p-value
# ---------------------------------------------------------------------------

def compute_fmtyp_p(
    ref_raw: np.ndarray,
    gen_raw: np.ndarray,
) -> dict[str, float]:
    """
    Full-Mahalanobis Typicality p-value, batch-averaged.

    Procedure
    ---------
    1. Estimate μ and Σ̂ (Ledoit-Wolf) from ref_raw.
    2. Compute m²(x) for every reference sequence x_ref and every generated
       sequence x_gen using the Cholesky factor of Σ̂.
    3. p(x_gen) = fraction of reference m² values ≥ m²(x_gen).
       (One-sided: we test whether x_gen is *more atypical* than reference
       sequences.  Atypicality = large Mahalanobis distance from the reference
       centre.)
    4. Return the mean p-value over all generated sequences.  Higher is better.

    Uses raw (unstandardised) feature vectors so the Ledoit-Wolf estimator
    captures both scale and cross-feature correlation.
    """
    Sigma, rho, mu = ledoit_wolf_cov(ref_raw)

    # Cholesky factorisation for stable inverse
    try:
        L = np.linalg.cholesky(Sigma)
    except np.linalg.LinAlgError:
        # Fallback: add a small ridge to ensure positive definiteness
        eps = 1e-6 * float(np.trace(Sigma)) / Sigma.shape[0]
        L = np.linalg.cholesky(Sigma + eps * np.eye(Sigma.shape[0]))

    m2_ref = mahalanobis_sq(ref_raw, mu, L)   # (n_ref,) null distribution
    m2_gen = mahalanobis_sq(gen_raw, mu, L)   # (n_gen,) test points

    # Vectorised: p(x_i) = mean(m2_ref >= m2_gen_i) over ref
    # Shape: (n_gen, n_ref) bool -> mean over axis=1
    pvalues = (m2_ref[np.newaxis, :] >= m2_gen[:, np.newaxis]).mean(axis=1)  # (n_gen,)

    return {
        "fmtyp_p":        float(pvalues.mean()),
        "fmtyp_p_std":    float(pvalues.std()),
        "fmtyp_p_frac05": float(np.mean(pvalues > 0.05)),
        "fmtyp_lw_rho":   float(rho),
        "fmtyp_m2_ref_mean": float(m2_ref.mean()),
        "fmtyp_m2_gen_mean": float(m2_gen.mean()),
    }


# ---------------------------------------------------------------------------
# Metric 3 — NHF@k: Neighbourhood Human Fraction
# ---------------------------------------------------------------------------

def compute_nhf(
    ref_z: np.ndarray,
    gen_z: np.ndarray,
    k: int,
) -> dict[str, float]:
    """
    Neighbourhood Human Fraction at k.

    For each generated sequence x_i, find its k nearest neighbours in the
    pooled set (reference ∪ generated) excluding x_i itself, and count the
    fraction that belong to the reference pool.

    Theoretical baseline under H0 (gen ~ ref):
        E[NHF] = n_ref / (n_ref + n_gen - 1)
    For balanced pools (n_ref = n_gen = n): E[NHF] ≈ n/(2n-1) → 0.5 as n→∞.

    Implementation detail:  we build the pooled distance matrix with the
    diagonal of D_GG set to +∞ (self-exclusion), then for each generated row
    concatenate its distances to all ref and all gen, and pick the k smallest.
    """
    n_ref = len(ref_z)
    n_gen = len(gen_z)
    k_use = min(k, n_ref + n_gen - 2)   # at most this many non-self neighbours

    # Pairwise distances: generated vs reference and generated vs generated
    D_GR = pairwise_distances(gen_z, ref_z)   # (n_gen, n_ref)
    D_GG = pairwise_distances(gen_z, gen_z)   # (n_gen, n_gen)
    np.fill_diagonal(D_GG, np.inf)            # exclude self

    # Build pooled distance array: columns 0..n_ref-1 are ref, rest are gen
    D_pool = np.concatenate([D_GR, D_GG], axis=1)  # (n_gen, n_ref + n_gen)

    # Label mask: True = reference, False = generated
    is_ref = np.zeros(n_ref + n_gen, dtype=bool)
    is_ref[:n_ref] = True

    nhf_per_seq = np.empty(n_gen)
    for i in range(n_gen):
        # Indices of the k nearest finite neighbours
        row = D_pool[i]
        # argpartition is O(n_ref+n_gen); the self-distance is +inf so it
        # will never be selected when k_use < n_ref + n_gen - 1
        knn_idx = np.argpartition(row, kth=k_use - 1)[:k_use]
        nhf_per_seq[i] = float(is_ref[knn_idx].sum()) / k_use

    # Theoretical baseline (for reporting; does NOT enter the metric value)
    baseline = n_ref / (n_ref + n_gen - 1)

    return {
        "nhf":          float(nhf_per_seq.mean()),
        "nhf_std":      float(nhf_per_seq.std()),
        "nhf_baseline": float(baseline),
        "nhf_k":        k_use,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Hypothesis-testing metrics: "
            "NE (normalised energy effect size, ↓), "
            "FMTyp-p (full-Mahalanobis typicality p-value, ↑), "
            "NHF@k (neighbourhood human fraction, ↑)."
        )
    )
    add_corpus_args(p, require_reference=True)
    p.add_argument("--n-permutations", type=int, default=1000,
                   help="Permutations for NE null distribution (default 1000).")
    p.add_argument("--perm-max-n", type=int, default=512,
                   help="Max samples per side in the NE permutation test.")
    p.add_argument("--nhf-k", type=int, default=15,
                   help="k for NHF neighbourhood (default 15).")
    p.add_argument("--log-every", type=int, default=256)
    p.add_argument(
        "--include-reference",
        action="store_true",
        help=(
            "Also evaluate the reference corpus against itself using a "
            "deterministic 50/50 split (first half = estimation pool, "
            "second half = evaluation set).  Provides a calibration baseline."
        ),
    )
    return p.parse_args()


def _run_one(
    corpus_label: str,
    ref_raw: np.ndarray,
    gen_raw: np.ndarray,
    ref_z: np.ndarray,
    gen_z: np.ndarray,
    n_permutations: int,
    perm_max_n: int,
    nhf_k: int,
    seed: int,
) -> dict[str, float]:
    """Compute all three metrics for one (ref, gen) pair."""
    print(f"  [NE]      n_perm={n_permutations}, max_n={perm_max_n}")
    ne_res = compute_ne(ref_z, gen_z, n_permutations, seed, perm_max_n)

    print(f"  [FMTyp-p] Ledoit-Wolf rho={ne_res.get('ne_lw_rho', '?')}")
    fmtyp_res = compute_fmtyp_p(ref_raw, gen_raw)
    print(f"            rho={fmtyp_res['fmtyp_lw_rho']:.4f}  "
          f"m2_ref_mean={fmtyp_res['fmtyp_m2_ref_mean']:.2f}  "
          f"m2_gen_mean={fmtyp_res['fmtyp_m2_gen_mean']:.2f}")

    print(f"  [NHF@{nhf_k}]")
    nhf_res = compute_nhf(ref_z, gen_z, nhf_k)

    print(
        f"  => NE={ne_res['ne']:+.3f}  "
        f"FMTyp-p={fmtyp_res['fmtyp_p']:.4f}  "
        f"NHF={nhf_res['nhf']:.4f} (baseline={nhf_res['nhf_baseline']:.4f})"
    )
    return {**ne_res, **fmtyp_res, **nhf_res}


def main() -> None:
    args = parse_args()
    out_dir = ensure_out_dir(args.out)
    reference = load_corpus(args.reference_corpus)
    corpora = load_corpora(args)

    print(f"[reference] loading {reference.label} …")
    ref_texts = read_texts(reference, limit=args.limit, seed=args.seed)
    print(f"[reference] {reference.label}: {len(ref_texts)} samples")

    # Raw feature matrix (for FMTyp-p)
    ref_raw = feature_matrix(
        ref_texts, entity_discourse_features,
        log_every=args.log_every, label="reference-raw",
    )
    # Standardised feature matrix (for NE and NHF)
    ref_z, _ = standardize_from_ref(ref_raw, ref_raw)

    eval_list: list[tuple] = []   # (corpus_or_None, label, is_self)
    if args.include_reference:
        eval_list.append((reference, reference.label + " (self†)", True))
    for c in corpora:
        is_self = c.sample_path.resolve() == reference.sample_path.resolve()
        eval_list.append((c, c.label, is_self))

    rows: list[dict] = []
    for corpus, label, is_self in eval_list:
        print(f"\n[eval] {label}")

        if is_self:
            # Deterministic 50/50 split: first half = estimation pool,
            # second half = evaluation ("generated") set.
            n_half = len(ref_raw) // 2
            # For FMTyp-p: estimate Σ from first half, evaluate second half
            est_raw = ref_raw[:n_half]
            gen_raw = ref_raw[n_half:]
            # For NE / NHF: standardise second half using first-half statistics
            est_z, gen_z = standardize_from_ref(est_raw, gen_raw)
            ref_raw_use = est_raw
            ref_z_use   = est_z
            n_samples   = len(gen_raw)
        else:
            texts = read_texts(corpus, limit=args.limit, seed=args.seed)
            print(f"  {len(texts)} samples")
            gen_raw_full = feature_matrix(
                texts, entity_discourse_features,
                log_every=args.log_every, label=corpus.model_id,
            )
            # Standardise generated features using the full reference statistics
            _, gen_z = standardize_from_ref(ref_raw, gen_raw_full)
            ref_raw_use = ref_raw
            ref_z_use   = ref_z
            gen_raw     = gen_raw_full
            n_samples   = len(texts)

        metrics = _run_one(
            label,
            ref_raw_use, gen_raw,
            ref_z_use,   gen_z,
            args.n_permutations,
            args.perm_max_n,
            args.nhf_k,
            args.seed,
        )
        meta = corpus_metadata(corpus, n_samples)
        rows.append({**meta, "label": label, "status": "ok", **metrics})

    payload = {
        "metric": "htesting",
        "reference": corpus_metadata(reference, len(ref_texts)),
        "config": {
            "limit":         args.limit,
            "seed":          args.seed,
            "n_permutations":args.n_permutations,
            "perm_max_n":    args.perm_max_n,
            "nhf_k":         args.nhf_k,
            "n_features":    len(ENTITY_DISCOURSE_FEATURE_NAMES),
            "feature_names": ENTITY_DISCOURSE_FEATURE_NAMES,
        },
        "rows": rows,
    }
    write_json(out_dir / "summary.json", payload)
    write_csv(
        out_dir / "summary.csv",
        rows,
        [
            "dataset", "suite_id", "model_id", "label", "source_type", "n_samples",
            "ne", "ne_T_obs", "ne_T_perm_mean", "ne_T_perm_std", "ne_pvalue",
            "fmtyp_p", "fmtyp_p_std", "fmtyp_p_frac05",
            "fmtyp_lw_rho", "fmtyp_m2_ref_mean", "fmtyp_m2_gen_mean",
            "nhf", "nhf_std", "nhf_baseline", "nhf_k",
            "status", "manifest",
        ],
    )
    write_report(
        out_dir / "report.md",
        title="Hypothesis-Testing Metrics v2 (NE / FMTyp-p / NHF)",
        config={
            "reference":      reference.label,
            "n_permutations": args.n_permutations,
            "perm_max_n":     args.perm_max_n,
            "nhf_k":          args.nhf_k,
        },
        rows=rows,
        columns=[
            ("label",    "Corpus"),
            ("n_samples","n"),
            ("ne",       "NE↓"),
            ("fmtyp_p",  "FMTyp-p↑"),
            ("nhf",      "NHF↑"),
        ],
        notes=[
            "NE↓: log10(T_obs / E[T|H0]).  Lower = more human-like.  0 = indistinguishable.",
            "FMTyp-p↑: mean per-sequence Mahalanobis typicality p-value.  Higher = more typical.",
            "NHF↑: mean fraction of k-NNs from reference pool.  Baseline ≈ 0.5 (printed per row).",
            "† Reference self-comparison uses first 512 samples as estimation pool, last 512 as evaluation.",
        ],
    )
    print(f"\nDone.  Results written to {out_dir}")


if __name__ == "__main__":
    main()
