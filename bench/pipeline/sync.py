#!/usr/bin/env python3
"""Snapshot the canonical lm-bench outputs into bench/ (provenance + curated pool).

Reads directly from ~/lm-bench:
  configs/checkpoints.yaml            -> registry/checkpoints.yaml  (+ parsed)
  configs/sample_suites/<suite>.yaml  -> registry/suites/<suite>.yaml
  results/samples/<dataset>/<suite>/  -> samples/<suite>/<model>/   (curated, seeded)
  results/metrics/final_metrics/report/<dataset>_final_table.csv -> registry/metrics.csv

Records the lm-bench git SHA so every downstream artifact is traceable.
Run:  python3 bench/pipeline/sync.py
"""
from __future__ import annotations

import random
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    CURATE_K, CURATE_SEED, DATASET, LM_BENCH, LM_CKPT_CFG, LM_FINAL_REPORT,
    LM_SAMPLES, LM_SAMPLES_V2, LM_SUITE_CFG, MIN_CHARS, REGISTRY_DIR,
    SAMPLES_DIR, SAMPLES_DIR_V2, SUITES, SUITES_V2,
    iter_model_dirs, manifest_summary, normalize_text, read_jsonl, write_json,
    write_jsonl,
)
import json


def lm_bench_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(LM_BENCH), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def snapshot_configs() -> dict:
    (REGISTRY_DIR / "suites").mkdir(parents=True, exist_ok=True)
    shutil.copy(LM_CKPT_CFG, REGISTRY_DIR / "checkpoints.yaml")
    checkpoints = yaml.safe_load(LM_CKPT_CFG.read_text()).get("checkpoints", [])

    suites = {}
    for suite in SUITES + SUITES_V2:
        cfg = LM_SUITE_CFG / f"{suite}.yaml"
        if cfg.exists():
            shutil.copy(cfg, REGISTRY_DIR / "suites" / f"{suite}.yaml")
            suites[suite] = yaml.safe_load(cfg.read_text())
    return {"checkpoints": checkpoints, "suites": suites}


def snapshot_metrics() -> Path | None:
    src = LM_FINAL_REPORT / f"{DATASET}_final_table.csv"
    if not src.exists():
        print(f"  warning: {src} not found — metrics will be empty")
        return None
    dst = REGISTRY_DIR / "metrics.csv"
    shutil.copy(src, dst)
    return dst


def _curate_suite_group(suites: list, lm_root, out_root) -> dict:
    """Seeded K-per-model subsample for a group of suites. Returns {suite/model: k}."""
    stats = {}
    if out_root.exists():
        shutil.rmtree(out_root)
    for suite in suites:
        for model_id, d in iter_model_dirs(suite, root=lm_root):
            manifest = json.loads((d / "manifest.json").read_text())
            rng = random.Random(f"{CURATE_SEED}:{model_id}")
            usable = []
            for rec in read_jsonl(d / "samples.jsonl"):
                norm = normalize_text(rec.get("text", ""))
                if len(norm) < MIN_CHARS:
                    continue
                usable.append({"sample_id": rec["id"], "model_id": model_id,
                               "suite_id": suite, "text": norm, "char_len": len(norm)})
            k = min(CURATE_K, len(usable))
            picked = sorted(rng.sample(usable, k), key=lambda r: r["sample_id"]) if usable else []
            out = out_root / suite / model_id
            write_jsonl(out / "samples.jsonl", picked)
            write_json(out / "manifest.json",
                       {**manifest_summary(manifest), "suite": suite, "curated_k": k})
            stats[f"{suite}/{model_id}"] = k
    return stats


def curate_samples() -> dict:
    stats = _curate_suite_group(SUITES, LM_SAMPLES, SAMPLES_DIR)
    stats.update(_curate_suite_group(SUITES_V2, LM_SAMPLES_V2, SAMPLES_DIR_V2))
    return stats


def main() -> None:
    sha = lm_bench_sha()
    cfg = snapshot_configs()
    metrics_csv = snapshot_metrics()
    stats = curate_samples()

    write_json(REGISTRY_DIR / "provenance.json", {
        "lm_bench_sha": sha,
        "lm_bench_path": str(LM_BENCH),
        "dataset": DATASET,
        "suites": SUITES,
        "suites_v2": SUITES_V2,
        "n_checkpoints": len(cfg["checkpoints"]),
        "metrics_csv": str(metrics_csv) if metrics_csv else None,
        "curated_models": len(stats),
        "curated_samples": sum(stats.values()),
    })

    print(f"lm-bench @ {sha[:10]}")
    print(f"  checkpoints.yaml: {len(cfg['checkpoints'])} entries")
    print(f"  suites: {', '.join(cfg['suites'])}")
    print(f"  metrics.csv: {'ok' if metrics_csv else 'MISSING'}")
    print(f"  curated: {sum(stats.values())} samples across {len(stats)} models")


if __name__ == "__main__":
    main()
