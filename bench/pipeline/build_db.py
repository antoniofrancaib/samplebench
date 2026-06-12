#!/usr/bin/env python3
"""Load the bench/ snapshot into samplebench.db (rebuilt from scratch each run).

Populates the static tables: provenance, checkpoints, suites, models, samples,
metric_meta, metrics. Votes are loaded *after* this by simulate_votes.py or
pull_votes.py (the Makefile orders them), so a rebuild is always fresh.

Run:  python3 bench/pipeline/build_db.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    DB_PATH, FRONTEND_EXCLUDE, FRONTEND_SUITES, METRIC_COLUMNS, REFERENCE_MODEL,
    REGISTRY_DIR, SAMPLES_DIR, SUITES, connect, init_db, iter_model_dirs,
    method_for, read_jsonl,
)


def load_provenance(con):
    prov = json.loads((REGISTRY_DIR / "provenance.json").read_text())
    con.executemany("INSERT OR REPLACE INTO provenance(key, value) VALUES (?, ?)",
                    [(k, json.dumps(v)) for k, v in prov.items()])


def load_checkpoints(con):
    data = yaml.safe_load((REGISTRY_DIR / "checkpoints.yaml").read_text())
    rows = []
    for c in data.get("checkpoints", []):
        rows.append((c["id"], c.get("label"), c.get("family"), c.get("dataset"),
                     int(bool(c.get("enabled", True))), c.get("path"), c.get("source"),
                     json.dumps(c.get("generation", {}))))
    con.executemany(
        "INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def load_suites(con):
    n = 0
    for suite in SUITES:
        cfg_path = REGISTRY_DIR / "suites" / f"{suite}.yaml"
        cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}
        con.execute(
            "INSERT OR REPLACE INTO suites VALUES (?,?,?,?,?,?)",
            (suite, cfg.get("dataset"), cfg.get("seq_len"), cfg.get("n_samples"),
             "owt_data_train", json.dumps(cfg)))
        n += 1
    return n


def load_models(con):
    served = served_model_ids()
    rows = []
    for suite in SUITES:
        for model_id, d in iter_model_dirs(suite, root=SAMPLES_DIR):
            m = json.loads((d / "manifest.json").read_text())
            method = method_for(m.get("family"), m.get("algo"), m.get("source_type"))
            rows.append((model_id, suite, m.get("label", model_id), method,
                         m.get("family"), m.get("algo"), m.get("nfe"),
                         int(model_id == REFERENCE_MODEL),
                         int((suite, model_id) in served)))
    con.executemany("INSERT OR REPLACE INTO models VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def served_model_ids() -> set:
    out = set()
    for suite in FRONTEND_SUITES:
        for model_id, _ in iter_model_dirs(suite, root=SAMPLES_DIR):
            if model_id not in FRONTEND_EXCLUDE:
                out.add((suite, model_id))
    return out


def load_samples(con):
    served_ids = served_sample_ids()
    rows = []
    for suite in SUITES:
        for model_id, d in iter_model_dirs(suite, root=SAMPLES_DIR):
            for rec in read_jsonl(d / "samples.jsonl"):
                rows.append((rec["sample_id"], suite, model_id, rec["text"],
                             rec["char_len"], int(rec["sample_id"] in served_ids)))
    con.executemany("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?)", rows)
    return len(rows)


def served_sample_ids() -> set:
    """Sample ids that build_frontend would ship (paper suite, real models)."""
    import random
    from common import CURATE_SEED, FRONTEND_K
    ids = set()
    for suite in FRONTEND_SUITES:
        for model_id, d in iter_model_dirs(suite, root=SAMPLES_DIR):
            if model_id in FRONTEND_EXCLUDE:
                continue
            recs = list(read_jsonl(d / "samples.jsonl"))
            rng = random.Random(f"frontend:{CURATE_SEED}:{model_id}")
            for r in rng.sample(recs, min(FRONTEND_K, len(recs))):
                ids.add(r["sample_id"])
    return ids


def load_metrics(con):
    # metric_meta
    con.executemany(
        "INSERT OR REPLACE INTO metric_meta VALUES (?,?,?)",
        [(key, label, int(hib)) for (key, label, hib) in METRIC_COLUMNS.values()])

    csv_path = REGISTRY_DIR / "metrics.csv"
    if not csv_path.exists():
        return 0
    n = 0
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            model_id = row["Generator"]
            # Suite column is either "paper" or a full suite id; map to the real suite.
            suite = next((s for s in SUITES if model_id_in_suite(model_id, s)), SUITES[0])
            for col, (key, _, _) in METRIC_COLUMNS.items():
                raw = (row.get(col) or "").strip()
                if raw in ("", "—", "-", "nan", "None"):
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    continue
                con.execute("INSERT OR REPLACE INTO metrics VALUES (?,?,?,?)",
                            (suite, model_id, key, val))
                n += 1
    return n


def model_id_in_suite(model_id: str, suite: str) -> bool:
    d = SAMPLES_DIR / suite / model_id
    return (d / "manifest.json").exists()


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()  # rebuild static tables from scratch
        for ext in ("-wal", "-shm"):
            Path(str(DB_PATH) + ext).unlink(missing_ok=True)

    con = connect()
    init_db(con)
    load_provenance(con)
    nc = load_checkpoints(con)
    ns = load_suites(con)
    nmod = load_models(con)
    nsamp = load_samples(con)
    nm = load_metrics(con)
    con.commit()

    nv = con.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
    nmodels = con.execute("SELECT COUNT(DISTINCT model_id) FROM metrics").fetchone()[0]
    con.close()
    print(f"built {DB_PATH.relative_to(DB_PATH.parents[2])}")
    print(f"  checkpoints={nc}  suites={ns}  models={nmod}  samples={nsamp}")
    print(f"  metrics={nm} values over {nmodels} models  votes={nv}")


if __name__ == "__main__":
    main()
