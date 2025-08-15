# Story S040-03: Enhanced Workforce Analytics

**Epic**: E040 - Employer Contribution Enhancements
**Status**: 📋 Future Enhancement
**Points**: 4
**Owner**: Data / Platform
**Priority**: Medium (After MVP)
**Prerequisites**: E039 - Employer Contribution Integration (MVP)

---

## Story Description

**As a** financial analyst
**I want** core contributions in the workforce snapshot
**So that** I can calculate total employer retirement costs and complete compensation packages

## Background

Building on S039-04 (Match Integration), this story completes the employer contribution integration by adding core (non-elective) contributions to the workforce snapshot. Core contributions are:

- **Independent of employee behavior**: Not tied to employee deferrals like match
- **Plan sponsor driven**: Employer decides contribution amounts/rates
- **Often significant costs**: Can represent 1-5% of total payroll
- **Required for complete modeling**: Essential for accurate cost projections

With both match and core contributions integrated, the workforce snapshot becomes the comprehensive source for all retirement plan costs and total compensation analysis.

## Acceptance Criteria

### Functional Requirements
- ✅ **Core Amount Integration**: Add `employer_core_amount` column to workforce snapshot
- ✅ **Eligibility Flag Integration**: Add `core_eligible_flag` column
- ✅ **Total Employer Contributions**: Add `total_employer_contributions` summary column
- ✅ **Complete Cost View**: Total plan contributions (employee + employer) with `total_plan_contributions` column
- ✅ **Data Consistency**: Core amounts align with core calculation model

### Technical Requirements
- ✅ **Efficient Integration**: Build on existing match integration pattern
- ✅ **Performance Optimization**: Minimize additional join overhead
- ✅ **Index Strategy**: Support analytical queries on contribution data
- ✅ **Incremental Compatibility**: Maintain existing incremental strategy
- ✅ **Schema Tests**: Comprehensive validation of new columns

### Business Requirements
- ✅ **Complete Cost Model**: All employer retirement costs in single view
- ✅ **Analytical Power**: Enable comprehensive cost analysis and projections
- ✅ **Budget Integration**: Support annual budgeting and forecasting
- ✅ **Audit Readiness**: Complete audit trail through to source calculations

## Technical Design

### Workforce Snapshot Extensions

#### Additional New Columns
```sql
-- Add to fct_workforce_snapshot.sql (building on S039-04)
-- Core contribution data
employer_core_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
core_eligible_flag BOOLEAN NOT NULL DEFAULT FALSE,
core_rate_applied DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
core_percentage_of_comp DECIMAL(6,4) NOT NULL DEFAULT 0.0000,

-- Summary columns
total_employer_contributions DECIMAL(10,2) NOT NULL DEFAULT 0.00,
total_plan_contributions DECIMAL(10,2) NOT NULL DEFAULT 0.00,
employer_contribution_rate DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
```

#### Integration Join Pattern
```sql
-- Core contribution data join
core_data AS (
  SELECT
    employee_id,
    simulation_year,
    core_contribution_amount AS employer_core_amount,
    core_rate AS core_rate_applied,
    CASE
      WHEN eligible_compensation > 0
      THEN core_contribution_amount / eligible_compensation
      ELSE 0
    END AS core_percentage_of_comp
  FROM {{ ref('int_employee_core_contributions') }}
  WHERE simulation_year = {{ simulation_year }}
),

-- Enhanced eligibility data (from S039-02)
eligibility_enhanced AS (
  SELECT
    employee_id,
    simulation_year,
    eligible_for_match AS match_eligible_flag,
    eligible_for_core AS core_eligible_flag
  FROM {{ ref('int_employer_contribution_eligibility') }}
  WHERE simulation_year = {{ simulation_year }}
),
```

#### Final Selection with Complete Integration
```sql
SELECT
  -- Existing workforce snapshot columns (including match from S039-04)
  base.*,

  -- Core contribution integration
  COALESCE(core.employer_core_amount, 0.00) AS employer_core_amount,
  COALESCE(eligibility.core_eligible_flag, FALSE) AS core_eligible_flag,
  COALESCE(core.core_rate_applied, 0.0000) AS core_rate_applied,
  COALESCE(core.core_percentage_of_comp, 0.0000) AS core_percentage_of_comp,

  -- Summary calculations
  (COALESCE(base.employer_match_amount, 0) +
   COALESCE(core.employer_core_amount, 0)) AS total_employer_contributions,

  -- Complete total plan contributions (employee + all employer)
  (COALESCE(base.annual_contribution_amount, 0) +
   COALESCE(match.employer_match_amount, 0) +
   COALESCE(core.employer_core_amount, 0)) AS total_plan_contributions,

  -- Enhanced analytical columns
  (base.employee_gross_compensation +
   COALESCE(base.annual_contribution_amount, 0) +
   COALESCE(match.employer_match_amount, 0) +
   COALESCE(core.employer_core_amount, 0)) AS total_retirement_compensation,

  CASE WHEN COALESCE(base.annual_contribution_amount, 0) > 0
            OR COALESCE(match.employer_match_amount, 0) > 0
            OR COALESCE(core.employer_core_amount, 0) > 0
       THEN TRUE ELSE FALSE END AS plan_participation_flag,

  -- Employer contribution rate (% of compensation)
  CASE
    WHEN base.employee_gross_compensation > 0
    THEN (COALESCE(base.employer_match_amount, 0) +
          COALESCE(core.employer_core_amount, 0)) / base.employee_gross_compensation
    ELSE 0
  END AS employer_contribution_rate

FROM base_workforce_final base
LEFT JOIN match_data match
  ON base.employee_id = match.employee_id
  AND base.simulation_year = match.simulation_year
LEFT JOIN core_data core
  ON base.employee_id = core.employee_id
  AND base.simulation_year = core.simulation_year
LEFT JOIN eligibility_enhanced eligibility
  ON base.employee_id = eligibility.employee_id
  AND base.simulation_year = eligibility.simulation_year
```

## Complete Schema Update

### Final Column Set for Employer Contributions
```sql
-- Complete employer contribution columns in fct_workforce_snapshot
-- (includes both S039-04 match and S039-05 core integration)

-- Employer match contributions (from S039-04)
employer_match_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00
  COMMENT 'Annual employer match contribution amount',
match_eligible_flag BOOLEAN NOT NULL DEFAULT FALSE
  COMMENT 'Employee meets match eligibility requirements',
effective_match_rate DECIMAL(6,4) NOT NULL DEFAULT 0.0000
  COMMENT 'Actual match rate received (match amount / deferrals)',
match_percentage_of_comp DECIMAL(6,4) NOT NULL DEFAULT 0.0000
  COMMENT 'Match as percentage of total compensation',
match_formula_used VARCHAR(50)
  COMMENT 'Match formula applied',

-- Employer core contributions (new in S039-05)
employer_core_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00
  COMMENT 'Annual employer core (non-elective) contribution amount',
core_eligible_flag BOOLEAN NOT NULL DEFAULT FALSE
  COMMENT 'Employee meets core contribution eligibility requirements',
core_rate_applied DECIMAL(6,4) NOT NULL DEFAULT 0.0000
  COMMENT 'Core contribution rate applied to compensation',
core_percentage_of_comp DECIMAL(6,4) NOT NULL DEFAULT 0.0000
  COMMENT 'Core contributions as percentage of compensation',

-- Summary totals (new in S039-05)
total_employer_contributions DECIMAL(10,2) NOT NULL DEFAULT 0.00
  COMMENT 'Total employer contributions (match + core)',
total_plan_contributions DECIMAL(10,2) NOT NULL DEFAULT 0.00
  COMMENT 'Total plan contributions (employee + employer)',
employer_contribution_rate DECIMAL(6,4) NOT NULL DEFAULT 0.0000
  COMMENT 'Total employer contributions as % of compensation',

-- Enhanced convenience totals
total_retirement_compensation DECIMAL(12,2) NOT NULL DEFAULT 0.00
  COMMENT 'Base salary + total retirement contributions',
plan_participation_flag BOOLEAN NOT NULL DEFAULT FALSE
  COMMENT 'Employee participates in any retirement plan component'
```

### Index Strategy Update
```sql
{{ config(
    indexes=[
        -- Existing indexes
        {'columns': ['simulation_year', 'employee_id'], 'type': 'btree', 'unique': true},
        {'columns': ['level_id', 'simulation_year'], 'type': 'btree'},
        {'columns': ['employment_status', 'simulation_year'], 'type': 'btree'},

        -- Match analysis indexes (from S039-04)
        {'columns': ['match_eligible_flag', 'simulation_year'], 'type': 'btree'},
        {'columns': ['employer_match_amount'], 'type': 'btree'},

        -- Core contribution analysis indexes (new)
        {'columns': ['core_eligible_flag', 'simulation_year'], 'type': 'btree'},
        {'columns': ['employer_core_amount'], 'type': 'btree'},

        -- Total contribution analysis indexes
        {'columns': ['total_employer_contributions'], 'type': 'btree'},
        {'columns': ['total_plan_contributions'], 'type': 'btree'},
        {'columns': ['employer_contribution_rate', 'simulation_year'], 'type': 'btree'}
    ]
) }}
```

## Performance Considerations

### Pre-Aggregation Join Optimization Strategy
```sql
-- Pre-aggregated join pattern combining match and core data
WITH employer_contributions_aggregated AS (
  -- Single CTE combining match and core with pre-computed analytics
  SELECT
    COALESCE(m.employee_id, c.employee_id) AS employee_id,
    COALESCE(m.simulation_year, c.simulation_year) AS simulation_year,

    -- Match data (pre-rounded for performance)
    ROUND(COALESCE(m.employer_match_amount, 0), 2) AS employer_match_amount,
    m.effective_match_rate,
    m.match_percentage_of_comp,
    m.formula_id AS match_formula_used,

    -- Core data (pre-rounded for performance)
    ROUND(COALESCE(c.employer_core_amount, 0), 2) AS employer_core_amount,
    c.core_rate_applied,
    c.core_percentage_of_comp,

    -- Pre-aggregate totals to reduce downstream calculation overhead
    ROUND(COALESCE(m.employer_match_amount, 0) +
          COALESCE(c.employer_core_amount, 0), 2) AS total_employer_contributions,

    -- Pre-compute participation flags for analytics
    CASE WHEN COALESCE(m.employer_match_amount, 0) > 0
              OR COALESCE(c.employer_core_amount, 0) > 0
         THEN TRUE ELSE FALSE END AS has_employer_contributions

  FROM {{ ref('int_employee_match_calculations') }} m
  FULL OUTER JOIN {{ ref('int_employee_core_contributions') }} c
    ON m.employee_id = c.employee_id
    AND m.simulation_year = c.simulation_year
  WHERE COALESCE(m.simulation_year, c.simulation_year) = {{ var('simulation_year') }}
)
```

### Expected Performance Impact
- **Build Time**: <10% additional increase (total <25% vs original)
- **Memory Usage**: Minimal increase due to efficient FULL OUTER JOIN pattern
- **Query Performance**: Enhanced indexes support comprehensive analytics
- **Scalability**: Maintains sub-linear scaling for larger datasets

## Advanced Analytics Examples

### Complete Cost Analysis
```sql
-- Comprehensive employer contribution cost analysis
SELECT
  simulation_year,

  -- Participation metrics
  COUNT(*) AS total_employees,
  COUNT(CASE WHEN match_eligible_flag THEN 1 END) AS match_eligible,
  COUNT(CASE WHEN core_eligible_flag THEN 1 END) AS core_eligible,
  COUNT(CASE WHEN employer_match_amount > 0 THEN 1 END) AS receiving_match,
  COUNT(CASE WHEN employer_core_amount > 0 THEN 1 END) AS receiving_core,

  -- Cost totals
  SUM(employer_match_amount) AS total_match_cost,
  SUM(employer_core_amount) AS total_core_cost,
  SUM(total_employer_contributions) AS total_employer_cost,

  -- Cost percentages
  AVG(match_percentage_of_comp) AS avg_match_rate,
  AVG(core_percentage_of_comp) AS avg_core_rate,
  AVG(employer_contribution_rate) AS avg_total_employer_rate,

  -- Cost per participant
  AVG(CASE WHEN employer_match_amount > 0 THEN employer_match_amount END) AS avg_match_per_recipient,
  AVG(CASE WHEN employer_core_amount > 0 THEN employer_core_amount END) AS avg_core_per_recipient

FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year BETWEEN 2025 AND 2029
GROUP BY simulation_year
ORDER BY simulation_year;
```

### Total Compensation Analysis
```sql
-- Complete total compensation view
SELECT
  level_id,
  COUNT(*) AS employees,

  -- Base compensation
  AVG(employee_gross_compensation) AS avg_base_salary,

  -- Employee contributions
  AVG(annual_contribution_amount) AS avg_employee_deferrals,
  AVG(COALESCE(annual_contribution_amount, 0) /
      NULLIF(employee_gross_compensation, 0)) AS avg_deferral_rate,

  -- Employer contributions
  AVG(employer_match_amount) AS avg_employer_match,
  AVG(employer_core_amount) AS avg_employer_core,
  AVG(total_employer_contributions) AS avg_total_employer,

  -- Total retirement
  AVG(total_plan_contributions) AS avg_total_retirement,
  AVG(total_plan_contributions / NULLIF(employee_gross_compensation, 0)) AS avg_retirement_rate,

  -- Total compensation
  AVG(employee_gross_compensation + total_plan_contributions) AS avg_total_comp

FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = 2025
  AND employment_status = 'active'
GROUP BY level_id
ORDER BY level_id;
```

### Cost Projection Analysis
```sql
-- Multi-year cost projection and growth analysis
WITH yearly_costs AS (
  SELECT
    simulation_year,
    SUM(employee_gross_compensation) AS total_payroll,
    SUM(annual_contribution_amount) AS total_employee_deferrals,
    SUM(employer_match_amount) AS total_match_cost,
    SUM(employer_core_amount) AS total_core_cost,
    SUM(total_employer_contributions) AS total_employer_cost,
    SUM(total_plan_contributions) AS total_plan_cost
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year BETWEEN 2025 AND 2029
    AND employment_status = 'active'
  GROUP BY simulation_year
)
SELECT
  simulation_year,
  total_payroll,
  total_employer_cost,
  total_plan_cost,

  -- Cost as % of payroll
  ROUND(total_employer_cost / total_payroll * 100, 2) AS employer_cost_pct_payroll,
  ROUND(total_plan_cost / total_payroll * 100, 2) AS total_plan_cost_pct_payroll,

  -- Year-over-year growth
  ROUND((total_employer_cost / LAG(total_employer_cost) OVER (ORDER BY simulation_year) - 1) * 100, 2) AS employer_cost_growth_pct,
  ROUND((total_plan_cost / LAG(total_plan_cost) OVER (ORDER BY simulation_year) - 1) * 100, 2) AS plan_cost_growth_pct

FROM yearly_costs
ORDER BY simulation_year;
```

## Testing Strategy

### Data Quality Tests
```yaml
models:
  - name: fct_workforce_snapshot
    tests:
      # Core contribution specific tests
      - relationships:
          to: ref('int_employee_core_contributions')
          field: employee_id
          where: "employer_core_amount > 0"

    columns:
      - name: employer_core_amount
        description: "Annual employer core contribution amount"
        tests:
          - not_null
          - accepted_range:
              min_value: 0
              max_value: 100000

      - name: total_employer_contributions
        description: "Total employer contributions (match + core)"
        tests:
          - not_null
          - accepted_range:
              min_value: 0
              max_value: 150000

      - name: total_plan_contributions
        description: "Total plan contributions (employee + employer)"
        tests:
          - not_null
          - accepted_range:
              min_value: 0
              max_value: 200000
```

### Business Logic Tests
```sql
-- Test: Total employer contributions = match + core
SELECT employee_id
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = {{ var('simulation_year') }}
  AND ABS(total_employer_contributions -
           (employer_match_amount + employer_core_amount)) > 0.01
-- Should return 0 rows

-- Test: Total plan contributions = employee + employer
SELECT employee_id
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = {{ var('simulation_year') }}
  AND ABS(total_plan_contributions -
           (COALESCE(annual_contribution_amount, 0) + total_employer_contributions)) > 0.01
-- Should return 0 rows

-- Test: Core amounts match calculation model
WITH snapshot_core AS (
  SELECT employee_id, simulation_year, employer_core_amount
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employer_core_amount > 0
),
calc_core AS (
  SELECT employee_id, simulation_year, core_contribution_amount
  FROM {{ ref('int_employee_core_contributions') }}
  WHERE simulation_year = {{ var('simulation_year') }}
)
SELECT s.employee_id
FROM snapshot_core s
JOIN calc_core c USING (employee_id, simulation_year)
WHERE ABS(s.employer_core_amount - c.core_contribution_amount) > 0.01
-- Should return 0 rows

-- Test: Only eligible employees have core amounts > 0
SELECT employee_id
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = {{ var('simulation_year') }}
  AND employer_core_amount > 0
  AND core_eligible_flag = FALSE
-- Should return 0 rows
```

### Integration Tests
```sql
-- Test: Cross-model consistency for total costs
WITH snapshot_totals AS (
  SELECT
    simulation_year,
    SUM(employer_match_amount) AS snapshot_match_total,
    SUM(employer_core_amount) AS snapshot_core_total
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),
calc_totals AS (
  SELECT
    simulation_year,
    SUM(employer_match_amount) AS calc_match_total
  FROM {{ ref('int_employee_match_calculations') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),
core_totals AS (
  SELECT
    simulation_year,
    SUM(core_contribution_amount) AS calc_core_total
  FROM {{ ref('int_employee_core_contributions') }}
  WHERE simulation_year = {{ var('simulation_year') }}
)
SELECT
  s.simulation_year,
  ABS(s.snapshot_match_total - c.calc_match_total) AS match_variance,
  ABS(s.snapshot_core_total - cr.calc_core_total) AS core_variance
FROM snapshot_totals s
JOIN calc_totals c USING (simulation_year)
JOIN core_totals cr USING (simulation_year)
WHERE match_variance > 1.00 OR core_variance > 1.00
-- Should return 0 rows (allowing $1 rounding variance)
```

## Documentation Updates

### Complete Schema Documentation
```yaml
# Updated documentation for comprehensive contribution system
models:
  - name: fct_workforce_snapshot
    description: |
      Point-in-time workforce snapshot with complete compensation and
      retirement contribution data. Includes base salary, employee deferrals,
      employer match and core contributions for comprehensive cost analysis.

      **S039-04**: Added employer match integration
      **S039-05**: Added employer core contribution integration

      This model serves as the primary source for total compensation analysis,
      retirement plan cost modeling, and multi-year financial projections.

    columns:
      - name: total_employer_contributions
        description: |
          Sum of all employer retirement contributions (match + core).
          Enables analysis of total employer retirement plan costs.

      - name: total_plan_contributions
        description: |
          Sum of all retirement plan contributions (employee + employer).
          Represents total retirement savings for the employee.

      - name: employer_contribution_rate
        description: |
          Total employer contributions as percentage of base compensation.
          Key metric for cost analysis and benchmarking.
```

## Success Metrics

### Technical Metrics
- ✅ All workforce snapshot tests pass including new contribution columns
- ✅ Performance impact remains under 25% total increase
- ✅ Data consistency across all contribution calculation models
- ✅ Complete integration test suite passes

### Business Metrics
- ✅ Complete employer contribution cost model available in single view
- ✅ Total compensation analysis possible from workforce snapshot
- ✅ Multi-year cost projections enabled with full contribution data
- ✅ Budget and forecasting models can use comprehensive contribution data

## Delivery Checklist

- [ ] Extend `fct_workforce_snapshot.sql` with core contribution integration
- [ ] Add core contribution columns with proper data types and defaults
- [ ] Implement efficient join pattern for core calculations and eligibility
- [ ] Add summary columns for total employer and plan contributions
- [ ] Update indexes to support comprehensive contribution analytics
- [ ] Create schema tests for all new columns and relationships
- [ ] Implement business logic validation tests for calculation consistency
- [ ] Create integration tests verifying cross-model data consistency
- [ ] Update model documentation with complete contribution system details
- [ ] Performance test with full contribution system integration
- [ ] Create comprehensive analytical examples demonstrating capabilities

---

**Next Story**: S039-06 - Data Quality and Validation (comprehensive testing framework)
