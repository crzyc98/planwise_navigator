# Story S025-01: Core Match Formula Models

**Epic**: E025 - Match Engine with Formula Support
**Story Points**: 6
**Priority**: High
**Sprint**: TBD
**Owner**: Platform Team
**Status**: 📋 **PLANNED**

## Story

**As a** plan administrator
**I want** SQL-based match formula calculations
**So that** I can efficiently calculate employer matches for different plan designs

## Business Context

This foundational story establishes the core match calculation engine using pure SQL/dbt models for maximum performance. It implements the two most common match formulas (simple percentage and tiered matching) that represent 90% of employer match designs in the market. The SQL-first approach leverages DuckDB's columnar processing to handle large employee populations efficiently.

## Acceptance Criteria

### Core Formula Support
- [ ] **Simple percentage match** (e.g., 50% of deferrals) implemented in pure SQL
- [ ] **Tiered match formula** (100% on first 3%, 50% on next 2%) using DuckDB optimization
- [ ] **Maximum match caps** applied as percentage of compensation
- [ ] **Formula configuration** via dbt variables without code changes
- [ ] **Integration** with contribution events from E024

### Performance Requirements
- [ ] **Process 100K employees** in <10 seconds using DuckDB columnar operations
- [ ] **Match calculations** complete in single SQL query execution
- [ ] **Memory efficiency** with streaming operations where possible

### Configuration Management
- [ ] **dbt variable support** for match formula parameters
- [ ] **Active formula selection** via configuration
- [ ] **Multiple formula definitions** stored in dbt_project.yml

## Technical Specifications

### Core dbt Model Implementation

```sql
-- dbt/models/intermediate/int_employee_match_calculations.sql
{{
  config(
    materialized='table',
    indexes=[
      {'columns': ['employee_id', 'simulation_year'], 'unique': true}
    ]
  )
}}

WITH employee_contributions AS (
  SELECT
    employee_id,
    simulation_year,
    SUM(contribution_amount) as annual_deferrals,
    MAX(eligible_compensation) as eligible_compensation,
    -- Calculate effective deferral rate
    CASE
      WHEN MAX(eligible_compensation) > 0
      THEN SUM(contribution_amount) / MAX(eligible_compensation)
      ELSE 0
    END as deferral_rate
  FROM {{ ref('fct_contribution_events') }}
  WHERE contribution_type = 'EMPLOYEE_DEFERRAL'
  GROUP BY employee_id, simulation_year
),

-- Simple match calculation
simple_match AS (
  SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    deferral_rate,
    annual_deferrals,
    -- Simple percentage match
    annual_deferrals * {{ var('match_formulas')['simple_match']['match_rate'] }} as match_amount,
    'simple' as formula_type
  FROM employee_contributions
  WHERE '{{ var("active_match_formula") }}' = 'simple_match'
),

-- Tiered match calculation using DuckDB's powerful window functions
tiered_match AS (
  SELECT
    ec.employee_id,
    ec.simulation_year,
    ec.eligible_compensation,
    ec.deferral_rate,
    ec.annual_deferrals,
    -- Calculate match for each tier
    SUM(
      CASE
        WHEN ec.deferral_rate > tier.employee_min
        THEN LEAST(
          ec.deferral_rate - tier.employee_min,
          tier.employee_max - tier.employee_min
        ) * tier.match_rate * ec.eligible_compensation
        ELSE 0
      END
    ) as match_amount,
    'tiered' as formula_type
  FROM employee_contributions ec
  CROSS JOIN (
    {% for tier in var('match_formulas')['tiered_match']['tiers'] %}
    SELECT
      {{ tier['tier'] }} as tier_number,
      {{ tier['employee_min'] }} as employee_min,
      {{ tier['employee_max'] }} as employee_max,
      {{ tier['match_rate'] }} as match_rate
    {% if not loop.last %}UNION ALL{% endif %}
    {% endfor %}
  ) as tier
  WHERE '{{ var("active_match_formula") }}' = 'tiered_match'
  GROUP BY ec.employee_id, ec.simulation_year, ec.eligible_compensation,
           ec.deferral_rate, ec.annual_deferrals
),

-- Combine all match types
all_matches AS (
  SELECT * FROM simple_match
  UNION ALL
  SELECT * FROM tiered_match
),

-- Apply match caps
final_match AS (
  SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    deferral_rate,
    annual_deferrals,
    formula_type,
    -- Apply maximum match cap
    LEAST(
      match_amount,
      eligible_compensation * {{ var('match_formulas')[var('active_match_formula')]['max_match_percentage'] }}
    ) as employer_match_amount,
    -- Track if cap was applied
    CASE
      WHEN match_amount > eligible_compensation * {{ var('match_formulas')[var('active_match_formula')]['max_match_percentage'] }}
      THEN true
      ELSE false
    END as match_cap_applied
  FROM all_matches
)

SELECT
  employee_id,
  simulation_year,
  eligible_compensation,
  deferral_rate,
  annual_deferrals,
  employer_match_amount,
  formula_type,
  match_cap_applied,
  '{{ var("active_match_formula") }}' as formula_id,
  -- Calculate effective match rate
  CASE
    WHEN annual_deferrals > 0
    THEN employer_match_amount / annual_deferrals
    ELSE 0
  END as effective_match_rate
FROM final_match
```

### Configuration via dbt Variables

```yaml
# dbt_project.yml
vars:
  match_formulas:
    simple_match:
      name: "Simple 50% Match"
      type: "simple"
      match_rate: 0.50
      max_match_percentage: 0.03

    tiered_match:
      name: "Standard Tiered Match"
      type: "tiered"
      tiers:
        - tier: 1
          employee_min: 0.00
          employee_max: 0.03
          match_rate: 1.00
        - tier: 2
          employee_min: 0.03
          employee_max: 0.05
          match_rate: 0.50
      max_match_percentage: 0.04

  # Active formula for simulations
  active_match_formula: "tiered_match"
```

### Integration Points
1. **Data Source**: Uses contribution events from S024-01 (`fct_contribution_events`)
2. **dbt Model**: Creates `int_employee_match_calculations` table
3. **Configuration**: Uses dbt variables for formula definitions and active selection
4. **Performance**: Single-query execution leveraging DuckDB columnar processing
5. **Output**: Structured match calculations ready for event generation

## Test Scenarios

### dbt Tests
```yaml
# dbt/models/intermediate/schema.yml
models:
  - name: int_employee_match_calculations
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - employee_id
            - simulation_year
    columns:
      - name: employer_match_amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              inclusive: true
      - name: effective_match_rate
        tests:
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1
              inclusive: true
```

### Test Cases
1. **Simple Match Formula**:
   - Employee deferrals: $3,000
   - Simple 50% match rate
   - Expected match: $1,500

2. **Tiered Match Formula**:
   - Salary: $100,000, Deferral: 5%
   - Tier 1: 100% on first 3% = $3,000 match
   - Tier 2: 50% on next 2% = $1,000 match
   - Total expected match: $4,000

3. **Match Cap Application**:
   - High earner with 10% deferral
   - Match cap at 4% of compensation
   - Verify cap enforcement

4. **Performance Test**:
   - 100K employees with mixed deferral patterns
   - Target: <10 seconds execution time

5. **Zero Deferral Handling**:
   - Employees with no deferrals
   - Expected match: $0

## Implementation Tasks

### Phase 1: Core SQL Logic
- [ ] **Create match calculation model** with simple and tiered formulas
- [ ] **Implement dbt variable configuration** for formula parameters
- [ ] **Add match cap logic** with compensation percentage limits
- [ ] **Create effective match rate calculations** for analysis

### Phase 2: Performance Optimization
- [ ] **Add proper indexing** on employee_id and simulation_year
- [ ] **Optimize tiered match query** using DuckDB features
- [ ] **Implement materialized table strategy** for performance
- [ ] **Add query profiling** to validate performance targets

### Phase 3: Testing & Documentation
- [ ] **Create comprehensive dbt tests** for all calculation scenarios
- [ ] **Add unit tests** for different formula configurations
- [ ] **Document formula configuration** patterns and examples
- [ ] **Performance benchmark** with 100K employee dataset

## Dependencies

### Technical Dependencies
- **E024**: Contribution Calculator (for contribution events)
- **DuckDB 1.0.0+** for columnar processing performance
- **dbt-core 1.8.8+** for variable configuration and model materialization
- **orchestrator_mvp multi-year simulation framework** for orchestration
- **Existing workforce data** (eligible_compensation field)

### Story Dependencies
- **S024-01**: Basic Contribution Calculations (provides contribution events)

## Success Metrics

### Functionality
- [ ] **Formula accuracy**: All test scenarios calculate correctly
- [ ] **Configuration flexibility**: Multiple formulas configurable without code changes
- [ ] **Match cap enforcement**: Caps applied correctly across all scenarios
- [ ] **Edge case handling**: Zero deferrals, high earners, part-time employees

### Performance
- [ ] **Calculation speed**: <10 seconds for 100K employees
- [ ] **Memory efficiency**: <2GB peak memory usage
- [ ] **Query optimization**: Single-pass calculation without temporary tables

## Definition of Done

- [ ] **Core match calculation model** implemented with both simple and tiered formulas
- [ ] **dbt variable configuration** working for formula parameters and active selection
- [ ] **Match cap logic** properly enforced based on compensation percentages
- [ ] **Performance targets met**: <10 seconds for 100K employees
- [ ] **All test scenarios passing** with comprehensive dbt test coverage
- [ ] **Documentation complete** with formula configuration examples
- [ ] **Integration ready** for event generation in S025-02
- [ ] **Integration testing** with orchestrator_mvp multi-year simulation framework

## Notes

This story focuses purely on the calculation logic and does not generate events. The match calculations will be consumed by S025-02 for event generation. The SQL-first approach ensures maximum performance while maintaining flexibility through dbt variables for different plan designs.
