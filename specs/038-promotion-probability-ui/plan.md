# Implementation Plan: Promotion Hazard Configuration UI

**Branch**: `038-promotion-probability-ui` | **Date**: 2026-02-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/038-promotion-probability-ui/spec.md`

## Summary

Add a "Promotion Hazard" section to PlanAlign Studio's Configuration page (after the Job Level Compensation section) that displays and allows editing of the three seed files that drive the simulation's promotion hazard model:

1. **Base parameters** (`config_promotion_hazard_base.csv`): base_rate (2%) and level_dampener_factor (15%)
2. **Age multipliers** (`config_promotion_hazard_age_multipliers.csv`): 6 multipliers by age band
3. **Tenure multipliers** (`config_promotion_hazard_tenure_multipliers.csv`): 5 multipliers by tenure band

The implementation follows the **band configuration pattern** (CSV-direct read/write via dedicated API endpoints and service layer), not the workspace YAML pattern. This ensures saved values are immediately reflected in the dbt seed files consumed by `dim_promotion_hazards.sql`.

## Technical Context

**Language/Version**: TypeScript 5.x (frontend), Python 3.11 (backend)
**Primary Dependencies**: React 18, Vite, FastAPI, Pydantic v2
**Storage**: dbt CSV seeds (`dbt/seeds/config_promotion_hazard_*.csv`) — direct read/write
**Testing**: Manual UI testing; pytest for backend service unit tests
**Target Platform**: Web browser (PlanAlign Studio)
**Project Type**: Web application (frontend + backend)
**Performance Goals**: N/A (13 values total — trivial data size)
**Constraints**: Must follow existing band config pattern for consistency
**Scale/Scope**: 3 CSV files, 13 editable values, 1 new API endpoint pair, 1 new service, 1 new model file, frontend additions to ConfigStudio.tsx and api.ts

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | No event store changes |
| II. Modular Architecture | PASS | New service/router/model follow band config modular pattern |
| III. Test-First Development | PASS | Backend service gets unit tests; frontend is manual |
| IV. Enterprise Transparency | PASS | Promotion hazard parameters become visible and configurable |
| V. Type-Safe Configuration | PASS | Pydantic v2 models with Field validators for all parameters |
| VI. Performance & Scalability | N/A | 13 values — no performance impact |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/038-promotion-probability-ui/
├── plan.md              # This file
├── research.md          # Phase 0: research findings
├── data-model.md        # Phase 1: data model
├── quickstart.md        # Phase 1: implementation quickstart
├── contracts/           # Phase 1: API contracts
│   └── promotion-hazard-api.md
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (files to create and modify)

```text
planalign_api/
├── models/
│   └── promotion_hazard.py          # NEW: Pydantic models for hazard config
├── services/
│   └── promotion_hazard_service.py  # NEW: CSV read/write/validate service
├── routers/
│   ├── __init__.py                  # MODIFY: export new router
│   └── promotion_hazard.py          # NEW: GET/PUT endpoints
└── main.py                          # MODIFY: register new router

planalign_studio/
├── components/
│   └── ConfigStudio.tsx             # MODIFY: add Promotion Hazard section
└── services/
    └── api.ts                       # MODIFY: add TS interfaces and API functions

dbt/seeds/
├── config_promotion_hazard_base.csv              # EXISTS (no change)
├── config_promotion_hazard_age_multipliers.csv   # EXISTS (no change)
└── config_promotion_hazard_tenure_multipliers.csv # EXISTS (no change)
```

**Structure Decision**: Follows the existing band configuration pattern — new backend files for models, service, and router; frontend additions to existing ConfigStudio.tsx and api.ts. CSV seeds are read/written directly (not through workspace YAML).

## Complexity Tracking

> No constitution violations — table not needed.
