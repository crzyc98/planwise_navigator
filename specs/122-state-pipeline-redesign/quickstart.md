# Quickstart: Validate the State Pipeline Redesign

All behavioral checks use isolated databases. Never point these commands at `dbt/simulation.duckdb`.

## 1. Activate the repository environment

```bash
cd /Users/nicholasamaral/Developer/fidelity_planalign
source .venv/bin/activate
```

Create a disposable validation root and keep its printed path for the session:

```bash
mktemp -d /tmp/planalign-f122.XXXXXX
```

In the examples below, replace `/tmp/planalign-f122.ABC123` with that exact path. Do not use an existing run directory or database.

## 2. Run fast contracts first

Database lifecycle and API selection:

```bash
pytest \
  tests/unit/test_database_path_resolver.py \
  tests/unit/simulation/test_simulation_service.py \
  tests/unit/simulation/test_run_archiver.py \
  tests/unit/storage/test_workspace_storage.py \
  tests/unit/storage/test_run_cleanup.py \
  tests/api/test_simulation_start.py \
  tests/api/test_openapi_contract.py \
  -v
```

Explicit domain-boundary and calibration contracts:

```bash
pytest \
  tests/unit/orchestrator/test_enrollment_projection.py \
  tests/unit/orchestrator/test_workflow_graph_contract.py \
  tests/test_calibration_workflow.py \
  -v
```

Graph, schedule, and validation contracts:

```bash
pytest \
  tests/unit/orchestrator/test_pipeline_graph_contract.py \
  tests/unit/test_stage_invocation_grouping.py \
  tests/unit/test_change_validation.py \
  -v
```

The graph test must compile the active production SQL configuration. It must not fail merely because an inactive legacy Polars compatibility branch still exists.

## 3. Verify run database isolation

Run the focused integration test with a fresh destination root:

```bash
DATABASE_PATH=/tmp/planalign-f122.ABC123/test-run.duckdb \
  pytest tests/integration/test_run_database_isolation.py -v
```

The test covers:

- each managed attempt receives a distinct, previously nonexistent run DB;
- reads remain on the latest success while a newer attempt runs;
- warning/result/active run headers identify that split;
- a forced failed stage retains its partial DB and does not change the pointer;
- a successful attempt atomically switches the pointer;
- pre-existing run DB/archive signatures and the shared dev DB signature do not change;
- the Studio batch path observes the same terminal outcome contract.

Measure representative reads in both idle and active-run conditions:

```bash
pytest tests/performance/test_scenario_read_latency.py -v
```

At least 95% of reads in each condition must complete within two seconds.

## 4. Build one isolated candidate end to end

Use the feature's checked validation configuration/census location once those fixtures are added. The destination must not already exist:

```bash
planalign simulate 2025-2029 \
  --config /tmp/planalign-f122.ABC123/candidate-config.yaml \
  --database /tmp/planalign-f122.ABC123/candidate.duckdb
```

Point database-backed tests at that exact DB:

```bash
DATABASE_PATH=/tmp/planalign-f122.ABC123/candidate.duckdb \
  pytest \
    tests/integration/test_determinism.py \
    tests/integration/test_multi_year_invariants.py \
    tests/integration/test_state_pipeline_characterization.py \
    -v
```

Run dbt commands only from `dbt/`, single-threaded, and against the isolated DB:

```bash
cd /Users/nicholasamaral/Developer/fidelity_planalign/dbt
DATABASE_PATH=/tmp/planalign-f122.ABC123/candidate.duckdb \
  dbt test \
    --select int_workforce_state_accumulator fct_yearly_events fct_workforce_snapshot \
    --exclude test_type:singular \
    --threads 1
cd /Users/nicholasamaral/Developer/fidelity_planalign
```

## 5. Run a migration phase gate

First verify the ignored A+B baseline DB against the checked characterization. Do not accept an arbitrary DB merely because it exists:

```bash
planalign validate-change \
  --baseline-db /tmp/planalign-f122.ABC123/frozen-ab-baseline.duckdb \
  --candidate-db /tmp/planalign-f122.ABC123/candidate.duckdb \
  --characterization specs/122-state-pipeline-redesign/baseline-characterization.json \
  --exclusions specs/122-state-pipeline-redesign/contracts/parity-exclusions.yaml \
  --phase event_publication
```

The implementation may expose this frozen-baseline mode through a dedicated `validate-pipeline-phase` command instead; whichever command is selected must preserve the same inputs and checks. The phase fails on:

- one-sided missing marts or unreported mart inventory entries;
- schema name/order/type/nullability changes outside the exact allowlist;
- either direction of `EXCEPT ALL` producing a row;
- changed duplicate multiplicity or grouped event counts;
- an unexpected publication count or stage schedule;
- a changed baseline ID/input fingerprint;
- any mutation of the shared DB or pre-existing run artifacts.

Run the heavy parity test directly when debugging validator behavior:

```bash
F122_BASELINE_DB=/tmp/planalign-f122.ABC123/frozen-ab-baseline.duckdb \
F122_CANDIDATE_DB=/tmp/planalign-f122.ABC123/candidate.duckdb \
  pytest tests/integration/test_state_pipeline_parity.py -v
```

## 6. Required phase order

Do not skip or reorder gates:

1. `baseline_characterization`
2. `run_database_isolation`
3. `event_publication`
4. `shadow_workforce`
5. `consumers_migrated`
6. `snapshot_composed_legacy_removed`
7. `state_stage_consolidated`

Each gate refers to the same baseline ID. Consumer migration cannot start until shadow-workforce parity passes. Legacy relations cannot be removed until all consumers are migrated and manifest audits pass. The state command boundary cannot be collapsed until the normalized graph passes.

## 7. Final regression and performance gate

Run the behavior suites against the isolated final candidate:

```bash
DATABASE_PATH=/tmp/planalign-f122.ABC123/candidate.duckdb \
  pytest \
    tests/integration/test_determinism.py \
    tests/integration/test_multi_year_invariants.py \
    tests/integration/test_state_pipeline_parity.py \
    tests/integration/test_run_database_isolation.py \
    -v
```

Also run the existing Feature 107 census-enrollment, Feature 112 post-termination, stale-rerun, failed-stage, and partial-failure suites selected by their repository markers/files.

Use the existing performance matrix for at least three warm repetitions of both the reference and 60,040-employee Studio workloads, labeling the frozen baseline and final candidate explicitly. The report must include normalized input/code fingerprints, wall/CPU/model/dbt/residue time, invocation/node counts, and median peak RSS. Final acceptance requires candidate median peak RSS at or below 110% of baseline.

The normalized five-year schedule must contain one event-generation publication command and one STATE_ACCUMULATION command per year, with no state-stage `--full-refresh`. Record the observed whole-run invocation total as evidence; do not assert a fixed total or use the earlier 20-invocation estimate as a pass/fail threshold.

## 8. Shared database guard

Record the shared DB signature before and after every behavioral campaign without querying or rebuilding it:

```bash
shasum -a 256 dbt/simulation.duckdb
```

If the file does not exist, record that state and require it to remain absent. Any unexpected signature/existence change invalidates the campaign.
