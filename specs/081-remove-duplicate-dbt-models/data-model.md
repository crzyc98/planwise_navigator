# Data Model: Remove Duplicate/Versioned dbt Models

**Feature Branch**: `081-remove-duplicate-dbt-models`
**Date**: 2026-03-19

## Entities

This feature involves no new entities. It is a cleanup/refactoring of existing dbt model files.

## File Removals (5 models)

| File to Remove | Reason |
|----------------|--------|
| `dbt/models/intermediate/int_enrollment_events_v2.sql` | Zero downstream refs |
| `dbt/models/intermediate/int_enrollment_events_optimized.sql` | Only debug ref; superseded |
| `dbt/models/intermediate/events/int_promotion_events_optimized.sql` | Zero refs; explicitly excluded from pipeline |
| `dbt/models/intermediate/int_deferral_rate_state_accumulator.sql` | Superseded by v2 (0 downstream refs) |
| `dbt/models/intermediate/int_workforce_previous_year.sql` | Superseded by v2 (test resolves naturally after rename) |

## File Renames (2 models)

| Current Name | New Name | Downstream Updates Required |
|-------------|----------|---------------------------|
| `int_deferral_rate_state_accumulator_v2.sql` | `int_deferral_rate_state_accumulator.sql` | 7 SQL `ref()` calls + 4 Python files + 1 schema.yml |
| `int_workforce_previous_year_v2.sql` | `int_workforce_previous_year.sql` | 1 SQL `ref()` call + 1 Python file + 1 schema.yml |

## Reference Update Matrix

### SQL `ref()` Updates (for `int_deferral_rate_state_accumulator_v2` → `int_deferral_rate_state_accumulator`)

| File | Change |
|------|--------|
| `fct_workforce_snapshot.sql` | `ref('int_deferral_rate_state_accumulator_v2')` → `ref('int_deferral_rate_state_accumulator')` |
| `int_deferral_escalation_state_accumulator.sql` | Same pattern |
| `rpt_deferral_rate_regulatory_audit_summary.sql` | Same pattern (2 occurrences) |
| `dq_deferral_rate_state_audit_validation_v2.sql` | Same pattern |
| `dq_deferral_rate_state_audit_validation.sql` | Same pattern |
| `int_employee_contributions.sql` | Same pattern |
| `debug_participation_pipeline.sql` | Same pattern |

### SQL `ref()` Updates (for `int_workforce_previous_year_v2` → `int_workforce_previous_year`)

| File | Change |
|------|--------|
| `int_year_snapshot_preparation.sql` | `ref('int_workforce_previous_year_v2')` → `ref('int_workforce_previous_year')` |

### Python String Updates

| File | Old String | New String |
|------|-----------|------------|
| `state_accumulator/__init__.py` | `"int_deferral_rate_state_accumulator_v2"` | `"int_deferral_rate_state_accumulator"` |
| `model_execution_types.py` | `"int_deferral_rate_state_accumulator_v2"`, `"int_workforce_previous_year_v2"` | Drop `_v2` suffix; remove base `"int_workforce_previous_year"` entry if separate |
| `pipeline/workflow.py` | `"int_deferral_rate_state_accumulator_v2"` | `"int_deferral_rate_state_accumulator"` |
| `pipeline/event_generation_executor.py` | `"int_promotion_events_optimized"` exclusion | Remove the exclusion entry entirely |
| `init_database.py` | `"int_deferral_rate_state_accumulator_v2"` | `"int_deferral_rate_state_accumulator"` |
| `planalign_api/services/simulation/db_cleanup.py` | `"int_deferral_rate_state_accumulator_v2"` | `"int_deferral_rate_state_accumulator"` |

### Schema YAML Updates

| File | Change |
|------|--------|
| `dbt/models/intermediate/schema.yml` | Remove model entry for base `int_deferral_rate_state_accumulator`; rename v2 entry to drop suffix; remove base `int_workforce_previous_year` entry; rename v2 entry |

### Collateral File Updates

| File | Change |
|------|--------|
| `dbt/models/analysis/debug_enrollment_event_counts.sql` | Remove `optimized_event_counts` CTE and references |
| `dbt/CLAUDE.md` | Update stage 4 reference from `int_deferral_rate_state_accumulator_v2` to `int_deferral_rate_state_accumulator` |

## Validation Rules

- **Pre-condition**: `dbt build --threads 1 --fail-fast` passes before any changes
- **Post-phase-1**: `dbt build --threads 1 --fail-fast` passes after removing unused models
- **Post-phase-2**: `dbt build --threads 1 --fail-fast` passes after renaming active models
- **Final**: Single-year simulation produces identical output (row counts and checksums)
