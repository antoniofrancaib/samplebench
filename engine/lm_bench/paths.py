from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_path(value: str | Path, base: Path | None = None) -> Path:
    """Resolve repo-relative, user-relative, and environment-expanded paths."""
    raw = os.path.expandvars(os.path.expanduser(str(value)))
    path = Path(raw)
    if path.is_absolute():
        return path
    return (base or REPO_ROOT) / path


def rel_to_repo(path: str | Path) -> str:
    resolved = resolve_path(path)
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)

