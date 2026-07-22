# Contract: All-Mart Correctness Parity Gate

**Feature**: 121-reduce-dbt-invocations

Every consolidation tier must be proven **output-neutral** before it is kept. The gate is a bidirectional, order-insensitive, duplicate-preserving multiset comparison of **all mart tables** between a baseline run and a candidate run, each in its own isolated database.

## Scope (per spec clarification Q2 → all marts)

- **In scope**: every `fct_*` and `dim_*` mart table. Enumerate, don't hardcode:
  ```bash
  cd dbt && dbt ls --select marts --resource-type model --output name
  ```
- **Out of scope**: `int_*` accumulators and staging (materialization may legitimately differ while marts stay identical); the marts are the authoritative surface.

## Excluded fields (audit-timestamp exemptions)

- `created_at`, `snapshot_created_at`
- `run_metadata` / `run_execution_metadata` rows (inherently per-run: timestamps, correlation/run IDs)

All other columns must match exactly.

## Comparison method (proven in feature 120)

For each mart `M`, both directions must return **0 rows**:

```sql
-- baseline − candidate
SELECT COUNT(*) FROM (
  SELECT <cols-except-excluded> FROM baseline.M
  EXCEPT ALL
  SELECT <cols-except-excluded> FROM candidate.M
);
-- candidate − baseline
SELECT COUNT(*) FROM (
  SELECT <cols-except-excluded> FROM candidate.M
  EXCEPT ALL
  SELECT <cols-except-excluded> FROM baseline.M
);
```

`EXCEPT ALL` preserves duplicate multiplicities (a row present 3× vs 2× is a diff), satisfying FR-009's "including duplicate multiplicities."

## Pass criteria

| Check | Requirement |
|---|---|
| Per-mart parity | 0 / 0 for **every** mart. One non-zero fails the tier. |
| Coverage | The compared mart set equals the full `dbt ls --select marts` set (no silent omission). |
| Determinism | Two candidate runs (same seed+config) also produce 0 / 0 (FR-010). |
| Horizon | Comparison is over the full five-year run, not a single year (multi-year invariant). |

## Where this runs

- Baseline DB: a full five-year run on HEAD (pre-tier) into an isolated `.duckdb`.
- Candidate DB: a full five-year run with the tier applied into a second isolated `.duckdb`.
- Never against the shared `dbt/simulation.duckdb`.
