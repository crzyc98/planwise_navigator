# Quickstart: Fail Dbt Stage

## Prerequisites

- Work from the repository root.
- Activate the existing virtual environment if available:

```bash
source .venv/bin/activate
```

## 1. Run The Focused Regression Test

Expected before implementation: the new regression test fails because `_execute_stage_core` ignores an unsuccessful stage outcome.

Expected after implementation: the test passes and confirms the run fails fast with stage, year, and error context.

```bash
pytest tests/unit/orchestrator/test_pipeline_stage_failure.py -q
```

## 2. Run The Fast Orchestrator Slice

Expected result: all fast orchestrator tests pass, including the new failure propagation coverage.

```bash
pytest tests/unit/orchestrator/test_pipeline_stage_failure.py tests/unit/orchestrator/test_year_executor.py -m fast -q
```

## 3. Optional CLI Smoke Check

Use this only when local dbt inputs are available and the environment can run a simulation. Create or select a scenario that triggers a required stage failure, such as a missing required dbt model or intentionally invalid validation setup.

Expected result: the simulation exits non-zero or is marked failed, and diagnostics identify the failed stage and simulation year.

```bash
planalign simulate 2025-2025
```

## 4. Verification Checklist

- A stage outcome with `success: false` stops orchestration.
- A malformed or missing stage outcome stops orchestration.
- Failure diagnostics include stage name and simulation year.
- The run cannot be reported as successfully completed after a required stage failure.
- No event store, dbt model, or public API contract changes are required.
