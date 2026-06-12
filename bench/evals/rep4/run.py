from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402
    add_corpus_args,
    corpus_metadata,
    ensure_out_dir,
    load_corpora,
    read_texts,
    write_csv,
    write_json,
    write_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute Rep-n within-sample repetition metric for each corpus. "
            "Rep-n = 1 - |distinct n-grams| / (L - n + 1), averaged over samples. "
            "Lower Rep-n means less within-sample repetition. "
            "Real text typically scores Rep-4 ~ 0.02-0.05; "
            "degenerate periodic sequences score Rep-4 = 1.0."
        )
    )
    add_corpus_args(parser)
    parser.add_argument(
        "--ngram-orders",
        type=int,
        nargs="+",
        default=[1, 2, 3, 4],
        help="Rep-n orders to compute (default: 1 2 3 4).",
    )
    return parser.parse_args()


def rep_n(tokens: list[str], n: int) -> float:
    """Rep-n for a single tokenised sequence.

    Rep-n = 1 - |distinct n-grams| / (L - n + 1)

    Returns 0.0 if the sequence is shorter than n (no n-gram windows).
    """
    total = len(tokens) - n + 1
    if total <= 0:
        return 0.0
    ngrams = [tuple(tokens[i : i + n]) for i in range(total)]
    distinct = len(set(ngrams))
    return 1.0 - distinct / total


def compute_rep_n_corpus(texts: list[str], n: int) -> dict[str, float]:
    scores = [rep_n(text.split(), n) for text in texts]
    arr = np.array(scores, dtype=float)
    return {
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=0)),
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


def main() -> None:
    args = parse_args()
    out_dir = ensure_out_dir(args.out)
    corpora = load_corpora(args)

    rows: list[dict[str, Any]] = []
    for corpus in corpora:
        texts = read_texts(corpus, limit=args.limit, seed=args.seed)
        print(f"[eval] {corpus.label}: {len(texts)} samples", flush=True)

        row: dict[str, Any] = {
            **corpus_metadata(corpus, len(texts)),
            "status": "ok",
        }
        for n in args.ngram_orders:
            result = compute_rep_n_corpus(texts, n)
            row[f"rep_{n}"] = result["mean"]
            row[f"rep_{n}_std"] = result["std"]
            row[f"rep_{n}_min"] = result["min"]
            row[f"rep_{n}_max"] = result["max"]
            print(
                f"  rep_{n}={result['mean']:.4f}  "
                f"std={result['std']:.4f}  "
                f"[{result['min']:.4f}, {result['max']:.4f}]"
            )
        rows.append(row)

    mean_cols = [f"rep_{n}" for n in args.ngram_orders]
    std_cols = [f"rep_{n}_std" for n in args.ngram_orders]
    min_cols = [f"rep_{n}_min" for n in args.ngram_orders]
    max_cols = [f"rep_{n}_max" for n in args.ngram_orders]

    payload = {
        "metric": "rep_n",
        "config": {
            "ngram_orders": args.ngram_orders,
            "limit": args.limit,
            "seed": args.seed,
        },
        "rows": rows,
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
        ]
        + mean_cols
        + std_cols
        + min_cols
        + max_cols
        + ["status", "manifest"],
    )
    write_report(
        out_dir / "report.md",
        title="Rep-n Within-Sample Repetition Metric",
        config={
            "ngram_orders": str(args.ngram_orders),
            "limit": args.limit,
            "seed": args.seed,
        },
        rows=rows,
        columns=[
            ("label", "Corpus"),
            ("source_type", "Source"),
            ("n_samples", "n"),
        ]
        + [(f"rep_{n}", f"Rep-{n}↓") for n in args.ngram_orders],
        notes=[
            "Rep-n: lower = less within-sample repetition.",
            "Rep-n = 1 - |distinct n-grams| / (L - n + 1), averaged over samples.",
            "Tokenisation: whitespace split on decoded text.",
            "Real text: Rep-4 ~ 0.02-0.05. Periodic-k=64: Rep-4 = 1.0.",
        ],
    )


if __name__ == "__main__":
    main()
