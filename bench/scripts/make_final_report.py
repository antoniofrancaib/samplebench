"""Aggregate final_metrics summary.json files into paper tables.

Reads:
    results/metrics/final_metrics/{metric}/{dataset}/{suite}/summary.json

Writes to results/metrics/final_metrics/report/:
    lm1b_final_table.{md,csv}
    owt_final_table.{md,csv}

Columns per table:
    Generator | Suite | gen-PPL | H (nats) | MAUVE | GradMoment |
    EnergyDist | FMTyp-p | Rep-1 | Rep-2 | Rep-3 | Rep-4
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
METRICS_ROOT = REPO_ROOT / "data" / "metrics"
REPORT_DIR = REPO_ROOT / "bench" / "analysis"

METRICS = ["gen_ppl", "mauve", "grad_moment", "energy_mmd", "htesting", "rep4"]

SUITES = {
    "owt": ["owt_L1024_diffusion_v2"],
}

SUITE_LABEL = {
    "lm1b_L128_paper":       "paper",
    "owt_L1024_paper":       "paper",
    "owt_L1024_diffusion_v2": "v2",
}

# Output columns: (header, field_key)
COLUMNS = [
    ("Generator",    "model_id"),
    ("Suite",        "suite_label"),
    ("gen-PPL↓",     "gen_ppl"),
    ("H↑ (nats)",    "h_emp"),
    ("MAUVE↑",       "mauve"),
    ("GradMoment↓",  "grad_moment"),
    ("EnergyDist↓",  "energy"),
    ("FMTyp-p↑",     "fmtyp_p"),
    ("Rep-1↓",       "rep_1"),
    ("Rep-2↓",       "rep_2"),
    ("Rep-3↓",       "rep_3"),
    ("Rep-4↓",       "rep_4"),
]

# Numeric precision for each output field
PRECISION = {
    "gen_ppl":      2,
    "h_emp":        4,
    "mauve":        4,
    "grad_moment":  4,
    "energy":       5,
    "fmtyp_p":      4,
    "rep_1":        4,
    "rep_2":        4,
    "rep_3":        4,
    "rep_4":        4,
}


def load_metric_rows(metric: str, dataset: str, suite: str) -> list[dict]:
    path = METRICS_ROOT / suite / metric / "summary.json"
    if not path.exists():
        print(f"  [missing] {path}", file=sys.stderr)
        return []
    with path.open() as fh:
        data = json.load(fh)
    return data.get("rows", [])


def build_key_map(dataset: str) -> dict[tuple[str, str], dict]:
    """Returns {(suite_id, model_id): merged_metric_row}."""
    records: dict[tuple[str, str], dict] = {}

    for suite in SUITES[dataset]:
        for metric in METRICS:
            for row in load_metric_rows(metric, dataset, suite):
                key = (row["suite_id"], row["model_id"])
                if key not in records:
                    records[key] = {
                        "model_id":    row["model_id"],
                        "suite_id":    row["suite_id"],
                        "suite_label": SUITE_LABEL.get(row["suite_id"], row["suite_id"]),
                    }
                # Pull relevant fields per metric
                if metric == "gen_ppl":
                    records[key]["gen_ppl"] = row.get("gen_ppl")
                    records[key]["h_emp"]   = row.get("h_emp")
                elif metric == "mauve":
                    records[key]["mauve"] = row.get("mauve")
                elif metric == "grad_moment":
                    records[key]["grad_moment"] = row.get("grad_moment")
                elif metric == "energy_mmd":
                    records[key]["energy"] = row.get("energy")
                elif metric == "htesting":
                    records[key]["fmtyp_p"] = row.get("fmtyp_p")
                elif metric == "rep4":
                    for n in [1, 2, 3, 4]:
                        records[key][f"rep_{n}"] = row.get(f"rep_{n}")

    return records


def sort_rows(records: dict, dataset: str) -> list[dict]:
    suite_order = {s: i for i, s in enumerate(SUITES[dataset])}
    rows = list(records.values())
    rows.sort(key=lambda r: (suite_order.get(r["suite_id"], 99), r["model_id"]))
    return rows


def fmt(val, field: str) -> str:
    if val is None:
        return "—"
    prec = PRECISION.get(field, 4)
    return f"{float(val):.{prec}f}"


def write_markdown(path: Path, dataset: str, rows: list[dict]) -> None:
    headers = [h for h, _ in COLUMNS]
    sep = ["-" * max(len(h), 6) for h in headers]
    lines = ["# Final Metrics Table — " + dataset.upper(), ""]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(sep) + " |")
    for row in rows:
        cells = []
        for header, field in COLUMNS:
            if field in ("model_id", "suite_label"):
                cells.append(str(row.get(field, "—")))
            else:
                cells.append(fmt(row.get(field), field))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    path.write_text("\n".join(lines))
    print(f"[report] {path}")


def write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [f for _, f in COLUMNS]
    display_names = {f: h for h, f in COLUMNS}
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writerow({f: display_names[f] for f in fieldnames})
        for row in rows:
            out = {}
            for _, field in COLUMNS:
                val = row.get(field)
                if field in ("model_id", "suite_label"):
                    out[field] = val or "—"
                else:
                    out[field] = fmt(val, field)
            writer.writerow(out)
    print(f"[report] {path}")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    for dataset in SUITES:
        records = build_key_map(dataset)
        if not records:
            print(f"[warn] no data for {dataset}", file=sys.stderr)
            continue
        rows = sort_rows(records, dataset)
        print(f"\n[{dataset}] {len(rows)} rows")
        write_markdown(REPORT_DIR / f"{dataset}_metrics_table.md", dataset, rows)
        write_csv(REPORT_DIR / f"{dataset}_metrics_table.csv", rows)


if __name__ == "__main__":
    main()
