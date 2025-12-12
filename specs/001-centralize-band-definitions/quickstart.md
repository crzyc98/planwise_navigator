# Quickstart: Centralized Band Configuration

**Feature**: 001-centralize-band-definitions
**Date**: 2025-12-12

## Overview

Age and tenure bands are now centralized in dbt seeds with reusable macros for band assignment. This guide covers how to use and modify band configurations.

## Using Band Assignment Macros

### Age Band Assignment

```sql
-- In any dbt model
SELECT
    employee_id,
    current_age,
    {{ assign_age_band('current_age') }} AS age_band
FROM {{ ref('int_employee_state') }}
```

### Tenure Band Assignment

```sql
-- In any dbt model
SELECT
    employee_id,
    years_of_service,
    {{ assign_tenure_band('years_of_service') }} AS tenure_band
FROM {{ ref('int_employee_state') }}
```

### Combined Usage

```sql
-- Common pattern in event models
SELECT
    employee_id,
    event_date,
    current_age,
    current_tenure,
    {{ assign_age_band('current_age') }} AS age_band,
    {{ assign_tenure_band('current_tenure') }} AS tenure_band
FROM {{ ref('source_model') }}
```

## Modifying Band Boundaries

### Step 1: Edit the Seed File

**Age Bands**: Edit `dbt/seeds/config_age_bands.csv`

```csv
band_id,band_label,min_value,max_value,display_order
1,< 25,0,25,1
2,25-34,25,35,2
3,35-44,35,45,3
4,45-54,45,55,4
5,55-64,55,65,5
6,65+,65,999,6
```

**Tenure Bands**: Edit `dbt/seeds/config_tenure_bands.csv`

```csv
band_id,band_label,min_value,max_value,display_order
1,< 2,0,2,1
2,2-4,2,5,2
3,5-9,5,10,3
4,10-19,10,20,4
5,20+,20,999,5
```

### Step 2: Run Seed Validation

```bash
cd dbt
dbt seed --threads 1
dbt test --select config_age_bands config_tenure_bands --threads 1
```

### Step 3: Update Hazard Multipliers (if band labels changed)

If you changed band labels, update the corresponding hazard multiplier seeds:
- `config_termination_hazard_age_multipliers.csv`
- `config_termination_hazard_tenure_multipliers.csv`
- `config_promotion_hazard_age_multipliers.csv`
- `config_promotion_hazard_tenure_multipliers.csv`

### Step 4: Rebuild Models

```bash
dbt run --threads 1
dbt test --threads 1
```

## Band Configuration Rules

### [min, max) Interval Convention

Bands use **lower bound inclusive, upper bound exclusive**:
- An employee aged exactly 35 is in the `35-44` band (not `25-34`)
- An employee with exactly 2 years tenure is in the `2-4` band (not `< 2`)

### Required Properties

1. **Contiguous**: No gaps between bands (`max_value[n] == min_value[n+1]`)
2. **Non-overlapping**: Bands must not overlap
3. **Starts at zero**: First band must have `min_value = 0`
4. **Unbounded end**: Last band should have `max_value = 999`

### Validation

The system validates band configuration at seed load time:
- Invalid configurations cause immediate pipeline abort
- Error messages identify the specific validation failure

## Common Patterns

### New Hire Tenure

New hires always have tenure band `< 2` since they start with zero tenure:

```sql
-- In hiring events, tenure band is always the first band
'< 2' AS tenure_band  -- New hires
```

### Hazard Calculation Join

```sql
-- Joining events to hazard multipliers
SELECT
    e.*,
    h.hazard_rate
FROM events e
INNER JOIN {{ ref('int_hazard_termination') }} h
    ON e.level_id = h.level_id
    AND e.age_band = h.age_band
    AND e.tenure_band = h.tenure_band
```

## Troubleshooting

### "Band configuration validation failed"

Check that your seed file:
1. Has no gaps between bands
2. Has no overlapping ranges
3. Starts at `min_value = 0`
4. Has unique `band_label` values

### "No matching band for value X"

This shouldn't happen with valid configuration. Check:
1. The value isn't negative
2. The last band has a high `max_value` (e.g., 999)

### Regression Test Failure

If event counts differ after band changes:
1. Verify band boundaries match the original values
2. Check that `band_label` values match hazard multiplier seeds
3. Run `dbt test` to validate all constraints

## Files Reference

| File | Purpose |
|------|---------|
| `dbt/seeds/config_age_bands.csv` | Age band definitions |
| `dbt/seeds/config_tenure_bands.csv` | Tenure band definitions |
| `dbt/models/staging/stg_config_age_bands.sql` | Staging model |
| `dbt/models/staging/stg_config_tenure_bands.sql` | Staging model |
| `dbt/macros/bands/assign_age_band.sql` | Age band assignment macro |
| `dbt/macros/bands/assign_tenure_band.sql` | Tenure band assignment macro |
