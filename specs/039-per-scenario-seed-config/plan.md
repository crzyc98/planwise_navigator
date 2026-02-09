# Implementation Plan: Per-Scenario Seed Configuration

**Branch**: `039-per-scenario-seed-config` | **Date**: 2026-02-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/039-per-scenario-seed-config/spec.md`

## Summary

Migrate seed-based configurations (promotion hazard rates, age/tenure band definitions) from global CSV files to per-scenario config overrides. Unify all configuration saves into a single atomic "Save Changes" button. Include seed configs in "Copy from Scenario". At simulation time, the orchestrator writes scenario-specific CSV files from the merged config so dbt picks up per-scenario values without any dbt model changes.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (API), Pydantic v2 (validation), React 18 + Vite (frontend), dbt-core 1.8.8
**Storage**: Workspace YAML files (`base_config.yaml`, `overrides.yaml`), DuckDB (simulation), CSV seeds (ephemeral working copies)
**Testing**: pytest (backend), manual E2E (frontend)
**Target Platform**: Linux server / work laptop
**Project Type**: Web application (FastAPI backend + React frontend + orchestrator)
**Performance Goals**: Config save <1s, merged config resolution <200ms, seed CSV write <100ms
**Constraints**: Sequential simulation execution (DuckDB single-writer lock), no dbt model SQL changes
**Scale/Scope**: ~10 files modified, ~3 files added (validators), ~500 LOC backend, ~300 LOC frontend

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No changes to event store or fct_yearly_events. Seed configs are configuration, not events. |
| II. Modular Architecture | PASS | Changes distributed across existing modules (storage, services, routers, orchestrator). No new monoliths. No circular dependencies introduced. |
| III. Test-First Development | PASS | Validation logic and merge fallback logic will have unit tests. Orchestrator seed injection will have integration tests. |
| IV. Enterprise Transparency | PASS | Config changes stored in version-controlled YAML files. Orchestrator logs which seed values are used per simulation. |
| V. Type-Safe Configuration | PASS | New seed config sections validated via Pydantic v2 models. Existing PromotionHazardConfig model reused. |
| VI. Performance & Scalability | PASS | CSV write adds <100ms to simulation start. No memory impact. Single-threaded execution preserved. |

**Post-design re-check**: All gates still PASS. The pre-seed copy approach introduces no new architectural complexity — it's a straightforward file write in the existing orchestrator initialization flow.

## Project Structure

### Documentation (this feature)

```text
specs/039-per-scenario-seed-config/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: Research decisions
├── data-model.md        # Phase 1: Data model extensions
├── quickstart.md        # Phase 1: Implementation summary
├── contracts/           # Phase 1: API contracts
│   └── api-contracts.md
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
planalign_api/
├── storage/
│   └── workspace_storage.py      # MODIFY: merged config fallback to global CSVs
├── routers/
│   ├── scenarios.py               # MODIFY: add seed config validation on update
│   ├── promotion_hazard.py        # MODIFY: remove PUT endpoint, keep GET
│   └── bands.py                   # MODIFY: remove PUT endpoint, keep GET
├── services/
│   ├── promotion_hazard_service.py # MODIFY: add read-from-config-dict helper
│   ├── band_service.py            # MODIFY: add read-from-config-dict helper
│   └── seed_config_validator.py   # NEW: unified validation for seed config sections
└── models/
    └── promotion_hazard.py        # KEEP: existing models reused

planalign_orchestrator/
├── pipeline_orchestrator.py       # MODIFY: inject seed CSVs from merged config
└── pipeline/
    └── seed_writer.py             # NEW: write config dict → CSV files

planalign_studio/
├── components/
│   └── ConfigStudio.tsx           # MODIFY: unified state, remove separate save buttons
└── services/
    └── api.ts                     # MODIFY: remove PUT save functions, keep GET reads

tests/
├── test_seed_config_validator.py  # NEW: validation unit tests
├── test_seed_writer.py            # NEW: CSV writer unit tests
└── test_merged_config_fallback.py # NEW: merge chain integration tests
```

**Structure Decision**: Follows the existing web application structure. Backend changes span the API layer (routers, services, storage) and orchestrator. Frontend changes are contained to ConfigStudio and api.ts. New files are minimal — one validator service, one seed writer utility, and corresponding tests.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
