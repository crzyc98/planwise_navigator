# Implementation Plan: ERISA 1,000-Hour Eligibility Rules

**Branch**: `063-1000-hr-eligibility` | **Date**: 2026-03-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/063-1000-hr-eligibility/spec.md`

## Summary

Implement ERISA-compliant eligibility computation periods (IECP with plan-year switching and overlap/double-credit rule), 1,000-hour eligibility threshold, independent eligibility vs. vesting service credit tracking, and IRC 410(a)(4) plan entry date computation. Uses boundary-aware annual approximation within the existing dbt pipeline — 2 new intermediate models, 1 macro, 3 data quality tests, and a new config section. No modifications to existing models. Continuous employment assumed (no break-in-service tracking).

## Technical Context

**Language/Version**: Python 3.11, SQL (dbt-core 1.8.8)
**Primary Dependencies**: dbt-duckdb 1.8.1, DuckDB 1.0.0, Pydantic 2.7.4
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: dbt tests (schema + custom SQL), pytest for Python config validation
**Target Platform**: Linux server (on-premises analytics)
**Project Type**: Simulation engine (CLI + web)
**Performance Goals**: Handle 100K+ employee records; dashboard queries < 2s (p95)
**Constraints**: Single-threaded dbt execution; annual pipeline steps preserved
**Scale/Scope**: 2 new dbt models, 1 macro, 3 dbt tests, config extension

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Event Sourcing & Immutability | PASS | New models produce immutable per-year service credit records. Accumulator uses `delete+insert` (idempotent, year-scoped). No events modified. |
| II. Modular Architecture | PASS | 2 focused models (computation period, accumulator), each with single responsibility. No circular dependencies — new models only read from existing intermediate + staging layers. |
| III. Test-First Development | PASS | 3 custom SQL tests + schema tests planned. Tests cover boundary values, IECP computation, independence of eligibility/vesting. |
| IV. Enterprise Transparency | PASS | Every eligibility determination includes `eligibility_reason` code and `service_credit_source` for audit trail. SC-005 requires full traceability. |
| V. Type-Safe Configuration | PASS | New `erisa_eligibility` config section uses existing Pydantic-validated YAML pattern. All model references via `{{ ref() }}`. |
| VI. Performance & Scalability | PASS | Annual pipeline preserved (no sub-annual stages). Models use existing proration formula. Incremental accumulator scales linearly with employee count. |

**Gate result**: ALL PASS — no violations, no justifications needed.

## Project Structure

### Documentation (this feature)

```text
specs/063-1000-hr-eligibility/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0: Research decisions
├── data-model.md        # Phase 1: Entity definitions
├── quickstart.md        # Phase 1: Developer quickstart
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
dbt/
├── models/
│   └── intermediate/
│       ├── int_eligibility_computation_period.sql   # NEW: IECP + plan year periods
│       ├── int_service_credit_accumulator.sql       # NEW: Temporal service credit
│       └── schema.yml                               # MODIFIED: Add schema tests
├── macros/
│   └── classify_service_hours.sql                   # NEW: 1,000-hour threshold macro
└── tests/
    └── data_quality/
        ├── test_iecp_computation.sql                 # NEW
        ├── test_hours_threshold.sql                  # NEW
        └── test_eligibility_vs_vesting_independence.sql  # NEW

config/
└── simulation_config.yaml                            # MODIFIED: Add erisa_eligibility section
```

**Structure Decision**: All new code lives within the existing `dbt/` directory structure following established naming conventions (`int_*` for intermediate models). No new directories needed.

## Design Decisions

### D1: Boundary-Aware IECP (see [research.md](research.md#r1))

The IECP spans a 12-month window from hire date that crosses plan year boundaries. Rather than adding sub-annual pipeline stages, `int_eligibility_computation_period` computes partial-year hours for each plan year within the IECP, then sums them. This preserves the annual pipeline architecture.

### D2: Temporal State Accumulator (see [research.md](research.md#r2))

Service credit uses the `{{ this }}` self-referencing pattern from `int_enrollment_state_accumulator.sql`. First year initializes from baseline; subsequent years merge prior-year state with current-year computation periods.

### D3: Parallel Architecture (see [research.md](research.md#r3))

Two new models operate alongside existing eligibility models without modification. This separates ERISA plan participation eligibility from match/core contribution allocation eligibility.

### D4: Hours Threshold Macro (see [research.md](research.md#r4))

A reusable `classify_service_hours()` macro ensures consistent threshold application across models.

### D5: Configuration Isolation (see [research.md](research.md#r5))

New `erisa_eligibility` section in `simulation_config.yaml` with feature toggle (`enabled: true/false`) for incremental adoption.

### D6: Continuous Employment (from spec clarifications)

All employees in the simulation are assumed active. No break-in-service tracking, rehire scenarios, or service credit restoration. This eliminates the `int_break_in_service` model and simplifies the data model to 2 models.

## Model Build Order

Within the existing pipeline workflow stages:

1. **STATE_ACCUMULATION stage**: `int_eligibility_computation_period` (reads `int_baseline_workforce`, `int_hiring_events`, `int_new_hire_termination_events`) — must run after EVENT_GENERATION so new-hire data is available
2. **STATE_ACCUMULATION stage**: `int_service_credit_accumulator` (reads `int_eligibility_computation_period` + `{{ this }}`) — dbt DAG ensures (1) builds before (2) within the same stage

This aligns with the existing 6-stage workflow: INITIALIZATION → FOUNDATION → EVENT_GENERATION → STATE_ACCUMULATION → VALIDATION → REPORTING.

## Complexity Tracking

No constitution violations. No complexity justifications needed.
