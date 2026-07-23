# Contract: Frozen-Baseline Parity and Phase Gates

## Authoritative reference

All migration phases compare to one locally retained, ignored A+B database regenerated from revision `c6ad648` or a proven equivalent. Before it is accepted, its run metadata/input fingerprints must match the checked `baseline-characterization.json`. A file SHA is provenance, not a substitute for semantic comparison.

The existing validate-against-current-HEAD mode remains available for ordinary changes. Feature 122 uses an explicit frozen-baseline DB and baseline ID so expected behavior cannot advance with implementation phases.

## Mart inventory and presence

Enumerate models with:

```text
dbt ls --select marts --resource-type model --output name
```

Every enumerated model receives exactly one result:

- `compared`: present in both DBs and fully checked;
- `not_built_in_either`: absent in both because the product workflow does not build it.

A relation present on only one side fails. No relation may disappear from the report. The current inventory includes nine marts; the baseline simulation builds the yearly-event, workforce-snapshot, and employer-match facts while the others are explicitly accounted for as not built.

## Schema and content comparison

For each built mart:

1. Read ordinal column name, DuckDB type, and nullability from both databases.
2. Remove only exact relation-column entries authorized by `parity-exclusions.yaml`.
3. Require the remaining schemas to be identical in name, order, type, and nullability.
4. Run `baseline EXCEPT ALL candidate` and `candidate EXCEPT ALL baseline` over that identical projection.
5. Require both differences to be empty.
6. Record row count, distinct-row count, duplicate groups, extra duplicate rows, and a multiplicity summary.

Unknown or duplicate exclusion entries fail validation. A listed column must exist whenever its relation is built. An exclusion never authorizes a missing relation, unlisted schema change, or any other value difference.

## Additional exact checks

- Event counts grouped by exact `(scenario_id, plan_design_id, simulation_year, event_type)`.
- Deterministic event identifiers and sequence through all-mart parity and targeted invariant tests.
- Aggregate workforce transitions by scenario/plan/year/status transition.
- Synthetic-fixture transition samples without real employee data.
- Per-node publication counts from dbt `run_results.json`, not only workflow selector strings.
- Invocation/stage/year/flag schedule from run execution metadata.
- Shared dev DB signature and every pre-existing run DB/archive signature before and after the candidate attempt.

## Phase cadence

Each migration phase runs one complete 60,040-employee, 2025–2029 candidate against the same baseline and writes `var/state_pipeline_validation/<phase>/gate.json`. Schema/content, counts, duplicates, graph contracts, relevant invariants, file guards, and directional resource evidence all pass before the next phase starts.

Final performance acceptance uses at least three warm repetitions of both the reference and 60,040-employee Studio workloads for the baseline and consolidated candidate. Compare median peak RSS and require:

```text
candidate_median_peak_rss <= 1.10 * baseline_median_peak_rss
```

Publish median wall time, CPU time, summed model time, dbt time, residue, invocation count, per-node execution count, and environment/input fingerprints. A single phase-local sample is diagnostic only, not the final RSS decision.

## Required regression suites

- determinism and multi-year invariants;
- stale-rerun behavior under new fresh-run semantics;
- failed dbt-stage and partial-failure status/attribution;
- Feature 107 census enrollment reconstruction;
- Feature 112 post-termination integrity;
- API latest-success/warning behavior;
- run database/archive/shared-DB immutability;
- normal and calibration workflow graph contracts.

## Data handling

Golden databases, real census/config paths, logs with PII, and employee row samples remain ignored. The checked characterization contains normalized hashes, aggregate counts, exact schemas, schedule summaries, and synthetic-fixture expectations only.
