from __future__ import annotations

import argparse
import json
import math
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
    write_csv,
    write_json,
    write_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute GPT-style generative perplexity and empirical token entropy."
    )
    add_corpus_args(parser)
    parser.add_argument("--scorer-model", default="gpt2-large")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--max-length",
        type=int,
        default=None,
        help="Tokenizer truncation length. Defaults to each corpus manifest seq_len capped by model context.",
    )
    parser.add_argument("--device", default=None)
    parser.add_argument("--hf-home", default=os.environ.get("HF_HOME"))
    parser.add_argument("--local-files-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = ensure_out_dir(args.out)
    corpora = load_corpora(args)
    tokenizer, model, device, model_max_length = load_scorer(args)

    rows: list[dict[str, Any]] = []
    for corpus in corpora:
        samples = read_gen_ppl_samples(corpus, limit=args.limit, seed=args.seed)
        texts = [sample["text"] for sample in samples]
        token_id_rows = sample_token_id_rows(samples)
        max_length = choose_max_length(args.max_length, corpus.payload.get("seq_len"), model_max_length)
        scoring_input = "token_ids" if token_id_rows is not None else "text"
        print(
            f"[eval] {corpus.label}: {len(texts)} samples "
            f"max_length={max_length} input={scoring_input}"
        )
        if token_id_rows is not None:
            result = score_token_id_rows(
                token_id_rows=token_id_rows,
                model=model,
                device=device,
                batch_size=args.batch_size,
                max_length=max_length,
                pad_token_id=int(tokenizer.pad_token_id),
            )
        else:
            result = score_texts(
                texts=texts,
                tokenizer=tokenizer,
                model=model,
                device=device,
                batch_size=args.batch_size,
                max_length=max_length,
            )
        row = {
            **corpus_metadata(corpus, len(texts)),
            "status": "ok",
            "scorer_model": args.scorer_model,
            "max_length": max_length,
            "scoring_input": scoring_input,
            **result,
        }
        row["token_length_status"] = token_length_status(row, corpus.payload.get("seq_len"))
        rows.append(row)
        print(
            f"  gen_ppl={row['gen_ppl']:.2f} h_emp={row['h_emp']:.4f} "
            f"mean_nll={row['mean_nll']:.4f} token_len={row['token_length_status']}"
        )

    payload = {
        "metric": "gen_ppl",
        "config": {
            "scorer_model": args.scorer_model,
            "batch_size": args.batch_size,
            "limit": args.limit,
            "seed": args.seed,
            "max_length": args.max_length,
            "device": str(device),
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
            "scorer_model",
            "max_length",
            "scoring_input",
            "gen_ppl",
            "h_emp",
            "h_emp_std",
            "mean_nll",
            "n_scored",
            "n_tokens_scored",
            "mean_token_length",
            "min_token_length",
            "max_token_length",
            "token_length_status",
            "status",
            "manifest",
        ],
    )
    write_main_report(
        out_dir / "report.md",
        title="Generative Perplexity Corpus Comparison",
        config={
            "scorer_model": args.scorer_model,
            "batch_size": args.batch_size,
            "limit": args.limit,
            "seed": args.seed,
            "device": str(device),
        },
        rows=rows,
        columns=[
            ("label", "Corpus"),
            ("source_type", "Source"),
            ("n_samples", "n"),
            ("gen_ppl", "gen-PPL"),
            ("h_emp", "H_emp nats"),
            ("h_emp_std", "H_emp std"),
            ("mean_nll", "NLL"),
            ("n_tokens_scored", "Scored Tokens"),
        ],
        notes=[
            "gen-PPL is exp(mean per-sample next-token NLL), matching the earlier fixed-length convention.",
            "H_emp is the mean empirical unigram entropy per sample, measured in nats on the scorer tokenizer IDs.",
        ],
    )
    write_dataset_reports(out_dir, args, rows)


def read_gen_ppl_samples(corpus, *, limit: int | None, seed: int) -> list[dict[str, Any]]:
    import random

    rows: list[dict[str, Any]] = []
    with corpus.sample_path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if not line.strip():
                continue
            obj = json.loads(line)
            text = obj.get("text")
            if not isinstance(text, str) or not text:
                continue
            rows.append({"index": index, **obj, "text": text})
    rng = random.Random(seed)
    rng.shuffle(rows)
    if limit is not None:
        if len(rows) < limit:
            raise ValueError(f"{corpus.sample_path}: need {limit} samples, got {len(rows)}")
        rows = rows[:limit]
    return rows


def sample_token_id_rows(samples: list[dict[str, Any]]) -> list[list[int]] | None:
    rows: list[list[int]] = []
    for sample in samples:
        token_ids = sample.get("token_ids")
        if token_ids is None:
            return None
        if not isinstance(token_ids, list) or not token_ids:
            return None
        try:
            rows.append([int(token_id) for token_id in token_ids])
        except (TypeError, ValueError):
            return None
    return rows


def token_length_status(row: dict[str, Any], manifest_seq_len: Any) -> str:
    try:
        expected = int(manifest_seq_len)
    except (TypeError, ValueError):
        return "unknown"
    if row["min_token_length"] == expected and row["max_token_length"] == expected:
        return "exact"
    return f"retokenized:{row['min_token_length']}-{row['max_token_length']} expected:{expected}"


def write_main_report(
    path: Path,
    *,
    title: str,
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str]],
    notes: list[str] | None = None,
) -> None:
    write_report(path, title=title, config=config, rows=rows, columns=columns, notes=notes)


def write_dataset_reports(out_dir: Path, args: argparse.Namespace, rows: list[dict[str, Any]]) -> None:
    datasets = sorted({str(row["dataset"]) for row in rows})
    for dataset in datasets:
        dataset_rows = [row for row in rows if row["dataset"] == dataset]
        write_json(out_dir / f"summary_{dataset}.json", {"metric": "gen_ppl", "rows": dataset_rows})
        write_csv(
            out_dir / f"summary_{dataset}.csv",
            dataset_rows,
            [
                "dataset",
                "suite_id",
                "model_id",
                "label",
                "source_type",
                "n_samples",
                "scorer_model",
                "max_length",
                "scoring_input",
                "gen_ppl",
                "h_emp",
                "h_emp_std",
                "mean_nll",
                "n_scored",
                "n_tokens_scored",
                "mean_token_length",
                "min_token_length",
                "max_token_length",
                "token_length_status",
                "status",
                "manifest",
            ],
        )
        write_report(
            out_dir / f"report_{dataset}.md",
            title=f"Generative Perplexity Corpus Comparison: {dataset}",
            config={
                "scorer_model": args.scorer_model,
                "batch_size": args.batch_size,
                "limit": args.limit,
                "seed": args.seed,
                "device": "see summary.json",
            },
            rows=dataset_rows,
            columns=[
                ("suite_id", "Suite"),
                ("label", "Corpus"),
                ("source_type", "Source"),
                ("n_samples", "n"),
                ("scoring_input", "Input"),
                ("gen_ppl", "gen-PPL"),
                ("h_emp", "H_emp nats"),
                ("mean_nll", "NLL"),
                ("mean_token_length", "Mean Tokens"),
                ("token_length_status", "Token Length"),
            ],
            notes=[
                "This dataset-specific report is generated alongside the full combined report.",
                "Token Length is exact when the scorer tokenizer sees exactly the manifest seq_len for every sample.",
            ],
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
    for param in model.parameters():
        param.requires_grad_(False)
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


def score_texts(
    *,
    texts: list[str],
    tokenizer,
    model,
    device: str,
    batch_size: int,
    max_length: int,
) -> dict[str, float | int]:
    import torch
    import torch.nn.functional as F

    sample_nlls: list[float] = []
    sample_entropies: list[float] = []
    sample_lengths: list[int] = []
    token_loss_sum = 0.0
    token_count = 0

    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            batch_texts = texts[start : start + batch_size]
            encoded = tokenizer(
                batch_texts,
                add_special_tokens=False,
                truncation=True,
                max_length=max_length,
                padding=True,
                return_tensors="pt",
            )
            input_ids = encoded["input_ids"].to(device)
            attention_mask = encoded["attention_mask"].to(device)
            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
            shifted_logits = logits[:, :-1, :].contiguous()
            shifted_labels = input_ids[:, 1:].contiguous()
            shifted_mask = attention_mask[:, 1:].contiguous().bool()
            losses = F.cross_entropy(
                shifted_logits.view(-1, shifted_logits.size(-1)),
                shifted_labels.view(-1),
                reduction="none",
            ).view(shifted_labels.size())
            losses = losses.masked_fill(~shifted_mask, 0.0)
            counts = shifted_mask.sum(dim=1)
            sums = losses.sum(dim=1)

            for row_ids, mask, count, loss_sum in zip(input_ids, attention_mask, counts, sums):
                valid_ids = row_ids[mask.bool()].detach().cpu().tolist()
                if int(count.item()) <= 0 or len(valid_ids) < 2:
                    continue
                nll = float(loss_sum.item() / int(count.item()))
                sample_nlls.append(nll)
                sample_lengths.append(len(valid_ids))
                sample_entropies.append(empirical_entropy_nats(valid_ids))
                token_loss_sum += float(loss_sum.item())
                token_count += int(count.item())

    if not sample_nlls:
        raise RuntimeError("no scoreable samples; need at least two tokens per text")
    mean_nll = float(np.mean(sample_nlls))
    token_weighted_nll = float(token_loss_sum / max(token_count, 1))
    return {
        "gen_ppl": safe_exp(mean_nll),
        "mean_nll": mean_nll,
        "std_nll": float(np.std(sample_nlls, ddof=0)),
        "token_weighted_gen_ppl": safe_exp(token_weighted_nll),
        "token_weighted_nll": token_weighted_nll,
        "h_emp": float(np.mean(sample_entropies)),
        "h_emp_std": float(np.std(sample_entropies, ddof=0)),
        "mean_token_length": float(np.mean(sample_lengths)),
        "min_token_length": int(np.min(sample_lengths)),
        "max_token_length": int(np.max(sample_lengths)),
        "n_scored": int(len(sample_nlls)),
        "n_tokens_scored": int(token_count),
    }


def score_token_id_rows(
    *,
    token_id_rows: list[list[int]],
    model,
    device: str,
    batch_size: int,
    max_length: int,
    pad_token_id: int,
) -> dict[str, float | int]:
    import torch
    import torch.nn.functional as F

    sample_nlls: list[float] = []
    sample_entropies: list[float] = []
    sample_lengths: list[int] = []
    token_loss_sum = 0.0
    token_count = 0

    with torch.inference_mode():
        for start in range(0, len(token_id_rows), batch_size):
            batch_rows = [row[:max_length] for row in token_id_rows[start : start + batch_size]]
            lengths = [len(row) for row in batch_rows]
            width = max(lengths)
            input_ids = torch.full(
                (len(batch_rows), width),
                int(pad_token_id),
                dtype=torch.long,
                device=device,
            )
            attention_mask = torch.zeros(
                (len(batch_rows), width),
                dtype=torch.long,
                device=device,
            )
            for row_index, row in enumerate(batch_rows):
                input_ids[row_index, : len(row)] = torch.tensor(row, dtype=torch.long, device=device)
                attention_mask[row_index, : len(row)] = 1

            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
            shifted_logits = logits[:, :-1, :].contiguous()
            shifted_labels = input_ids[:, 1:].contiguous()
            shifted_mask = attention_mask[:, 1:].contiguous().bool()
            losses = F.cross_entropy(
                shifted_logits.view(-1, shifted_logits.size(-1)),
                shifted_labels.view(-1),
                reduction="none",
            ).view(shifted_labels.size())
            losses = losses.masked_fill(~shifted_mask, 0.0)
            counts = shifted_mask.sum(dim=1)
            sums = losses.sum(dim=1)

            for row_ids, count, loss_sum in zip(batch_rows, counts, sums):
                if int(count.item()) <= 0 or len(row_ids) < 2:
                    continue
                nll = float(loss_sum.item() / int(count.item()))
                sample_nlls.append(nll)
                sample_lengths.append(len(row_ids))
                sample_entropies.append(empirical_entropy_nats(row_ids))
                token_loss_sum += float(loss_sum.item())
                token_count += int(count.item())

    if not sample_nlls:
        raise RuntimeError("no scoreable samples; need at least two tokens per row")
    mean_nll = float(np.mean(sample_nlls))
    token_weighted_nll = float(token_loss_sum / max(token_count, 1))
    return {
        "gen_ppl": safe_exp(mean_nll),
        "mean_nll": mean_nll,
        "std_nll": float(np.std(sample_nlls, ddof=0)),
        "token_weighted_gen_ppl": safe_exp(token_weighted_nll),
        "token_weighted_nll": token_weighted_nll,
        "h_emp": float(np.mean(sample_entropies)),
        "h_emp_std": float(np.std(sample_entropies, ddof=0)),
        "mean_token_length": float(np.mean(sample_lengths)),
        "min_token_length": int(np.min(sample_lengths)),
        "max_token_length": int(np.max(sample_lengths)),
        "n_scored": int(len(sample_nlls)),
        "n_tokens_scored": int(token_count),
    }


def empirical_entropy_nats(token_ids: list[int]) -> float:
    counts: dict[int, int] = {}
    for token_id in token_ids:
        counts[int(token_id)] = counts.get(int(token_id), 0) + 1
    arr = np.asarray(list(counts.values()), dtype=np.float64)
    probs = arr / arr.sum()
    return float(-(probs * np.log(probs)).sum())


def safe_exp(value: float) -> float:
    return float(math.exp(min(float(value), 20.0)))


if __name__ == "__main__":
    main()
