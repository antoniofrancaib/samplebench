"""GPT-2 Gradient Moment evaluator.

Metric (Hoogeboom et al. 2026, arXiv:2603.20155, Eq. 13):

    ||E_g[∇_θ log p^GPT2(x)] - E_q[∇_θ log p^GPT2(x)]||²

where g is the generator distribution and q is the data distribution.

Lower is better; zero means the reference model cannot distinguish the
generated distribution from the training data by its gradient signal.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402
    add_corpus_args,
    corpus_metadata,
    ensure_out_dir,
    load_corpus,
    load_corpora,
    write_csv,
    write_json,
    write_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute GPT-2 Gradient Moment: ||E_g[∇log p] - E_q[∇log p]||² "
            "(Hoogeboom et al. 2026, arXiv:2603.20155 §5)."
        )
    )
    add_corpus_args(parser)
    parser.add_argument("--scorer-model", default="gpt2",
                        help="Reference LM for gradient computation (default: gpt2).")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-length", type=int, default=None,
                        help="Truncation length. Defaults to corpus manifest seq_len.")
    parser.add_argument("--device", default=None)
    parser.add_argument("--hf-home", default=os.environ.get("HF_HOME"))
    parser.add_argument("--local-files-only", action="store_true")
    # Single reference (used for all corpora, compatible with lm_bench.cli eval)
    parser.add_argument("--reference-corpus", default=None,
                        help="Reference corpus for all datasets (lm_bench.cli integration).")
    # Per-dataset references (used when evaluating mixed-dataset batches)
    parser.add_argument("--ref-lm1b", default=None,
                        help="Reference corpus for lm1b dataset.")
    parser.add_argument("--ref-owt", default=None,
                        help="Reference corpus for owt dataset.")
    return parser.parse_args()


def main() -> None:
    import torch

    args = parse_args()
    out_dir = ensure_out_dir(args.out)

    # Build per-dataset reference map. Explicit --ref-{dataset} takes priority;
    # --reference-corpus is the fallback for all datasets (for lm_bench.cli compat).
    per_dataset_refs: dict[str, Any] = {}
    if args.ref_lm1b:
        per_dataset_refs["lm1b"] = load_corpus(args.ref_lm1b)
    if args.ref_owt:
        per_dataset_refs["owt"] = load_corpus(args.ref_owt)
    generic_ref = load_corpus(args.reference_corpus) if args.reference_corpus else None

    if not per_dataset_refs and generic_ref is None:
        raise ValueError(
            "provide at least one of --reference-corpus, --ref-lm1b, or --ref-owt"
        )

    def pick_ref(dataset: str):
        return per_dataset_refs.get(dataset) or generic_ref

    tokenizer, model, device, model_max_length = load_scorer(args)
    corpora = load_corpora(args)
    pad_id = int(tokenizer.pad_token_id)

    # Pre-compute reference gradients once per (ref_path, max_length) pair.
    # This avoids re-running backward through GPT-2 for every corpus that
    # shares the same reference dataset.
    ref_grad_cache: dict[tuple[str, int], list] = {}

    def get_ref_grads(ref, max_length: int) -> list:
        key = (str(ref.sample_path), max_length)
        if key not in ref_grad_cache:
            print(f"[ref]  computing reference gradients for {ref.label} max_length={max_length}")
            ref_rows = load_token_rows_corpus(
                ref, tokenizer, max_length, limit=args.limit, seed=args.seed
            )
            ref_grad_cache[key] = _compute_mean_gradient(
                model=model,
                token_rows=ref_rows,
                device=device,
                batch_size=args.batch_size,
                max_length=max_length,
                pad_token_id=pad_id,
            )
            print(f"[ref]  done ({len(ref_rows)} samples)")
        return ref_grad_cache[key]

    rows: list[dict[str, Any]] = []
    for corpus in corpora:
        ref = pick_ref(corpus.dataset)
        if ref is None:
            print(f"[skip] {corpus.label}: no reference corpus for dataset={corpus.dataset!r}")
            continue

        max_length = choose_max_length(
            args.max_length, corpus.payload.get("seq_len"), model_max_length
        )

        gen_rows = load_token_rows_corpus(
            corpus, tokenizer, max_length, limit=args.limit, seed=args.seed
        )
        ref_grads = get_ref_grads(ref, max_length)

        print(
            f"[eval] {corpus.label}: gen={len(gen_rows)} max_length={max_length}"
        )

        gen_grads = _compute_mean_gradient(
            model=model,
            token_rows=gen_rows,
            device=device,
            batch_size=args.batch_size,
            max_length=max_length,
            pad_token_id=pad_id,
        )

        result = _diff_grad_moment(gen_grads, ref_grads)

        row: dict[str, Any] = {
            **corpus_metadata(corpus, len(gen_rows)),
            "status": "ok",
            "scorer_model": args.scorer_model,
            "max_length": max_length,
            "ref_label": ref.label,
            **result,
        }
        rows.append(row)
        print(
            f"  grad_moment={row['grad_moment']:.6g}  "
            f"gen_grad_norm_sq={row['gen_grad_norm_sq']:.6g}  "
            f"ref_grad_norm_sq={row['ref_grad_norm_sq']:.6g}"
        )

    _write_outputs(out_dir, args, rows)


def _write_outputs(out_dir: Path, args: argparse.Namespace, rows: list[dict[str, Any]]) -> None:
    payload = {
        "metric": "grad_moment",
        "config": {
            "scorer_model": args.scorer_model,
            "batch_size": args.batch_size,
            "limit": args.limit,
            "seed": args.seed,
            "max_length": args.max_length,
        },
        "rows": rows,
    }
    columns = [
        "dataset", "suite_id", "model_id", "label", "source_type",
        "n_samples", "scorer_model", "max_length",
        "grad_moment", "gen_grad_norm_sq", "ref_grad_norm_sq",
        "ref_label", "status", "manifest",
    ]
    report_cols = [
        ("label", "Corpus"),
        ("source_type", "Source"),
        ("n_samples", "n"),
        ("grad_moment", "GPT-2 GM↓"),
        ("gen_grad_norm_sq", "||∇gen||²"),
        ("ref_grad_norm_sq", "||∇ref||²"),
    ]
    notes = [
        "GPT-2 GM = ||E_g[∇log p] - E_q[∇log p]||²; lower → generator closer to training data.",
        "Metric from Hoogeboom et al. 2026 (arXiv:2603.20155 §5). Reference model: gpt2.",
    ]

    write_json(out_dir / "summary.json", payload)
    write_csv(out_dir / "summary.csv", rows, columns)
    write_report(
        out_dir / "report.md",
        title="GPT-2 Gradient Moment Corpus Comparison",
        config={
            "scorer_model": args.scorer_model,
            "batch_size": args.batch_size,
            "limit": args.limit,
            "seed": args.seed,
        },
        rows=rows,
        columns=report_cols,
        notes=notes,
    )

    datasets = sorted({str(r["dataset"]) for r in rows})
    for dataset in datasets:
        dataset_rows = [r for r in rows if r["dataset"] == dataset]
        write_json(out_dir / f"summary_{dataset}.json", {"metric": "grad_moment", "rows": dataset_rows})
        write_csv(out_dir / f"summary_{dataset}.csv", dataset_rows, columns)
        write_report(
            out_dir / f"report_{dataset}.md",
            title=f"GPT-2 Gradient Moment: {dataset}",
            config={
                "scorer_model": args.scorer_model,
                "batch_size": args.batch_size,
                "limit": args.limit,
                "seed": args.seed,
            },
            rows=dataset_rows,
            columns=[
                ("suite_id", "Suite"),
                ("label", "Corpus"),
                ("source_type", "Source"),
                ("n_samples", "n"),
                ("grad_moment", "GPT-2 GM↓"),
                ("gen_grad_norm_sq", "||∇gen||²"),
                ("ref_grad_norm_sq", "||∇ref||²"),
            ],
            notes=notes,
        )


def load_scorer(args: argparse.Namespace):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        args.scorer_model,
        cache_dir=args.hf_home,
        local_files_only=args.local_files_only,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.scorer_model,
        cache_dir=args.hf_home,
        local_files_only=args.local_files_only,
    )
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    model_max_length = int(getattr(model.config, "n_positions", 1024) or 1024)
    return tokenizer, model, device, model_max_length


def choose_max_length(arg_value: int | None, manifest_seq_len: Any, model_max_length: int) -> int:
    if arg_value is not None:
        return min(int(arg_value), model_max_length)
    try:
        seq_len = int(manifest_seq_len)
    except (TypeError, ValueError):
        seq_len = model_max_length
    return max(2, min(seq_len, model_max_length))


def load_token_rows_corpus(
    corpus,
    tokenizer,
    max_length: int,
    *,
    limit: int | None,
    seed: int,
) -> list[list[int]]:
    """Load samples from a corpus as GPT-2 token-id lists."""
    rows: list[list[int]] = []
    with corpus.sample_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            obj = json.loads(line)
            token_ids = obj.get("token_ids")
            if isinstance(token_ids, list) and token_ids:
                rows.append([int(t) for t in token_ids[:max_length]])
            else:
                text = str(obj.get("text", "")).strip()
                if text:
                    ids = tokenizer(
                        text,
                        add_special_tokens=False,
                        truncation=True,
                        max_length=max_length,
                        return_attention_mask=False,
                    )["input_ids"]
                    if ids:
                        rows.append(ids)

    rng = random.Random(seed)
    rng.shuffle(rows)
    if limit is not None:
        rows = rows[:limit]
    return [row for row in rows if len(row) >= 2]


def _diff_grad_moment(gen_grads: list, ref_grads: list) -> dict[str, float]:
    """Compute ||mean_gen_grad - mean_ref_grad||² and diagnostic norms."""
    import torch

    grad_moment = 0.0
    gen_norm_sq = 0.0
    ref_norm_sq = 0.0
    with torch.no_grad():
        for g_gen, g_ref in zip(gen_grads, ref_grads):
            g_gen_f = g_gen.float()
            g_ref_f = g_ref.float()
            diff = g_gen_f - g_ref_f
            grad_moment += float(diff.pow(2).sum().item())
            gen_norm_sq += float(g_gen_f.pow(2).sum().item())
            ref_norm_sq += float(g_ref_f.pow(2).sum().item())

    return {
        "grad_moment": grad_moment,
        "gen_grad_norm_sq": gen_norm_sq,
        "ref_grad_norm_sq": ref_norm_sq,
    }


def _compute_mean_gradient(
    *,
    model,
    token_rows: list[list[int]],
    device: str,
    batch_size: int,
    max_length: int,
    pad_token_id: int,
) -> list:
    """Return a list of gradient tensors (one per parameter), averaged over all mini-batches.

    Each mini-batch contributes the gradient of its mean per-sequence NLL.
    We accumulate these via PyTorch's native gradient accumulation (successive
    loss.backward() calls without zero_grad() in between), then divide by
    the number of batches.
    """
    import torch
    import torch.nn.functional as F

    model.zero_grad()
    n_batches = 0

    for start in range(0, len(token_rows), batch_size):
        batch_rows = [r[:max_length] for r in token_rows[start : start + batch_size]]
        batch_rows = [r for r in batch_rows if len(r) >= 2]
        if not batch_rows:
            continue

        lengths = [len(r) for r in batch_rows]
        width = max(lengths)

        input_ids = torch.full(
            (len(batch_rows), width), pad_token_id, dtype=torch.long, device=device
        )
        attention_mask = torch.zeros(
            (len(batch_rows), width), dtype=torch.long, device=device
        )
        for i, row in enumerate(batch_rows):
            t = torch.tensor(row, dtype=torch.long, device=device)
            input_ids[i, : len(row)] = t
            attention_mask[i, : len(row)] = 1

        logits = model(input_ids=input_ids, attention_mask=attention_mask).logits

        shifted_logits = logits[:, :-1].contiguous()
        shifted_labels = input_ids[:, 1:].contiguous()
        shifted_mask = attention_mask[:, 1:].bool()

        token_losses = F.cross_entropy(
            shifted_logits.view(-1, shifted_logits.size(-1)),
            shifted_labels.view(-1),
            reduction="none",
        ).view(shifted_labels.size())
        token_losses = token_losses.masked_fill(~shifted_mask, 0.0)
        seq_counts = shifted_mask.sum(dim=1).clamp(min=1).float()
        seq_nlls = token_losses.sum(dim=1) / seq_counts
        loss = seq_nlls.mean()

        loss.backward()
        n_batches += 1

    if n_batches == 0:
        raise RuntimeError("no valid batches in gradient computation")

    grads: list = []
    with torch.no_grad():
        for p in model.parameters():
            if p.grad is not None:
                grads.append(p.grad.detach().clone() / n_batches)

    model.zero_grad()
    return grads


if __name__ == "__main__":
    main()
