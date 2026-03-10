# Implementation Plan: Configurable Auto-Enrollment Opt-Out Rates

**Branch**: `068-optout-rate-config` | **Date**: 2026-03-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/068-optout-rate-config/spec.md`

## Summary

Expose 8 hardcoded auto-enrollment opt-out rates (4 age-band, 4 income-band) as editable fields in PlanAlign Studio's DC Plan configuration. The dbt SQL layer already supports these rates via `{{ var() }}` templates — this feature threads analyst-configured values from the UI through the API and orchestrator to dbt. No dbt or SQL changes are required.

## Technical Context

**Language/Version**: TypeScript (React/Vite frontend), Python 3.11 (FastAPI backend)
**Primary Dependencies**: React, FastAPI, Pydantic v2, dbt-duckdb 1.8.1
**Storage**: DuckDB (`dbt/simulation.duckdb`) — no schema changes needed
**Testing**: Vitest (frontend), pytest (backend)
**Target Platform**: Web application (localhost)
**Project Type**: Web application (full-stack: React frontend + FastAPI backend + dbt pipeline)
**Performance Goals**: N/A (configuration UI, no performance-critical paths)
**Constraints**: Backward compatible — scenarios without opt-out rates must use existing defaults
**Scale/Scope**: 6 files modified, 0 files created, ~150 lines added

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No changes to event store or event generation logic |
| II. Modular Architecture | PASS | Changes are scoped to existing modules; no new modules needed |
| III. Test-First Development | PASS | Tests for orchestrator export mapping; frontend validation tests |
| IV. Enterprise Transparency | PASS | Config changes flow through existing audit trail (scenario config_overrides) |
| V. Type-Safe Configuration | PASS | UI validation (0-100%), API validation (0.00-1.00), Pydantic models unchanged |
| VI. Performance & Scalability | PASS | No performance impact; adds 8 fields to config dict |

**Post-Phase 1 Re-check**: All gates still pass. No new modules, no circular dependencies, no schema changes.

## Project Structure

### Documentation (this feature)

```text
specs/068-optout-rate-config/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: Research findings
├── data-model.md        # Phase 1: Data model
├── quickstart.md        # Phase 1: Development quickstart
├── contracts/           # Phase 1: API contracts
│   └── api-contract.md
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_studio/components/config/
├── types.ts                  # Add 8 dcOptOutRate* fields to FormData
├── constants.ts              # Add 8 defaults to DEFAULT_FORM_DATA
├── DCPlanSection.tsx         # Add collapsible "Opt-Out Assumptions" section
└── buildConfigPayload.ts     # Map 8 fields to dc_plan payload

planalign_api/routers/
└── system.py                 # Add opt_out_rates to /config/defaults response

planalign_orchestrator/config/
└── export.py                 # Add 8 opt-out rate mappings in E095 dc_plan section
```

**Structure Decision**: Web application pattern — modifications span frontend (React), API (FastAPI), and orchestrator (Python). All changes are to existing files in established directories. No new files or directories needed.

## Complexity Tracking

No constitution violations. All changes follow existing patterns with minimal complexity.
