from __future__ import annotations

from typing import Any

from .config import load_yaml


def load_checkpoint_registry(path: str) -> list[dict[str, Any]]:
    payload = load_yaml(path)
    rows = payload.get("checkpoints", [])
    if not isinstance(rows, list):
        raise ValueError(f"{path}: checkpoints must be a list")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{path}: checkpoint rows must be mappings")
        for key in ("id", "label", "dataset", "adapter"):
            if key not in row:
                raise ValueError(f"{path}: checkpoint row missing {key}: {row}")
    return rows


def select_models(
    registry: list[dict[str, Any]],
    *,
    dataset: str,
    model_ids: list[str] | None,
) -> list[dict[str, Any]]:
    wanted = None if not model_ids or model_ids == ["all"] else set(model_ids)
    selected = [
        row for row in registry
        if row.get("dataset") == dataset
        and (wanted is None or row["id"] in wanted)
        and (wanted is not None or row.get("enabled", True))
    ]
    if not selected:
        suffix = "all models" if wanted is None else ", ".join(sorted(wanted))
        raise ValueError(f"no registry entries matched dataset={dataset} models={suffix}")
    return selected


def registry_ids(registry: list[dict[str, Any]], dataset: str | None = None) -> list[str]:
    rows = registry if dataset is None else [row for row in registry if row.get("dataset") == dataset]
    return [str(row["id"]) for row in rows]
