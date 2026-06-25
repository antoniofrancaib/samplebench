#!/usr/bin/env python3
"""Curate the 40-per-model sample pool from data/samples/ into bench/samples_v2/.

Reads from:
    data/samples/owt_L1024_diffusion_v2/<model_id>/samples.jsonl + manifest.json

Writes to:
    bench/samples_v2/<suite>/<model_id>/samples.jsonl + manifest.json
    bench/registry/provenance.json

Run:  python3 bench/pipeline/sync.py
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    CURATE_K, CURATE_SEED, MIN_CHARS, RAW_SAMPLES_DIR,
    REGISTRY_DIR, SAMPLES_DIR_V2, SUITES_V2,
    iter_model_dirs, manifest_summary, normalize_text, read_jsonl,
    write_json, write_jsonl,
)


def curate_v2() -> dict:
    stats = {}
    if SAMPLES_DIR_V2.exists():
        shutil.rmtree(SAMPLES_DIR_V2)
    for suite in SUITES_V2:
        for model_id, d in iter_model_dirs(suite, root=RAW_SAMPLES_DIR):
            manifest = json.loads((d / "manifest.json").read_text())
            rng = random.Random(f"{CURATE_SEED}:{model_id}")
            usable = []
            for rec in read_jsonl(d / "samples.jsonl"):
                norm = normalize_text(rec.get("text", ""))
                if len(norm) < MIN_CHARS:
                    continue
                usable.append({
                    "sample_id": rec["id"], "model_id": model_id,
                    "suite_id": suite, "text": norm, "char_len": len(norm),
                })
            k = min(CURATE_K, len(usable))
            picked = sorted(rng.sample(usable, k), key=lambda r: r["sample_id"]) if usable else []
            out = SAMPLES_DIR_V2 / suite / model_id
            write_jsonl(out / "samples.jsonl", picked)
            write_json(out / "manifest.json",
                       {**manifest_summary(manifest), "suite": suite, "curated_k": k})
            stats[f"{suite}/{model_id}"] = k
    return stats


def main() -> None:
    stats = curate_v2()
    write_json(REGISTRY_DIR / "provenance.json", {
        "source": "data/samples",
        "suites_v2": SUITES_V2,
        "curated_models": len(stats),
        "curated_samples": sum(stats.values()),
    })
    print(f"curated: {sum(stats.values())} samples across {len(stats)} models")


if __name__ == "__main__":
    main()
