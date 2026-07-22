# Quickstart: Validating Reduced Production-Path dbt Invocations

**Feature**: 121-reduce-dbt-invocations

How to baseline, apply a consolidation tier, and prove it is faster **and** output-neutral. Every run uses an **isolated** database; the shared `dbt/simulation.duckdb` is never built into.

## Prerequisites

```bash
source .venv/bin/activate
python -c "import planalign_orchestrator"   # triggers the sqlparse .pth fix
CENSUS=workspaces/1497b19c-b212-4c67-82d3-bc0455b637e0/data/census.parquet   # 60,040 rows
STUDIO_CFG=workspaces/1497b19c-b212-4c67-82d3-bc0455b637e0/scenarios/dc111f09-b27b-4406-8e6f-03eee015e123/config.yaml
```

## 1. Confirm the HEAD baseline schedule (retire "62")

```bash
# Build a baseline five-year run into an isolated DB, then read the recorded schedule.
DATABASE_PATH=/tmp/f121/baseline.duckdb \
  planalign simulate 2025-2029 --config config/simulation_config.yaml --database /tmp/f121/baseline.duckdb

duckdb /tmp/f121/baseline.duckdb \
  "SELECT invocation_count FROM run_execution_metadata ORDER BY recorded_at DESC LIMIT 1"
```

**Expected: 38** (feature-120 authoritative baseline). If it differs, record the actual value — that becomes *the* baseline. "62" is not an invocation count and is not used.

## 2. Measure the warm baseline (median-of-three) for both configs

```bash
# Reference config
python -m scripts.perf_profile.run_matrix --campaign-id f121-base \
  --construction wrapper --config config/simulation_config.yaml --config-label reference \
  --census "$CENSUS" --horizon 2025-2029 --reps 3 --skip-cold

# Studio-realistic config
python -m scripts.perf_profile.run_matrix --campaign-id f121-base \
  --construction wrapper --config "$STUDIO_CFG" --config-label studio \
  --census "$CENSUS" --horizon 2025-2029 --reps 3 --skip-cold
```

Record warm-median wall time, four-way time split (subprocess launch / dbt command wall / model execution / residue), peak RSS, config+census fingerprints, and the construction signature. This is the **before** artifact (SC-009).

## 3. Apply one consolidation tier, then re-measure

Apply Tier A, then B, then C — one at a time. After each:

```bash
# invocation count
DATABASE_PATH=/tmp/f121/after.duckdb \
  planalign simulate 2025-2029 --config config/simulation_config.yaml --database /tmp/f121/after.duckdb
duckdb /tmp/f121/after.duckdb \
  "SELECT invocation_count FROM run_execution_metadata ORDER BY recorded_at DESC LIMIT 1"

# warm wall time (both configs, as in step 2, --campaign-id f121-afterA / afterB / afterC)
```

Targets per tier: A → ~33–34, B → ~28–29, C → ~19–24. All ≤ 32.

## 4. Prove output-neutrality (all-mart parity) — the hard gate

```bash
# Enumerate marts, then EXCEPT ALL both directions for each, excluding audit-timestamps.
cd dbt && dbt ls --select marts --resource-type model --output name
```

For every `fct_*` / `dim_*` mart, both directions must return **0** (see `contracts/correctness-parity.md`):

```sql
ATTACH '/tmp/f121/baseline.duckdb' AS b; ATTACH '/tmp/f121/after.duckdb' AS a;
SELECT COUNT(*) FROM (SELECT * EXCLUDE(created_at, snapshot_created_at) FROM b.fct_workforce_snapshot
                      EXCEPT ALL
                      SELECT * EXCLUDE(created_at, snapshot_created_at) FROM a.fct_workforce_snapshot);
-- repeat reversed, and for fct_yearly_events, fct_employer_match_events, dim_*_hazards, every other mart
```

**Any non-zero on any mart fails the tier** — reconsider or drop it.

## 5. Determinism, invariants, failure attribution

```bash
# Determinism: two candidate runs, same seed+config → 0/0 parity between them.
# Multi-year invariants + rerun-on-existing-output + failed-stage suites:
pytest -m "integration and (invariants or determinism or rerun or failed_stage)" -v \
  # (run against the isolated candidate DB via DATABASE_PATH)

# Failure attribution: inject a broken model inside a batched selection; confirm the error
# names the model + stage + year.
```

## 6. Peak RSS and the ship gate

- **RSS**: candidate peak RSS ≤ baseline × 1.10 for every tier (from the `run_matrix` artifact). Over that → reconsider the tier.
- **Ship gate**: cumulative warm-median improvement vs the step-2 baseline.
  - **≥ 20%** → ships automatically.
  - **< 20%** → **do not auto-decide.** Present the full before/after artifact set to the maintainer and record an explicit ship / no-ship decision (the *Ship decision record*). This is the clarified human-in-the-loop gate (spec Clarifications, Session 2026-07-21).

## Success (feature-level)

- Invocation count ≤ 32 (target ~20–26), confirmed from `run_execution_metadata`.
- All-mart parity 0/0 for every tier shipped; determinism + invariant + rerun + failed-stage suites green.
- Peak RSS ≤ +10%; model/stage/year failure attribution intact.
- Both reference and Studio configs pass identically.
- Shared `dbt/simulation.duckdb` SHA-256 unchanged across the whole campaign.
