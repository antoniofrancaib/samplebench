#!/usr/bin/env python3
"""Build the committed SampleBench catalog from canonical dLMbench corpora."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


# Keep the r1 selection seed so adding one corpus does not reshuffle the 64
# previously deployed model subsets. The study version changes because the UI
# now presents complete texts instead of truncated excerpts.
RELEASE_ID = "dlmbench-canonical-20260814-r3"
RELEASE_SEED = "samplebench-dlmbench-canonical-20260814-r1"
SAMPLES_PER_MODEL = 40
EXPECTED_SOURCE_DATASETS = {"lm1b": 8, "owt": 57}
EXPECTED_FILES = {"samples.jsonl", "manifest.json", "checksums.sha256"}

# These legacy IDs are byte-identical aliases of the corresponding v2 slots.
# Keeping both would create self-distribution battles and double-count one
# corpus family in the public study. The source corpora remain canonical and
# are recorded as excluded from this deployment release.
EXCLUDED_CORPORA = {
    "owt_duo_base_1024_nfe",
    "owt_flm_1024_nfe",
    "owt_fmlm_1_nfe",
    "owt_fmlm_4_nfe",
    "owt_fmlm_32_nfe",
    "owt_mdlm_1024_nfe",
    "owt_sedd_1024_nfe",
    "owt_v2_replaid_nosc_ddpm_1024_nfe",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def family_for(generator_id: str) -> str:
    checks = (
        ("replaid", "replaid"),
        ("cobit", "cobit"),
        ("langflow", "langflow"),
        ("fmlm", "fmlm"),
        ("flm", "flm"),
        ("mdlm", "mdlm"),
        ("sedd", "sedd"),
        ("di4c", "di4c"),
        ("sdtt", "sdtt"),
        ("duo", "duo"),
        ("elf", "elf"),
        ("rdlm", "rdlm"),
        ("_ar_", "ar"),
        ("owt_ar_", "ar"),
    )
    for marker, family in checks:
        if marker in generator_id:
            return family
    return "other"


def select_rows(rows: list[dict], corpus_digest: str) -> list[dict]:
    ranked = sorted(
        rows,
        key=lambda row: hashlib.sha256(
            f"{RELEASE_SEED}\0{corpus_digest}\0{row['id']}".encode("utf-8")
        ).digest(),
    )
    return sorted(ranked[:SAMPLES_PER_MODEL], key=lambda row: row["id"])


def load_corpus(path: Path, dataset: str) -> tuple[dict, dict]:
    actual_files = {item.name for item in path.iterdir() if item.is_file()}
    if actual_files != EXPECTED_FILES:
        raise ValueError(f"{path}: expected exactly {sorted(EXPECTED_FILES)}, found {sorted(actual_files)}")

    manifest_path = path / "manifest.json"
    samples_path = path / "samples.jsonl"
    checksum_path = path / "checksums.sha256"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    generator_id = path.name
    canonical = manifest.get("canonical") or {}
    schema_version = manifest.get("schema_version")
    if schema_version == "dlmbench-inference-v2":
        if manifest.get("provenance_status") != "complete":
            raise ValueError(f"{path}: replicated provenance is not complete")
        source_type = "dlmbench_replicated_generation"
    elif schema_version == "dlmbench-author-provided-v1":
        if manifest.get("provenance_status") != "author-provided":
            raise ValueError(f"{path}: author-provided provenance status is invalid")
        if manifest.get("source_type") != "author-provided":
            raise ValueError(f"{path}: author-provided source type is invalid")
        source_type = "dlmbench_author_provided"
    else:
        raise ValueError(f"{path}: unsupported manifest schema {schema_version!r}")
    if manifest.get("sample_count") != 1024:
        raise ValueError(f"{path}: expected 1024 samples")
    if canonical.get("dataset") != dataset or canonical.get("generator_id") != generator_id:
        raise ValueError(f"{path}: canonical identity mismatch")

    corpus_digest = sha256_file(samples_path)
    if manifest.get("output_sha256") != corpus_digest:
        raise ValueError(f"{path}: manifest sample digest mismatch")
    if checksum_path.read_text(encoding="utf-8").strip() != f"{corpus_digest}  samples.jsonl":
        raise ValueError(f"{path}: checksum file mismatch")

    rows: list[dict] = []
    with samples_path.open(encoding="utf-8") as handle:
        for expected_id, line in enumerate(handle):
            row = json.loads(line)
            if row.get("id") != expected_id or not isinstance(row.get("text"), str) or not row["text"]:
                raise ValueError(f"{path}: invalid sample row {expected_id}")
            rows.append({"id": expected_id, "text": row["text"]})
    if len(rows) != 1024:
        raise ValueError(f"{path}: found {len(rows)} rows")

    selected = select_rows(rows, corpus_digest)
    config = manifest.get("generation_config") or {}
    sampling = manifest.get("sampling") or {}
    family = family_for(generator_id)
    model = {
        "id": generator_id,
        "name": config.get("label") or manifest.get("label") or generator_id,
        "dataset": dataset,
        "method": "Autoregressive" if family == "ar" else "Diffusion",
        "family": family,
        "algo": config.get("algo") or sampling.get("algorithm") or family,
        "nfe": config.get("nfe") or sampling.get("benchmark_nfe_label"),
        "corpusSha256": corpus_digest,
        "samples": [
            {
                "id": f"{dataset}-{generator_id}-{corpus_digest[:12]}-{row['id']:06d}",
                "sourceId": row["id"],
                "text": row["text"],
            }
            for row in selected
        ],
    }
    record = {
        "dataset": dataset,
        "generator_id": generator_id,
        "label": model["name"],
        "family": family,
        "source_sample_count": 1024,
        "selected_sample_count": len(selected),
        "selected_source_ids": [row["id"] for row in selected],
        "samples_sha256": corpus_digest,
        "source_manifest_sha256": sha256_file(manifest_path),
        "generation_code_commit": manifest.get("code_commit"),
        "source_bundle_digest": manifest.get("source_bundle_digest")
        or (manifest.get("conversion") or {}).get("source_bundle_digest"),
        "source_type": source_type,
        "provider": (manifest.get("provider") or {}).get("name"),
    }
    return model, record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    models: list[dict] = []
    records: list[dict] = []
    observed: dict[str, int] = {}
    source_observed: dict[str, int] = {}
    for dataset, expected_count in EXPECTED_SOURCE_DATASETS.items():
        dataset_root = args.source / dataset
        corpus_dirs = sorted(path for path in dataset_root.iterdir() if path.is_dir())
        if len(corpus_dirs) != expected_count:
            raise ValueError(f"{dataset_root}: expected {expected_count} corpora, found {len(corpus_dirs)}")
        source_observed[dataset] = len(corpus_dirs)
        observed[dataset] = sum(path.name not in EXCLUDED_CORPORA for path in corpus_dirs)
        for corpus_dir in corpus_dirs:
            model, record = load_corpus(corpus_dir, dataset)
            if corpus_dir.name in EXCLUDED_CORPORA:
                record["deployment_excluded"] = True
            else:
                models.append(model)
            records.append(record)

    models.sort(key=lambda model: (model["dataset"], model["id"]))
    records.sort(key=lambda record: (record["dataset"], record["generator_id"]))
    families = sorted({model["family"] for model in models})
    args.output.mkdir(parents=True, exist_ok=True)

    data_js = (
        "// Generated from canonical dLMbench corpora. Do not edit by hand.\n"
        f"export const checkpointFamilies = {json.dumps(families, ensure_ascii=False)};\n"
        f"export const studyVersion = {json.dumps(RELEASE_ID)};\n"
        f"export const availableDatasets = {json.dumps(sorted(EXPECTED_SOURCE_DATASETS))};\n"
        "export const models = "
        + json.dumps(models, ensure_ascii=False, indent=2)
        + ";\n"
    )
    (args.output / "data.js").write_text(data_js, encoding="utf-8")
    release = {
        "schema_version": "samplebench-data-release-v1",
        "release_id": RELEASE_ID,
        "source_type": "canonical_dlmbench_only",
        "selection": {
            "algorithm": "lowest SHA-256 ranks without replacement, then source-ID order",
            "seed": RELEASE_SEED,
            "samples_per_model": SAMPLES_PER_MODEL,
        },
        "excluded_corpora": sorted(EXCLUDED_CORPORA),
        "dataset_counts": observed,
        "source_dataset_counts": source_observed,
        "source_corpus_count": len(records),
        "deployment_model_count": len(models),
        "deployment_sample_count": sum(len(model["samples"]) for model in models),
        "model_count": len(models),
        "sample_count": sum(len(model["samples"]) for model in models),
        "corpora": records,
    }
    (args.output / "data-release.json").write_text(
        json.dumps(release, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"release_id": RELEASE_ID, "models": len(models), "samples": release["sample_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
