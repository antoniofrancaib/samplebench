"""Shared paths, config, and helpers for the SampleBench data pipeline.

The lm-bench corpus (manifests + samples.jsonl) is the single source of truth.
Everything under bench/ is a *generated, regenerable* artifact — never hand-edit.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────
HOME = Path(os.path.expanduser("~"))
LM_BENCH = HOME / "lm-bench"
SAMPLES_SRC = LM_BENCH / "results" / "samples" / "owt"
CKPT_SRC = LM_BENCH / "checkpoints" / "owt"

REPO = Path(__file__).resolve().parents[2]          # .../samplebench
BENCH = REPO / "bench"
REGISTRY_DIR = BENCH / "registry"
SAMPLES_DIR = BENCH / "samples"
METRICS_DIR = BENCH / "metrics"
ANALYSIS_DIR = BENCH / "analysis"
FRONTEND_DATA = REPO / "src" / "data.js"

# ── Config ───────────────────────────────────────────────────────────────
SUITES = ["owt_L1024_paper", "owt_L1024_naive"]
REFERENCE_MODEL = "owt_data_train"   # real OWT human text — distribution reference
CURATE_K = 64                        # samples kept per model for the study pool
FRONTEND_K = 40                      # samples per model shipped to the browser
CURATE_SEED = 1234
MIN_CHARS = 200                      # drop degenerate/empty generations below this

# Models shown in the blind A/B web UI (real model generations only).
# The reference human text and the naive control samplers stay out of the UI
# but remain in the registry + metrics + correlation study as anchors.
FRONTEND_SUITES = ["owt_L1024_paper"]
FRONTEND_EXCLUDE = {REFERENCE_MODEL}

# Diffusion-family algos (everything else that isn't AR / a naive sampler).
DIFFUSION_FAMILIES = {
    "mdlm", "sedd", "duo", "flm", "fmlm", "sdtt", "di4c", "elf", "langflow",
}

EOT = "<|endoftext|>"


# ── Helpers ──────────────────────────────────────────────────────────────
def read_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def normalize_text(text: str) -> str:
    """Strip end-of-text markers and surrounding whitespace for display."""
    if not text:
        return ""
    text = text.replace(EOT, " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def tokenize(text: str):
    """Lightweight word tokenizer for intrinsic metrics (no deps)."""
    return re.findall(r"[a-z0-9]+", text.lower())


def manifest_summary(manifest: dict) -> dict:
    """Normalize the two manifest dialects (checkpoint samplers vs naive)."""
    gen = manifest.get("generation") or {}
    sampler = manifest.get("sampler") or {}
    ckpt = manifest.get("checkpoint") or {}
    return {
        "model_id": manifest.get("model_id"),
        "label": manifest.get("label", manifest.get("model_id", "")),
        "family": ckpt.get("family"),
        "algo": gen.get("algo") or sampler.get("name"),
        "nfe": gen.get("nfe"),
        "n_samples": manifest.get("n_samples"),
        "source_type": manifest.get("source_type", ckpt.get("adapter")),
        "checkpoint_path": ckpt.get("path"),
        "source": manifest.get("source"),
    }


def method_for(family: str | None, algo: str | None, source_type: str | None) -> str:
    fam = (family or "").lower()
    if fam == "ar" or algo == "ar":
        return "Autoregressive"
    if source_type in ("naive_sampler",) or fam in (
        "mirror", "topk", "periodic", "phrase_bank",
    ):
        return "Naive baseline"
    if fam in DIFFUSION_FAMILIES:
        return "Diffusion"
    return "Other"


def iter_model_dirs(suite: str, root: Path = SAMPLES_SRC):
    """Yield (model_id, dir_path) for every model in a suite, sorted."""
    suite_dir = root / suite
    if not suite_dir.is_dir():
        return
    for d in sorted(suite_dir.iterdir()):
        if d.is_dir() and (d / "manifest.json").exists():
            yield d.name, d
