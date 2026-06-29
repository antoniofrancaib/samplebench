#!/usr/bin/env python3
"""Integrate new generator samples + metrics from lm-bench into samplebench.

Run after:
1. All generation jobs are complete (results/samples/v2/...)
2. All 6 metric jobs are complete (results/metrics/...)

Steps performed:
  A. Copy new model sample dirs from lm-bench → data/samples/
  B. Rebuild data/metrics/ from lm-bench metric summary.json files
  C. Rebuild bench/registry/metrics.csv from all summary.json files
  D. Run sync.py (curate bench/samples_v2/)
  E. Run build_db.py (rebuild samplebench.db)
  F. Run build_frontend.py (rebuild src/data.js)

Usage:
    python3 bench/pipeline/integrate_new_models.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LMBENCH = Path(os.environ.get("LMBENCH_ROOT", REPO.parent / "lm-bench")).expanduser()
SUITE = "owt_L1024_diffusion_v2"

# lm-bench paths
LM_SAMPLES = LMBENCH / "results" / "samples" / "v2" / "owt" / SUITE
LM_METRICS = LMBENCH / "results" / "metrics"

# samplebench paths
SB_SAMPLES = REPO / "data" / "samples" / SUITE
SB_METRICS = REPO / "data" / "metrics" / SUITE
METRICS_CSV = REPO / "bench" / "registry" / "metrics.csv"

METRICS_ORDER = ["gen_ppl", "mauve", "grad_moment", "energy_mmd", "htesting", "rep4"]

# Maps summary.json fields → (metric_source, field, decimal_places)
CSV_COLUMNS = [
    ("Generator",   None),
    ("Suite",       None),
    ("gen-PPL↓",    ("gen_ppl",    "gen_ppl",    2)),
    ("H↑ (nats)",   ("gen_ppl",    "h_emp",      4)),
    ("MAUVE↑",      ("mauve",      "mauve",      4)),
    ("GradMoment↓", ("grad_moment","grad_moment",4)),
    ("EnergyDist↓", ("energy_mmd", "energy",     5)),
    ("FMTyp-p↑",    ("htesting",   "fmtyp_p",    4)),
    ("Rep-1↓",      ("rep4",       "rep_1",      4)),
    ("Rep-2↓",      ("rep4",       "rep_2",      4)),
    ("Rep-3↓",      ("rep4",       "rep_3",      4)),
    ("Rep-4↓",      ("rep4",       "rep_4",      4)),
]


def load_all_metric_rows() -> dict[str, dict[str, dict]]:
    """Returns {metric: {model_id: row_dict}} for all 6 metrics."""
    result: dict[str, dict[str, dict]] = {}
    for metric in METRICS_ORDER:
        path = LM_METRICS / metric / "owt" / SUITE / "summary.json"
        if not path.exists():
            print(f"  [warn] missing: {path}", file=sys.stderr)
            result[metric] = {}
            continue
        data = json.loads(path.read_text())
        result[metric] = {row["model_id"]: row for row in data.get("rows", [])}
    return result


def copy_samples(new_ids: list[str], dry_run: bool) -> int:
    """Copy sample dirs for new_ids from lm-bench → samplebench data/samples/."""
    copied = 0
    for mid in new_ids:
        src = LM_SAMPLES / mid
        dst = SB_SAMPLES / mid
        if not src.exists():
            print(f"  [skip] no samples for {mid} at {src}")
            continue
        if not (src / "samples.jsonl").exists():
            print(f"  [skip] no samples.jsonl for {mid}")
            continue
        if dry_run:
            print(f"  [dry] would copy {src.name}")
        else:
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"  copied samples: {mid}")
        copied += 1
    return copied


def copy_metrics(dry_run: bool) -> None:
    """Copy metric summary.json files from lm-bench → samplebench data/metrics/."""
    for metric in METRICS_ORDER:
        src = LM_METRICS / metric / "owt" / SUITE / "summary.json"
        dst = SB_METRICS / metric / "summary.json"
        if not src.exists():
            print(f"  [skip] no {metric} summary.json in lm-bench")
            continue
        if dry_run:
            rows = json.loads(src.read_text()).get("rows", [])
            print(f"  [dry] would copy {metric}/summary.json ({len(rows)} rows)")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            rows = json.loads(dst.read_text()).get("rows", [])
            print(f"  copied {metric}/summary.json ({len(rows)} rows)")


def rebuild_metrics_csv(all_rows: dict[str, dict[str, dict]], dry_run: bool) -> None:
    """Rebuild bench/registry/metrics.csv from all metric summary rows."""
    # Collect all model_ids that appear in any metric
    all_model_ids: set[str] = set()
    for metric_rows in all_rows.values():
        all_model_ids.update(metric_rows.keys())

    # Load existing metrics.csv to preserve paper rows (non-v2)
    existing_paper: list[dict] = []
    if METRICS_CSV.exists():
        with open(METRICS_CSV, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row.get("Suite", "") != "v2":
                    existing_paper.append(row)

    # Build v2 rows from metric summary files
    v2_rows: list[dict] = []
    for mid in sorted(all_model_ids):
        if not mid.startswith("owt_v2_"):
            continue
        row: dict[str, str] = {"Generator": mid, "Suite": "v2"}
        for col, mapping in CSV_COLUMNS:
            if mapping is None:
                continue
            metric, field, decimals = mapping
            val = all_rows.get(metric, {}).get(mid, {}).get(field)
            row[col] = f"{val:.{decimals}f}" if val is not None else "—"
        v2_rows.append(row)

    headers = [col for col, _ in CSV_COLUMNS]
    all_output_rows = existing_paper + v2_rows

    if dry_run:
        print(f"  [dry] would write {METRICS_CSV.name}: "
              f"{len(existing_paper)} paper + {len(v2_rows)} v2 rows")
        return

    with open(METRICS_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_output_rows)
    print(f"  wrote {METRICS_CSV.name}: "
          f"{len(existing_paper)} paper + {len(v2_rows)} v2 rows")


def run_script(script: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry] would run: python3 {script.relative_to(REPO)}")
        return
    subprocess.run([sys.executable, str(script)], cwd=str(REPO), check=True)
    print(f"  ran: {script.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--models", nargs="+", default=None,
                    help="Specific model IDs to integrate (default: all new v2 models)")
    args = ap.parse_args()

    pipeline_dir = REPO / "bench" / "pipeline"

    # Discover new model IDs (in lm-bench but not yet in samplebench)
    existing = {d.name for d in SB_SAMPLES.iterdir() if d.is_dir()} if SB_SAMPLES.exists() else set()
    lmbench_models = {d.name for d in LM_SAMPLES.iterdir() if d.is_dir()} if LM_SAMPLES.exists() else set()
    new_ids = sorted(args.models or (lmbench_models - existing))
    if not new_ids:
        print("No new models to integrate.")
    else:
        print(f"New models to integrate ({len(new_ids)}): {', '.join(new_ids)}")

    print("\n[A] Copying samples...")
    n = copy_samples(new_ids, args.dry_run)
    print(f"    {n} model dirs copied")

    print("\n[B] Copying metric summary files...")
    copy_metrics(args.dry_run)

    print("\n[C] Rebuilding metrics.csv...")
    all_rows = load_all_metric_rows()
    rebuild_metrics_csv(all_rows, args.dry_run)

    print("\n[D] Running sync.py (curate samples_v2/)...")
    run_script(pipeline_dir / "sync.py", args.dry_run)

    print("\n[E] Running build_db.py...")
    run_script(pipeline_dir / "build_db.py", args.dry_run)

    print("\n[F] Running build_frontend.py...")
    run_script(pipeline_dir / "build_frontend.py", args.dry_run)

    print("\nDone. Review changes then commit and push to deploy.")


if __name__ == "__main__":
    main()
