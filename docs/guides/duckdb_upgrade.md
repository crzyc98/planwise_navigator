# DuckDB 1.5.5 migration

PlanAlign pins DuckDB 1.5.5 with dbt-core 1.9.11 and dbt-duckdb 1.9.6. The upgrade preserves the 1.1.3 simulation contract rather than accepting new seeded decisions or rounding results.

## Compatibility rules

- Incremental dates, hire counts, and escalation amounts have their final types from year one. The error-level `assert_stable_incremental_column_types` test guards the eight affected columns. The multi-year suite also requires no `__dbt_alter` statements in its isolated dbt logs.
- Use `PLANALIGN_HASH` for simulation decisions, placeholder identifiers, and deterministic event identifiers. DuckDB documents built-in `HASH` as version-dependent. The dbt startup hook installs SQL macros implementing the UTF-8 MurmurHash64A behavior of DuckDB 1.1.3, including empty strings and NULL. Golden values and randomized Unicode tests guard it. Do not replace it with built-in `HASH` or a different digest without an explicit simulation-contract change.
- `stable_decimal` preserves 1.1.3's nearest-even rounding of scaled FLOAT/DOUBLE census values and escalation percentages. Exact DECIMAL and string inputs retain their existing cast semantics. For example, a DOUBLE census amount of `100.005` stays `100.00`, while an exact DECIMAL input of the same amount becomes `100.01`.

Hash algorithm attribution and the MIT notice are in [the third-party notice](../third_party/duckdb_hash_license.txt). The authoritative upstream implementation is [DuckDB v1.1.3 hash.cpp](https://github.com/duckdb/duckdb/blob/v1.1.3/src/common/types/hash.cpp); the version-dependent built-in contract is documented in [DuckDB utility functions](https://duckdb.org/docs/stable/sql/functions/utility.html#hashvalue).

## Validation evidence

Fresh Python 3.12 environments used the same resolved runtime packages except DuckDB. Each run used a new database and separate dbt artifacts. The SQL simulation covered 2025–2027 with the same 7,505-row census, seed 42, and configuration.

| Run | Result | Incremental widening operations |
|---|---|---:|
| Current main, DuckDB 1.1.3 | Completed | 8 |
| Type fix, DuckDB 1.1.3 | Completed, equivalent state | 0 |
| Final compatibility code, DuckDB 1.1.3 | Completed, equivalent state | 0 |
| Final compatibility code, DuckDB 1.5.5 | Completed, equivalent state | 0 |

All 83 state relations (82 tables and one view) matched in both directions, including duplicate multiplicity and column names/types. Physical column order can differ because the old run widened columns in place. DOUBLE values use absolute tolerance `1e-8` and relative tolerance `1e-12`; DECIMAL values compare exactly.

Only `run_metadata` and `run_execution_metadata` are excluded as complete bookkeeping tables. The comparison excludes these explicitly named runtime columns where present: `created_at`, `snapshot_created_at`, `cache_built_at`, `built_at`, `last_updated`, `determination_timestamp`, `calculation_timestamp`, `audit_timestamp`, `processed_at`, `resolved_at`, `calculated_at`, `metadata_generated_at`, `workforce_needs_id`, and `dbt_invocation_id`. The last two identify dbt invocations; deterministic employee and event identifiers are compared.

The final regression runs passed 48 tests on each engine version, covering the four edge configurations, three-year invariants, deterministic reruns, the frozen hash, and decimal rounding. The DuckDB 1.5.5 fast suite also passed all 2,961 selected tests. Studio completed two fresh 2025–2027 API-managed runs in a disposable workspace, with 57,762 events and all six run validation checks passing; analytics and cost comparisons matched the retained 1.1.3 result.

## Existing databases and rollback

The migration does not request a newer storage format. On copies of a 1.1.3 database, both read-only access and a simple write/checkpoint in 1.5.5 left the file readable by 1.1.3. Fresh 1.5.5 simulation output and the persisted hash macros were also readable/callable with 1.1.3. These checks correct the earlier assumption in issue #750 that opening any old database necessarily upgrades it irreversibly.

Keep a filesystem backup of workspace archives before changing engine versions. Treat compatibility as verified for the tested operations, not a guarantee for arbitrary newer DuckDB features or an explicitly newer storage format. To roll back a deployment, restore the previous code/environment and use the preserved pre-upgrade archive if the affected database cannot be opened by the older engine. Never validate migration behavior in `dbt/simulation.duckdb`.

## Repeat the regression checks

```bash
source .venv/bin/activate
DBT_PARTIAL_PARSE=false DATABASE_PATH=/tmp/planalign-upgrade-test.duckdb \
  pytest tests/unit/test_stable_duckdb_semantics.py \
    tests/integration/test_multi_year_invariants.py \
    tests/integration/test_edge_config_matrix.py -v

# Always use a new output path and an explicit, identical config for each side.
DBT_PARTIAL_PARSE=false DATABASE_PATH=/tmp/planalign-upgrade-run.duckdb \
  planalign simulate 2025-2027 --config /tmp/upgrade-config.yaml \
    --database /tmp/planalign-upgrade-run.duckdb
```

Run the full CI workflow on the final PR head before merging an engine upgrade. Unit tests and dbt compilation alone do not exercise the year-two transaction boundary.
