from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import format_args, load_yaml
from .manifest import SampleManifest, find_manifests, load_manifest
from .paths import REPO_ROOT, rel_to_repo, resolve_path


@dataclass(frozen=True)
class MetricBackend:
    script: str
    needs_reference: bool
    fixed_args: tuple[str, ...] = ()


BACKENDS: dict[str, MetricBackend] = {
    "gen_ppl": MetricBackend(
        script="bench/evals/gen_ppl/run.py",
        needs_reference=False,
    ),
    "mauve": MetricBackend(
        script="bench/evals/mauve/run.py",
        needs_reference=True,
    ),
    "grad_moment": MetricBackend(
        script="bench/evals/grad_moment/run.py",
        needs_reference=True,
    ),
    "energy_mmd": MetricBackend(
        script="bench/evals/energy_mmd/run.py",
        needs_reference=True,
    ),
    "htesting": MetricBackend(
        script="bench/evals/htesting/run.py",
        needs_reference=True,
    ),
    "rep4": MetricBackend(
        script="bench/evals/rep4/run.py",
        needs_reference=False,
    ),
}


def add_eval_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "eval",
        help="run one metric backend over manifest-backed sample corpora",
    )
    parser.add_argument("--metric", required=True, choices=sorted([*BACKENDS.keys(), "all"]))
    parser.add_argument("--suite", required=True, help="sample-suite YAML")
    parser.add_argument("--metrics-config", default="data/configs/metrics.yaml")
    parser.add_argument("--samples-root", default="data/samples")
    parser.add_argument("--output-root", default="data/metrics")
    parser.add_argument("--models", nargs="+", default=["all"], help="model ids or all")
    parser.add_argument("--manifests", nargs="*", default=None)
    parser.add_argument(
        "--reference-corpus",
        default=None,
        help="Reference corpus for distributional metrics.",
    )
    parser.add_argument("--suffix", default=None, help="output suffix; defaults to suite id")
    parser.add_argument("--python", default=sys.executable or "python3")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("backend_args", nargs=argparse.REMAINDER, help="extra args after --")
    parser.set_defaults(func=run_eval)


def run_eval(args: argparse.Namespace) -> int:
    suite = load_yaml(args.suite)
    metrics_config = _load_metrics_config(args.metrics_config)
    manifests = _load_requested_manifests(args, suite)
    metric_names = list(BACKENDS) if args.metric == "all" else [args.metric]
    status = 0
    for metric in metric_names:
        try:
            run_metric(metric, suite, manifests, metrics_config, args)
        except Exception as exc:  # noqa: BLE001
            status = 1
            print(f"[error] {metric}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return status


def run_metric(
    metric: str,
    suite: dict[str, Any],
    manifests: list[SampleManifest],
    metrics_config: dict[str, Any],
    args: argparse.Namespace,
) -> Path:
    backend = BACKENDS[metric]
    script = resolve_path(backend.script)
    suffix = args.suffix or str(suite["id"])
    dataset = str(suite["dataset"])
    n_samples = min(int(suite["n_samples"]), *(manifest.n_samples for manifest in manifests))
    run_dir = _metric_run_dir(args.output_root, metric, dataset, suffix)

    cmd = [args.python, str(script), "--out", str(run_dir), "--limit", str(n_samples)]
    cmd += ["--seed", str(suite.get("seed", 0))]
    if backend.needs_reference:
        if not args.reference_corpus:
            raise ValueError(f"{metric} requires --reference-corpus")
        cmd += ["--reference-corpus", args.reference_corpus]

    cmd += _metric_config_args(metric, metrics_config, suite, n_samples)
    for manifest in manifests:
        cmd += ["--corpus", str(manifest.path)]
    if args.backend_args:
        extra = args.backend_args[1:] if args.backend_args and args.backend_args[0] == "--" else args.backend_args
        cmd += extra

    printable = " ".join(shlex_quote(part) for part in cmd)
    print(f"[metric] {metric}: {printable}", flush=True)
    if args.dry_run:
        return run_dir

    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)
    _write_run_record(run_dir, metric, suite, manifests, cmd)
    return run_dir


def _load_requested_manifests(args: argparse.Namespace, suite: dict[str, Any]) -> list[SampleManifest]:
    if args.manifests:
        return [load_manifest(path) for path in args.manifests]
    return find_manifests(
        samples_root=args.samples_root,
        dataset=str(suite["dataset"]),
        suite_id=str(suite["id"]),
        model_ids=args.models,
    )


def _load_metrics_config(path: str) -> dict[str, Any]:
    config_path = resolve_path(path)
    if not config_path.exists():
        return {}
    return load_yaml(config_path)


def _metric_config_args(
    metric: str,
    config: dict[str, Any],
    suite: dict[str, Any],
    n_samples: int,
) -> list[str]:
    metric_cfg = (config.get("metrics") or {}).get(metric, {})
    args = metric_cfg.get("args", [])
    if not args:
        return []
    values = {
        "suite_id": suite["id"],
        "dataset": suite["dataset"],
        "seq_len": suite["seq_len"],
        "n_samples": n_samples,
        "seed": suite.get("seed", 0),
    }
    return format_args([str(arg) for arg in args], values)


def _metric_run_dir(output_root: str, metric: str, dataset: str, suffix: str) -> Path:
    return resolve_path(output_root) / metric / dataset / suffix


def _write_run_record(
    run_dir: Path,
    metric: str,
    suite: dict[str, Any],
    manifests: list[SampleManifest],
    cmd: list[str],
) -> None:
    payload = {
        "metric": metric,
        "suite_id": suite["id"],
        "dataset": suite["dataset"],
        "seq_len": suite["seq_len"],
        "n_samples": min(manifest.n_samples for manifest in manifests),
        "command": cmd,
        "manifests": [rel_to_repo(manifest.path) for manifest in manifests],
        "sample_files": [rel_to_repo(manifest.sample_path) for manifest in manifests],
    }
    (run_dir / "run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"[out] {rel_to_repo(run_dir / 'run.json')}")


def shlex_quote(value: object) -> str:
    import shlex

    return shlex.quote(str(value))
