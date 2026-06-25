from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import rel_to_repo, resolve_path


SCHEMA_VERSION = "lm-bench-samples-v1"


@dataclass(frozen=True)
class SampleManifest:
    path: Path
    payload: dict[str, Any]

    @property
    def model_id(self) -> str:
        return str(self.payload["model_id"])

    @property
    def label(self) -> str:
        return str(self.payload.get("label") or self.model_id)

    @property
    def dataset(self) -> str:
        return str(self.payload["dataset"])

    @property
    def suite_id(self) -> str:
        return str(self.payload["suite_id"])

    @property
    def seq_len(self) -> int:
        return int(self.payload["seq_len"])

    @property
    def n_samples(self) -> int:
        return int(self.payload["n_samples"])

    @property
    def seed(self) -> int:
        return int(self.payload["seed"])

    @property
    def sample_path(self) -> Path:
        raw = self.payload["sample_path"]
        return resolve_path(raw, base=self.path.parent)


def load_manifest(path: str | Path) -> SampleManifest:
    manifest_path = resolve_path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{manifest_path}: expected schema_version={SCHEMA_VERSION}, "
            f"got {payload.get('schema_version')!r}"
        )
    return SampleManifest(path=manifest_path, payload=payload)


def find_manifests(
    samples_root: str | Path,
    dataset: str,
    suite_id: str,
    model_ids: list[str] | None = None,
) -> list[SampleManifest]:
    root = resolve_path(samples_root) / dataset / suite_id
    wanted = None if not model_ids or model_ids == ["all"] else set(model_ids)
    manifests: list[SampleManifest] = []
    for path in sorted(root.glob("*/manifest.json")):
        manifest = load_manifest(path)
        if wanted is None or manifest.model_id in wanted:
            manifests.append(manifest)
    if not manifests:
        suffix = "all models" if wanted is None else ", ".join(sorted(wanted))
        raise FileNotFoundError(f"no sample manifests found under {root} for {suffix}")
    return manifests


def write_manifest(path: str | Path, payload: dict[str, Any]) -> None:
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_manifest_payload(
    *,
    model: dict[str, Any],
    suite: dict[str, Any],
    out_dir: Path,
    sample_path: Path,
    n_samples: int,
    source_type: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "suite_id": suite["id"],
        "model_id": model["id"],
        "label": model.get("label", model["id"]),
        "dataset": suite["dataset"],
        "seq_len": int(suite["seq_len"]),
        "n_samples": int(n_samples),
        "seed": int(suite.get("seed", 0)),
        "sample_path": rel_to_manifest(sample_path, out_dir),
        "source_type": source_type,
        "checkpoint": {
            "path": rel_to_repo(model["path"]) if model.get("path") else None,
            "family": model.get("family"),
            "adapter": model.get("adapter"),
        },
        "sampling": suite.get("sampling", {}),
    }
    if model.get("generation"):
        payload["generation"] = model["generation"]
    if model.get("source"):
        payload["source"] = model["source"]
    if model.get("revision"):
        payload["revision"] = model["revision"]
    if model.get("sample_file"):
        payload["source_sample_file"] = rel_to_repo(model["sample_file"])
    if extra:
        payload.update(extra)
    return payload


def rel_to_manifest(path: Path, manifest_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(manifest_dir.resolve()))
    except ValueError:
        return rel_to_repo(path)
