# Implementation Plan: Enforce Census Path Validation on Simulation Start

**Branch**: `080-census-path-validation` | **Date**: 2026-03-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/080-census-path-validation/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Replace silent fallback to default census path with hard-fail validation. When a simulation is launched from Studio, the system MUST validate that `census_parquet_path` exists in the merged config and that the file exists on disk. Missing or invalid paths trigger immediate, actionable errors in the UI before any data processing begins, preventing silent corruption of simulation results.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Pydantic v2.7.4, FastAPI, DuckDB 1.0.0
**Storage**: DuckDB (dbt/simulation.duckdb)
**Testing**: pytest with fixture library (`tests/fixtures/`)
**Target Platform**: Linux server (on-premises)
**Project Type**: web-service (FastAPI backend + React/Vite frontend)
**Performance Goals**: Validation must occur in <100ms to not impact pre-run experience
**Constraints**: 90%+ test coverage for core modules; fast tests must complete in <10s; error messages must be user-actionable
**Scale/Scope**: Handles 100K+ employee records; this feature validates a single filesystem path check

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Event Sourcing & Immutability
✅ **Compliant**: This feature does not modify or read immutable events. It validates input before events are generated. No action required.

### Principle II: Modular Architecture
✅ **Compliant**: Validation logic will be isolated in a dedicated validation function/module. No circular dependencies. Single responsibility: validate census path existence.

### Principle III: Test-First Development
✅ **Required**: Tests MUST be written before implementation (Red-Green-Refactor). Target 90%+ coverage for validation module. Fast tests (<10s) for unit tests; integration tests for Studio API path.

### Principle IV: Enterprise Transparency
✅ **Required**: Configuration validation errors MUST be logged with correlation ID, scenario context, and resolution guidance. Error catalog entry needed for `ConfigurationError` with census path context.

### Principle V: Type-Safe Configuration
✅ **Required**: Validation uses existing Pydantic models from `config.SimulationConfig`. No raw string access to config dict; all config access through typed objects.

### Principle VI: Performance & Scalability
✅ **Compliant**: Filesystem existence check is O(1) and negligible. No performance impact on initialization or bulk operations.

**Gate Status**: ✅ **PASS** - No violations. Feature aligns with all six core principles.

## Project Structure

### Documentation (this feature)

```text
specs/080-census-path-validation/
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0 output (research & design decisions)
├── data-model.md        # Phase 1 output (entity & config validation model)
├── quickstart.md        # Phase 1 output (implementation quick reference)
├── contracts/           # Phase 1 output (API request/response contracts)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

The feature affects two main areas:

**Backend (Python)**:
- `planalign_api/services/simulation/service.py` - **Primary**: Add validation logic here
- `planalign_orchestrator/exceptions.py` - **Existing**: Already has `ConfigurationError` base class
- `planalign_orchestrator/error_catalog.py` - **Extend**: Add census-path validation error entries
- `planalign_orchestrator/config.py` - **Use**: Reference existing `SimulationConfig` validation

**Frontend (React/TypeScript)**:
- `planalign_studio/src/services/simulationService.ts` - **Extend**: Handle validation errors in API calls
- `planalign_studio/src/components/` - **Extend**: Display error messages in simulation launcher UI

**Tests (Python)**:
- `tests/test_census_validation.py` - **New**: Test census path validation
- `tests/fixtures/` - **Existing**: Use existing fixture library for test setup

**Structure Decision**: Single monolithic API service with modular error handling. Validation logic is centralized in `service.py` with reusable error catalog entries. No architectural changes needed—this is a validation insertion before simulation execution.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

✅ **No violations** - Feature passes all constitutional gates. No complexity justification needed.

---

## Phase 1: Design Artifacts ✅ COMPLETE

### Deliverables

1. **research.md** (Phase 0 Research)
   - Current implementation analysis (silent fallback in `_validate_census()`)
   - ConfigurationError infrastructure review
   - Error catalog system design
   - 7 design decisions with alternatives evaluated
   - Implementation roadmap with 3 phases (4h + 2h + 6h = 12h)

2. **data-model.md** (Phase 1 Design)
   - Entity 1: Scenario Configuration (census_parquet_path field, validation rules)
   - Entity 2: Validation Context (scenario_id, workspace_id, error_type, correlation_id)
   - Entity 3: Configuration Error (message, context, resolution hints)
   - Data flow diagrams (validation flow, error handling flow)
   - Validation rules table (FR-001 to FR-007 enforcement)
   - Edge case handling (8 edge cases mapped to expected behavior)
   - Type-safe configuration using Pydantic v2

3. **quickstart.md** (Implementation Guide)
   - 3 key code changes:
     * File 1: `service.py` — Replace silent fallback with ConfigurationError
     * File 2: `error_catalog.py` — Add 2 error patterns with resolution hints
     * File 3: `test_simulation_service.py` — 7 test cases covering all scenarios
   - Example error messages for both failure modes
   - Integration points (no changes to error handler or frontend)
   - Dependencies (all existing, no new imports)
   - Deployment considerations and migration notes
   - Testing checklist and code review checklist

4. **contracts/api-error-response.md** (API Contract)
   - No new endpoints (feature changes error behavior of existing endpoint)
   - Existing error response format (no changes)
   - 2 census validation errors with example responses
   - Client error handling (frontend and CLI)
   - Error logging contract with correlation IDs
   - Backward compatibility note (breaking change)
   - Validation contracts (internal input/output specifications)
   - Monitoring & alerting recommendations

### Agent Context Updated

- Language: Python 3.11
- Frameworks: Pydantic v2.7.4, FastAPI, DuckDB 1.0.0
- Database: DuckDB (dbt/simulation.duckdb)
- Project Type: web-service (FastAPI + React/Vite)

### Constitution Check: Re-evaluation ✅ PASS

All 6 core principles verified:

1. **Event Sourcing & Immutability** ✅ — Validation does not touch immutable events
2. **Modular Architecture** ✅ — Validation is isolated in dedicated function
3. **Test-First Development** ✅ — 90%+ coverage target with 7 test cases
4. **Enterprise Transparency** ✅ — Error logging includes correlation_id and scenario_id
5. **Type-Safe Configuration** ✅ — Uses Pydantic v2 and ConfigurationError
6. **Performance & Scalability** ✅ — Filesystem stat is O(1), <100ms impact

---

## Next Phase: Phase 2 Implementation

**Ready for**: `/speckit.tasks` command to generate implementation tasks

**Estimated Timeline**: 12-15 hours total
- Phase 1 Design (analysis): 6 hours (COMPLETE)
- Phase 2 Implementation: 12 hours estimated
  - Validation logic: 4 hours
  - Error catalog: 2 hours
  - Testing: 6 hours
