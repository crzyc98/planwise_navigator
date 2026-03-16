# Implementation Plan: Apply Workforce Parameters Across Scenarios

**Branch**: `072-apply-workforce-params` | **Date**: 2026-03-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/072-apply-workforce-params/spec.md`

## Summary

Add an "Apply Workforce Params" action to the scenario config page that lets analysts push workforce assumptions (compensation, turnover, hiring, demographics, seed configs) from one scenario to multiple target scenarios in a single operation, while preserving each target's DC plan parameters. Implemented as a new API endpoint with a frontend modal for target selection and confirmation.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript (frontend React/Vite)
**Primary Dependencies**: FastAPI, Pydantic v2 (backend); React 18, Lucide React (frontend)
**Storage**: File-based JSON/YAML per scenario (`workspaces/{id}/scenarios/{id}/scenario.json`)
**Testing**: pytest (backend), manual E2E (frontend)
**Target Platform**: Linux server (backend), modern browsers (frontend)
**Project Type**: Web application (FastAPI + React/Vite)
**Performance Goals**: <2 seconds for applying to 10 target scenarios
**Constraints**: No new npm dependencies; use existing UI patterns
**Scale/Scope**: Operates within a single workspace; typically 2-10 scenarios

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Event Sourcing & Immutability | N/A | This feature modifies config, not event data. No events are created/modified/deleted. |
| II. Modular Architecture | PASS | New endpoint in existing router; new modal component; service method ~40 lines. No module exceeds limits. |
| III. Test-First Development | PASS | Backend tests for the service method and endpoint. Frontend tested via manual E2E. |
| IV. Enterprise Transparency | PASS | API returns detailed per-scenario results. Existing config versioning (overrides.yaml) provides audit trail. |
| V. Type-Safe Configuration | PASS | New Pydantic v2 request/response models for the endpoint. |
| VI. Performance & Scalability | PASS | Sequential read-merge-write for <10 scenarios; well within <2s target. |

**Post-Phase 1 Re-check**: All gates still pass. No new storage patterns, no circular dependencies, no modules exceeding size limits.

## Project Structure

### Documentation (this feature)

```text
specs/072-apply-workforce-params/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: Research decisions
├── data-model.md        # Phase 1: Data model
├── quickstart.md        # Phase 1: Developer quickstart
├── contracts/           # Phase 1: API contracts
│   └── api.md           # REST endpoint contract
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
planalign_api/
├── models/
│   └── scenario.py                          # ADD: WorkforceParamsApplyRequest, WorkforceParamsApplyResult models
├── routers/
│   └── scenarios.py                         # ADD: POST .../apply-workforce-params endpoint
└── services/
    └── scenario_service.py                  # ADD: apply_workforce_params() method

planalign_studio/
├── components/
│   ├── ConfigStudio.tsx                     # MODIFY: Add "Apply Workforce Params" button
│   └── config/
│       └── ApplyWorkforceParamsModal.tsx     # NEW: Multi-select target modal with confirmation
└── services/
    └── api.ts                               # ADD: applyWorkforceParams() client function

tests/
└── test_apply_workforce_params.py           # NEW: Backend unit tests
```

**Structure Decision**: Web application pattern. Backend changes are additive (new models, endpoint, service method) within existing packages. Frontend adds one new component and modifies two existing files. No new packages or directories beyond the new modal component file.

## Complexity Tracking

No constitution violations. No complexity justifications needed.
