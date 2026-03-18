# Implementation Plan: Fix Termination Rate Suggestion Bug

**Branch**: `001-fix-termination-rate` | **Date**: 2026-03-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from GitHub issue #245

**Note**: This implementation plan addresses the bug where termination rate suggestions always return 100% regardless of input census data.

## Summary

The termination rate suggestion feature returns an invalid 100% for all scenarios, making it impossible for users to make informed decisions about workforce turnover rates. This fix corrects the calculation logic to derive realistic rates from census data by fixing the denominator calculation (active employees vs. just terminations) and addressing any division-by-zero or fallback logic that defaults to 100%.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: FastAPI (backend), React/Vite (frontend), Pydantic v2, DuckDB 1.0.0
**Storage**: DuckDB (`dbt/simulation.duckdb`) for census data and audit trails
**Testing**: pytest with fixtures library (tests/fixtures/)
**Target Platform**: Linux server (on-premises enterprise deployment)
**Project Type**: web-service (FastAPI backend + React frontend + Python CLI)
**Performance Goals**: Termination rate suggestions <2 seconds (95th percentile for dashboard queries)
**Constraints**: Work laptop deployments require single-threaded execution by default; memory footprint <500MB for 100k+ employee datasets
**Scale/Scope**: Workforce simulation system supporting 100k+ employee records; suggestion feature used across all scenarios

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Event Sourcing & Immutability** | ✅ PASS | Bug fix does not change event sourcing architecture; immutable event store unaffected |
| **II. Modular Architecture** | ✅ PASS | Fix is isolated to termination rate suggestion service; no circular dependencies introduced |
| **III. Test-First Development** | ✅ PASS | Implementation will include pytest fixtures and unit tests; must achieve 90%+ coverage |
| **IV. Enterprise Transparency** | ✅ PASS | Fix includes error handling with informative messages for edge cases (zero denominator, missing data) |
| **V. Type-Safe Configuration** | ✅ PASS | Census data schema and calculation inputs use Pydantic v2 validation |
| **VI. Performance & Scalability** | ✅ PASS | Calculation is lightweight; <2s response time achievable with optimized denominator aggregation |

**Gate Verdict**: PASS - All principles maintained. No complexity tracking required.

## Project Structure

### Documentation (this feature)

```text
specs/001-fix-termination-rate/
├── plan.md              # This file (implementation plan)
├── research.md          # Phase 0: Research findings (to be generated)
├── data-model.md        # Phase 1: Data model design (to be generated)
├── quickstart.md        # Phase 1: Developer quickstart (to be generated)
├── contracts/           # Phase 1: API contracts (to be generated)
├── tasks.md             # Phase 2: Task breakdown (created by /speckit.tasks)
└── checklists/
    └── requirements.md  # Specification quality checklist (pre-created)
```

### Source Code (PlanAlign Engine)

```text
planalign_engine/
├── planalign_orchestrator/        # Core orchestration (E072 refactored)
│   ├── generators/                # Event type abstraction layer (E004)
│   │   ├── base.py               # EventGenerator ABC, EventRegistry
│   │   ├── registry.py           # Centralized event registration
│   │   └── [event type modules]
│   └── pipeline/                  # Modular pipeline (E072)
│       ├── workflow.py
│       ├── state_manager.py
│       └── event_generation_executor.py
│
├── planalign_api/                 # FastAPI backend for Studio
│   ├── main.py
│   ├── routers/                   # API endpoints
│   │   └── scenarios.py           # Includes termination rate suggestion endpoint
│   └── services/                  # Business logic
│       └── suggestion_service.py  # ← FIX LOCATION
│
├── planalign_studio/              # React/Vite frontend
│   └── src/
│       └── services/              # API client services
│
├── planalign_cli/                 # Rich-based CLI
│   └── commands/
│
├── dbt/                           # SQL models
│   └── models/
│       └── staging/               # Source data transformation
│
└── tests/                         # Comprehensive test suite (E075)
    ├── fixtures/                  # Centralized fixture library
    ├── test_*.py                  # Test modules
    └── integration/               # Integration tests
```

**Structure Decision**: Fix is located in `planalign_api/services/suggestion_service.py` (or similar) where the termination rate calculation logic resides. The bug is isolated to the calculation service; no structural changes needed. Tests will be added to `tests/test_termination_rate_suggestion.py` following E075 fixture patterns.

## Complexity Tracking

> No Constitution Check violations - no complexity tracking required.
