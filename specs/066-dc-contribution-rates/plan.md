# Implementation Plan: Trended Contribution Percentage Rates

**Branch**: `066-dc-contribution-rates` | **Date**: 2026-03-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/066-dc-contribution-rates/spec.md`

## Summary

Add four contribution rate percentage fields (employee, match, core, total) to the analytics API and render them as a trended line chart on the DC Plan comparison page. The existing `employer_cost_rate` computation pattern in `analytics_service.py` serves as the exact template — extend it with three additional rate calculations using the same division-by-compensation approach. The frontend follows the established `buildTrendData()` + Recharts `LineChart` pattern already used for Employer Cost Rate, Participation Rate, and Average Deferral Rate trend charts.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript (frontend React/Vite)
**Primary Dependencies**: FastAPI, Pydantic v2 (backend); React, Recharts 3.5.0 (frontend)
**Storage**: DuckDB via `fct_workforce_snapshot` (read-only for this feature)
**Testing**: pytest (backend), manual verification (frontend)
**Target Platform**: Linux server (API), modern browsers (frontend)
**Project Type**: Web application (API + SPA)
**Performance Goals**: Chart renders within 2 seconds; API response adds negligible overhead (4 additional float divisions per year)
**Constraints**: No new database models or dbt changes required
**Scale/Scope**: 3 files modified (backend model, backend service, frontend component), ~80 lines added

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Read-only from `fct_workforce_snapshot`; no events created or modified |
| II. Modular Architecture | PASS | Extends existing model/service/component; no new modules needed |
| III. Test-First Development | PASS | Backend rate computation testable with pytest; edge cases defined |
| IV. Enterprise Transparency | PASS | Rates derived from auditable event-sourced data |
| V. Type-Safe Configuration | PASS | New fields added to Pydantic v2 model with explicit types and defaults |
| VI. Performance & Scalability | PASS | 4 float divisions per year row; negligible overhead |

No violations. No Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/066-dc-contribution-rates/
├── plan.md              # This file
├── research.md          # Phase 0: codebase research findings
├── data-model.md        # Phase 1: data model extensions
├── quickstart.md        # Phase 1: implementation quickstart
├── contracts/           # Phase 1: API contract changes
│   └── api-contract.md
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_api/
├── models/
│   └── analytics.py            # Add 4 rate fields to ContributionYearSummary
├── services/
│   └── analytics_service.py    # Compute rates in _get_contribution_by_year() and _compute_grand_totals()
└── routers/
    └── analytics.py            # No changes needed (returns existing model)

planalign_studio/
└── components/
    └── DCPlanComparisonSection.tsx  # Add Contribution Rate Trends chart + summary table rows

planalign_studio/
└── services/
    └── api.ts                  # Add 4 fields to ContributionYearSummary interface

tests/
└── test_analytics_service.py   # Test rate computation logic
```

**Structure Decision**: Web application pattern — backend API model/service extension + frontend chart addition. All changes fit within existing module boundaries.
