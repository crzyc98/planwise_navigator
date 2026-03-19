# Research: Remove Duplicate/Versioned dbt Models

**Feature Branch**: `081-remove-duplicate-dbt-models`
**Date**: 2026-03-19

## R1: Complete Inventory of Duplicate/Versioned Models

**Decision**: 7 models with `_v2` or `_optimized` suffixes identified across the codebase.

**Findings**:

| Model | Location | Status | Downstream Refs |
|-------|----------|--------|-----------------|
| `int_enrollment_events_v2` | `dbt/models/intermediate/` | UNUSED | 0 |
| `int_enrollment_events_optimized` | `dbt/models/intermediate/` | UNUSED (1 debug ref) | 1 (debug only) |
| `int_promotion_events_optimized` | `dbt/models/intermediate/events/` | UNUSED (explicitly excluded) | 0 |
| `int_deferral_rate_state_accumulator` (base) | `dbt/models/intermediate/` | SUPERSEDED by v2 | 0 |
| `int_workforce_previous_year` (base) | `dbt/models/intermediate/` | SUPERSEDED by v2 | 1 (standalone test) |
| `int_deferral_rate_state_accumulator_v2` | `dbt/models/intermediate/` | ACTIVE | 7 |
| `int_workforce_previous_year_v2` | `dbt/models/intermediate/` | ACTIVE | 1 |

**Out of Scope** (per spec assumptions):
- `int_workforce_snapshot_optimized` — actively referenced by 2 production models
- `dq_deferral_rate_state_audit_validation_v2` — actively referenced; both base and v2 serve different validation purposes

## R2: Downstream Reference Map for Active v2 Models

### `int_deferral_rate_state_accumulator_v2` → rename to `int_deferral_rate_state_accumulator`

7 downstream `ref()` calls in SQL:
1. `dbt/models/marts/fct_workforce_snapshot.sql` (line 817)
2. `dbt/models/intermediate/int_deferral_escalation_state_accumulator.sql` (line 36)
3. `dbt/models/marts/reporting/rpt_deferral_rate_regulatory_audit_summary.sql` (lines 86, 116)
4. `dbt/models/marts/data_quality/dq_deferral_rate_state_audit_validation_v2.sql` (line 35)
5. `dbt/models/marts/data_quality/dq_deferral_rate_state_audit_validation.sql` (line 69)
6. `dbt/models/intermediate/events/int_employee_contributions.sql` (line 83)
7. `dbt/models/analysis/debug_participation_pipeline.sql` (line 99)

### `int_workforce_previous_year_v2` → rename to `int_workforce_previous_year`

1 downstream `ref()` call:
1. `dbt/models/intermediate/int_year_snapshot_preparation.sql` (line 7)

## R3: Python/Orchestrator String References

Model names referenced as strings in Python files:

| File | Model Referenced | Lines |
|------|-----------------|-------|
| `planalign_orchestrator/state_accumulator/__init__.py` | `int_deferral_rate_state_accumulator_v2` | 78-83 |
| `planalign_orchestrator/model_execution_types.py` | `int_deferral_rate_state_accumulator_v2`, `int_workforce_previous_year`, `int_workforce_previous_year_v2` | 83-86 |
| `planalign_orchestrator/pipeline/workflow.py` | `int_deferral_rate_state_accumulator_v2` | 200 |
| `planalign_orchestrator/pipeline/year_executor.py` | `int_workforce_snapshot_optimized` | 579, 605 |
| `planalign_orchestrator/pipeline/event_generation_executor.py` | `int_promotion_events_optimized` (exclusion) | 263 |
| `planalign_orchestrator/init_database.py` | `int_deferral_rate_state_accumulator_v2` | 269 |
| `planalign_api/services/simulation/db_cleanup.py` | `int_deferral_rate_state_accumulator_v2` | 15 |

## R4: Schema/YAML References

| File | Models Referenced |
|------|-----------------|
| `dbt/models/intermediate/schema.yml` | `int_deferral_rate_state_accumulator` (base, line 311), `int_deferral_rate_state_accumulator_v2` (line 586), `int_workforce_previous_year` (line 1262) |
| `dbt/models/analysis/schema.yml` | `int_enrollment_events` references (lines 20, 49) |

## R5: Collateral Changes Required

### Debug Model: `debug_enrollment_event_counts.sql`
- References `int_enrollment_events_optimized` on line 49
- **Decision**: Remove the `optimized_event_counts` CTE and its usage in the validation summary (lines 43-51, 93-94) rather than removing the entire debug model, as it also validates the active `int_enrollment_events` model.

### Legacy Test: `tests/test_backward_compatibility_legacy_mode.sql`
- References `int_workforce_previous_year` (base) on lines 11, 25
- **Decision**: After renaming the v2 to drop its suffix, this test will naturally resolve to the renamed model (which was the v2). No change needed since the renamed model will have the same name `int_workforce_previous_year`.

### Event Generation Executor Exclusion
- `event_generation_executor.py` line 263 excludes `int_promotion_events_optimized`
- **Decision**: Remove the exclusion entry after the model file is deleted.

## R6: Safe Rename Strategy for dbt Models

**Decision**: Use a two-phase approach (remove unused first, then rename).

**Rationale**: Renaming `int_deferral_rate_state_accumulator_v2` to `int_deferral_rate_state_accumulator` requires the base model to be removed first, otherwise dbt will have two models with conflicting names. The same applies to `int_workforce_previous_year_v2`.

**Alternatives considered**:
- Single-phase (simultaneous remove + rename): Rejected — riskier, harder to debug if something fails.
- Keep v2 suffixes: Rejected — violates naming convention and creates permanent tech debt.
