# Test audit — July 2026

This is a living, evidence-based audit of the PlanAlign test suite. It records
whether a test exercises a current public or internal contract, is isolated
from shared runtime state, and is placed in the right pytest execution lane.

## Audit rules

- Behavioral tests must use a disposable database; `dbt/simulation.duckdb` is
  not a validation fixture.
- A test must invoke the production boundary named in its assertion. Testing a
  helper or a framework behavior is not a substitute.
- Test configuration must come from the supplied config or dbt variable, not a
  hard-coded value that only matches today's default.
- Tests using only mocks, in-memory DuckDB, or `tmp_path` are eligible for the
  fast lane unless their measured runtime says otherwise.

## Batch 1: recent pipeline and enrollment work

Reviewed: 2026-07-11.

| Area | Evidence | Decision | Follow-up |
| --- | --- | --- | --- |
| Stage failure handling (feature 106) | `tests/unit/orchestrator/test_pipeline_stage_failure.py` covers false, missing, and ambiguous outcomes plus specialized stages. | Retain. | Targeted suite passed. |
| Census enrollment projection (feature 107) | `tests/unit/orchestrator/test_enrollment_projection.py` and `tests/integration/test_census_enrollment_persistence.py` execute isolated in-memory DuckDB state. | Retain; reclassify the latter as fast/unit-level coverage or consolidate its overlap. | Do not require a materialized database. |
| Stale rerun cleanup (feature 108) | `tests/integration/test_stale_rerun_purge.py` uses an isolated in-memory DuckDB and validates scenario and year boundaries. | Retain; eligible for the fast lane. | Keep the multi-year sequence assertion. |
| Decimal configuration logging | `tests/test_pipeline_orchestrator_initialization.py` only called Pydantic `model_dump(mode="json")`; it did not invoke `PipelineOrchestrator`, whose observability setup is the claimed boundary. | Rewritten. | A single fast test now constructs the orchestrator with isolated collaborators and verifies the configuration delivered to observability is JSON-safe. |
| Deferral escalation events | `tests/test_escalation_events.py` read the ambient database and assumed a 10% cap. `dbt/tests/data_quality/test_deferral_escalation.sql` validates the ledger using `deferral_escalation_cap`. | Removed. | The dbt singular test is parameterized by the active configuration and runs at the behavior boundary. |
| New-hire voluntary enrollment | `tests/test_new_hire_voluntary_enrollment.py` read an arbitrary populated database and required every year to have a nonzero, non-total enrollment share. | Removed. | `assert_new_hire_voluntary_enrollment_hire_year`, `assert_new_hire_single_enrollment_event`, and `assert_new_hire_voluntary_enroll_effective_date` enforce the current configurable contract. |
| Existing-participant auto-enrollment | `tests/test_existing_participant_not_auto_enrolled.py` read an arbitrary populated database and skipped if auto enrollment was disabled. | Removed. | `test_census_participants_not_reenrolled` and the isolated enrollment-projection tests retain the behavior-level regression coverage without ambient state. |
| CLI health check | `tests/test_orchestrator_wrapper.py::test_check_system_health_healthy` opened the shared development database despite being marked fast. | Fixed. | It now supplies a mocked successful connection and verifies the health query, so a local DuckDB lock cannot affect the test. |
| dbt/sqlparse subprocess checks | `tests/integration/test_sqlparse_subprocess.py` hard-coded `/workspace/dbt`, so two tests skipped outside that container layout. | Fixed. | They now resolve the repository-local `dbt/` directory and run in local and CI checkouts. |
| Uncollected initialization script | `planalign_orchestrator/test_init.py` was outside pytest's `testpaths`, returned booleans instead of asserting, and retained the retired product name. | Removed. | Current initialization behavior is covered by the collected self-healing and orchestrator tests. |

## Validation run

The following isolated tests passed on 2026-07-11:

```text
pytest -q \
  tests/integration/test_census_enrollment_persistence.py \
  tests/integration/test_stale_rerun_purge.py \
  tests/unit/orchestrator/test_enrollment_projection.py \
  tests/unit/orchestrator/test_pipeline_stage_failure.py

33 passed in 0.91s
```

## Next batch

Audit the remaining tests that connect to a materialized database or skip based
on ambient runtime state, then review top-level tests marked `integration` that
only use mocks or temporary resources. Run all true behavioral replacements
with an explicit disposable `DATABASE_PATH`.

## Suite-wide classification

The inventory contains 148 remaining test modules after the removals below.
The classifications use the module location plus its fixtures and external
dependencies; individual exceptions are listed explicitly.

| Classification | Modules | Decision |
| --- | --- | --- |
| Retain | `tests/unit/**` (60 modules), `tests/api/**` (11 modules), `tests/performance/test_census_enrollment_performance.py`, and the top-level fast tests other than the exceptions below. | These use mocks, `tmp_path`, in-memory DuckDB, or explicitly controlled fixtures, and assert current Python/API contracts. |
| Retain as deliberate integration | `tests/test_calibration_exactness.py`, `tests/integration/test_enroll_window_reproducibility.py`, and `tests/integration/test_sqlparse_subprocess.py`. | They require explicit opt-in inputs or subprocess behavior and are correctly excluded from the default fast lane. |
| Keep, but classify for a future marker cleanup | `tests/integration/test_auto_enrollment_disabled.py`, `test_census_enrollment_persistence.py`, `test_config_serialization_roundtrip.py`, `test_event_parity.py`, `test_new_event_type.py`, `test_self_healing_integration.py`, `test_simulation_logs.py`, `test_stale_rerun_purge.py`, `test_vesting_api.py`, and `test_year_dependency_validation.py`. | They are isolated and quick but currently inherit `slow` from their directory. Their behavior is valid; marker normalization can be a separate low-risk change. |
| Fixed | `tests/test_pipeline_orchestrator_initialization.py`, `tests/test_orchestrator_wrapper.py`. | Each now exercises the claimed production boundary without opening the shared development database. |
| Removed | `tests/test_escalation_events.py`, `tests/test_existing_participant_not_auto_enrolled.py`, `tests/test_new_hire_voluntary_enrollment.py`, and `planalign_orchestrator/test_init.py`. | Replaced by current parameterized dbt singular tests or collected initialization coverage; the removed versions were ambient-state dependent, uncollected, or asserted obsolete fixed defaults. |

The dbt parser completes successfully after the removals. It reports pre-existing
warnings for schema patches that reference models no longer present; those are
outside this Python-test audit and are not changed here.
