#!/usr/bin/env python3
"""Build the committed SampleBench catalog from canonical dLMbench corpora."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


# Keep the source selection explicit. The dLMbench working tree also contains
# naive baselines and other exploratory exports; those are not part of this
# human-comparison release. The release is rebuilt from the 65 canonical
# directories below, even when the source tree contains extras.
RELEASE_ID = "dlmbench-canonical-20260814-r4"
RELEASE_SEED = "samplebench-dlmbench-canonical-20260814-r4"
SAMPLES_PER_MODEL = 40
EXPECTED_SOURCE_DATASETS = {"lm1b": 8, "owt": 57}
EXPECTED_FILES = {"samples.jsonl", "manifest.json", "checksums.sha256"}

NON_CANONICAL_CORPORA = {
    "lm1b_phrase_bank_1000",
    "lm1b_mirror_5000",
    "lm1b_periodic_k_64",
    "lm1b_topk_iid_k32",
    "owt_phrase_bank_5000",
    "owt_mirror_5000",
    "owt_periodic_k_400",
    "owt_topk_iid_k64",
}

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

# Conservative, deterministic public-safety screen. It removes obvious
# contact information, markup/decoding failures, and high-risk terms before
# cryptographic sample selection. This is a screening gate, not a claim that
# automated moderation replaces human review.
SAFETY_PATTERNS = {
    "replacement_character": re.compile("�"),
    "url": re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "phone": re.compile(
        r"(?:\+\d{1,3}[ .-]?(?:\(?\d{2,4}\)?[ .-]?)?\d{3,4}[ .-]\d{3,4}|\b\d{3}[-.]\d{3}[-.]\d{4}\b)"
    ),
    "html": re.compile(r"</?[a-z][^>]*>", re.IGNORECASE),
    "sexual": re.compile(
        r"\b(?:porn|pornographic|blowjob|masturbat\w*|semen|ejaculat\w*|genital\w*|penetrat\w*|"
        r"nude|nudity|anal sex|oral sex|intercourse|prostitut\w*|rape\w*|molest\w*|"
        r"pedophil\w*|child porn)\b",
        re.IGNORECASE,
    ),
    "hate_slur": re.compile(
        r"\b(?:nigger|nigga|faggot|kike|chink|spic|wetback|retard(?:ed)?)\b", re.IGNORECASE
    ),
    "self_harm": re.compile(
        r"\b(?:suicide|suicidal|self[- ]harm|kill myself|take my own life)\b", re.IGNORECASE
    ),
    "graphic_violence": re.compile(
        r"\b(?:beheaded|decapitat\w*|dismember\w*|gore\w*|mutilat\w*|disembowel\w*|"
        r"bloodbath|massacre\w*|tortur\w*)\b",
        re.IGNORECASE,
    ),
    "profanity": re.compile(
        r"\b(?:fuck(?:ing|ed)?|shit|cunt|slut|whore|bitch|dick|pussy|cock|asshole|motherfucker)\b",
        re.IGNORECASE,
    ),
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


def public_sample_id(dataset: str, generator_id: str, corpus_digest: str, source_id: int) -> str:
    token = hashlib.sha256(
        f"{RELEASE_ID}\0{dataset}\0{generator_id}\0{corpus_digest}\0{source_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"s-{token}"


def public_group_id(dataset: str, generator_id: str, corpus_digest: str) -> str:
    token = hashlib.sha256(
        f"{RELEASE_ID}\0group\0{dataset}\0{generator_id}\0{corpus_digest}".encode("utf-8")
    ).hexdigest()[:16]
    return f"g-{token}"


def safety_reasons(text: str) -> list[str]:
    return [name for name, pattern in SAFETY_PATTERNS.items() if pattern.search(text)]


def select_rows(rows: list[dict], corpus_digest: str) -> tuple[list[dict], dict[str, int]]:
    rejected: dict[str, int] = {}
    safe_rows = []
    for row in rows:
        reasons = safety_reasons(row["text"])
        if reasons:
            for reason in reasons:
                rejected[reason] = rejected.get(reason, 0) + 1
        else:
            safe_rows.append(row)
    if len(safe_rows) < SAMPLES_PER_MODEL:
        raise ValueError(
            f"{corpus_digest}: safety screen leaves {len(safe_rows)} rows, "
            f"fewer than the required {SAMPLES_PER_MODEL}"
        )
    ranked = sorted(
        safe_rows,
        key=lambda row: hashlib.sha256(
            f"{RELEASE_SEED}\0{corpus_digest}\0{row['id']}".encode("utf-8")
        ).digest(),
    )
    return sorted(ranked[:SAMPLES_PER_MODEL], key=lambda row: row["id"]), rejected


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

    selected, rejected = select_rows(rows, corpus_digest)
    config = manifest.get("generation_config") or {}
    sampling = manifest.get("sampling") or {}
    family = family_for(generator_id)
    model = {
        "id": generator_id,
        "name": config.get("label") or manifest.get("label") or generator_id,
        "dataset": dataset,
        "method": "Autoregressive" if family == "ar" else "Diffusion",
        "family": family,
        "public_group_id": public_group_id(dataset, generator_id, corpus_digest),
        "algo": config.get("algo") or sampling.get("algorithm") or family,
        "nfe": config.get("nfe") or sampling.get("benchmark_nfe_label"),
        "corpusSha256": corpus_digest,
        "samples": [
            {
                "id": public_sample_id(dataset, generator_id, corpus_digest, row["id"]),
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
        "safety_screen": {
            "policy": "samplebench-public-safety-v1",
            "rejected_count": sum(rejected.values()),
            "rejected_reason_counts": rejected,
        },
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
    parser.add_argument("--server-output", type=Path)
    args = parser.parse_args()

    models: list[dict] = []
    records: list[dict] = []
    observed: dict[str, int] = {}
    source_observed: dict[str, int] = {}
    for dataset, expected_count in EXPECTED_SOURCE_DATASETS.items():
        dataset_root = args.source / dataset
        corpus_dirs = sorted(
            path
            for path in dataset_root.iterdir()
            if path.is_dir() and path.name not in NON_CANONICAL_CORPORA
        )
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
    public_samples = [
        {
            "id": sample["id"],
            "dataset": model["dataset"],
            "group": model["public_group_id"],
            "text": sample["text"],
        }
        for model in models
        for sample in model["samples"]
    ]
    public_js = (
        "// Generated from the reviewed public release. Do not edit by hand.\n"
        f"export const studyVersion = {json.dumps(RELEASE_ID)};\n"
        f"export const availableDatasets = {json.dumps(sorted(EXPECTED_SOURCE_DATASETS))};\n"
        "export const samples = "
        + json.dumps(public_samples, ensure_ascii=False, indent=2)
        + ";\n"
    )
    (args.output / "data-public.js").write_text(public_js, encoding="utf-8")
    if args.server_output:
        server_entries = []
        for model in models:
            server_entries.append(
                {
                    "id": model["id"],
                    "label": model["name"],
                    "dataset": model["dataset"],
                    "digest": model["corpusSha256"],
                    "publicGroupId": model["public_group_id"],
                    "sourceIds": [sample["sourceId"] for sample in model["samples"]],
                    "sampleIds": [sample["id"] for sample in model["samples"]],
                }
            )
        server_js = (
            "// Generated from the reviewed public release. Do not edit by hand.\n"
            "// Model identity and source mappings stay server-side.\n"
            f"export const ACTIVE_CATALOG_VERSION = {json.dumps(RELEASE_ID)};\n\n"
            "const entries = "
            + json.dumps(server_entries, ensure_ascii=False, indent=2)
            + ";\n\n"
            "export const CATALOG = new Map(entries.map((entry) => [entry.id, entry]));\n"
            "const SAMPLE_CATALOG = new Map();\n"
            "for (const entry of entries) {\n"
            "  entry.sampleIds.forEach((sampleId, index) => SAMPLE_CATALOG.set(sampleId, {\n"
            "    modelId: entry.id, dataset: entry.dataset, sourceId: entry.sourceIds[index],\n"
            "  }));\n"
            "}\n\n"
            "export function getCatalogEntry(modelId) {\n"
            "  return typeof modelId === 'string' ? CATALOG.get(modelId) ?? null : null;\n"
            "}\n\n"
            "export function getCatalogSample(sampleId) {\n"
            "  return typeof sampleId === 'string' ? SAMPLE_CATALOG.get(sampleId) ?? null : null;\n"
            "}\n\n"
            "export function isCatalogSample(modelId, sampleId) {\n"
            "  return getCatalogSample(sampleId)?.modelId === modelId;\n"
            "}\n"
        )
        args.server_output.parent.mkdir(parents=True, exist_ok=True)
        args.server_output.write_text(server_js, encoding="utf-8")
    release = {
        "schema_version": "samplebench-data-release-v1",
        "release_id": RELEASE_ID,
        "source_type": "canonical_dlmbench_only",
        "selection": {
            "algorithm": "lowest SHA-256 ranks without replacement, then source-ID order",
            "seed": RELEASE_SEED,
            "samples_per_model": SAMPLES_PER_MODEL,
            "safety_policy": "samplebench-public-safety-v1",
            "public_sample_ids": "opaque SHA-256 tokens; model identity is server-only",
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
