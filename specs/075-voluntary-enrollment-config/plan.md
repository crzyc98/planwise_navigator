# Implementation Plan: Voluntary Enrollment Rate Configuration

**Branch**: `075-voluntary-enrollment-config` | **Date**: 2026-03-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/075-voluntary-enrollment-config/spec.md`
**GitHub Issue**: [#247](https://github.com/crzyc98/planwise_navigator/issues/247)

## Summary

Add a configurable voluntary enrollment rate (0–100%) to the DC plan configuration page. The rate acts as a uniform multiplier on existing demographic-based enrollment probabilities in two dbt models (`int_voluntary_enrollment_decision` and `int_proactive_voluntary_enrollment`). The value flows through the established config pipeline: UI form → API → scenario config_overrides → Pydantic config → dbt variable export → SQL models. Backwards compatible — when not set, defaults to 1.0 (no change).

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript (React/Vite frontend), SQL (dbt-core 1.8.8)
**Primary Dependencies**: FastAPI, Pydantic v2, React 18, dbt-duckdb 1.8.1
**Storage**: DuckDB (simulation), filesystem JSON/YAML (scenario config)
**Testing**: pytest (Python), dbt test (SQL)
**Target Platform**: On-premises analytics server + web browser
**Project Type**: Web application (full-stack) + simulation engine
**Performance Goals**: No impact — single field addition to existing forms and a scalar multiply in SQL
**Constraints**: Single-threaded dbt execution, work laptop deployment
**Scale/Scope**: 3 files modified per layer (Python, SQL, React) — ~9 files total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No changes to event store; multiplier affects enrollment probability only |
| II. Modular Architecture | PASS | Changes are scoped to existing modules; no new modules needed |
| III. Test-First Development | PASS | Tests planned for each layer (Pydantic, dbt, integration) |
| IV. Enterprise Transparency | PASS | Config value is auditable via scenario config_overrides |
| V. Type-Safe Configuration | PASS | Using Pydantic field with `ge=0, le=1` validation |
| VI. Performance & Scalability | PASS | Single scalar multiply per employee — negligible overhead |

**Post-Phase 1 Re-check**: All gates still pass. Design adds one field to existing Pydantic model, one multiplier to existing SQL calculation, and one form field to existing React component. No architectural changes.

## Project Structure

### Documentation (this feature)

```text
specs/075-voluntary-enrollment-config/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research findings
├── data-model.md        # Phase 1 data model
├── quickstart.md        # Phase 1 developer quickstart
├── contracts/           # Phase 1 API contracts
│   └── api-contract.md  # API and dbt variable contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (files to modify)

```text
# Layer 1: Python Config
planalign_orchestrator/config/
├── workforce.py                    # Add voluntary_enrollment_rate to AutoEnrollmentSettings
└── export.py                       # Export field in _export_auto_enrollment_fields()

# Layer 2: dbt Models
dbt/
├── dbt_project.yml                 # Add default variable
└── models/intermediate/
    ├── int_voluntary_enrollment_decision.sql     # Apply multiplier
    └── int_proactive_voluntary_enrollment.sql    # Apply multiplier

# Layer 3: Frontend
planalign_studio/components/config/
├── DCPlanSection.tsx               # Add form field (slider + numeric input)
├── ConfigContext.tsx                # Add form state + mapping
└── buildConfigPayload.ts           # Transform to API payload

# Tests
tests/
├── test_config_export.py           # Test dbt variable export
└── test_workforce_config.py        # Test Pydantic validation
```

**Structure Decision**: This feature modifies existing files across all three layers of the established architecture (Python config → dbt SQL → React UI). No new files or modules are created except tests.

## Implementation Approach

### Phase 1: Python Config + Export (Backend)

1. Add `voluntary_enrollment_rate: Optional[float] = Field(default=None, ge=0, le=1)` to `AutoEnrollmentSettings` in `workforce.py`
2. Add `_set_if_not_none(dbt_vars, "voluntary_enrollment_rate", auto.voluntary_enrollment_rate, float)` to `_export_auto_enrollment_fields()` in `export.py`
3. Write unit tests verifying field validation and export behavior

### Phase 2: dbt Models (SQL)

1. Add `voluntary_enrollment_rate: null` default in `dbt_project.yml`
2. In `int_voluntary_enrollment_decision.sql`, multiply `final_enrollment_probability` by `COALESCE({{ var('voluntary_enrollment_rate', none) }}, 1.0)`
3. In `int_proactive_voluntary_enrollment.sql`, apply the same multiplier
4. Write dbt tests verifying enrollment counts scale with the rate

### Phase 3: Frontend (React)

1. Add `dcVoluntaryEnrollmentRate` to FormData in `ConfigContext.tsx`
2. Add mapping in `mapDCPlanEnrollmentFields()` to load from config
3. Add transform in `buildConfigPayload.ts` to export as `voluntary_enrollment_rate` (convert % to decimal)
4. Add form field in `DCPlanSection.tsx` — percentage input (0–100%) with validation message

### Phase 4: Integration Testing

1. End-to-end: set config → run simulation → verify enrollment counts
2. Test with auto-enrollment ON and OFF
3. Test edge cases: 0%, 100%, null/unset

## Complexity Tracking

> No violations — all changes fit within existing architecture.
