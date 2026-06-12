#!/usr/bin/env python3
"""Ingest the lm-bench OWT corpus into the repo as regenerable artifacts.

Outputs (all under bench/):
  registry/checkpoints.json   one row per checkpoint dir (metadata only, no weights)
  registry/suites.json        per-suite list of models w/ manifest summaries
  samples/<suite>/<model>/…   curated, seeded K-per-model sample pool + manifest

Run:  python3 bench/scripts/ingest.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lmbench_common import (  # noqa: E402
    CKPT_SRC, CURATE_K, CURATE_SEED, MIN_CHARS, REGISTRY_DIR, SAMPLES_DIR,
    SAMPLES_SRC, SUITES, iter_model_dirs, manifest_summary, method_for,
    normalize_text, read_jsonl, write_json, write_jsonl,
)


def build_checkpoint_registry() -> list[dict]:
    rows = []
    if not CKPT_SRC.is_dir():
        return rows
    for family_dir in sorted(p for p in CKPT_SRC.iterdir() if p.is_dir()):
        family = family_dir.name
        variants = [p for p in sorted(family_dir.iterdir()) if p.is_dir()]
        targets = variants or [family_dir]
        for variant_dir in targets:
            variant = variant_dir.name if variants else "base"
            # Sum the on-disk weight bytes (symlinks/pointers count as ~0).
            size = 0
            for f in variant_dir.rglob("*"):
                if f.is_file() and not f.is_symlink():
                    try:
                        size += f.stat().st_size
                    except OSError:
                        pass
            rows.append({
                "id": f"{family}/{variant}",
                "family": family,
                "variant": variant,
                "path": str(variant_dir.relative_to(CKPT_SRC.parents[1])),
                "weight_bytes": size,
                "weights_present": size > 5_000_000,   # >5MB ⇒ real weights on disk
                "weights_committed": False,             # never commit weights to the web repo
            })
    return rows


def build_suites_registry() -> dict:
    suites = {}
    for suite in SUITES:
        models = []
        for model_id, d in iter_model_dirs(suite):
            manifest = json.loads((d / "manifest.json").read_text())
            s = manifest_summary(manifest)
            s["method"] = method_for(s["family"], s["algo"], s["source_type"])
            s["suite"] = suite
            models.append(s)
        suites[suite] = {"models": models, "n_models": len(models)}
    return suites


def curate_samples() -> dict:
    """Seeded subsample of K usable generations per model; preserve raw metrics."""
    stats = {}
    for suite in SUITES:
        for model_id, d in iter_model_dirs(suite):
            manifest = json.loads((d / "manifest.json").read_text())
            rng = random.Random(f"{CURATE_SEED}:{model_id}")

            usable = []
            for rec in read_jsonl(d / "samples.jsonl"):
                norm = normalize_text(rec.get("text", ""))
                if len(norm) < MIN_CHARS:
                    continue
                usable.append({
                    "sample_id": rec["id"],
                    "model_id": model_id,
                    "suite_id": suite,
                    "text": norm,
                    "char_len": len(norm),
                    # raw metrics carried through (0.0 / None ⇒ not yet computed)
                    "raw_generative_ppl": rec.get("raw_generative_ppl"),
                    "raw_entropy": rec.get("raw_entropy"),
                    "algo": rec.get("algo") or rec.get("sampler"),
                    "nfe": rec.get("nfe"),
                })

            k = min(CURATE_K, len(usable))
            picked = rng.sample(usable, k) if usable else []
            picked.sort(key=lambda r: r["sample_id"])

            out_dir = SAMPLES_DIR / suite / model_id
            write_jsonl(out_dir / "samples.jsonl", picked)
            write_json(out_dir / "manifest.json", {
                **manifest_summary(manifest),
                "suite": suite,
                "curated_k": k,
                "available_in_source": len(usable),
                "curate_seed": CURATE_SEED,
            })
            stats[f"{suite}/{model_id}"] = {"curated": k, "usable": len(usable)}
    return stats


def main() -> None:
    ckpts = build_checkpoint_registry()
    write_json(REGISTRY_DIR / "checkpoints.json", {
        "source_root": str(CKPT_SRC),
        "checkpoints": ckpts,
    })

    suites = build_suites_registry()
    write_json(REGISTRY_DIR / "suites.json", {
        "source_root": str(SAMPLES_SRC),
        "suites": suites,
    })

    stats = curate_samples()

    print(f"checkpoints: {len(ckpts)} entries "
          f"({sum(c['weights_present'] for c in ckpts)} with weights on disk)")
    for suite, info in suites.items():
        print(f"suite {suite}: {info['n_models']} models")
    print("curated pool:")
    for key, s in sorted(stats.items()):
        print(f"  {key:36s} {s['curated']:3d}/{s['usable']:<4d}")
    total = sum(s["curated"] for s in stats.values())
    print(f"total curated samples: {total}")


if __name__ == "__main__":
    main()
