# Contract: Exact Parity and Acceptance Evidence

## Parity command

```bash
planalign parity 2025-2027 \
  --config <config.yaml> \
  --census <census.csv-or-parquet> \
  --seed <integer> \
  [--json]
```

- Creates two fresh isolated DuckDB databases for the standard and compiled engines.
- Refuses any resolution to `dbt/simulation.duckdb`.
- Uses identical config, census, seed, horizon, versions, and commit.
- Exit code is zero only when all authoritative schemas and row multisets match and the compiled run records zero unexpected fallbacks.
- Failure artifacts are retained under the campaign runtime directory; output samples remain bounded.

## Schema comparison

For each authoritative table, compare ordered:

- column name;
- DuckDB logical type;
- nullability and other available contract metadata.

The timestamp exemptions apply only to values. Their columns must still exist with equal schema.

## Value comparison

Authoritative tables:

- `fct_yearly_events`, excluding only `created_at` values;
- `fct_workforce_snapshot`, excluding only `snapshot_created_at` values.

The verdict uses both directions of `EXCEPT ALL` over the projected columns. Ordinary `EXCEPT` is forbidden because it collapses duplicates.

Diagnostics group projected rows with side counters and report:

- baseline multiplicity;
- compiled multiplicity;
- delta;
- bounded row sample;
- per-year and, where applicable, per-event-type count summaries.

The duplicate regression uses equal total counts: baseline `(x,x,y)` and candidate `(x,y,y)` must report divergence.

## JSON report minimum shape

```json
{
  "schema_version": 1,
  "input_fingerprint": "sha256",
  "baseline_engine": "dbt",
  "candidate_engine": "compiled",
  "tables": [
    {
      "name": "fct_yearly_events",
      "schema_equal": true,
      "rows_baseline": 0,
      "rows_candidate": 0,
      "baseline_only_all": 0,
      "candidate_only_all": 0,
      "multiplicity_samples": []
    }
  ],
  "unexpected_fallback_count": 0,
  "verdict": "IDENTICAL"
}
```

## Ordered gate evidence

1. Tiny exact parity.
2. Multi-year invariants, determinism, and rerun parity.
3. Development and 60K exact parity.
4. Actual >=100K completion and peak process-tree RSS capture.
5. Paired tiny/development/60K performance including all overhead.
6. Zero unexpected fallback aggregation across gates 1–5.

Each evidence artifact records commit, versions, census row count/fingerprint, effective config fingerprint, seed, horizon, engine, database artifact, completion status, and gate-specific metrics. A later gate cannot waive or precede a failed earlier gate.
