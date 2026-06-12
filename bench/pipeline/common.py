"""Shared paths, config, canonical-metric mapping, and DB helpers.

~/lm-bench is the single source of truth (checkpoint registry, generated samples,
and the paper metrics in results/metrics/final_metrics). Everything under bench/
is a regenerable mirror: sync.py snapshots lm-bench, build_db.py loads the snapshot
into samplebench.db, and the rest read that DB.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────
HOME = Path(os.path.expanduser("~"))
LM_BENCH = HOME / "lm-bench"
LM_SAMPLES = LM_BENCH / "results" / "samples"
LM_CKPT_CFG = LM_BENCH / "configs" / "checkpoints.yaml"
LM_SUITE_CFG = LM_BENCH / "configs" / "sample_suites"
LM_FINAL_REPORT = LM_BENCH / "results" / "metrics" / "final_metrics" / "report"

REPO = Path(__file__).resolve().parents[2]          # .../samplebench
BENCH = REPO / "bench"
REGISTRY_DIR = BENCH / "registry"                   # synced yaml + parsed snapshot
SAMPLES_DIR = BENCH / "samples"                     # curated sample pool
ANALYSIS_DIR = BENCH / "analysis"
DB_PATH = BENCH / "db" / "samplebench.db"
SCHEMA_PATH = BENCH / "db" / "schema.sql"
FRONTEND_DATA = REPO / "src" / "data.js"

# ── Config ───────────────────────────────────────────────────────────────
DATASET = "owt"
SUITES = ["owt_L1024_paper", "owt_L1024_naive"]
REFERENCE_MODEL = "owt_data_train"
CURATE_K = 64                  # curated pool per model (serving + analysis)
FRONTEND_K = 40                # samples per model shipped to the browser
CURATE_SEED = 1234
MIN_CHARS = 200

FRONTEND_SUITES = ["owt_L1024_paper"]
FRONTEND_EXCLUDE = {REFERENCE_MODEL}

DIFFUSION_FAMILIES = {"mdlm", "sedd", "duo", "flm", "fmlm", "sdtt", "di4c",
                      "elf", "langflow"}
EOT = "<|endoftext|>"

# Canonical metrics: final-table CSV column -> (key, label, higher_is_better).
METRIC_COLUMNS = {
    "gen-PPL↓":    ("gen_ppl",      "gen-PPL",    False),
    "H↑ (nats)":   ("entropy_nats", "H (nats)",   True),
    "MAUVE↑":      ("mauve",        "MAUVE",      True),
    "GradMoment↓": ("grad_moment",  "GradMoment", False),
    "EnergyDist↓": ("energy_dist",  "EnergyDist", False),
    "FMTyp-p↑":    ("fmtyp_p",      "FMTyp-p",    True),
    "Rep-1↓":      ("rep1",         "Rep-1",      False),
    "Rep-2↓":      ("rep2",         "Rep-2",      False),
    "Rep-3↓":      ("rep3",         "Rep-3",      False),
    "Rep-4↓":      ("rep4",         "Rep-4",      False),
}


# ── IO helpers ───────────────────────────────────────────────────────────
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


# ── Text helpers ─────────────────────────────────────────────────────────
def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace(EOT, " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def method_for(family, algo, source_type) -> str:
    fam = (family or "").lower()
    if fam == "ar" or algo == "ar":
        return "Autoregressive"
    if source_type in ("naive_sampler",) or fam in ("mirror", "topk", "periodic", "phrase_bank"):
        return "Naive baseline"
    if fam in DIFFUSION_FAMILIES:
        return "Diffusion"
    return "Other"


def manifest_summary(manifest: dict) -> dict:
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
    }


def iter_model_dirs(suite: str, root: Path):
    """Yield (model_id, dir) for a suite under either a dataset-nested or flat root."""
    suite_dir = root / DATASET / suite
    if not suite_dir.is_dir():
        suite_dir = root / suite
    if not suite_dir.is_dir():
        return
    for d in sorted(suite_dir.iterdir()):
        if d.is_dir() and (d / "manifest.json").exists():
            yield d.name, d


# ── DB helpers ───────────────────────────────────────────────────────────
def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_PATH.read_text())
