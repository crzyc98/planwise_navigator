# Story S039-02: Workforce Snapshot Integration

**Epic**: E039 - Employer Contribution Integration (MVP)
**Status**: 📋 Ready for Development
**Points**: 2
**Owner**: Data / Platform
**Priority**: High

---

## Story Description

**As a** financial analyst
**I want** employer contributions in the workforce snapshot
**So that** I can analyze total retirement costs in one place

## Background

The workforce snapshot currently includes employee contributions but not employer contributions (match or core). This creates fragmented analysis requiring manual joins across multiple models.

This story adds three simple columns to provide a complete view of retirement costs in the primary analytical model. Uses simple LEFT JOINs to maintain performance and reliability.

## Acceptance Criteria

### Functional Requirements
- ✅ **Three New Columns**: `employer_match_amount`, `employer_core_amount`, `total_employer_contributions`
- ✅ **Complete Coverage**: All workforce snapshot records include contribution data (with proper nulls/zeros)
- ✅ **Data Consistency**: Contribution amounts match source calculation models
- ✅ **Backward Compatibility**: Existing queries continue to work unchanged

### Technical Requirements
- ✅ **Simple LEFT JOINs**: Use existing match calculations and new core calculations
- ✅ **Null Handling**: Proper COALESCE for missing contribution data
- ✅ **Performance**: No significant impact on snapshot build time
- ✅ **Schema Tests**: Validate new columns and relationships

## Technical Design

### Workforce Snapshot Updates

#### New Columns Added
```sql
-- Add to fct_workforce_snapshot.sql
-- Employer contribution columns
employer_match_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
employer_core_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
total_employer_contributions DECIMAL(10,2) NOT NULL DEFAULT 0.00
```

#### Simple Join Pattern
```sql
-- Add these JOINs to the final SELECT in fct_workforce_snapshot.sql

-- Join with existing match calculations
LEFT JOIN {{ ref('int_employee_match_calculations') }} match
  ON base_workforce.employee_id = match.employee_id
  AND base_workforce.simulation_year = match.simulation_year

-- Join with new core calculations (from S039-01)
LEFT JOIN {{ ref('int_employer_core_contributions') }} core
  ON base_workforce.employee_id = core.employee_id
  AND base_workforce.simulation_year = core.simulation_year
```

#### New Column Selection
```sql
-- Add to final SELECT statement
-- Employer contribution data with proper null handling
COALESCE(match.employer_match_amount, 0.00) AS employer_match_amount,
COALESCE(core.employer_core_amount, 0.00) AS employer_core_amount,
COALESCE(match.employer_match_amount, 0.00) +
COALESCE(core.employer_core_amount, 0.00) AS total_employer_contributions
```

## Updated Schema

### New Columns in `fct_workforce_snapshot`
```sql
-- Employer contribution columns (added in S039-02)
employer_match_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00
  COMMENT 'Annual employer match contribution amount',

employer_core_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00
  COMMENT 'Annual employer core (non-elective) contribution amount',

total_employer_contributions DECIMAL(10,2) NOT NULL DEFAULT 0.00
  COMMENT 'Total employer contributions (match + core)'
```

## Schema Tests

```yaml
models:
  - name: fct_workforce_snapshot
    tests:
      # Existing tests preserved
      - unique:
          column_name: "concat(employee_id, '_', simulation_year)"

      # New tests for employer contributions
      - relationships:
          to: ref('int_employee_match_calculations')
          field: employee_id
          where: "employer_match_amount > 0"
      - relationships:
          to: ref('int_employer_core_contributions')
          field: employee_id
          where: "employer_core_amount > 0"

    columns:
      - name: employer_match_amount
        description: "Annual employer match contribution"
        tests:
          - not_null
          - accepted_range:
              min_value: 0
              max_value: 50000

      - name: employer_core_amount
        description: "Annual employer core contribution"
        tests:
          - not_null
          - accepted_range:
              min_value: 0
              max_value: 50000

      - name: total_employer_contributions
        description: "Total employer contributions (match + core)"
        tests:
          - not_null
          - accepted_range:
              min_value: 0
              max_value: 100000
```

## Business Logic Validation

### Consistency Tests
```sql
-- Test: Total equals sum of parts
SELECT employee_id
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = {{ var('simulation_year') }}
  AND ABS(total_employer_contributions -
           (employer_match_amount + employer_core_amount)) > 0.01
-- Should return 0 rows

-- Test: Match amounts align with match calculation model
SELECT s.employee_id
FROM {{ ref('fct_workforce_snapshot') }} s
JOIN {{ ref('int_employee_match_calculations') }} m USING (employee_id, simulation_year)
WHERE s.simulation_year = {{ var('simulation_year') }}
  AND ABS(s.employer_match_amount - m.employer_match_amount) > 0.01
-- Should return 0 rows

-- Test: Core amounts align with core calculation model
SELECT s.employee_id
FROM {{ ref('fct_workforce_snapshot') }} s
JOIN {{ ref('int_employer_core_contributions') }} c USING (employee_id, simulation_year)
WHERE s.simulation_year = {{ var('simulation_year') }}
  AND ABS(s.employer_core_amount - c.employer_core_amount) > 0.01
-- Should return 0 rows
```

## Analytics Examples

### New Analytical Capabilities
```sql
-- Total employer contribution costs by year
SELECT
  simulation_year,
  COUNT(*) AS total_employees,
  SUM(employer_match_amount) AS total_match_cost,
  SUM(employer_core_amount) AS total_core_cost,
  SUM(total_employer_contributions) AS total_employer_cost,
  AVG(total_employer_contributions) AS avg_employer_per_employee
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year BETWEEN 2025 AND 2029
GROUP BY simulation_year
ORDER BY simulation_year;

-- Complete retirement cost analysis
SELECT
  level_id,
  COUNT(*) AS employees,
  AVG(employee_gross_compensation) AS avg_salary,
  AVG(annual_contribution_amount) AS avg_employee_deferrals,
  AVG(employer_match_amount) AS avg_employer_match,
  AVG(employer_core_amount) AS avg_employer_core,
  AVG(total_employer_contributions) AS avg_total_employer,
  AVG(annual_contribution_amount + total_employer_contributions) AS avg_total_retirement
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = 2025
  AND employment_status = 'active'
GROUP BY level_id
ORDER BY level_id;
```

## Performance Considerations

### Simple Optimization
- **LEFT JOIN Strategy**: Preserves all workforce records, handles missing data gracefully
- **Indexed Joins**: Uses existing composite keys `(employee_id, simulation_year)`
- **Early Filtering**: Apply simulation_year filters in join conditions
- **No Aggregation**: Simple column selection, no complex calculations

### Expected Performance Impact
- **Build Time**: <10% increase (from ~45s to ~50s for 100K employees)
- **Memory Usage**: Minimal increase due to simple LEFT JOINs
- **Query Performance**: New columns available for analytics without additional joins

## Integration Points

### Upstream Dependencies
- `int_employee_match_calculations` - Existing match calculation system
- `int_employer_core_contributions` - New core calculations (from S039-01)
- Existing `fct_workforce_snapshot` - Base workforce data

### Downstream Impact
- Analytics queries can now get complete retirement cost data from single model
- Dashboards can show total compensation including employer contributions
- Cost modeling gets complete picture without manual joins

## Migration Strategy

### Backward Compatibility
- **Existing Columns**: All preserved with identical names and types
- **Existing Queries**: Continue to work without modification
- **New Columns**: Default to 0, so no NULL issues
- **Incremental Safety**: Can rebuild single year if issues arise

### Rollout Plan
1. **Update model** with new JOINs and columns
2. **Run tests** to validate data consistency
3. **Test analytics** to verify new capabilities work
4. **Document changes** for analyst team

## Edge Cases

1. **Missing match data**: LEFT JOIN + COALESCE handles gracefully (results in $0)
2. **Missing core data**: LEFT JOIN + COALESCE handles gracefully (results in $0)
3. **Both missing**: Results in $0 for all employer contribution columns
4. **Performance**: Simple joins scale linearly with workforce size

## Delivery Checklist

- [ ] Add LEFT JOINs to `fct_workforce_snapshot.sql`
- [ ] Add three new columns with proper COALESCE
- [ ] Update schema tests for new columns
- [ ] Create business logic validation queries
- [ ] Test with sample data to verify calculations
- [ ] Verify existing queries still work
- [ ] Run performance test (build time impact)

## Success Criteria

### Technical Success
- ✅ All workforce snapshot records include employer contribution data
- ✅ Data consistency tests pass
- ✅ Performance impact <10% (build time under 60 seconds)
- ✅ All existing functionality preserved

### Business Success
- ✅ Analysts can generate complete retirement cost reports from single model
- ✅ Total employer contribution costs visible in primary analytical model
- ✅ Foundation for enhanced analytics and dashboards
- ✅ Complete compensation view (salary + employee + employer contributions)

## Future Enhancements (E040)

This foundation enables future enhancements:
- Additional analytical columns (participation rates, etc.)
- Performance optimizations with pre-aggregation
- Enhanced cost modeling with projections
- Integration with budget planning tools

---

**Dependencies**: Requires S039-01 (Basic Employer Contributions) to be completed first
