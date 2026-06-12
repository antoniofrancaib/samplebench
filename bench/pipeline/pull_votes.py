#!/usr/bin/env python3
"""Pull real collected votes from Supabase into samplebench.db.

The web UI writes votes to the Supabase REST table (see src/main.jsx). This
snapshots them into the local analytical DB so correlate.py runs on real data
exactly as it does on the simulated votes.

Env:  VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_SUPABASE_TABLE (default sample_votes)
Run:  python3 bench/pipeline/pull_votes.py   (after build_db.py)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import connect  # noqa: E402

URL = (os.environ.get("VITE_SUPABASE_URL") or "").rstrip("/")
KEY = os.environ.get("VITE_SUPABASE_ANON_KEY") or ""
TABLE = os.environ.get("VITE_SUPABASE_TABLE", "sample_votes")


def fetch_all(page=1000):
    rows, offset = [], 0
    while True:
        req = urllib.request.Request(
            f"{URL}/rest/v1/{TABLE}?select=*&order=id.asc&limit={page}&offset={offset}",
            headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.loads(resp.read())
        rows.extend(batch)
        if len(batch) < page:
            return rows
        offset += page


def main() -> None:
    if not (URL and KEY):
        print("Supabase not configured (VITE_SUPABASE_URL / _ANON_KEY). Nothing pulled.")
        return
    rows = fetch_all()
    out = []
    for r in rows:
        out.append((
            str(r.get("id") or r.get("vote_id")), r.get("session_id"), r.get("battle_id"),
            r.get("choice"), r.get("winner_model_id"), r.get("loser_model_id"),
            r.get("left_model_id"), r.get("right_model_id"),
            r.get("left_sample_id"), r.get("right_sample_id"),
            r.get("response_time_ms"), r.get("app_version"), 0,
        ))
    con = connect()
    con.execute("DELETE FROM votes WHERE is_simulated = 0")
    con.executemany("INSERT OR REPLACE INTO votes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", out)
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM votes WHERE is_simulated = 0").fetchone()[0]
    con.close()
    print(f"pulled {len(out)} votes from Supabase `{TABLE}` ({n} real votes in DB)")


if __name__ == "__main__":
    main()
