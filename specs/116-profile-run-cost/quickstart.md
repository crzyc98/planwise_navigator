# Quickstart: Run-Cost Profile

End-to-end path from clean checkout to the committed report. Total ~1–2 days, dominated by large-census run time.

## Prerequisites

```bash
source .venv/bin/activate          # project venv (dbt, duckdb, planalign_orchestrator installed)
planalign health                   # no DB locks, sqlparse fix installed
```

## 1. Generate the large census (~60K employees)

```bash
python -m scripts.perf_profile.make_large_census --out var/perf_profile/census_large.parquet --factor 8
# Verify: prints row count (~60,040) and a demographic sanity summary vs the dev census
```

## 2. Run the measurement matrix (~9 timed runs + 3 warm-up runs)

```bash
python -m scripts.perf_profile.run_matrix --sizes tiny,dev,large --reps 3 --horizon 2025-2027
# - Captures SHA-256 of dbt/simulation.duckdb first; re-verifies at the end (SC-007)
# - Each repetition: fresh DuckDB under var/perf_profile/db/, DATABASE_PATH set, threads=1
# - Emits var/perf_profile/samples/{size}-{rep}.json per run (contract: contracts/timing-data.md)
# Tip: start with --sizes tiny --reps 1 to smoke-test the harness in ~2 minutes
```

## 3. Run the direct-execution probe (EVENT_GENERATION, year 2025, dev census)

```bash
python -m scripts.perf_profile.probe_direct_execution --year 2025
# Builds a dev-census run to post-FOUNDATION, copies the DB, then times the stage
# both ways and diffs results. Emits var/perf_profile/samples/probe.json
```

## 4. Build the report

```bash
python -m scripts.perf_profile.build_report --out docs/perf/run_cost_profile.md
# Renders all tables from samples; fails loudly on schema mismatch or residue > 10%
# Re-running regenerates the same tables from the same samples (SC-006)
```

## 5. Decide and close the loop

1. Read `docs/perf/run_cost_profile.md` — criteria appear before results; the recommendation row evaluates the **large** census.
2. Commit `scripts/perf_profile/`, `docs/perf/run_cost_profile.md`, and the spec artifacts (never `var/perf_profile/`).
3. Comment the recommendation + report link on issue **#455**; check it off in tracking issue **#463**.
4. GO → pick up **#456** with the report's projection as its acceptance baseline. NO-GO → open the redirect issue naming the report's top-3 compute hotspots.

## Sanity checklist (before trusting the numbers)

- [ ] `run_matrix` exit code 0 and final line `shared dev DB unchanged (sha256 verified)`
- [ ] Every headline size has ≥ 3 `warm=true` samples (`large` ≥ 2, labeled in report)
- [ ] Report section 4: residue ≤ 10% at every size
- [ ] Report section 6: cross-check ratio within same order of magnitude (0.3×–3×)
- [ ] Probe `equivalent=true` — if false, treat as a critical finding and read section 7 before the recommendation
