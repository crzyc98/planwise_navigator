# Implementation Plan: Core Contribution Tier Validation & Points-Based Mode

**Branch**: `053-core-contribution-tiers` | **Date**: 2026-02-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/053-core-contribution-tiers/spec.md`

## Summary

Add tier gap/overlap validation warnings to graded-by-service core contributions (reusing existing `validateMatchTiers()` function) and add a points-based core contribution mode with a tier editor, config persistence pipeline, and dbt simulation support. The implementation extends existing patterns at every layer — no new architectural concepts are introduced.

## Technical Context

**Language/Version**: TypeScript 5.x (frontend), Python 3.11 (backend), SQL/Jinja2 (dbt)
**Primary Dependencies**: React 18, Vite (frontend); dbt-core 1.8.8, dbt-duckdb 1.8.1 (backend)
**Storage**: DuckDB 1.0.0 (`dbt/simulation.duckdb`)
**Testing**: Visual testing via PlanAlign Studio (frontend); dbt compile/build (backend)
**Target Platform**: Linux server (web application)
**Project Type**: Web application (frontend + backend + dbt)
**Performance Goals**: Client-side validation is instant; no latency concerns
**Constraints**: Single-threaded dbt execution (`--threads 1`)
**Scale/Scope**: 3-6 tiers per schedule (small data); 7 files modified

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Core contributions flow through existing immutable event pipeline; no changes to event model |
| II. Modular Architecture | PASS | Changes are localized to existing modules; no new modules created; no file exceeds 600 lines |
| III. Test-First Development | PASS | P1/P2 are frontend-only (visual testing); P3 adds dbt model changes testable via `dbt build` |
| IV. Enterprise Transparency | PASS | Configuration changes are version-controlled via workspace config; contribution rates are auditable in event store |
| V. Type-Safe Configuration | PASS | New `PointsCoreTier` interface in TypeScript; Pydantic validation in export pipeline; dbt vars with explicit types |
| VI. Performance & Scalability | PASS | Tier validation is O(n log n) on small arrays (3-6 tiers); no impact on simulation performance |

**Post-design re-check**: All gates still pass. No new dependencies, no circular references, no module size increases beyond limits.

## Project Structure

### Documentation (this feature)

```text
specs/053-core-contribution-tiers/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research decisions
├── data-model.md        # Phase 1 data model
├── quickstart.md        # Phase 1 developer quickstart
├── contracts/           # Phase 1 API contracts
│   └── dc-plan-config.md
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_studio/components/config/        # Frontend (P1 + P2)
├── DCPlanSection.tsx                      # Main component: add validation + points editor
├── types.ts                              # Add PointsCoreTier interface + FormData field
├── constants.ts                          # Add default dcCorePointsSchedule
├── buildConfigPayload.ts                 # Add core_points_schedule to payload
└── ConfigContext.tsx                      # Load dcCorePointsSchedule from saved config

planalign_orchestrator/config/             # Backend config (P3)
└── export.py                             # Export employer_core_points_schedule dbt var

dbt/models/intermediate/                   # dbt model (P3)
└── int_employer_core_contributions.sql   # Add points_based conditional branch
```

**Structure Decision**: Web application structure. All changes are modifications to existing files — no new files created except the data model, research, quickstart, and contract documents. The feature touches 5 frontend files and 2 backend files.

## Complexity Tracking

No constitution violations. No complexity justifications needed.
