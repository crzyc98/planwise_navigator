# Implementation Plan: Service-Based Match Contribution Tiers

**Branch**: `010-fix-match-service-tiers` | **Date**: 2026-01-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/010-fix-match-service-tiers/spec.md`

## Summary

Add service-based employer match contribution tiers as a new mutually exclusive formula option. When `employer_match_status = 'graded_by_service'`, the match rate is determined by employee years of service rather than deferral percentage. Each service tier defines: min_years, max_years, rate, and max_deferral_pct. Calculation: rate × min(deferral%, max_deferral_pct) × compensation.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator), SQL/Jinja (dbt models), TypeScript 5.x (frontend)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, Pydantic v2, React 18
**Storage**: DuckDB 1.0.0 (immutable event store at `dbt/simulation.duckdb`)
**Testing**: pytest (Python), dbt tests (SQL), existing test fixtures
**Target Platform**: Linux/macOS server, web browser (PlanAlign Studio)
**Project Type**: Web application (backend + frontend)
**Performance Goals**: Handle 100K+ employees, <2s dashboard queries
**Constraints**: Single-threaded dbt execution for stability, backward compatibility required
**Scale/Scope**: Existing codebase, ~4 files modified, 1 new macro

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|-----------|------------|-------|
| I. Event Sourcing & Immutability | ✅ PASS | Match calculations derive from existing events; no event modifications |
| II. Modular Architecture | ✅ PASS | Changes contained within existing modules; new macro follows established pattern |
| III. Test-First Development | ✅ PASS | Will include dbt tests for new calculation paths |
| IV. Enterprise Transparency | ✅ PASS | `applied_years_of_service` audit field provides decision traceability |
| V. Type-Safe Configuration | ✅ PASS | New variables use Pydantic models; config export validates field types |
| VI. Performance & Scalability | ✅ PASS | Service tier lookup is O(1) via CASE expression; no additional joins |

**Gate Status**: PASSED - All principles satisfied

## Project Structure

### Documentation (this feature)

```text
specs/010-fix-match-service-tiers/
├── spec.md              # Feature specification (complete)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── service-tier-schema.yaml
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
# Backend (dbt + Python orchestrator)
dbt/
├── models/intermediate/events/
│   └── int_employee_match_calculations.sql  # MODIFY: Add service-based logic
├── macros/
│   ├── get_tiered_core_rate.sql             # REFERENCE: Pattern to follow
│   └── get_tiered_match_rate.sql            # NEW: Service-based rate macro
└── tests/
    └── schema.yml                            # ADD: Tests for service-based match

planalign_orchestrator/
└── config/
    └── export.py                             # MODIFY: Export service tier config

# Frontend (React/TypeScript)
planalign_studio/
├── components/
│   └── MatchConfigSection.tsx               # MODIFY: Add service-based UI
└── services/
    └── api.ts                                # MODIFY: Handle service tier API calls

tests/
└── test_service_match_tiers.py              # NEW: Integration tests
```

**Structure Decision**: Web application structure - backend dbt models + Python orchestrator, frontend React components. Follows existing project layout.

## Complexity Tracking

> No Constitution violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
