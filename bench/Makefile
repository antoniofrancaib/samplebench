# SampleBench data pipeline. Source of truth: ~/lm-bench.
# Run from this dir (`make -C bench refresh`). Scripts resolve repo paths internally.
PY := python3
P  := pipeline

.PHONY: refresh refresh-real sync db simulate pull frontend correlate reverify clean

# Demo refresh (simulated votes until real ones are collected).
refresh: sync db simulate frontend correlate

# Production refresh (pull real votes from Supabase).
refresh-real: sync db pull frontend correlate

sync:        ## snapshot ~/lm-bench (configs, curated samples, canonical metrics)
	$(PY) $(P)/sync.py
db:          ## (re)build samplebench.db static tables from the snapshot
	$(PY) $(P)/build_db.py
simulate:    ## load simulated Bradley-Terry votes into the DB
	$(PY) $(P)/simulate_votes.py
pull:        ## load real votes from Supabase into the DB
	$(PY) $(P)/pull_votes.py
frontend:    ## regenerate src/data.js from the DB
	$(PY) $(P)/build_frontend.py
correlate:   ## fit human scores + write analysis/report.md
	$(PY) $(P)/correlate.py
reverify:    ## re-run a vendored metric on the corpus, diff vs DB (default rep4)
	$(PY) $(P)/reverify.py --metric rep4 --suite owt_L1024_paper
clean:       ## drop the built database
	rm -f db/samplebench.db db/samplebench.db-wal db/samplebench.db-shm
