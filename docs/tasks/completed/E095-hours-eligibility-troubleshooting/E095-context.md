# E095: Context and Key Files

## Key Files

### Reference Files (Read-Only)
- `dbt/models/intermediate/int_employer_eligibility.sql` - Hours calculation logic (lines 260-288)
- `dbt/models/analysis/debug_enrollment_eligibility.sql` - Pattern to follow
- `config/simulation_config.yaml` - Configuration source (lines 326-332, 435-441)

### Files to Create/Modify
- `dbt/models/analysis/debug_hours_eligibility.sql` - New diagnostic model
- `dbt/models/analysis/schema.yml` - Add documentation

## Configuration Reference

### Match Eligibility (simulation_config.yaml lines 326-332)
```yaml
employer_match:
  eligibility:
    minimum_hours_annual: 1000
    require_active_at_year_end: true
    allow_new_hires: true
    allow_terminated_new_hires: false
```

### Core Eligibility (simulation_config.yaml lines 435-441)
```yaml
employer_core_contribution:
  eligibility:
    minimum_hours_annual: 1000
    require_active_at_year_end: true
    allow_new_hires: true
    allow_terminated_new_hires: false
```

## Hours Calculation Formula

From `int_employer_eligibility.sql` (lines 260-288):
- Full year employee: 2080 hours
- New hire: `days_from_hire_to_dec31 * (2080 / 365)`
- Terminated: `days_from_jan1_to_termination * (2080 / 365)`

## Decisions Made

1. Follow existing `debug_enrollment_eligibility.sql` pattern with SUMMARY/DETAIL rows
2. Include hours bucket distribution analysis
3. Add configuration validation (thresholds 0-2080)
4. Single model approach (no separate summary model needed)
