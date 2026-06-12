from __future__ import annotations

import argparse
import os
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
    load_corpus,
    read_texts,
    write_csv,
    write_json,
    write_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute MAUVE between each generated corpus and a reference corpus. "
            "Higher MAUVE means the generated distribution is closer to the reference. "
            "Uses GPT-2 features by default, matching the gen-PPL scorer."
        )
    )
    add_corpus_args(parser, require_reference=True)
    parser.add_argument("--featurize-model", default="gpt2-large")
    parser.add_argument(
        "--max-text-length",
        type=int,
        default=512,
        help="Max token length passed to the featurizer (default 512).",
    )
    parser.add_argument(
        "--num-buckets",
        type=int,
        default=None,
        help="Number of buckets for the MAUVE quantization (default: auto).",
    )
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--device-id",
        type=int,
        default=None,
        help="CUDA device id (0-indexed). Defaults to 0 if CUDA is available, else CPU (-1).",
    )
    parser.add_argument("--hf-home", default=os.environ.get("HF_HOME"))
    return parser.parse_args()


def _resolve_device_id(arg_value: int | None) -> int:
    if arg_value is not None:
        return arg_value
    try:
        import torch

        return 0 if torch.cuda.is_available() else -1
    except ImportError:
        return -1


def main() -> None:
    import mauve as mauve_lib

    args = parse_args()

    if args.hf_home:
        os.environ["HF_HOME"] = args.hf_home

    out_dir = ensure_out_dir(args.out)
    device_id = _resolve_device_id(args.device_id)

    reference = load_corpus(args.reference_corpus)
    ref_texts = read_texts(reference, limit=args.limit, seed=args.seed)
    print(
        f"[reference] {reference.label}: {len(ref_texts)} samples  "
        f"featurize_model={args.featurize_model}  device_id={device_id}"
    )

    corpora = load_corpora(args)
    rows: list[dict[str, Any]] = []

    for corpus in corpora:
        texts = read_texts(corpus, limit=args.limit, seed=args.seed)
        print(f"[eval] {corpus.label}: {len(texts)} samples", flush=True)

        kwargs: dict[str, Any] = dict(
            p_text=ref_texts,
            q_text=texts,
            device_id=device_id,
            max_text_length=args.max_text_length,
            featurize_model_name=args.featurize_model,
            batch_size=args.batch_size,
            verbose=False,
        )
        if args.num_buckets is not None:
            kwargs["num_buckets"] = args.num_buckets

        try:
            result = mauve_lib.compute_mauve(**kwargs)
            row: dict[str, Any] = {
                **corpus_metadata(corpus, len(texts)),
                "status": "ok",
                "mauve": float(result.mauve),
                "frontier_integral": float(result.frontier_integral),
            }
            print(
                f"  mauve={row['mauve']:.4f}  "
                f"frontier_integral={row['frontier_integral']:.4f}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] MAUVE failed for {corpus.label}: {exc}", flush=True)
            row = {
                **corpus_metadata(corpus, len(texts)),
                "status": f"error:{type(exc).__name__}",
                "mauve": float("nan"),
                "frontier_integral": float("nan"),
            }
        rows.append(row)

    payload = {
        "metric": "mauve",
        "reference": corpus_metadata(reference, len(ref_texts)),
        "config": {
            "featurize_model": args.featurize_model,
            "max_text_length": args.max_text_length,
            "num_buckets": args.num_buckets,
            "batch_size": args.batch_size,
            "device_id": device_id,
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
            "mauve",
            "frontier_integral",
            "status",
            "manifest",
        ],
    )
    write_report(
        out_dir / "report.md",
        title="MAUVE Corpus Comparison",
        config={
            "reference": reference.label,
            "featurize_model": args.featurize_model,
            "max_text_length": args.max_text_length,
            "batch_size": args.batch_size,
            "device_id": device_id,
            "limit": args.limit,
            "seed": args.seed,
        },
        rows=rows,
        columns=[
            ("label", "Corpus"),
            ("source_type", "Source"),
            ("n_samples", "n"),
            ("mauve", "MAUVE↑"),
            ("frontier_integral", "Frontier Integral"),
        ],
        notes=[
            "MAUVE in [0, 1]; higher means the generated distribution is closer to the reference.",
            f"Reference corpus: {reference.label}.",
            f"Features extracted with {args.featurize_model}, max_text_length={args.max_text_length}.",
        ],
    )


if __name__ == "__main__":
    main()
