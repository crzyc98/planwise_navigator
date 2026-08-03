# Quickstart: Seed Ensembles

**Feature**: 133-seed-ensemble-bands

How to run an ensemble, read the output, and validate the implementation.

---

## Run one

```bash
source .venv/bin/activate

# 25-seed ensemble — bands only
planalign simulate 2025-2029 --seeds 25

# With budget thresholds
planalign simulate 2025-2029 --seeds 25 \
  --threshold "total_employer_plan_cost:2400000"

# With variance attribution (states its run count before spending it)
planalign simulate 2025-2029 --seeds 25 --attribution --attribution-seeds 10
```

Output lands in a timestamped directory — never in the shared dev database:

```
var/ensembles/20260803T141522Z-baseline/
├── seed_42.duckdb  seed_1043.duckdb  ...      # one per seed, read-only after their run
└── ensemble.duckdb                            # bands, provenance, and optional attribution
```

## Read the results

```bash
E=var/ensembles/20260803T141522Z-baseline/ensemble.duckdb

# The bands
duckdb "$E" "SELECT simulation_year, p10, p50, p90, n_seeds
           FROM fct_metric_distributions
           WHERE metric = 'total_employer_plan_cost'
           ORDER BY simulation_year"

# Anything where percentiles were withheld
duckdb "$E" "SELECT metric, simulation_year, n_seeds, n_seeds_requested
           FROM fct_metric_distributions WHERE NOT is_sufficient"

# Provenance
duckdb "$E" "SELECT ensemble_id, ensemble_seed_count, ensemble_role,
                  substr(config_fingerprint,1,12) AS fp
           FROM run_metadata ORDER BY run_timestamp DESC"
```

## Verify the percentiles yourself (SC-003)

The per-seed values are retained precisely so the bands can be checked independently:

```bash
duckdb "$E" "SELECT seed, value FROM fct_metric_seed_values
           WHERE metric='total_employer_plan_cost' AND simulation_year=2029
           ORDER BY seed"
```

```python
import numpy as np
np.percentile(values, [10, 25, 50, 75, 90], method="linear")
```

## Verify determinism (SC-002)

```bash
planalign simulate 2025-2029 --seed-list 42,1043,2044 --database /tmp/ens_a
planalign simulate 2025-2029 --seed-list 42,1043,2044 --database /tmp/ens_b
EA=$(find /tmp/ens_a -name ensemble.duckdb -print -quit)
EB=$(find /tmp/ens_b -name ensemble.duckdb -print -quit)
duckdb "$EA" "ATTACH '$EB' AS other (READ_ONLY);
              SELECT COUNT(*) AS differences FROM (
                (SELECT * FROM fct_metric_distributions
                 EXCEPT SELECT * FROM other.fct_metric_distributions)
                UNION ALL
                (SELECT * FROM other.fct_metric_distributions
                 EXCEPT SELECT * FROM fct_metric_distributions)
              )"
# expect 0
```

---

## Testing

```bash
# Fast — pure functions, no simulation
pytest -m fast tests/test_ensemble_aggregate.py tests/test_ensemble_planner.py \
               tests/test_ensemble_risk.py tests/test_ensemble_attribution.py

# The Stage 5 gate — must pass before attribution work begins
pytest -m integration tests/test_subsystem_seed_identity.py

# Full ensemble in isolated temp databases
pytest -m integration tests/test_ensemble_end_to_end.py
```

---

## What you will not see, and why

**Enrollment and merit report `not stochastic`, not `0%`.**

Enrollment's ten hash sites omit the random seed, so every seed draws the same enrollment decisions for the same employee — enrollment outcomes differ between seeds only because the surviving population differs. Merit contains no random draws at all; it is a deterministic formula.

Both would measure ~0% variance contribution, and both would be read as "this assumption doesn't drive cost" — the opposite of the truth, which is "this assumption isn't modeled stochastically." The table says so directly instead.

Making enrollment seed-variant is a real change worth making, but it shifts results for every existing scenario and every stored baseline, so it belongs in its own change with its own before/after evidence. See `research.md` D1.

---

## Gotchas

- **Memory, not CPU, binds.** Each concurrent seed run peaks around 1296 MiB. The pool sizes itself from available memory; `--parallel` overrides it and will warn if you exceed the budget.
- **`--discard-seed-dbs` forfeits baseline reuse.** A later `--attribution` run will re-execute its baselines instead of reusing the headline runs.
- **Attribution seeds must be a subset of the headline seed list.** That is what makes the comparison paired — frozen and baseline runs must differ *only* in the frozen subsystem.
- **Below `--min-seeds`, percentiles are withheld, not computed.** This exits 0, not an error. The per-seed values are still written.
