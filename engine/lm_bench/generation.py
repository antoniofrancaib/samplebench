from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import load_yaml
from .manifest import make_manifest_payload, write_manifest
from .paths import REPO_ROOT, rel_to_repo, resolve_path
from .registry import load_checkpoint_registry, select_models
from .samples import read_text_records, select_records, write_jsonl


def add_generate_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "generate",
        help="materialize decoded sample corpora and manifest.json files",
    )
    parser.add_argument("--checkpoints", default="configs/checkpoints.yaml")
    parser.add_argument("--suite", required=True, help="sample-suite YAML")
    parser.add_argument("--models", nargs="+", default=["all"], help="model ids or all")
    parser.add_argument("--output-root", default="results/samples")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(func=run_generate)


def run_generate(args: argparse.Namespace) -> int:
    suite = load_yaml(args.suite)
    _validate_suite(suite, args.suite)
    registry = load_checkpoint_registry(args.checkpoints)
    models = select_models(registry, dataset=suite["dataset"], model_ids=args.models)

    status = 0
    for model in models:
        try:
            materialize_model(model, suite, args)
        except Exception as exc:  # noqa: BLE001 - keep batch runs going.
            status = 1
            print(f"[error] {model['id']}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return status


def materialize_model(model: dict[str, Any], suite: dict[str, Any], args: argparse.Namespace) -> Path:
    out_dir = resolve_path(args.output_root) / suite["dataset"] / suite["id"] / model["id"]
    sample_path = out_dir / "samples.jsonl"
    manifest_path = out_dir / "manifest.json"

    if manifest_path.exists() and sample_path.exists() and not args.force:
        print(f"[skip] {model['id']} already materialized: {rel_to_repo(manifest_path)}")
        return manifest_path

    adapter = str(model.get("adapter", ""))
    print(f"[generate] {model['id']} ({adapter}) -> {rel_to_repo(out_dir)}")
    if args.dry_run:
        return manifest_path

    out_dir.mkdir(parents=True, exist_ok=True)
    if adapter == "sample_file":
        n_written = _materialize_sample_file(model, suite, sample_path)
        source_type = "sample_file"
        extra: dict[str, Any] = {}
    elif adapter == "command":
        n_written = _materialize_command(model, suite, sample_path, out_dir)
        source_type = "checkpoint"
        extra = {"generation_command": model.get("command")}
    else:
        raise NotImplementedError(
            f"adapter={adapter!r} is not implemented. Use adapter: sample_file "
            "for existing decoded samples or adapter: command with a generation command."
        )

    payload = make_manifest_payload(
        model=model,
        suite=suite,
        out_dir=out_dir,
        sample_path=sample_path,
        n_samples=n_written,
        source_type=source_type,
        extra=extra,
    )
    write_manifest(manifest_path, payload)
    print(f"[out] {rel_to_repo(sample_path)}")
    print(f"[out] {rel_to_repo(manifest_path)}")
    return manifest_path


def _materialize_sample_file(model: dict[str, Any], suite: dict[str, Any], sample_path: Path) -> int:
    source = model.get("sample_file")
    if not source:
        raise ValueError("adapter=sample_file requires sample_file")
    records = read_text_records(resolve_path(source))
    selected = select_records(records, int(suite["n_samples"]), int(suite.get("seed", 0)))
    rows = []
    for i, record in enumerate(selected):
        row = {
            "id": f"{suite['dataset']}-{model['id']}-{i:06d}",
            "text": str(record["text"]).replace("\n", " ").strip(),
            "dataset": suite["dataset"],
            "model_id": model["id"],
            "model_label": model.get("label", model["id"]),
            "suite_id": suite["id"],
            "seq_len": int(suite["seq_len"]),
            "seed": int(suite.get("seed", 0)),
            "source": "sample_file",
            "source_path": rel_to_repo(source),
            "source_index": record.get("source_index", i),
        }
        for key, value in record.items():
            if key not in row and key != "text":
                row[key] = value
        rows.append(row)
    write_jsonl(sample_path, rows)
    return len(rows)


def _materialize_command(
    model: dict[str, Any],
    suite: dict[str, Any],
    sample_path: Path,
    out_dir: Path,
) -> int:
    command = model.get("command")
    if not command:
        raise ValueError("adapter=command requires a command in configs/checkpoints.yaml")

    values = {
        "repo_root": str(REPO_ROOT),
        "generate_python": os.environ.get("LM_BENCH_GENERATE_PYTHON", sys.executable),
        "checkpoint_path": str(resolve_path(model.get("path", ""))),
        "output": str(sample_path),
        "output_dir": str(out_dir),
        "dataset": suite["dataset"],
        "suite_id": suite["id"],
        "seq_len": int(suite["seq_len"]),
        "n_samples": int(suite["n_samples"]),
        "seed": int(suite.get("seed", 0)),
        "model_id": model["id"],
        "label": model.get("label", model["id"]),
    }
    if isinstance(command, list):
        cmd = [str(part).format_map(values) for part in command]
        if cmd and cmd[0] in {"python", "python3"}:
            cmd[0] = values["generate_python"]
        printable = " ".join(shlex.quote(part) for part in cmd)
        run_kwargs = {"args": cmd, "shell": False}
    else:
        printable = str(command).format_map(values)
        run_kwargs = {"args": printable, "shell": True}

    env = os.environ.copy()
    env.update({f"LM_BENCH_{key.upper()}": str(value) for key, value in values.items()})
    print(f"[cmd] {printable}")
    subprocess.run(cwd=str(REPO_ROOT), env=env, check=True, **run_kwargs)
    if not sample_path.exists():
        raise FileNotFoundError(f"generation command did not create {sample_path}")
    n_rows = sum(1 for line in sample_path.read_text(encoding="utf-8").splitlines() if line.strip())
    if n_rows < int(suite["n_samples"]):
        raise ValueError(f"{sample_path}: expected at least {suite['n_samples']} rows, got {n_rows}")
    return n_rows


def _validate_suite(suite: dict[str, Any], path: str) -> None:
    for key in ("id", "dataset", "seq_len", "n_samples"):
        if key not in suite:
            raise ValueError(f"{path}: missing required key {key}")
