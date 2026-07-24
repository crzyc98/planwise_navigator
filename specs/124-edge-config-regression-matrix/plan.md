# Implementation Plan: Edge-Configuration Regression Matrix

**Branch**: `124-edge-config-regression-matrix` | **Date**: 2026-07-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/124-edge-config-regression-matrix/spec.md`

## Summary

Add a pytest-driven, pre-merge regression matrix with exactly four short multi-year cases. Each case owns a purpose-built census/configuration, runs through the existing `ConstructionSpec`/`build_orchestrator` path into a per-case temporary DuckDB, validates fixture boundary coverage before execution, and evaluates targeted business outcomes from completed fact tables. Failures use a common diagnostic that distinguishes simulation errors from assertion failures and includes bounded affected-row samples. The matrix reuses Feature 113's isolation and general invariant/determinism support without adding full-output snapshots or a second determinism framework.

## Technical Context

**Language/Version**: Python 3.11; SQL/Jinja executed by dbt Core 1.8.8 with dbt-duckdb 1.8.1
**Primary Dependencies**: pytest, DuckDB 1.0.0, pandas/pyarrow, existing `planalign_orchestrator` config loader and multi-year executor
**Storage**: Per-case DuckDB files under pytest `tmp_path`; checked-in CSV fixture/config inputs; never `dbt/simulation.duckdb`
**Testing**: pytest; new `edge_config_matrix` marker plus existing `integration`; existing Feature 113 harness patterns and CI artifact handling
**Target Platform**: macOS developer laptops and Ubuntu CI
**Project Type**: Test infrastructure in the existing simulation monorepo
**Performance Goals**: Four cases complete within 5 minutes locally; bounded short horizons and small populations
**Constraints**: Isolated and concurrency-safe runs, single-threaded dbt, no full-output snapshots, no public schema/config changes
**Scale/Scope**: Exactly four initial cases, each with a small population crossing its boundary and a documented one- or two-year horizon

## Constitution Check

*GATE: PASS against Constitution v1.0.0 before Phase 0 and after Phase 1.*

| Principle | Assessment |
|---|---|
| I. Event Sourcing & Immutability | PASS: read-only assertions consume completed event/snapshot outputs; no events or state are mutated. |
| II. Modular Architecture | PASS: scenario definitions, fixture execution, assertions, and diagnostics are separated under `tests/edge_config/` and `tests/fixtures/`. |
| III. Test-First Development | PASS: the feature is regression-test infrastructure and includes seeded mutation tests for all four boundaries. |
| IV. Enterprise Transparency | PASS: named case/boundary, expected/observed values, bounded employee samples, and simulation-vs-assertion error distinction are contractual. |
| V. Type-Safe Configuration | PASS: YAML inputs are loaded through existing Pydantic configuration models; no raw SQL table interpolation is introduced. |
| VI. Performance & Scalability | PASS: small fixtures, short horizons, `threads=1`, and the five-minute matrix budget preserve conservative execution. |

No violations require complexity tracking.

## Project Structure

### Documentation

```
specs/124-edge-config-regression-matrix/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── matrix-interface.md
```

### Source Code

```
tests/
├── fixtures/
│   ├── edge_config_matrix.py
│   └── edge_config/
├── edge_config/
│   ├── __init__.py
│   ├── catalog.py
│   ├── assertions.py
│   └── queries.py
└── integration/
    └── test_edge_config_matrix.py

.github/workflows/ci.yml
pyproject.toml
```

**Structure Decision**: Extend the existing pytest integration-test structure. Case metadata and assertions live in `tests/edge_config/`; case-specific census/config inputs live below `tests/fixtures/edge_config/`; orchestration helpers reuse the established `tests/fixtures/invariant_simulation.py` isolation conventions rather than modifying product runtime code.

## Complexity Tracking

No constitution violations.
