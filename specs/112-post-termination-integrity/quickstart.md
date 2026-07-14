# Quickstart: Validate Post-Termination Event Integrity

All behavioral checks use disposable databases. Never point these commands at `dbt/simulation.duckdb`, a live scenario database, or an archived run database.

## 1. Activate the environment

```bash
source .venv/bin/activate
mkdir -p /tmp/planalign-112
```

The supplied baseline archive is read-only:

```bash
BASELINE_RUN="workspaces/91fe76fe-5792-4568-9337-9e5c02a06993/scenarios/8cccac95-e134-46e8-9630-e55055949cb5/runs/c9e319bd-e1bd-4c03-9210-30ced7f42185"
```

Record archive hashes or modification times before investigation and confirm them again at the end. Do not persist queries containing employee-level rows. The approved safe aggregate baseline is documented in [research.md](./research.md): 73, 95, 106, 94, and 91 violations by year, totaling 459.

## 2. Run the fast test loop

```bash
pytest -m fast \
  tests/test_validation_framework.py \
  tests/test_telemetry_emitter.py \
  tests/unit/test_provenance_capture.py \
  tests/unit/orchestrator/test_config_export.py -v
```

Expected result: synthetic before/same-day/after, duplicate-termination, prior-year, scope-isolation, and validation-disposition cases all pass.

Foundation result (2026-07-13): `pytest tests/test_validation_framework.py -q` passed 8 tests. The new lifetime/scope cases were first observed failing under the same-year implementation (one unexpected pass and one unsupported configurable-column argument), then passed after the rule correction.

## 3. Compile the affected transformation graph

Run dbt only from `dbt/`, with one thread and a disposable database path:

```bash
cd dbt
DATABASE_PATH=/tmp/planalign-112/compile.duckdb \
  dbt compile \
  --select int_employee_termination_dates int_eligibility_events int_enrollment_events int_promotion_events int_merit_events int_deferral_rate_escalation_events fct_yearly_events \
  --threads 1
cd ..
```

Expected result: the graph compiles without a circular dependency; every affected generator resolves the shared termination boundary before the fact and accumulator stages.

Foundation result (2026-07-13): from `dbt/`, `DATABASE_PATH=/tmp/planalign-112/foundation-compile.duckdb dbt compile --select test_integrity_violations --threads 1` completed successfully against dbt 1.8.8 and dbt-duckdb 1.8.1.

Producer-graph result (2026-07-13): the first compile against a blank disposable database correctly exposed the existing band macros' seed dependency (`config_age_bands` absent). After `DATABASE_PATH=/tmp/planalign-112/synthetic.duckdb dbt seed --threads 1`, the exact affected-model compile command above completed successfully with 122 models discovered and no dependency cycle.

## 4. Run the synthetic integration scenario

```bash
DATABASE_PATH=/tmp/planalign-112/synthetic.duckdb \
  pytest -m integration tests/integration/test_post_termination_event_integrity.py -v
```

Expected result:

- Events before and on termination remain.
- Eligibility, enrollment, opt-out, promotion, merit, and configured deferral events after termination are absent.
- Same-year new hires and experienced employees use the same cutoff semantics.
- Employees terminated in an earlier year produce no later activity.
- Python and dbt validation counts agree and equal zero after correction.

Synthetic result (2026-07-13): `DATABASE_PATH=/tmp/planalign-112/synthetic.duckdb pytest -m integration tests/integration/test_post_termination_event_integrity.py -q` passed 10 tests. The suite retains before/same-day activity, removes later eligibility/enrollment/opt-out/promotion/merit/deferral candidates, preserves an earlier auto-enrollment fallback when a higher-priority voluntary candidate is too late, and reports PASS with zero affected records. Workflow ordering tests passed separately (2 tests).

## 5. Run the complete affected period in isolation

Create a disposable dbt project copy so generated targets and logs remain isolated, then use the archived effective configuration only as an input:

```bash
cp -R dbt /tmp/planalign-112/dbt-project
DATABASE_PATH=/tmp/planalign-112/corrected.duckdb \
  planalign simulate 2026-2030 \
  --config "$BASELINE_RUN/config.yaml" \
  --database /tmp/planalign-112/corrected.duckdb \
  --dbt-project-dir /tmp/planalign-112/dbt-project \
  --threads 1 \
  --fail-on-validation-error
```

Expected result: all five event-sequence checks pass with zero affected records and every annual workforce reconciliation variance is zero. Before trusting the result, confirm the census and seed fingerprints used by the isolated run match the baseline provenance manifest.

First full-run result (2026-07-13): completed all five years in 137.90 seconds. The effective config fingerprint was `ef0d600a413743ed4665936a1b409452505621d526cebd7462a3dbeaf7c838f4`, matching the archived manifest; random seed was 42. Sequence results were PASS/0 for 2026–2030. Reconciliation tuples `(year, opening, hires, terminations, closing, variance)` were `(2026, 6764, 1163, 960, 6967, 0)`, `(2027, 6967, 1374, 1165, 7176, 0)`, `(2028, 7176, 1440, 1225, 7391, 0)`, `(2029, 7391, 1488, 1266, 7613, 0)`, and `(2030, 7613, 1534, 1306, 7841, 0)`.

## 6. Prove determinism

Repeat step 5 into a second disposable project and database:

```bash
cp -R dbt /tmp/planalign-112/dbt-project-repeat
DATABASE_PATH=/tmp/planalign-112/repeat.duckdb \
  planalign simulate 2026-2030 \
  --config "$BASELINE_RUN/config.yaml" \
  --database /tmp/planalign-112/repeat.duckdb \
  --dbt-project-dir /tmp/planalign-112/dbt-project-repeat \
  --threads 1 \
  --fail-on-validation-error
```

Compare ordered aggregate tuples for event type/year, workforce reconciliation, and validation outcomes. Exclude generated UUIDs and audit timestamps. The two runs must match exactly. Explain pre-correction differences as removal of the 459 invalid events or their documented downstream effects.

Repeat result (2026-07-13): completed in 140.76 seconds. All 39 ordered year/type count tuples and all five closing-workforce aggregates matched the first run exactly; sequence validation remained PASS/0 for every year. The before/after delta is recorded in `research.md` and is limited to the three diagnosed event families.

## 7. Verify performance

Compare equivalent isolated five-year runs under similar system load. Use repeated measurements or a median when practical. The corrected run must not exceed the 183.42-second archived baseline by more than 10% (approximately 201.76 seconds), allowing documented environmental variance.

Performance result (2026-07-13): three successful equivalent runs measured 137.90, 140.76, and 144.55 seconds. The accepted best measurement is 137.90 seconds, below both the 183.42-second baseline and 201.76-second gate. One non-measurement setup attempt used a hyphenated disposable database filename and failed during seeding because DuckDB parsed the catalog name as an expression; it was replaced by a fresh underscore-named database and did not enter the timing set.

## 8. Verify the Studio audit outcome

Use a copied temporary workspace root, run the corrected scenario through Studio, and download its audit report. CLI simulation alone does not create a Studio run archive.

The new report must show:

- completed status and all five completed years;
- no missing required evidence;
- `event_sequence_validation` PASS with affected-record count 0 for every year;
- zero annual workforce variance;
- fully verified disposition when all other checks pass; and
- a deterministic digest that verifies independently.

The same archive can also be rendered without rerunning:

```bash
planalign provenance "$NEW_RUN_ID" \
  --workspaces-root /tmp/planalign-112/workspaces \
  --output-dir /tmp/planalign-112/report
```

Finally, confirm the baseline archive hashes or modification times recorded in step 1 are unchanged.

Studio acceptance result (2026-07-13): the copied-workspace service run ID is `11200000-0000-4000-8000-000000000001`. It completed all five years and archived exact PASS/0 `event_sequence_validation` results for 2026–2030 plus zero reconciliation variance for every year. `planalign provenance` rendered the archive from `/tmp/planalign-112/workspaces` with `fully_verified` disposition, zero missing evidence, and SHA-256 digest `5c0d79483cf8206370e02dff5b0439253fc9b9416c8292f0c202ef095fcc1802`; an independent canonical-payload computation matched the digest.

## 9. Final quality gates

```bash
ruff check planalign_orchestrator planalign_api tests
mypy planalign_orchestrator planalign_api --ignore-missing-imports
pytest -m fast -q
git diff --check
```

Any dbt behavioral test must continue using an explicit disposable `DATABASE_PATH`, from the `dbt/` directory, with `--threads 1`.

Quality dbt result (2026-07-13): using a copy at `/tmp/planalign-112/quality.duckdb`, the affected graph compiled for simulation year 2030; all six schema tests on `int_employee_termination_dates` passed; and `test_integrity_violations` passed. Every command ran from `dbt/` with `DATABASE_PATH` explicit and `--threads 1`.

Python quality result (2026-07-13): feature-scoped Ruff passed; mypy reported no issues in the four changed source modules; 128 focused fast tests passed; 15 focused integration tests passed; and the complete fast suite passed 1,645 tests with 651 deselected in 119.87 seconds.

## 10. Success-criteria evidence

| Criterion | Evidence |
|---|---|
| SC-001 | Safe baseline categories reconcile 73/95/106/94/91 and 459 overall; `research.md` records the cohort/path split. |
| SC-002 | Corrected CLI and Studio runs report PASS/0 for every year from 2026 through 2030. |
| SC-003 | All five reconciliation tuples have variance 0. |
| SC-004 | The first and repeat runs match all 39 ordered year/type aggregates and all workforce totals. |
| SC-005 | Synthetic tests cover experienced, same-year hire, duplicate, prior-year, same-day, null-date, and scope cases. |
| SC-006 | Studio archive has zero missing evidence and an independently matching digest. |
| SC-007 | Studio report disposition is `fully_verified`. |
| SC-008 | Baseline archive SHA-256 digests and modification times match the pre-implementation fingerprint; shared/live databases were never behavioral test targets. |
| SC-009 | Persisted diagnostics contain only aggregate/synthetic fields; prohibited employee-level patterns were absent from new documentation and artifacts. |
| SC-010 | Three runs measured 137.90, 140.76, and 144.55 seconds; best 137.90 is below the 201.76-second gate. |
