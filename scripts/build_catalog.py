#!/usr/bin/env python3
"""Build the committed SampleBench catalog from canonical dLMbench corpora."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


# r6 is a new study: votes and public IDs must never mix with earlier releases.
RELEASE_ID = "dlmbench-canonical-20260826-r6"
RELEASE_SEED = "samplebench-dlmbench-canonical-20260826-r6"
SAMPLES_PER_MODEL = 40
EXPECTED_SOURCE_DATASETS = {"lm1b": 9, "owt": 63}
EXPECTED_DEPLOYMENT_DATASETS = {"lm1b": 7, "owt": 21}
EXPECTED_COHORT_COUNTS = {"primary": 28}
EXPECTED_FILES = {"samples.jsonl", "manifest.json", "checksums.sha256"}
EVIDENCE_SCHEMA = "samplebench-arm-evidence-v1"
SAFETY_POLICY = "samplebench-public-safety-v2"
VALID_COHORTS = {"primary"}
HISTORICAL_RECOVERY_SCHEMA = "dlmbench-historical-recovery-v1"
HISTORICAL_SOURCE_COMMIT = "90d5b419b4fa0381b4952fed0df2f9c4f7bc0415"
HISTORICAL_BUNDLE_ID = "audit-20260826-candi-plaid-cobit-recovery-r3"
HISTORICAL_BUNDLE_DIGEST = "ec12cdb8d277e275860318914f76367f13198dee1a9181f24fb69017656a3b65"
HISTORICAL_LEGACY_SCHEMA = "lm-bench-samples-v1"
HISTORICAL_SUITE_ID = "owt_L1024_diffusion_v2"

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

# Conservative, deterministic public-safety screen. It removes obvious
# contact information, markup/decoding failures, and high-risk terms before
# cryptographic sample selection. This is a screening gate, not a claim that
# automated moderation replaces human review. The v2 additions are limited to
# failures found during the r6 manual review: bare links/handles, rendered
# block/editorial artifacts, and clearly unsafe violent or sexual-assault text.
SAFETY_PATTERNS = {
    "replacement_character": re.compile("�"),
    "url": re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE),
    "bare_domain": re.compile(
        r"(?<![@\w])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b",
        re.IGNORECASE,
    ),
    "social_handle": re.compile(r"(?<![\w@])@[a-z0-9_]{2,}\b", re.IGNORECASE),
    "url_fragment": re.compile(
        r"\b[a-z0-9_-]{2,}/(?:watch|videos?|status)\?[^\s<]+", re.IGNORECASE
    ),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "phone": re.compile(
        r"(?:\+\d{1,3}[ .-]?(?:\(?\d{2,4}\)?[ .-]?)?\d{3,4}[ .-]\d{3,4}|"
        r"\b\d{3}[-.]\d{3}[-.]\d{4}\b|\(\d{3}\)\s*\d{3}[-.\s]\d{4})"
    ),
    "html": re.compile(r"</?[a-z][^>]*>", re.IGNORECASE),
    "block_glyph": re.compile(r"[\u2580-\u259f\u25a0]"),
    "editorial_markup": re.compile(
        r"(?:\[(?:/?caption|date\s*=|edit\s*)[^\]]*\]|"
        r"\b(?:hide|show)\s+transcript\b|"
        r"\[(?:instagram|check\s+out)\b[^\]]*\])",
        re.IGNORECASE,
    ),
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
        r"bloodbath|massacre\w*|tortur\w*|gunned\s+down|"
        r"(?:was|were|been|be|is|are)\s+murder\w*|murder\s+trial|"
        r"(?:grotesque\s+body|sickening\s+patterns|head\s+(?:away|off)|"
        r"torn\s+(?:loose|apart)|woman['’]s\s+head\s+(?:away|off))|"
        r"shot\s+(?:dead|himself|herself)|literally\s+shot|open(?:ed)?\s+fire|"
        r"(?:taking|took|holding|held)\s+(?:\w+\s+){0,3}hostage\w*|"
        r"(?:bombing\s+rampage|two\s+bombs?\s+and\s+a\s+missile|bomb\s+scare)|"
        r"shoot(?:ing|ings)\s+(?:event|him|her|the)|"
        r"pistol\s+in\s+(?:his|her)\s+hand|sharp\s+blade|"
        r"pull(?:ed|ing)?\s+the\s+trigger|female\s+circumcision|"
        r"genital\s+mutilat\w*|sexual[- ](?:assault|abuse|harassment)|"
        r"sex[- ]offender\w*|adult\s+content|neo[- ]nazi\w*|lynch\w*\s+nazi|"
        r"campaign\s+of\s+terrorism|al\s+shabaab|armed\s+struggle\w*|"
        r"uninterrupted\s+warfare|civil\s+war|female\s+circumcision|"
        r"vehicular\s+execution|gunshot|stabbing\s+(?:dempsey|switchstone)|"
        r"stabbed\s+one\s+of\s+the\s+boys|violent\s+law\s+enforcement\s+encounter|"
        r"phishing\s+site|login\s+password|names\s+and\s+emails)\b",
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
        ("plaid", "plaid"),
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


def require_subset(actual: object, expected: object, label: str) -> None:
    """Require every evidence value recursively without constraining extra fields."""

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise ValueError(f"{label}: expected an object")
        for key, value in expected.items():
            if key not in actual:
                raise ValueError(f"{label}: missing required field {key!r}")
            require_subset(actual[key], value, f"{label}.{key}")
    elif actual != expected:
        raise ValueError(f"{label}: expected {expected!r}, found {actual!r}")


def git_blob_sha1(path: Path) -> str:
    """Return the Git blob object ID for a file without invoking Git."""

    content = path.read_bytes()
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def validate_historical_recovery_manifest(
    path: Path,
    manifest: dict,
    arm: dict,
    dataset: str,
    generator_id: str,
) -> None:
    """Fail closed on the lossless, legacy Git-recovery provenance contract."""

    requirements = arm.get("historical_recovery")
    if not isinstance(requirements, dict):
        raise ValueError(f"{path}: historical arm lacks recovery requirements")
    if dataset != "owt":
        raise ValueError(f"{path}: historical recovery is only supported for OWT r6 arms")
    required_recovery_values = {
        "source_commit": HISTORICAL_SOURCE_COMMIT,
        "bundle_id": HISTORICAL_BUNDLE_ID,
        "source_bundle_digest": HISTORICAL_BUNDLE_DIGEST,
        "legacy_schema_version": HISTORICAL_LEGACY_SCHEMA,
        "suite_id": HISTORICAL_SUITE_ID,
        "legacy_id_prefix": f"owt-{generator_id}-",
    }
    for key, expected in required_recovery_values.items():
        if requirements.get(key) != expected:
            raise ValueError(f"{path}: historical recovery {key} does not match the r6 contract")
    required_manifest = {
        "schema_version": HISTORICAL_RECOVERY_SCHEMA,
        "provenance_status": "historical-recovery",
        "source_type": "historical-git-recovery",
        "bundle_id": requirements.get("bundle_id"),
        "dataset": dataset,
        "generator_id": generator_id,
        "sample_count": 1024,
        "output_sha256": requirements.get("samples_sha256"),
        "historical_source_commit": requirements.get("source_commit"),
        "legacy_schema_version": requirements.get("legacy_schema_version"),
        "legacy_id_prefix": requirements.get("legacy_id_prefix"),
        "source_bundle_digest": requirements.get("source_bundle_digest"),
        "source_manifest_sha256": requirements.get("source_manifest_sha256"),
        "canonical": {
            "dataset": dataset,
            "generator_id": generator_id,
            "source_manifest_sha256": requirements.get("canonical_source_manifest_sha256"),
        },
        "frozen_checksum": requirements.get("frozen_checksum"),
    }
    require_subset(manifest, required_manifest, f"{path}: historical recovery manifest")

    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"{path}: historical recovery source metadata is missing")
    required_source = {
        "git_commit": requirements.get("source_commit"),
        "kind": "git-commit",
        "manifest_blob_id": requirements.get("manifest_blob_id"),
        "manifest_git_path": requirements.get("manifest_git_path"),
        "manifest_sha256": requirements.get("source_manifest_sha256"),
        "sample_blob_id": requirements.get("sample_blob_id"),
        "sample_git_path": requirements.get("sample_git_path"),
        "slurm_job_id": requirements.get("source_slurm_job_id"),
        "extraction_command": requirements.get("extraction_command"),
    }
    require_subset(source, required_source, f"{path}: historical source metadata")

    immutable_bundle = manifest.get("immutable_bundle")
    require_subset(
        immutable_bundle,
        {
            "bundle_id": requirements.get("bundle_id"),
            "root": (requirements.get("immutable_bundle") or {}).get("root"),
            "source_archive": "source.tar",
            "source_bundle_sha256": requirements.get("source_bundle_digest"),
        },
        f"{path}: immutable source bundle",
    )
    legacy_manifest = source.get("legacy_manifest")
    require_subset(
        legacy_manifest,
        {
            "dataset": dataset,
            "model_id": generator_id,
            "n_samples": 1024,
            "sample_path": "samples.jsonl",
            "schema_version": HISTORICAL_LEGACY_SCHEMA,
            "seq_len": 1024,
            "suite_id": HISTORICAL_SUITE_ID,
            "label": requirements.get("label"),
            "generation": {
                "algo": requirements.get("legacy_algo"),
                "backend": requirements.get("legacy_backend"),
                "nfe": requirements.get("nfe"),
                "paper_aligned": True,
            },
        },
        f"{path}: legacy source manifest",
    )
    if source.get("manifest_blob_id") != requirements.get("manifest_blob_id"):
        raise ValueError(f"{path}: historical manifest Git blob mismatch")
    if source.get("sample_blob_id") != git_blob_sha1(path / "samples.jsonl"):
        raise ValueError(f"{path}: historical sample Git blob mismatch")


def require_unavailable_checkpoint(checkpoint: dict, path: Path, schema_version: str) -> None:
    """Prevent historical and author-provided arms from gaining fake identity."""

    expected_status = (
        "unavailable" if schema_version == HISTORICAL_RECOVERY_SCHEMA else "samples-only"
    )
    if checkpoint.get("status") != expected_status or checkpoint.get("revision") is not None or checkpoint.get("digest") is not None:
        raise ValueError(f"{path}: {schema_version} arm has fabricated checkpoint identity")


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


def load_corpus(
    path: Path,
    dataset: str,
    arm: dict,
    evidence_sources: dict[str, dict],
    checkpoints: dict[str, dict],
) -> tuple[dict, dict]:
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
    elif schema_version == "dlmbench-historical-recovery-v1":
        if manifest.get("provenance_status") != "historical-recovery":
            raise ValueError(f"{path}: historical recovery provenance status is invalid")
        if manifest.get("source_type") != "historical-git-recovery":
            raise ValueError(f"{path}: historical recovery source type is invalid")
        source_type = "dlmbench_historical_git_recovery"
    else:
        raise ValueError(f"{path}: unsupported manifest schema {schema_version!r}")
    if manifest.get("sample_count") != 1024:
        raise ValueError(f"{path}: expected 1024 samples")
    if canonical.get("dataset") != dataset or canonical.get("generator_id") != generator_id:
        raise ValueError(f"{path}: canonical identity mismatch")
    if arm.get("dataset") != dataset:
        raise ValueError(f"{path}: evidence dataset mismatch")
    if arm.get("configuration") != f"configs/generation.yaml:{generator_id}":
        raise ValueError(f"{path}: evidence must bind the exact generation config")
    evidence_ref = arm.get("evidence")
    if evidence_ref not in evidence_sources:
        raise ValueError(f"{path}: unknown paper evidence reference {evidence_ref!r}")
    checkpoint_ref = arm.get("checkpoint")
    if checkpoint_ref not in checkpoints:
        raise ValueError(f"{path}: unknown checkpoint evidence reference {checkpoint_ref!r}")
    checkpoint_evidence = checkpoints[checkpoint_ref]
    status = arm.get("status")
    cohorts = arm.get("cohorts")
    if status == "included":
        if not isinstance(cohorts, list) or not cohorts or set(cohorts) - VALID_COHORTS:
            raise ValueError(f"{path}: included arm has invalid cohorts")
        if schema_version == "dlmbench-inference-v2" and arm.get("provenance_tier") not in {"A", "B"}:
            raise ValueError(f"{path}: included replicated arm must have A/B provenance")
        if schema_version == "dlmbench-author-provided-v1" and arm.get("provenance_tier") != "C":
            raise ValueError(f"{path}: included author-provided arm must have C provenance")
        if schema_version == HISTORICAL_RECOVERY_SCHEMA and arm.get("provenance_tier") != "historical-recovery":
            raise ValueError(f"{path}: included historical arm must have historical-recovery provenance")
    elif status == "excluded":
        if cohorts != [] or not arm.get("exclusion_reason"):
            raise ValueError(f"{path}: excluded arm needs no cohorts and a reason")
    else:
        raise ValueError(f"{path}: invalid evidence status {status!r}")

    if schema_version == HISTORICAL_RECOVERY_SCHEMA:
        validate_historical_recovery_manifest(path, manifest, arm, dataset, generator_id)
        if status == "included":
            require_unavailable_checkpoint(checkpoint_evidence, path, schema_version)
    elif status == "included" and schema_version == "dlmbench-author-provided-v1":
        require_unavailable_checkpoint(checkpoint_evidence, path, schema_version)

    # Included replicated arms must bind every deployment identity to the
    # reviewed checkpoint evidence record. Historical and author-provided
    # arms deliberately carry an unavailable checkpoint record instead.
    if status == "included" and schema_version == "dlmbench-inference-v2":
        if manifest.get("checkpoint_id") != checkpoint_ref:
            raise ValueError(f"{path}: checkpoint identity does not match arm evidence")
        if manifest.get("checkpoint_revision") != checkpoint_evidence.get("revision"):
            raise ValueError(f"{path}: checkpoint revision does not match arm evidence")
        if manifest.get("checkpoint_digest") != checkpoint_evidence.get("digest"):
            raise ValueError(f"{path}: checkpoint digest does not match arm evidence")
    corpus_digest = sha256_file(samples_path)
    if manifest.get("output_sha256") != corpus_digest:
        raise ValueError(f"{path}: manifest sample digest mismatch")
    if checksum_path.read_text(encoding="utf-8").strip() != f"{corpus_digest}  samples.jsonl":
        raise ValueError(f"{path}: checksum file mismatch")

    rows: list[dict] = []
    historical_rows = schema_version == HISTORICAL_RECOVERY_SCHEMA
    with samples_path.open(encoding="utf-8") as handle:
        for expected_id, line in enumerate(handle):
            row = json.loads(line)
            expected_source_id = (
                f"{arm['historical_recovery']['legacy_id_prefix']}{expected_id:06d}"
                if historical_rows else expected_id
            )
            if row.get("id") != expected_source_id or not isinstance(row.get("text"), str) or not row["text"]:
                raise ValueError(f"{path}: invalid sample row {expected_id}")
            rows.append({"id": expected_id, "text": row["text"]})
    if len(rows) != 1024:
        raise ValueError(f"{path}: found {len(rows)} rows")

    selected, rejected = select_rows(rows, corpus_digest)
    config = manifest.get("generation_config") or {}
    legacy_manifest = ((manifest.get("source") or {}).get("legacy_manifest") or {})
    legacy_generation = legacy_manifest.get("generation") or {}
    if status == "included" and schema_version == "dlmbench-inference-v2" and config.get("id") != generator_id:
        raise ValueError(f"{path}: manifest generation config identity mismatch")
    nfe_match = re.search(r"_(\d+)_nfe$", generator_id)
    if status == "included" and nfe_match:
        if schema_version == HISTORICAL_RECOVERY_SCHEMA:
            manifest_nfe = legacy_generation.get("nfe")
        elif schema_version == "dlmbench-author-provided-v1":
            manifest_nfe = (manifest.get("sampling") or {}).get("benchmark_nfe_label")
        else:
            manifest_nfe = config.get("nfe")
        if manifest_nfe != int(nfe_match.group(1)):
            raise ValueError(f"{path}: manifest NFE does not match generator identity")
    if status == "included" and arm.get("manifest_requirements"):
        require_subset(manifest, arm["manifest_requirements"], f"{path}: manifest evidence")
    sampling = manifest.get("sampling") or {}
    family = family_for(generator_id)
    name = config.get("label") or manifest.get("label") or legacy_manifest.get("label") or generator_id
    algo = config.get("algo") or sampling.get("algorithm") or legacy_generation.get("algo") or family
    nfe = config.get("nfe") or sampling.get("benchmark_nfe_label") or legacy_generation.get("nfe")
    generator_matches = manifest.get("generator_id") == generator_id
    if schema_version == "dlmbench-inference-v2":
        generator_matches = generator_matches and config.get("id") == generator_id
    checkpoint_matches = manifest.get("checkpoint_id") == checkpoint_ref
    checkpoint_revision_matches = manifest.get("checkpoint_revision") == checkpoint_evidence.get("revision")
    checkpoint_digest_matches = manifest.get("checkpoint_digest") == checkpoint_evidence.get("digest")
    model = {
        "id": generator_id,
        "name": name,
        "dataset": dataset,
        "method": "Autoregressive" if family == "ar" else "Diffusion",
        "family": family,
        "public_group_id": public_group_id(dataset, generator_id, corpus_digest),
        "algo": algo,
        "nfe": nfe,
        "cohorts": cohorts,
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
            "policy": SAFETY_POLICY,
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
        "manifest_identity_matches_arm": {
            "generator": generator_matches,
            "checkpoint": checkpoint_matches if schema_version == "dlmbench-inference-v2" else None,
            "checkpoint_revision": checkpoint_revision_matches if schema_version == "dlmbench-inference-v2" else None,
            "checkpoint_digest": checkpoint_digest_matches if schema_version == "dlmbench-inference-v2" else None,
            "nfe": not nfe_match or nfe == int(nfe_match.group(1)),
        },
        "arm_evidence": {
            **arm,
            "paper": evidence_sources[evidence_ref],
            "checkpoint_record": checkpoint_evidence,
        },
    }
    return model, record


def load_arm_evidence(path: Path) -> dict:
    evidence = json.loads(path.read_text(encoding="utf-8"))
    if evidence.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError(f"{path}: unsupported evidence schema")
    if evidence.get("study_version") != RELEASE_ID:
        raise ValueError(f"{path}: evidence study version does not match r6")
    if set(evidence.get("cohorts", {})) != VALID_COHORTS:
        raise ValueError(f"{path}: evidence must define only the primary cohort")
    inventory = evidence.get("inventory")
    if not isinstance(inventory, dict):
        raise ValueError(f"{path}: r6 evidence must include the inspected inventory")
    if inventory.get("inspected_source_counts") != EXPECTED_SOURCE_DATASETS:
        raise ValueError(f"{path}: inspected source inventory does not match the r6 contract")
    if inventory.get("deployment_counts") != EXPECTED_DEPLOYMENT_DATASETS:
        raise ValueError(f"{path}: deployment inventory does not match the r6 contract")
    if set(inventory.get("non_canonical_exclusions", [])) != NON_CANONICAL_CORPORA:
        raise ValueError(f"{path}: non-canonical exclusion inventory does not match the r6 contract")
    arms = evidence.get("arms")
    if not isinstance(arms, dict) or not arms:
        raise ValueError(f"{path}: arms must be a non-empty object")
    if not isinstance(evidence.get("papers"), dict) or not evidence["papers"]:
        raise ValueError(f"{path}: papers must be a non-empty object")
    if not isinstance(evidence.get("checkpoints"), dict) or not evidence["checkpoints"]:
        raise ValueError(f"{path}: checkpoints must be a non-empty object")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--server-output", type=Path)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path(__file__).with_name("arm-evidence-r6.json"),
    )
    args = parser.parse_args()

    evidence = load_arm_evidence(args.evidence)
    arms = evidence["arms"]
    papers = evidence["papers"]
    checkpoints = evidence["checkpoints"]

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
        source_ids = {path.name for path in corpus_dirs}
        evidence_ids = {generator_id for generator_id, arm in arms.items() if arm.get("dataset") == dataset}
        if source_ids != evidence_ids:
            raise ValueError(
                f"{dataset_root}: arm evidence classification mismatch; "
                f"missing={sorted(source_ids - evidence_ids)}, extra={sorted(evidence_ids - source_ids)}"
            )
        observed[dataset] = sum(arms[path.name].get("status") == "included" for path in corpus_dirs)
        for corpus_dir in corpus_dirs:
            arm = arms[corpus_dir.name]
            model, record = load_corpus(corpus_dir, dataset, arm, papers, checkpoints)
            if arm["status"] == "excluded":
                record["deployment_excluded"] = True
                record["exclusion_reason"] = arm["exclusion_reason"]
            else:
                models.append(model)
            records.append(record)

    if observed != EXPECTED_DEPLOYMENT_DATASETS:
        raise ValueError(f"deployment dataset counts mismatch: {observed}")

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
                    "cohorts": model["cohorts"],
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
            "    modelId: entry.id, dataset: entry.dataset, sourceId: entry.sourceIds[index], cohorts: entry.cohorts,\n"
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
            "safety_policy": SAFETY_POLICY,
            "public_sample_ids": "opaque SHA-256 tokens; model identity is server-only",
        },
        "arm_evidence_schema": EVIDENCE_SCHEMA,
        "arm_evidence_sha256": sha256_file(args.evidence),
        "excluded_corpora": sorted(
            generator_id for generator_id, arm in arms.items() if arm["status"] == "excluded"
        ),
        "dataset_counts": observed,
        "source_dataset_counts": source_observed,
        "source_corpus_count": len(records),
        "deployment_model_count": len(models),
        "deployment_sample_count": sum(len(model["samples"]) for model in models),
        "model_count": len(models),
        "sample_count": sum(len(model["samples"]) for model in models),
        "cohort_model_counts": {
            cohort: sum(cohort in model["cohorts"] for model in models)
            for cohort in sorted(VALID_COHORTS)
        },
        "cohorts": evidence["cohorts"],
        "inventory": evidence["inventory"],
        "corpora": records,
    }
    if release["cohort_model_counts"] != EXPECTED_COHORT_COUNTS:
        raise ValueError(f"cohort model counts mismatch: {release['cohort_model_counts']}")
    (args.output / "data-release.json").write_text(
        json.dumps(release, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"release_id": RELEASE_ID, "models": len(models), "samples": release["sample_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
