# Enrollment State Accumulator Usage Guide

## Overview

The `int_enrollment_state_accumulator` model is a temporal state accumulator that tracks enrollment state across simulation years without circular dependencies. This is Phase 1 of fixing the enrollment architecture where 321 employees have enrollment events but no enrollment dates in workforce snapshots.

## Model Architecture

### Key Features
- **Incremental materialization** with `unique_key=['employee_id', 'simulation_year']`
- **Temporal dependency pattern** (year N depends on year N-1, not circular)
- **Base case handling** for first simulation year using baseline workforce
- **Event-sourced state accumulation** from `fct_yearly_events`

### Dependencies
- **Input Sources:**
  - `fct_yearly_events` (current year events only)
  - `int_baseline_workforce` (first year baseline)
  - Self-reference to previous year's data (temporal dependency)
- **No Circular Dependencies:** Only uses completed data from previous years

## How It Works

### Year 1 (Base Case)
```sql
-- Uses baseline workforce + current year enrollment events
SELECT
    employee_id,
    enrollment_date,  -- From baseline or current events
    enrollment_status -- true/false based on enrollment
FROM int_baseline_workforce bl
FULL OUTER JOIN current_year_events ev
```

### Subsequent Years (Year N)
```sql
-- Uses previous year state + current year events
SELECT
    employee_id,
    enrollment_date,  -- Carry forward or update from events
    enrollment_status -- Apply current year changes
FROM int_enrollment_state_accumulator prev -- Year N-1
FULL OUTER JOIN current_year_events ev      -- Year N events
```

## Column Guide

| Column | Description | Type |
|--------|-------------|------|
| `employee_id` | Unique employee identifier | VARCHAR |
| `simulation_year` | Year for this enrollment record | INTEGER |
| `enrollment_date` | Date of first enrollment (NULL if never enrolled) | DATE |
| `enrollment_status` | Current enrollment status (true/false) | BOOLEAN |
| `years_since_first_enrollment` | Years since first enrollment | INTEGER |
| `enrollment_source` | Source of enrollment (baseline/event_YYYY/none) | VARCHAR |
| `effective_enrollment_date` | enrollment_date if enrolled, NULL otherwise | DATE |
| `is_enrolled` | Boolean flag for current enrollment status | BOOLEAN |

## Usage Examples

### 1. Get Current Year Enrollment State
```sql
SELECT
    employee_id,
    enrollment_status,
    enrollment_date,
    years_since_first_enrollment
FROM {{ ref('int_enrollment_state_accumulator') }}
WHERE simulation_year = {{ var('simulation_year') }}
```

### 2. Track Enrollment History
```sql
SELECT
    employee_id,
    simulation_year,
    enrollment_status,
    enrollment_source,
    enrollment_events_this_year
FROM {{ ref('int_enrollment_state_accumulator') }}
WHERE employee_id = 'EMP001'
ORDER BY simulation_year
```

### 3. Replace int_historical_enrollment_tracker
```sql
-- OLD (broken circular dependency):
-- FROM {{ ref('int_historical_enrollment_tracker') }}

-- NEW (temporal accumulator):
FROM {{ ref('int_enrollment_state_accumulator') }}
WHERE simulation_year = {{ var('simulation_year') }}
```

## Integration Steps

### Step 1: Update int_enrollment_events.sql
Replace the reference to `int_historical_enrollment_tracker`:
```sql
-- Change this:
FROM {{ ref('int_historical_enrollment_tracker') }}

-- To this:
FROM {{ ref('int_enrollment_state_accumulator') }}
WHERE simulation_year = {{ var('simulation_year') }}
```

### Step 2: Update fct_workforce_snapshot.sql
Replace the enrollment data source:
```sql
-- Change enrollment lookups from int_historical_enrollment_tracker
-- To use int_enrollment_state_accumulator
```

### Step 3: Run Incremental Builds
```bash
# Build for current year
dbt run --select int_enrollment_state_accumulator --vars '{"simulation_year": 2025}'

# Build for subsequent years
dbt run --select int_enrollment_state_accumulator --vars '{"simulation_year": 2026}'
```

## Validation

### Data Quality Checks
- `employee_id` and `simulation_year` uniqueness
- `enrollment_status` is always boolean
- `data_quality_flag` tracks validation status
- Event counts are non-negative

### Performance Expectations
- **Build time:** <2 minutes for 10K employees
- **Storage:** ~500KB per simulation year
- **Query performance:** <1 second for year lookups

## Troubleshooting

### Issue: "Relation not found"
**Cause:** Running before previous year is complete
**Solution:** Ensure year N-1 exists before building year N

### Issue: "No enrollment data"
**Cause:** No enrollment events in `fct_yearly_events`
**Solution:** Verify enrollment events are being generated

### Issue: "Circular dependency"
**Cause:** Model still references circular dependencies
**Solution:** Ensure all references use temporal pattern (previous year only)

## Next Steps (Phase 2)

1. **Update enrollment events model** to use this accumulator
2. **Update workforce snapshot** to get enrollment dates from accumulator
3. **Validate 321 employees** now have correct enrollment dates
4. **Performance optimization** for large datasets
5. **Historical data migration** from old tracker

This temporal accumulator pattern resolves the circular dependency issue and provides a clean foundation for enrollment state tracking across multi-year simulations.
