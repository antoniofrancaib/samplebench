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
    energy_distance,
    entity_discourse_features,
    feature_matrix,
    multi_rbf_mmd2,
    standardize_from_ref,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare corpora with energy distance and RBF-MMD over text features."
    )
    add_corpus_args(parser, require_reference=True)
    parser.add_argument("--log-every", type=int, default=128)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = ensure_out_dir(args.out)
    reference = load_corpus(args.reference_corpus)
    corpora = load_corpora(args)

    ref_texts = read_texts(reference, limit=args.limit, seed=args.seed)
    print(f"[reference] {reference.label}: {len(ref_texts)} samples")
    ref_mat = feature_matrix(
        ref_texts,
        entity_discourse_features,
        log_every=args.log_every,
        label="reference",
    )

    rows: list[dict] = []
    detail_rows: list[dict] = []
    for corpus in corpora:
        texts = read_texts(corpus, limit=args.limit, seed=args.seed)
        print(f"[eval] {corpus.label}: {len(texts)} samples")
        gen_mat = feature_matrix(
            texts,
            entity_discourse_features,
            log_every=args.log_every,
            label=corpus.model_id,
        )
        ref_z, gen_z = standardize_from_ref(ref_mat, gen_mat)
        energy = energy_distance(ref_z, gen_z)
        mmd2, bandwidth, bandwidth_rows = multi_rbf_mmd2(ref_z, gen_z, seed=args.seed)
        row = {
            **corpus_metadata(corpus, len(texts)),
            "status": "ok",
            "energy": float(energy),
            "mmd2": float(mmd2),
            "median_bandwidth": float(bandwidth),
        }
        rows.append(row)
        for bw_row in bandwidth_rows:
            detail_rows.append({"model_id": corpus.model_id, **bw_row})
        print(f"  energy={energy:.5f} mmd2={mmd2:.6f} median_bw={bandwidth:.5f}")

    payload = {
        "metric": "energy_mmd",
        "reference": corpus_metadata(reference, len(ref_texts)),
        "config": {
            "limit": args.limit,
            "seed": args.seed,
            "feature_count": len(ENTITY_DISCOURSE_FEATURE_NAMES),
        },
        "feature_names": ENTITY_DISCOURSE_FEATURE_NAMES,
        "rows": rows,
        "bandwidth_rows": detail_rows,
    }
    write_json(out_dir / "summary.json", payload)
    write_csv(
        out_dir / "summary.csv",
        rows,
        [
            "dataset",
            "suite_id",
            "model_id",
            "label",
            "source_type",
            "n_samples",
            "energy",
            "mmd2",
            "median_bandwidth",
            "status",
            "manifest",
        ],
    )
    write_report(
        out_dir / "report.md",
        title="Energy/MMD Corpus Comparison",
        config={
            "reference": reference.label,
            "limit": args.limit,
            "seed": args.seed,
            "feature_count": len(ENTITY_DISCOURSE_FEATURE_NAMES),
        },
        rows=rows,
        columns=[
            ("label", "Corpus"),
            ("source_type", "Source"),
            ("n_samples", "n"),
            ("energy", "Energy"),
            ("mmd2", "MMD2"),
            ("median_bandwidth", "Bandwidth"),
        ],
        notes=["Lower values are closer to the reference corpus feature distribution."],
    )


if __name__ == "__main__":
    main()
