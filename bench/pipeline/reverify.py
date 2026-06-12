#!/usr/bin/env python3
"""Re-verify the canonical metrics by re-running the VENDORED eval code.

Runs bench/evals/<metric>/run.py on the full lm-bench corpus for a suite and
diffs the result against the values stored in samplebench.db (which came from
lm-bench's published final table). A pass means the vendored snapshot reproduces
the numbers we serve.

CPU metrics (rep4, energy_mmd, htesting) run anywhere. GPU metrics
(gen_ppl, mauve, grad_moment) need the bench/requirements-eval.txt stack + CUDA.

Run:  python3 bench/pipeline/reverify.py --metric rep4 --suite owt_L1024_paper
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    BENCH, DATASET, LM_BENCH, LM_SAMPLES, REFERENCE_MODEL, connect,
)

EVALS = BENCH / "evals"

# runner output key -> DB metric key
KEY_MAP = {
    "rep4":        {"rep_1": "rep1", "rep_2": "rep2", "rep_3": "rep3", "rep_4": "rep4"},
    "energy_mmd":  {"energy": "energy_dist"},
    "htesting":    {"fmtyp_p": "fmtyp_p"},
    "gen_ppl":     {"gen_ppl": "gen_ppl", "h_emp": "entropy_nats"},
    "mauve":       {"mauve": "mauve"},
    "grad_moment": {"grad_moment": "grad_moment"},
}
CPU_METRICS = {"rep4", "energy_mmd", "htesting"}
NEEDS_REF = {"energy_mmd", "htesting", "mauve", "grad_moment"}


def torch_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def metric_args(metric: str) -> list[str]:
    cfg = yaml.safe_load((LM_BENCH / "configs" / "metrics.yaml").read_text())
    return [str(a) for a in cfg.get("metrics", {}).get(metric, {}).get("args", [])]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metric", default="rep4", choices=sorted(KEY_MAP))
    ap.add_argument("--suite", default="owt_L1024_paper")
    ap.add_argument("--limit", type=int, default=None, help="samples per model (default: all)")
    ap.add_argument("--tol", type=float, default=0.02, help="abs tolerance")
    args = ap.parse_args()

    if args.metric not in CPU_METRICS and not torch_available():
        print(f"{args.metric} needs torch/CUDA (pip install -r bench/requirements-eval.txt).")
        print("Run a CPU metric instead, e.g. --metric rep4.")
        sys.exit(2)

    suite_dir = LM_SAMPLES / DATASET / args.suite
    models = sorted(p.name for p in suite_dir.iterdir()
                    if (p / "manifest.json").exists()) if suite_dir.is_dir() else []
    if not models:
        print(f"no corpus at {suite_dir}")
        sys.exit(1)

    con = connect()
    db_vals = {(r["model_id"], r["metric"]): r["value"]
               for r in con.execute("SELECT model_id, metric, value FROM metrics "
                                     "WHERE suite_id = ?", (args.suite,))}
    con.close()

    out_dir = Path(tempfile.mkdtemp(prefix="reverify_"))
    cmd = [sys.executable, str(EVALS / args.metric / "run.py"),
           "--out", str(out_dir), "--seed", "1"]
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    if args.metric in NEEDS_REF:
        ref = suite_dir / REFERENCE_MODEL / "manifest.json"
        cmd += ["--reference-corpus", str(ref)]
    cmd += metric_args(args.metric)
    for m in models:
        cmd += ["--corpus", str(suite_dir / m / "manifest.json")]

    print(f"re-running vendored {args.metric} on {len(models)} models …")
    env = {"PYTHONPATH": str(EVALS)}
    proc = subprocess.run(cmd, cwd=str(LM_BENCH), env={**_os_environ(), **env},
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout[-2000:]); print(proc.stderr[-2000:])
        sys.exit(proc.returncode)

    rows = json.loads((out_dir / "summary.json").read_text())["rows"]
    keymap = KEY_MAP[args.metric]
    n_ok = n_fail = n_skip = 0
    print(f"\n{'model':26s}{'metric':12s}{'recomputed':>12}{'db':>12}{'Δ':>10}  ok")
    for r in rows:
        mid = r["model_id"]
        for rk, dbk in keymap.items():
            if rk not in r or (mid, dbk) not in db_vals:
                n_skip += 1
                continue
            got, want = float(r[rk]), float(db_vals[(mid, dbk)])
            ok = abs(got - want) <= args.tol
            n_ok += ok; n_fail += (not ok)
            print(f"{mid:26s}{dbk:12s}{got:12.4f}{want:12.4f}{got-want:+10.4f}  "
                  f"{'✓' if ok else '✗'}")
    print(f"\n{n_ok} pass, {n_fail} fail, {n_skip} skipped (tol={args.tol})")
    sys.exit(1 if n_fail else 0)


def _os_environ():
    import os
    return dict(os.environ)


if __name__ == "__main__":
    main()
