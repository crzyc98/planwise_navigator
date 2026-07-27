# Contract: Edge Configuration Matrix Interface

## Local command

    pytest -m edge_config_matrix -v

The command executes exactly four catalog cases and reports one result per case. Each case uses a unique temporary DuckDB and does not create or modify dbt/simulation.duckdb.

## Case contract

Each case declares its name, fixture/config inputs, horizon, boundary, and targeted assertion. Setup verifies both sides of the boundary before simulation. The catalog rejects duplicate names and a count other than four for this initial feature.

## Result semantics

- Fixture setup failure: the population cannot prove the boundary; report setup failure and do not run behavioral assertions.
- Simulation execution failure: orchestration/dbt failed; report the execution error and do not evaluate assertions against a partial database.
- Business-rule failure: the simulation completed, but a targeted query returned violations; report case, boundary, expected value/rule, observed value/rule, and no more than 20 affected employee/year/row samples.
- Pass: simulation completed and all targeted queries returned zero violations.

## Required targeted outcomes

| Case | Required assertion |
|---|---|
| Broad auto-enrollment cutoff | Employees outside the hire-date boundary are not automatically enrolled; in-boundary controls follow configured enrollment behavior. |
| New-hire suppression + auto-enrollment | Suppressed labeled new hires remain excluded from enrollment/eligibility outcomes; unaffected eligible controls follow auto-enrollment. |
| Tenure-graded matching | Distinct completed-service groups resolve to configured match bands and produce distinct expected match treatment/amounts. |
| Low-cap escalation | For below-, equal-, and above-cap starts, every resulting deferral rate is <= configured cap and no invalid escalation crosses it. |

## CI contract

Add a dedicated edge-config-matrix job after normal environment setup, with a timeout consistent with the five-minute local budget. Upload case DuckDB files and diagnostic output only on failure. The job runs on pull requests and is a required pre-merge check according to branch protection.

## Traceability

| Requirement group | Implementation evidence |
|---|---|
| FR-001–FR-003 | `tests/edge_config/catalog.py`, catalog-shape tests |
| FR-004–FR-006 | `tests/fixtures/edge_config_matrix.py`, isolated-run tests |
| FR-007–FR-009 | `tests/edge_config/assertions.py`, `queries.py`, matrix tests |
| FR-010–FR-012 | failure preservation, bounded diagnostics, shared-signature tests |
| FR-013–FR-014 | `pyproject.toml`, CI job, `TEST_INFRASTRUCTURE.md` |
| SC-001–SC-007 | four parametrized cases, fixture boundary checks, and quickstart validation |
