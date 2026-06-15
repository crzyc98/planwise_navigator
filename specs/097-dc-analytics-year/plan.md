# Implementation Plan: DC Plan Analytics — 0% Deferral Fix and Year Filter

**Branch**: `097-dc-analytics-year` | **Date**: 2026-06-15 | **Spec**: [spec.md](./spec.md)

## Summary

Fix a bug introduced by feature 096 where the Deferral Rate Distribution chart shows zero employees at 0% deferral, even when 35% of eligible employees are not enrolled. The cause: the distribution query filtered `is_enrolled_flag = true`, so non-enrolled employees (with NULL deferral rates) were never counted. Removing that filter lets non-enrolled active employees naturally fall into the 0% bucket. Additionally, add a year picker to the DC Plan analytics page so planners can drill into any specific simulation year across all charts, KPIs, and scenario comparisons.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript/React 18 (frontend)
**Primary Dependencies**: FastAPI + Pydantic v2 (backend API); React 18 + Recharts 3.5.0 + Tailwind CSS v4 (frontend)
**Storage**: DuckDB 1.0.0 (`dbt/simulation.duckdb`) — read-only; no schema migration needed
**Testing**: pytest (Python unit tests with in-memory DuckDB fixtures)
**Target Platform**: Web application (FastAPI backend + Vite/React frontend)
**Project Type**: Web application analytics page
**Performance Goals**: Dashboard queries respond in <2 seconds (SC-002)
**Constraints**: No new API endpoints; year filtering is client-side from existing response data; one new field (`total_eligible_count`) added to existing response shape
**Scale/Scope**: One Python service file, one Python models file, one TypeScript API file, one React component

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ Pass | Read-only analytics queries; no events modified |
| II. Modular Architecture | ✅ Pass | Changes isolated to `analytics_service.py`, `models/analytics.py`, `api.ts`, `DCPlanAnalytics.tsx` — no cross-layer violations |
| III. Test-First Development | ✅ Pass | Tests written before service changes |
| IV. Enterprise Transparency | ✅ Pass | Bug fix improves data accuracy/transparency |
| V. Type-Safe Configuration | ✅ Pass | New field added with explicit Pydantic v2 `Field()` declaration |
| VI. Performance & Scalability | ✅ Pass | Removing a filter reduces DB work; client-side year filtering is O(n) on small arrays |

No complexity violations.

## Project Structure

### Documentation (this feature)

```text
specs/097-dc-analytics-year/
├── plan.md              ← this file
├── research.md          ← root cause + data strategy decisions
├── data-model.md        ← query changes and entity extensions
├── quickstart.md        ← step-by-step implementation reference
├── contracts/
│   └── analytics-contract.md  ← changed API response shape
├── checklists/
│   └── requirements.md  ← spec quality checklist (all pass)
└── tasks.md             ← created by /speckit.tasks (not yet)
```

### Source Code

```text
planalign_api/
├── models/
│   └── analytics.py           ← add total_eligible_count to ContributionYearSummary
└── services/
    ├── analytics_service.py   ← remove is_enrolled_flag filter; add total_eligible query
    └── (no other files changed)

planalign_studio/
├── services/
│   └── api.ts                 ← add total_eligible_count to ContributionYearSummary interface
└── components/
    └── DCPlanAnalytics.tsx    ← year picker state + controls + derived data + chart updates

tests/
└── test_dc_plan_analytics.py  ← add/update tests for 0% bucket fix and total_eligible_count
```

**Structure Decision**: Two-layer web application (FastAPI backend, React frontend). Changes are contained to one service, one model, one TS interface, and one React component.
