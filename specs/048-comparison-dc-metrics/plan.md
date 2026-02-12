# Implementation Plan: DC Plan Metrics in Scenario Comparison

**Branch**: `048-comparison-dc-metrics` | **Date**: 2026-02-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/048-comparison-dc-metrics/spec.md`

## Summary

Extend the scenario comparison backend to include DC plan metrics (participation rate, average deferral rate, employer contribution rates) aggregated by year for each scenario. The comparison service already loads per-scenario DuckDB databases and builds workforce/event comparisons with delta calculations. This feature adds a parallel DC plan comparison flow using the same proven SQL pattern from `analytics_service.py`, structured to match the existing per-year comparison pattern with scenario-keyed values and deltas.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: FastAPI, Pydantic v2.7.4, DuckDB 1.0.0
**Storage**: DuckDB (per-scenario databases resolved via `DatabasePathResolver`)
**Testing**: pytest with in-memory DuckDB fixtures (follows `test_analytics_service.py` pattern)
**Target Platform**: Linux server (FastAPI backend)
**Project Type**: Web application (backend API extension)
**Performance Goals**: Same response time as current comparison endpoint (~<2s per SC-003)
**Constraints**: Read-only database access; single additional SQL query per scenario
**Scale/Scope**: 3 files modified, 1 test file added; ~200 lines of new code

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Event Sourcing & Immutability | PASS | Read-only aggregation from `fct_workforce_snapshot`; no events created or modified |
| II. Modular Architecture | PASS | Extends existing `ComparisonService` with a new private method (`_load_dc_plan_data`, `_build_dc_plan_comparison`); no new modules needed; comparison_service.py stays under 600 lines |
| III. Test-First Development | PASS | New test file `test_comparison_dc_plan.py` with in-memory DuckDB fixtures; edge case coverage |
| IV. Enterprise Transparency | PASS | Follows existing logging pattern in comparison_service.py |
| V. Type-Safe Configuration | PASS | New Pydantic v2 models for DC plan metrics; no raw SQL string concatenation |
| VI. Performance & Scalability | PASS | Single additional GROUP BY query per scenario on existing connection; negligible overhead |

**Gate Result**: ALL PASS. No violations. Proceeding to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/048-comparison-dc-metrics/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── comparison-api.md
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_api/
├── models/
│   └── comparison.py          # ADD: DCPlanYearMetrics, DCPlanComparisonYear models
├── services/
│   └── comparison_service.py  # ADD: _load_dc_plan_data(), _build_dc_plan_comparison(), _build_dc_plan_summary_deltas()
└── routers/
    └── comparison.py          # MODIFY: Include dc_plan_comparison in response (no changes needed if model is extended)

tests/
└── test_comparison_dc_plan.py # NEW: Unit tests for DC plan comparison logic
```

**Structure Decision**: Backend-only extension. No new modules; extends existing comparison service with new methods and models. Follows the established pattern of `_load_*` → `_build_*_comparison` → include in `ComparisonResponse`.
