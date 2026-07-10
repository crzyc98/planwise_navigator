# Contract: Multi-Year Setup Clear Mode

## Purpose

Define user-visible execution semantics for the existing `setup.clear_tables` and `setup.clear_mode` configuration shared by CLI and Studio scenarios. This contract changes no request schema, YAML key, or database schema.

## Configuration Shape

```yaml
setup:
  clear_tables: true
  clear_mode: year  # year | all
  clear_table_patterns:
    - int_
  census_parquet_path: /absolute/path/to/census.parquet
```

`clear_tables`, `clear_mode`, and `clear_table_patterns` remain optional. `census_parquet_path` alone must not imply full-refresh behavior.

## Required Behavior

| Configuration | Before the year loop | Start-year FOUNDATION | Later-year FOUNDATION and temporal models |
|---|---|---|---|
| `clear_tables: true`, `clear_mode: all` | Clear configured tables once | Full refresh permitted | Preserve prior years; no run-wide forced full refresh |
| `clear_tables: true`, `clear_mode: year` | No run-wide reset | Full refresh permitted | Clear/rebuild current-year rows only |
| `clear_tables: true`, `clear_mode` omitted | No run-wide reset; use year-scoped cleanup | Full refresh permitted | Clear/rebuild current-year rows only |
| `setup` contains only `census_parquet_path` | No implicit destructive yearly behavior | Full refresh permitted | Preserve prior years |
| `clear_tables: false` or omitted | No configured clearing | Full refresh permitted for first-year initialization | Preserve prior years |

Model-specific full-refresh exceptions may continue only where they do not depend on prior-year temporal rows.

## Invariants

- `clear_mode: all` describes a clean-slate simulation run, not a request to erase completed years between iterations of that run.
- An omitted `clear_mode` resolves to year-preserving behavior; only explicit `all` requests a clean-slate reset.
- FOUNDATION full refresh is a first-simulation-year initialization behavior.
- Registered temporal accumulators must never be full-refreshed after the start year.
- Existing scenario configuration remains backward compatible; no migration is required.
- CLI and Studio executions resolve these semantics identically.

## Error Behavior

Before generating events for year N where N is later than the start year, the run must verify required year N-1 accumulator rows exist. If required state is missing, the run fails with the existing year-dependency error context rather than treating employees as never enrolled.
