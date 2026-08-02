# Step 1b — merge the hazard-cache pair — REVERTED

## Change attempted

Replace the two-command hazard-cache rebuild in
`planalign_orchestrator/hazard_cache_manager.py:395-432`:

```
run   --select int_effective_parameters --full-refresh
build --select dim_*_hazards hazard_cache_metadata --full-refresh
```

with a single DAG-ordered invocation:

```
build --select int_effective_parameters dim_*_hazards hazard_cache_metadata --full-refresh
```

## Outcome: STOP condition hit on the first 60k run

T024 predeclared this exact stop: *"Confirm `int_effective_parameters`' schema
tests pass at 60k, since moving from `run` to `build` newly executes them. If
they are flaky, revert step 1b."*

They do not pass. The run fails with a **DuckDB binder error, `VARCHAR >=
INTEGER`**.

## Root cause — a pre-existing broken test, not a regression

`dbt/models/intermediate/schema.yml:1241-1246` declares:

```yaml
- name: job_level
  data_tests:
    - not_null
    - dbt_utils.accepted_range:
        min_value: 1
        max_value: 5
```

`dbt_utils.accepted_range` generates `job_level >= 1`. But the materialized
column is a string:

| Column | Type |
|---|---|
| `fiscal_year` | INTEGER |
| **`job_level`** | **VARCHAR** |
| `parameter_value` | DOUBLE |

`VARCHAR >= INTEGER` cannot bind in DuckDB, so the test errors rather than
fails.

**This test has never run.** The orchestrator only ever `run`s this model
(`hazard_cache_manager.py:403`), and `dbt run` does not execute tests. Step 1b
did not break anything — switching to `build` merely executed a test that had
been dormant since it was written. `int_effective_parameters` is tagged
`["critical", "foundation"]`, and its `job_level` range has never been
validated.

Timing repetitions were stopped at the failure; no measurement was taken,
because a step that cannot complete has no wall time to report.

## Decision: **REVERT**

- Parity: **not reached** — the candidate run never completed.
- Delta: **not measured.**
- Bar: 3.000s (rebased). Moot.

Reverted in full: `hazard_cache_manager.py` and
`tests/unit/test_hazard_cache_batching.py` restored to their pre-step state.

### Why not fix the test and retry

Three reasons, in order of weight:

1. **Fixing it means deciding what it should assert**, on a critical foundation
   model whose `job_level` typing is itself suspect — four `dim_*_hazards`
   models join against this column. That is a correctness investigation, not a
   performance change, and folding it into an invocation-count feature would
   make this diff impossible to review as behavior-preserving.
2. **The payoff does not justify it.** Step 1b is worth roughly one command's
   marginal cost. Against a multi-run 60k gate plus an unbounded correctness
   investigation, that is a bad trade.
3. **Weakening or skipping the test to obtain a pass was never an option.** It
   would convert a real, newly surfaced coverage gap into a silently suppressed
   one — the opposite of what the gate exists to do.

Filed separately as a correctness issue. See [decision-log.md](decision-log.md).
