from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any


def slug(value: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return out.strip("_") or "run"


def read_text_records(path: str | Path) -> list[dict[str, Any]]:
    """Read TXT, JSON, or JSONL samples and return records with a text field."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    if p.suffix == ".json":
        payload = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            rows = payload.get("generated_seqs") or payload.get("samples") or payload.get("texts")
            if rows is None:
                raise ValueError(f"{p}: JSON lacks generated_seqs/samples/texts")
        elif isinstance(payload, list):
            rows = payload
        else:
            raise ValueError(f"{p}: unsupported JSON sample format")
        return [_coerce_record(row, i) for i, row in enumerate(rows)]

    records: list[dict[str, Any]] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        if p.suffix == ".jsonl":
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                obj = {"text": line}
            records.append(_coerce_record(obj, i))
        else:
            records.append({"text": line.strip(), "source_index": i})
    return [row for row in records if str(row.get("text", "")).strip()]


def select_records(records: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    if len(records) < n:
        raise ValueError(f"need {n} samples, got {len(records)}")
    rng = random.Random(seed)
    indexed = list(enumerate(records))
    rng.shuffle(indexed)
    selected: list[dict[str, Any]] = []
    for source_index, row in indexed[:n]:
        out = dict(row)
        out.setdefault("source_index", source_index)
        selected.append(out)
    return selected


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _coerce_record(value: Any, index: int) -> dict[str, Any]:
    if isinstance(value, dict):
        text = value.get("text") or value.get("sample") or value.get("generated_text")
        if text is None:
            text = value.get("generated_seq")
        row = dict(value)
        row["text"] = str(text if text is not None else "").replace("\n", " ").strip()
        row.setdefault("source_index", index)
        return row
    return {"text": str(value).replace("\n", " ").strip(), "source_index": index}

