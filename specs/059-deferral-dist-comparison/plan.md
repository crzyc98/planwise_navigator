# Implementation Plan: Deferral Rate Distribution Comparison

**Branch**: `059-deferral-dist-comparison` | **Date**: 2026-02-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/059-deferral-dist-comparison/spec.md`

## Summary

Add a grouped bar chart to the DC Plan comparison section that compares deferral rate distributions (0%-10%+) across scenarios with a year selector. The existing `DCPlanComparisonResponse` already includes final-year distribution data per scenario; this feature extends it with per-year distributions and adds the frontend visualization.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (backend API), Pydantic v2 (models), React 18 + Recharts 3.5 (frontend charts)
**Storage**: DuckDB 1.0.0 (per-scenario `simulation.duckdb` via `DatabasePathResolver`) — read-only access
**Testing**: Manual verification (frontend chart), existing analytics service patterns
**Target Platform**: Web (FastAPI + React/Vite)
**Project Type**: Web application (backend + frontend)
**Performance Goals**: Chart renders within 2 seconds of page load or year selection
**Constraints**: Max 6 scenarios compared simultaneously; payload ~10KB for distribution data
**Scale/Scope**: 4 files modified, ~150 lines added

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | **Pass** | Read-only queries against `fct_workforce_snapshot`; no events created or modified |
| II. Modular Architecture | **Pass** | Extends existing `DCPlanComparisonSection` component and `AnalyticsService`; no new modules needed |
| III. Test-First Development | **Pass** | Backend changes are minimal (new model field + SQL method); chart tested via manual verification consistent with E057 |
| IV. Enterprise Transparency | **Pass** | No new audit requirements; uses existing data pipeline |
| V. Type-Safe Configuration | **Pass** | New Pydantic model `DeferralDistributionYear`; TypeScript interface added |
| VI. Performance & Scalability | **Pass** | Payload ~10KB; bounded by 11 buckets × years × scenarios |

**Post-design re-check**: All gates pass. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/059-deferral-dist-comparison/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api.md           # API contract changes
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_api/
├── models/
│   └── analytics.py          # Add DeferralDistributionYear model, extend DCPlanAnalytics
└── services/
    └── analytics_service.py  # Add _get_deferral_distribution_all_years() method

planalign_studio/
├── components/
│   └── DCPlanComparisonSection.tsx  # Add grouped bar chart + year selector
└── services/
    └── api.ts                       # Add DeferralDistributionYear TypeScript interface
```

**Structure Decision**: Web application structure following existing `planalign_api` (backend) + `planalign_studio` (frontend) layout. No new files created; all changes are extensions to existing files.

## Complexity Tracking

No constitution violations. Table not applicable.
