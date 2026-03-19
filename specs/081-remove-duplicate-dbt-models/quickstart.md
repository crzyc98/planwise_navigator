# Quickstart: Remove Duplicate/Versioned dbt Models

**Branch**: `081-remove-duplicate-dbt-models`

## What This Feature Does

Removes 5 unused/superseded dbt model files and renames 2 active `_v2` models to their canonical names. Pure cleanup — no business logic changes.

## Implementation Phases

### Phase 1: Remove Unused Models (P1)
1. Delete 5 unused `.sql` files
2. Update `debug_enrollment_event_counts.sql` to remove optimized CTE
3. Remove `int_promotion_events_optimized` exclusion from Python executor
4. Remove schema.yml entries for deleted models
5. Verify: `cd dbt && dbt build --threads 1 --fail-fast`

### Phase 2: Rename Active v2 Models (P2)
1. Rename `int_deferral_rate_state_accumulator_v2.sql` → `int_deferral_rate_state_accumulator.sql`
2. Rename `int_workforce_previous_year_v2.sql` → `int_workforce_previous_year.sql`
3. Update all 8 SQL `ref()` calls
4. Update all 6 Python string references
5. Update schema.yml entries
6. Verify: `cd dbt && dbt build --threads 1 --fail-fast`

### Phase 3: Validate Output Consistency (P3)
1. Run simulation before and after, compare outputs

## Key Files

- **Models to delete**: `dbt/models/intermediate/` (3 files) + `dbt/models/intermediate/events/` (1 file) + 1 base model
- **Models to rename**: 2 files in `dbt/models/intermediate/`
- **Python updates**: `planalign_orchestrator/` (5 files) + `planalign_api/` (1 file)
- **Schema updates**: `dbt/models/intermediate/schema.yml`

## Verification

```bash
# After each phase
cd dbt && dbt build --threads 1 --fail-fast

# Final validation
grep -r "_v2\|_optimized" dbt/models/intermediate/ --include="*.sql" -l
# Expected: 0 results (except int_workforce_snapshot_optimized which is out of scope)
```
