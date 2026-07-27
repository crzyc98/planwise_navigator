# Quickstart: Edge-Configuration Regression Matrix

## Prerequisites

Activate the existing Python 3.11 environment, ensure dbt dependencies are available, and run from the repository root. No shared database setup is required.

## Run the matrix

    source .venv/bin/activate
    pytest -m edge_config_matrix -v

Expected result: exactly four named cases pass within five minutes. Each case runs a short multi-year simulation in its own temporary DuckDB. dbt/simulation.duckdb remains untouched.

## Run one case while developing

    pytest -m edge_config_matrix -k broad_auto_enrollment_cutoff -v

Other case names are new_hire_eligibility_suppression, tenure_graded_employer_match, and auto_escalation_low_cap.

## Interpret failures

- Fixture/setup error: the case no longer contains both sides of its intended boundary.
- Simulation error: orchestration/dbt failed; behavioral assertions are not evaluated.
- Business-rule failure: the diagnostic names the case and boundary, shows expected versus observed behavior, and includes up to 20 affected records with employee/year context.
- Failed run databases are preserved locally and uploaded by CI for inspection.

## Add a scenario or assertion

Add a case only when a concrete regression risk justifies it. Preserve the four existing catalog names and semantics. Document the horizon, boundary groups, expected outcome, and diagnostic fields in the catalog contract, then add a targeted mutation test proving the assertion fails when its rule is deliberately broken. General multi-year invariants and same-seed reproducibility remain covered by pytest -m multi_year_invariants -v.

## Validation checklist

- Both boundary groups are non-empty before simulation.
- Effective configuration/override is visible in failure diagnostics.
- Assertions query only completed isolated outputs.
- The shared development database signature is unchanged.
- Concurrent invocations use distinct temporary paths and equivalent case results.

## Validation record

Run the documented command twice locally with `--durations=10`; the acceptance
budget is five minutes for all four cases. Contract-only checks can be run with:

    pytest tests/integration/test_edge_config_matrix.py -m edge_config_matrix -k 'catalog or fixture or bounded or shared' -v
