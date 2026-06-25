# SampleBench data pipeline. Self-contained — no external repo dependency.
# Run from this dir (`make -C bench refresh`). Scripts resolve repo paths internally.
PY := python3
P  := pipeline

.PHONY: refresh refresh-real sync db simulate pull frontend correlate metrics-v2 report reverify clean

# Demo refresh (simulated votes until real ones are collected).
refresh: sync db simulate frontend correlate

# Production refresh (pull real votes from Supabase).
refresh-real: sync db pull frontend correlate

sync:        ## curate data/samples/ → bench/samples_v2/ (seeded 64-per-model subset)
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
metrics-v2:  ## submit metric eval Slurm jobs for all 28 v2 generators (SSH to cluster first)
	@echo "Submitting v2 metrics (gen_ppl mauve rep4 htesting energy_mmd grad_moment)"
	@cd .. && for M in gen_ppl mauve rep4 htesting energy_mmd grad_moment; do \
	  python3 bench/scripts/submit.py eval \
	    --suite owt_L1024_diffusion_v2 --metric $$M; \
	done
	@echo "After jobs complete, run: make report"
report:      ## aggregate metric summary.json files → bench/analysis/owt_metrics_table.{md,csv}
	$(PY) scripts/make_final_report.py
reverify:    ## re-run a vendored metric on the corpus, diff vs DB (default rep4)
	$(PY) $(P)/reverify.py --metric rep4 --suite owt_L1024_diffusion_v2
clean:       ## drop the built database
	rm -f db/samplebench.db db/samplebench.db-wal db/samplebench.db-shm
