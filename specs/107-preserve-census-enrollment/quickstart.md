# Quickstart: Preserve Census Enrollment

## Prerequisites

Work from the repository root and activate the existing environment:

```bash
source .venv/bin/activate
```

All integration and performance work must use temporary or explicitly isolated DuckDB paths, never `dbt/simulation.duckdb`.

## 1. Run Fast Unit Regressions

```bash
pytest \
  tests/unit/orchestrator/test_cleanup_scoping.py \
  tests/unit/orchestrator/test_enrollment_projection.py \
  tests/unit/orchestrator/test_year_executor.py \
  tests/unit/orchestrator/test_pipeline_stage_failure.py \
  tests/unit/test_year_dependency_validator.py \
  -q
```

Expected: reset semantics preserve later years, the projection is deterministic and fact-scoped, and projection/dependency failures stop event generation with structured context.

## 2. Validate dbt Test Selectors Before Story Checkpoints

Run from `dbt/` with one thread:

```bash
cd dbt
DATABASE_PATH=/absolute/path/to/isolated.duckdb ../.venv/bin/dbt ls \
  --resource-type test \
  --select \
    test_census_participants_not_reenrolled \
    test_enrollment_population_split \
    test_multi_year_state_history_retained \
    assert_no_multi_cycle_enrollment \
    assert_voluntary_enrollment_persists \
    test_enrollment_continuity \
    test_enrollment_architecture
cd ..
```

Expected: every selector resolves before implementation checkpoints reference it.

## 3. Run the Isolated Two-Year Outcome, Isolation, and Audit Tests

```bash
RUN_CENSUS_ENROLLMENT_E2E=1 pytest \
  tests/integration/test_census_enrollment_persistence.py \
  tests/integration/test_year_dependency_validation.py \
  -v
```

Expected:

- census participants receive no duplicate year-two enrollment or resulting opt-out;
- their 5% census deferral persists absent a valid change;
- never-enrolled controls remain in the applicable eligible decision population;
- deterministic `1.0` fixtures emit the expected enrollment event;
- scenario A and B use different database/artifact paths and cannot mutate each other;
- all fact rows match the run's scenario/plan IDs;
- the fixture participant lineage trace completes in under 300 seconds; and
- missing prior-year state stops before event generation.

## 4. Run All Enrollment dbt Invariants

Run against the retained isolated two-year database:

```bash
cd dbt
DATABASE_PATH=/absolute/path/to/isolated.duckdb ../.venv/bin/dbt test \
  --select \
    test_census_participants_not_reenrolled \
    test_enrollment_population_split \
    test_multi_year_state_history_retained \
    assert_no_multi_cycle_enrollment \
    assert_voluntary_enrollment_persists \
    test_enrollment_continuity \
    test_enrollment_architecture \
  --vars '{simulation_year: 2026, simulation_start_year: 2025, scenario_id: scenario-a, plan_design_id: plan-a}' \
  --threads 1
cd ..
```

Expected: all projection, population-split, history-retention, continuity, and event-to-state invariants pass.

## 5. Run the 100K Projection Performance Gate

```bash
pytest tests/performance/test_census_enrollment_performance.py -m performance -v
```

Required results:

- 100K employees plus 200K history rows produce exactly 100K unique projected states;
- wall-clock time is <=30 seconds;
- RSS growth is <=1,024 MiB;
- when an accepted baseline exists, median runtime regression is <=15% and RSS regression is <=20%.

## 6. Enforce the Constitutional Fast-Suite Budget

```bash
python scripts/check_fast_suite_runtime.py \
  --max-seconds 10 \
  -- python -m pytest -m fast
```

Expected: the wrapper exits zero only when the complete fast suite finishes in less than 10 seconds.

## 7. Timed Participant Audit

```bash
RUN_CENSUS_ENROLLMENT_E2E=1 pytest \
  tests/integration/test_census_enrollment_persistence.py::test_participant_lineage_trace_under_five_minutes \
  -v
```

Expected: the trace reconciles census state, prior authoritative facts, projection provenance, accumulator state, and year-two snapshot in under 300 seconds.

## Final Verification Checklist

- `fct_yearly_events` is the only post-census enrollment authority.
- No enrollment decision model reads its own history, a fact table, accumulator, or projection by raw table name.
- Projection rebuild is atomic, fact-reconciled, deterministic, prior-year-only, and scenario/plan scoped.
- Full reset occurs once; no temporal model full-refreshes after the start year.
- Eligibility assertions are distinct from stochastic event assertions.
- Scenario/run isolation, retained history, audit timing, reproducibility, 100K scale, and fast-suite timing all pass.
