# Implementation Plan: Employer Cost Ratio Metrics

**Branch**: `013-cost-comparison-metrics` | **Date**: 2026-01-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-cost-comparison-metrics/spec.md`

## Summary

Add employer cost ratio metrics to the ScenarioCostComparison page to display employer contributions as a percentage of total payroll. This involves extending the backend analytics API to aggregate `prorated_annual_compensation` from `fct_workforce_snapshot`, updating Pydantic models and TypeScript interfaces, and adding new MetricCard components and table rows to the frontend.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (backend), React 18 + Vite (frontend), Pydantic v2 (validation)
**Storage**: DuckDB 1.0.0 (`dbt/simulation.duckdb`)
**Testing**: pytest (backend), existing frontend patterns
**Target Platform**: Linux server (API), web browser (frontend)
**Project Type**: Web application (backend + frontend)
**Performance Goals**: <2 seconds response time (SC-001), inherits from existing analytics patterns
**Constraints**: Single-threaded DuckDB queries, work laptop deployments
**Scale/Scope**: Existing workforce simulation datasets (100K+ employee records supported)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ PASS | Read-only feature; does not modify events |
| II. Modular Architecture | ✅ PASS | Extends existing AnalyticsService; no new modules |
| III. Test-First Development | ✅ PASS | Tests will be written first for API and frontend |
| IV. Enterprise Transparency | ✅ PASS | No new logging required; inherits from existing |
| V. Type-Safe Configuration | ✅ PASS | Pydantic models extended; TypeScript interfaces updated |
| VI. Performance & Scalability | ✅ PASS | <2 second query target; single query aggregation |

**Gate Result**: ✅ PASS - All principles satisfied

## Project Structure

### Documentation (this feature)

```text
specs/013-cost-comparison-metrics/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
planalign_api/                  # Backend
├── models/
│   └── analytics.py           # Extend ContributionYearSummary, DCPlanAnalytics
├── services/
│   └── analytics_service.py   # Extend _get_contribution_by_year() query
└── tests/
    └── test_analytics_service.py  # New tests for cost rate calculations

planalign_studio/               # Frontend
├── components/
│   └── ScenarioCostComparison.tsx  # Add MetricCard, table row, Grand Totals
├── services/
│   └── api.ts                 # Extend TypeScript interfaces
└── tests/
    └── (optional: component tests)
```

**Structure Decision**: Extends existing web application structure. No new modules required; all changes are additions to existing files following established patterns.

## Complexity Tracking

> No violations identified - feature follows existing patterns without introducing new complexity.
