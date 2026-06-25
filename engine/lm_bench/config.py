from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .paths import resolve_path


def load_yaml(path: str | Path) -> dict[str, Any]:
    config_path = resolve_path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{config_path}: top-level YAML object must be a mapping")
    return data


def format_args(args: list[str], values: dict[str, object]) -> list[str]:
    return [str(arg).format_map(_MissingIsLiteral(values)) for arg in args]


class _MissingIsLiteral(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"

