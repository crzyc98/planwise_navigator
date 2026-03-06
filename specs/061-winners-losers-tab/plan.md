# Implementation Plan: Winners & Losers Comparison Tab

**Branch**: `061-winners-losers-tab` | **Date**: 2026-03-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/061-winners-losers-tab/spec.md`

## Summary

Add a "Winners & Losers" tab to PlanAlign Studio that compares two simulation scenarios and classifies employees as winners, losers, or neutral based on total employer contributions (match + core). The tab displays bar charts by age band and tenure band, plus an age×tenure heatmap. Backend adds a single API endpoint that queries two scenario databases, joins on employee_id, computes deltas, and aggregates by demographic bands.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript/React (frontend)
**Primary Dependencies**: FastAPI, DuckDB, Pydantic v2, React, Recharts, Tailwind CSS
**Storage**: DuckDB (per-scenario databases via DatabasePathResolver)
**Testing**: pytest (backend), manual browser testing (frontend)
**Target Platform**: Web application (localhost deployment)
**Project Type**: Web application (FastAPI + React/Vite)
**Performance Goals**: <3 seconds for full render with 10K employees (SC-002)
**Constraints**: Read-only database access; single-threaded queries
**Scale/Scope**: Up to 10K employees per scenario; 6 age bands × 5 tenure bands = 30 heatmap cells

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Read-only queries against existing `fct_workforce_snapshot`; no event creation |
| II. Modular Architecture | PASS | New service file <300 lines; new component ~600 lines; single responsibility each |
| III. Test-First Development | PASS | Backend service tested with in-memory DuckDB fixtures |
| IV. Enterprise Transparency | PASS | API response includes `total_excluded` count for employees not compared |
| V. Type-Safe Configuration | PASS | Pydantic v2 models for all API inputs/outputs; no raw SQL string concatenation for table refs |
| VI. Performance & Scalability | PASS | Single query per scenario database; aggregation in SQL; <3s target |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/061-winners-losers-tab/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research decisions
├── data-model.md        # Entity definitions
├── quickstart.md        # Developer quickstart
├── contracts/
│   └── api.md           # API contract
└── tasks.md             # Implementation tasks (via /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_api/
├── routers/
│   └── analytics.py              # Add winners-losers endpoint (existing file)
├── services/
│   └── winners_losers_service.py # NEW: comparison logic + DuckDB queries
└── models/
    └── winners_losers.py         # NEW: Pydantic response models

planalign_studio/
├── components/
│   └── WinnersLosersTab.tsx      # NEW: full tab component
├── services/
│   └── api.ts                    # Add API client function (existing file)
├── App.tsx                       # Add route (existing file)
└── components/
    └── Layout.tsx                # Add nav item (existing file)

tests/
└── test_winners_losers.py        # NEW: backend unit tests
```

**Structure Decision**: Follows existing patterns — new service file for business logic, new models file for Pydantic types, single new React component for the full tab. Reuses existing router and navigation infrastructure.

## Architecture

### Backend Flow

```
GET /api/workspaces/{wid}/analytics/winners-losers?plan_a=A&plan_b=B
  │
  ├─ Validate workspace + both scenarios exist and are completed
  │
  ├─ Resolve DB paths: db_resolver.resolve(wid, plan_a), db_resolver.resolve(wid, plan_b)
  │
  ├─ Query Plan A: SELECT employee_id, age_band, tenure_band,
  │                        employer_match_amount + employer_core_amount AS employer_total
  │                 FROM fct_workforce_snapshot
  │                 WHERE simulation_year = MAX(simulation_year)
  │                   AND LOWER(employment_status) = 'active'
  │
  ├─ Query Plan B: same query
  │
  ├─ INNER JOIN on employee_id (Python: merge DataFrames)
  │
  ├─ Compute delta = plan_b_total - plan_a_total
  │   → winner (delta > 0), loser (delta < 0), neutral (delta == 0)
  │
  ├─ Aggregate by age_band → age_band_results
  ├─ Aggregate by tenure_band → tenure_band_results
  ├─ Aggregate by (age_band, tenure_band) → heatmap
  │
  └─ Return WinnersLosersResponse
```

### Frontend Component Structure

```
WinnersLosersTab
├── Header (title + Plan A/B selectors + refresh button)
├── Summary Banner (total winners / losers / neutral / excluded)
├── Age Band Bar Chart (Recharts BarChart, grouped winners/losers)
├── Tenure Band Bar Chart (Recharts BarChart, grouped winners/losers)
└── Age × Tenure Heatmap (CSS Grid, diverging green/red color scale)
```

### Key Design Decisions

1. **Join in Python, not SQL**: Two scenario databases may be separate files; DuckDB ATTACH on same file causes errors. Load two DataFrames, merge via pandas.
2. **Custom heatmap**: Recharts has no heatmap chart type. CSS Grid + Tailwind is simpler and matches existing styling.
3. **URL params for persistence**: Matches existing AnalyticsDashboard pattern. Enables deep linking.
4. **Same-scenario comparison allowed**: Returns all-neutral results (edge case from spec).

## Phases

### Phase 1: Backend Models + Service (P1)

1. Create `planalign_api/models/winners_losers.py` with Pydantic models
2. Create `planalign_api/services/winners_losers_service.py` with comparison logic
3. Write unit tests for classification logic and aggregation

### Phase 2: API Endpoint (P1)

1. Add endpoint to `planalign_api/routers/analytics.py`
2. Wire dependency injection for the new service
3. Test endpoint with curl/httpie

### Phase 3: Frontend Component (P1)

1. Create `WinnersLosersTab.tsx` with workspace/scenario selectors
2. Add API client function to `api.ts`
3. Add route in `App.tsx` and nav item in `Layout.tsx`
4. Implement bar charts for age band and tenure band

### Phase 4: Heatmap + Polish (P2)

1. Add CSS Grid heatmap with diverging color scale
2. Add tooltips to all charts and heatmap cells
3. Handle edge cases (fewer than 2 scenarios, empty bands, same scenario selected)
4. Add session persistence via URL params
