# E096 Context

## Key Files

### Files to Modify
- `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql` - Fix event type filter

### Files to Create
- `dbt/models/analysis/debug_participation_pipeline.sql` - Debug dashboard

### Related Files (Read-Only Context)
- `dbt/models/staging/stg_census_data.sql` - Census participation source
- `dbt/models/intermediate/int_baseline_workforce.sql` - Baseline enrollment
- `dbt/models/intermediate/int_enrollment_events.sql` - Generates 'enrollment' events
- `dbt/models/intermediate/events/int_employee_contributions.sql` - Uses deferral rates
- `dbt/models/marts/fct_workforce_snapshot.sql` - Final participation status

## Data Flow
```
Census Data (employee_deferral_rate field)
    ↓
stg_census_data (sets employee_enrollment_date if deferral_rate > 0)
    ↓
int_baseline_workforce (passes through enrollment fields)
    ↓
int_enrollment_events (generates 'enrollment' events) ← CORRECT
    ↓
fct_yearly_events (stores events)
    ↓
int_deferral_rate_state_accumulator_v2 (looks for 'benefit_enrollment') ← BUG!
    ↓
int_employee_contributions (gets is_enrolled_flag=false, deferral_rate=0)
    ↓
fct_workforce_snapshot (participation_status = 'not_participating')
```

## Decisions
- Fix both event type values ('enrollment' and 'benefit_enrollment') for backward compatibility
- Create permanent debug model for future troubleshooting
