#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Submit or run lm-bench pipeline jobs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("generate", help="submit a sample-generation job")
    gen.add_argument("--suite", required=True)
    gen.add_argument("--checkpoints", default="data/configs/checkpoints.yaml")
    gen.add_argument("--model", required=True)
    gen.add_argument("--samples-root", default="data/samples")
    gen.add_argument("--generate-python", default=None,
                     help="Python executable used inside upstream sampler commands.")
    gen.add_argument("--partition", default=None, help="override the Slurm partition for this job")
    gen.add_argument("--qos", default=None, help="override the Slurm QOS for this job")
    gen.add_argument("--local", action="store_true")
    gen.add_argument("--dry-run", action="store_true")

    ev = subparsers.add_parser("eval", help="submit a metric-evaluation job")
    ev.add_argument("--metric", required=True)
    ev.add_argument("--suite", required=True)
    ev.add_argument("--metrics-config", default="data/configs/metrics.yaml")
    ev.add_argument("--models", nargs="+", default=["all"])
    ev.add_argument("--samples-root", default="data/samples")
    ev.add_argument("--metrics-root", default="data/metrics")
    ev.add_argument("--reference-corpus", default=None)
    ev.add_argument("--local", action="store_true")
    ev.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "generate":
        cmd = generate_command(args)
    else:
        cmd = eval_command(args)

    print(" ".join(shlex.quote(part) for part in cmd))
    if args.dry_run:
        return 0
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)
    return 0


def generate_command(args: argparse.Namespace) -> list[str]:
    env_prefix = ""
    if args.generate_python:
        env_prefix = f"LM_BENCH_GENERATE_PYTHON={shlex.quote(args.generate_python)} "
    if args.local:
        cli_python = shlex.quote(args.generate_python or "python3")
        module_prefix = ""
        if args.generate_python:
            module_prefix = "module load python/3.12.12 >/dev/null 2>&1 || true; "
        return [
            "bash",
            "-lc",
            f"{module_prefix}{env_prefix}PYTHONPATH=src {cli_python} -m lm_bench.cli generate "
            f"--checkpoints {shlex.quote(args.checkpoints)} "
            f"--suite {shlex.quote(args.suite)} "
            f"--models {shlex.quote(args.model)} "
            f"--output-root {shlex.quote(args.samples_root)}",
        ]
    exports = [
        "ALL",
        f"SUITE_CONFIG={args.suite}",
        f"CHECKPOINTS_CONFIG={args.checkpoints}",
        f"MODEL_ID={args.model}",
        f"SAMPLES_ROOT={args.samples_root}",
    ]
    if args.generate_python:
        exports.append(f"LM_BENCH_GENERATE_PYTHON={args.generate_python}")
    export = ",".join(exports)
    cmd = ["sbatch"]
    if args.partition:
        cmd.append(f"--partition={args.partition}")
    if args.qos:
        cmd.append(f"--qos={args.qos}")
    cmd.extend([f"--export={export}", "slurm/generate.sbatch"])
    return cmd


def eval_command(args: argparse.Namespace) -> list[str]:
    models = " ".join(shlex.quote(model) for model in args.models)
    reference_arg = ""
    if args.reference_corpus:
        reference_arg = f" --reference-corpus {shlex.quote(args.reference_corpus)}"
    if args.local:
        return [
            "bash",
            "-lc",
            "PYTHONPATH=engine python3 -m lm_bench.cli eval "
            f"--metric {shlex.quote(args.metric)} "
            f"--suite {shlex.quote(args.suite)} "
            f"--metrics-config {shlex.quote(args.metrics_config)} "
            f"--samples-root {shlex.quote(args.samples_root)} "
            f"--output-root {shlex.quote(args.metrics_root)} "
            f"--models {models}"
            f"{reference_arg}",
        ]
    exports = [
        "ALL",
        f"METRIC={args.metric}",
        f"SUITE_CONFIG={args.suite}",
        f"METRICS_CONFIG={args.metrics_config}",
        f"MODELS={','.join(args.models)}",
        f"SAMPLES_ROOT={args.samples_root}",
        f"METRICS_ROOT={args.metrics_root}",
    ]
    if args.reference_corpus:
        exports.append(f"REFERENCE_CORPUS={args.reference_corpus}")
    export = ",".join(exports)
    return ["sbatch", f"--export={export}", "slurm/eval_metric.sbatch"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
