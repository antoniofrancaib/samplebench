"""Shared paths, config, canonical-metric mapping, and DB helpers."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parents[2]          # .../samplebench
BENCH = REPO / "bench"
DATA_DIR = REPO / "data"
RAW_SAMPLES_DIR = DATA_DIR / "samples"              # full 1024/model JSONL (v2)
METRICS_DIR = DATA_DIR / "metrics"                  # metric outputs from Slurm
CONFIGS_DIR = DATA_DIR / "configs"                  # suite/checkpoint/metric YAMLs

REGISTRY_DIR = BENCH / "registry"                   # curated snapshot + provenance
SAMPLES_DIR_V2 = BENCH / "samples_v2"               # curated 40/model for frontend
ANALYSIS_DIR = BENCH / "analysis"
DB_PATH = BENCH / "db" / "samplebench.db"
SCHEMA_PATH = BENCH / "db" / "schema.sql"
FRONTEND_DATA = REPO / "src" / "data.js"

# ── Config ───────────────────────────────────────────────────────────────
DATASET = "owt"
SUITES_V2 = ["owt_L1024_diffusion_v2"]      # v2 study (diffusion-vs-diffusion only)
REFERENCE_MODEL = "owt_data_train"
CURATE_K = 64                  # curated pool per model (serving + analysis)
FRONTEND_K = 40                # samples per model shipped to the browser
CURATE_SEED = 1234
MIN_CHARS = 200

# v1 study (AR + diffusion). Empty = v2-only deployment.
FRONTEND_SUITES = []
# v2 study (pure diffusion-vs-diffusion, 28 generators).
FRONTEND_SUITES_V2 = ["owt_L1024_diffusion_v2"]
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
