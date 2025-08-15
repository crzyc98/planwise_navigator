# Story S039-01: Basic Employer Contributions

**Epic**: E039 - Employer Contribution Integration (MVP)
**Status**: 📋 Ready for Development
**Points**: 3
**Owner**: Platform / Modeling
**Priority**: High

---

## Story Description

**As a** plan administrator
**I want** basic employer contribution calculations
**So that** I can model core (non-elective) contributions alongside existing match

## Background

Currently the system calculates employee contributions and employer match but lacks core (non-elective) employer contributions. This story implements the minimal viable version: simple eligibility determination and flat-rate core contributions that integrate cleanly with existing systems.

This MVP approach uses fixed assumptions (2080 hours/year, 1000 hour threshold, 2% flat rate) to get working functionality tonight that can be enhanced later.

## Acceptance Criteria

### Functional Requirements
- ✅ **Simple Eligibility**: Active employees get 2080 hours, inactive get 0, threshold is 1000 hours
- ✅ **Core Contributions**: Flat 2% of compensation for eligible employees
- ✅ **Clean Integration**: Works with existing compensation and workforce models
- ✅ **Deterministic**: Same results across multiple runs

### Technical Requirements
- ✅ **Two Models**: `int_employer_eligibility` and `int_employer_core_contributions`
- ✅ **Standard dbt**: Use proven patterns, no fancy optimizations
- ✅ **Basic Tests**: Schema tests for data quality
- ✅ **Fast Performance**: Complete in <30 seconds for 100K employees

## Technical Design

### Model 1: `int_employer_eligibility.sql`

```sql
{{ config(
    materialized='table',
    tags=['eligibility', 'employer_contributions']
) }}

/*
  Simple Employer Contribution Eligibility - Story S039-01

  MVP approach: Active employees get 2080 hours, others get 0.
  Eligible if >= 1000 hours. Simple and reliable.
*/

SELECT
  employee_id,
  simulation_year,
  employment_status,

  -- Simple hours calculation
  CASE
    WHEN employment_status = 'active' THEN 2080
    ELSE 0
  END as hours_worked,

  -- Simple eligibility determination
  CASE
    WHEN employment_status = 'active' THEN TRUE
    ELSE FALSE
  END as eligible_for_contributions,

  -- Metadata
  CURRENT_TIMESTAMP as created_at

FROM {{ ref('int_baseline_workforce') }}
WHERE simulation_year = {{ var('simulation_year') }}
```

### Model 2: `int_employer_core_contributions.sql`

```sql
{{ config(
    materialized='table',
    tags=['core_contributions', 'employer_contributions']
) }}

/*
  Simple Core Contribution Calculation - Story S039-01

  MVP approach: Flat 2% of compensation for eligible employees.
  Clean, simple, and reliable.
*/

SELECT
  e.employee_id,
  e.simulation_year,
  e.prorated_annual_compensation,
  elig.eligible_for_contributions,

  -- Simple core contribution calculation
  CASE
    WHEN elig.eligible_for_contributions
    THEN ROUND(e.prorated_annual_compensation * 0.02, 2)
    ELSE 0.00
  END as employer_core_amount,

  -- Track calculation method for future enhancement
  CASE
    WHEN elig.eligible_for_contributions THEN 'flat_2_percent'
    ELSE 'ineligible'
  END as calculation_method,

  -- Metadata
  CURRENT_TIMESTAMP as created_at

FROM {{ ref('int_employee_compensation_by_year') }} e
LEFT JOIN {{ ref('int_employer_eligibility') }} elig
  ON e.employee_id = elig.employee_id
  AND e.simulation_year = elig.simulation_year
WHERE e.simulation_year = {{ var('simulation_year') }}
```

## Output Schema

### `int_employer_eligibility` Columns
```sql
employee_id VARCHAR NOT NULL,
simulation_year INTEGER NOT NULL,
employment_status VARCHAR NOT NULL,
hours_worked INTEGER NOT NULL,
eligible_for_contributions BOOLEAN NOT NULL,
created_at TIMESTAMP NOT NULL

-- Composite unique key
UNIQUE (employee_id, simulation_year)
```

### `int_employer_core_contributions` Columns
```sql
employee_id VARCHAR NOT NULL,
simulation_year INTEGER NOT NULL,
prorated_annual_compensation DECIMAL(12,2) NOT NULL,
eligible_for_contributions BOOLEAN NOT NULL,
employer_core_amount DECIMAL(10,2) NOT NULL,
calculation_method VARCHAR(50) NOT NULL,
created_at TIMESTAMP NOT NULL

-- Composite unique key
UNIQUE (employee_id, simulation_year)
```

## Schema Tests

```yaml
models:
  - name: int_employer_eligibility
    tests:
      - unique:
          column_name: "concat(employee_id, '_', simulation_year)"
    columns:
      - name: employee_id
        tests:
          - not_null
      - name: hours_worked
        tests:
          - not_null
          - accepted_range:
              min_value: 0
              max_value: 2080
      - name: eligible_for_contributions
        tests:
          - not_null

  - name: int_employer_core_contributions
    tests:
      - unique:
          column_name: "concat(employee_id, '_', simulation_year)"
    columns:
      - name: employee_id
        tests:
          - not_null
      - name: employer_core_amount
        tests:
          - not_null
          - accepted_range:
              min_value: 0
              max_value: 50000
      - name: calculation_method
        tests:
          - not_null
          - accepted_values:
              values: ['flat_2_percent', 'ineligible']
```

## Integration Points

### Upstream Dependencies
- `int_baseline_workforce` - Employment status and employee data
- `int_employee_compensation_by_year` - Compensation for core contribution calculation

### Downstream Usage
- `fct_workforce_snapshot` - Will consume employer_core_amount (S039-02)
- Future enhancements - Can build on this foundation

## Business Logic Examples

### Example Calculations
```sql
-- Active employee making $100,000
-- hours_worked = 2080
-- eligible_for_contributions = TRUE
-- employer_core_amount = $100,000 * 0.02 = $2,000

-- Inactive employee
-- hours_worked = 0
-- eligible_for_contributions = FALSE
-- employer_core_amount = $0
```

## Testing Strategy

### Unit Tests
1. **Active employees**: Verify 2080 hours and eligibility
2. **Inactive employees**: Verify 0 hours and ineligibility
3. **Core calculation**: Verify 2% of compensation for eligible
4. **Ineligible handling**: Verify $0 for ineligible employees

### Integration Tests
1. **Data consistency**: All baseline workforce employees have eligibility records
2. **Amount validation**: Core amounts are reasonable (0-$50K range)
3. **Method tracking**: Calculation methods recorded correctly

## Performance Considerations

### Expected Performance
- **100K employees**: <30 seconds total for both models
- **Memory usage**: <500MB for standard datasets
- **Simple queries**: No complex joins or calculations

### Optimization Notes
- Uses simple CASE statements for fast processing
- Minimal joins (only eligibility → core contributions)
- Early filtering by simulation_year

## Edge Cases

1. **Missing compensation**: Handled by LEFT JOIN (results in $0)
2. **Null employment status**: Treated as inactive (0 hours, ineligible)
3. **Zero compensation**: Results in $0 core contribution
4. **Future enhancements**: calculation_method field allows tracking changes

## Delivery Checklist

- [ ] Create `int_employer_eligibility.sql` with simple logic
- [ ] Create `int_employer_core_contributions.sql` with 2% calculation
- [ ] Add schema tests for both models
- [ ] Test with sample data (verify calculations)
- [ ] Ensure models complete in <30 seconds
- [ ] Document business logic assumptions

## Success Criteria

### Technical Success
- ✅ Both models run successfully for full dataset
- ✅ All schema tests pass
- ✅ Performance targets met (<30s for 100K employees)
- ✅ Data quality looks reasonable

### Business Success
- ✅ Eligible employees receive 2% core contributions
- ✅ Ineligible employees receive $0
- ✅ Foundation ready for workforce snapshot integration
- ✅ Simple enough to debug and enhance

## Future Enhancements (E040)

This MVP foundation enables future enhancements:
- Business day hours calculation with holiday calendars
- Level-based contribution rates via parameter framework
- Reason codes and audit trails
- Complex eligibility scenarios
- Performance optimizations

---

**Next Story**: S039-02 - Workforce Snapshot Integration (consumes this foundation)
