from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "lm-bench-samples-v1"


@dataclass(frozen=True)
class Corpus:
    manifest_path: Path
    sample_path: Path
    payload: dict[str, Any]

    @property
    def dataset(self) -> str:
        return str(self.payload.get("dataset", "unknown"))

    @property
    def suite_id(self) -> str:
        return str(self.payload.get("suite_id", "unknown"))

    @property
    def model_id(self) -> str:
        return str(self.payload.get("model_id") or self.sample_path.parent.name)

    @property
    def label(self) -> str:
        return str(self.payload.get("label") or self.model_id)

    @property
    def n_samples(self) -> int:
        return int(self.payload.get("n_samples", 0))

    @property
    def source_type(self) -> str:
        return str(self.payload.get("source_type", "unknown"))


def resolve_path(value: str | Path, base: Path | None = None) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return (base or REPO_ROOT) / path


def rel_path(path: str | Path) -> str:
    resolved = resolve_path(path)
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def add_corpus_args(parser, *, require_reference: bool = False) -> None:
    parser.add_argument(
        "--corpus",
        action="append",
        default=[],
        help="Corpus directory, manifest.json, or samples.jsonl. Can be repeated.",
    )
    parser.add_argument(
        "--corpus-dir",
        action="append",
        default=[],
        help="Directory containing one subdirectory per corpus manifest. Can be repeated.",
    )
    if require_reference:
        parser.add_argument(
            "--reference-corpus",
            required=True,
            help="Reference corpus directory, manifest.json, or samples.jsonl.",
        )
    parser.add_argument("--out", required=True, help="Output directory for metric report files.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum samples per corpus.")
    parser.add_argument("--seed", type=int, default=0)


def load_corpora(args) -> list[Corpus]:
    corpora: list[Corpus] = []
    for value in args.corpus:
        corpora.append(load_corpus(value))
    for value in args.corpus_dir:
        corpora.extend(discover_corpora(value))
    unique: dict[Path, Corpus] = {}
    for corpus in corpora:
        unique[corpus.sample_path.resolve()] = corpus
    out = list(unique.values())
    if not out:
        raise ValueError("no corpora provided; pass --corpus or --corpus-dir")
    return sorted(out, key=lambda c: (c.dataset, c.suite_id, c.model_id))


def discover_corpora(path: str | Path) -> list[Corpus]:
    root = resolve_path(path)
    if not root.exists():
        raise FileNotFoundError(str(root))
    manifests = sorted(root.glob("*/manifest.json"))
    if not manifests and (root / "manifest.json").exists():
        manifests = [root / "manifest.json"]
    if not manifests:
        raise FileNotFoundError(f"no corpus manifests found under {root}")
    return [load_corpus(path) for path in manifests]


def load_corpus(path: str | Path) -> Corpus:
    raw = resolve_path(path)
    if raw.is_dir():
        manifest_path = raw / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"{raw}: missing manifest.json")
        return _load_from_manifest(manifest_path)
    if raw.name == "manifest.json":
        return _load_from_manifest(raw)
    if raw.name == "samples.jsonl":
        manifest_path = raw.with_name("manifest.json")
        if manifest_path.exists():
            return _load_from_manifest(manifest_path)
        payload = _fallback_manifest(raw)
        return Corpus(manifest_path=manifest_path, sample_path=raw, payload=payload)
    raise ValueError(f"{raw}: expected corpus directory, manifest.json, or samples.jsonl")


def _load_from_manifest(path: Path) -> Corpus:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{path}: expected schema_version={SCHEMA_VERSION}, got {payload.get('schema_version')!r}"
        )
    sample_path = resolve_path(payload["sample_path"], base=path.parent)
    if not sample_path.exists():
        raise FileNotFoundError(str(sample_path))
    return Corpus(manifest_path=path, sample_path=sample_path, payload=payload)


def _fallback_manifest(sample_path: Path) -> dict[str, Any]:
    parent = sample_path.parent
    suite = parent.parent.name if parent.parent != parent else "unknown"
    dataset = parent.parent.parent.name if parent.parent.parent != parent.parent else "unknown"
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset": dataset,
        "suite_id": suite,
        "model_id": parent.name,
        "label": parent.name,
        "n_samples": 0,
        "sample_path": str(sample_path),
        "source_type": "sample_file",
    }


def read_samples(corpus: Corpus, *, limit: int | None, seed: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(corpus.sample_path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        obj = json.loads(line)
        text = str(obj.get("text", "")).replace("\n", " ").strip()
        if not text:
            continue
        row = {"index": index, **obj, "text": text}
        rows.append(row)
    rng = random.Random(seed)
    rng.shuffle(rows)
    if limit is not None:
        if len(rows) < limit:
            raise ValueError(f"{corpus.sample_path}: need {limit} samples, got {len(rows)}")
        rows = rows[:limit]
    return rows


def read_texts(corpus: Corpus, *, limit: int | None, seed: int) -> list[str]:
    return [row["text"] for row in read_samples(corpus, limit=limit, seed=seed)]


def corpus_metadata(corpus: Corpus, n: int) -> dict[str, Any]:
    return {
        "dataset": corpus.dataset,
        "suite_id": corpus.suite_id,
        "model_id": corpus.model_id,
        "label": corpus.label,
        "source_type": corpus.source_type,
        "n_samples": n,
        "manifest": rel_path(corpus.manifest_path),
        "sample_path": rel_path(corpus.sample_path),
    }


def ensure_out_dir(path: str | Path) -> Path:
    out = resolve_path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_json(path: str | Path, payload: Any) -> None:
    out = resolve_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[out] {rel_path(out)}")


def write_csv(path: str | Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    out = resolve_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"[out] {rel_path(out)}")


def write_report(
    path: str | Path,
    *,
    title: str,
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str]],
    notes: list[str] | None = None,
) -> None:
    lines = [f"# {title}", ""]
    if config:
        lines.extend(["## Config", ""])
        for key, value in config.items():
            lines.append(f"- `{key}`: `{value}`")
        lines.append("")
    lines.extend(["## Results", ""])
    header = [label for _key, label in columns]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows:
        vals = [_format_cell(row.get(key)) for key, _label in columns]
        lines.append("| " + " | ".join(vals) + " |")
    if notes:
        lines.extend(["", "## Notes", ""])
        for note in notes:
            lines.append(f"- {note}")
    out = resolve_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[out] {rel_path(out)}")


def _format_cell(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text
