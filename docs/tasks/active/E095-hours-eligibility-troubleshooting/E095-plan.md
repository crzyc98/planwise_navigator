# E095: Hours Worked DC Plan Troubleshooting Feature

## Overview

Create a diagnostic feature to troubleshoot hours worked requirements for DC plan match and core contribution eligibility.

## Problem

Currently there is no easy way to:
1. See WHY employees fail/pass hours eligibility checks
2. View the step-by-step hours calculation breakdown
3. Get aggregate statistics on hours eligibility patterns
4. Validate configuration is working correctly

## Solution

Create a dbt diagnostic model `debug_hours_eligibility.sql` following the existing `debug_enrollment_eligibility.sql` pattern.

### Files to Create/Modify

| File | Purpose |
|------|---------|
| `dbt/models/analysis/debug_hours_eligibility.sql` | Detailed per-employee hours calculation breakdown |
| `dbt/models/analysis/schema.yml` | Add documentation for new model |

### Model Output

**Record Types:**
- `SUMMARY` - Aggregate statistics
- `CONFIG` - Configuration validation
- `HOURS_BUCKET` - Distribution by hours worked buckets
- `DETAIL` - Per-employee breakdown

**Key Columns:**
- Hours calculation breakdown (days employed, calculated hours)
- Eligibility thresholds from configuration
- Step-by-step eligibility flags
- Reason codes for failures

## Usage

```bash
# Build diagnostic model
cd dbt
dbt run --select debug_hours_eligibility --vars "simulation_year: 2025"

# View summary
duckdb simulation.duckdb "SELECT * FROM debug_hours_eligibility WHERE record_type = 'SUMMARY'"
```

## Dependencies

- `int_employer_eligibility.sql` - Primary source
- `int_employee_compensation_by_year.sql` - Employee base data
