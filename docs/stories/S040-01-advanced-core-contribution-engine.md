# Story S040-01: Advanced Core Contribution Engine

**Epic**: E040 - Employer Contribution Enhancements
**Status**: 📋 Future Enhancement
**Points**: 6
**Owner**: Platform / Modeling
**Priority**: Medium (After MVP)
**Prerequisites**: E039 - Employer Contribution Integration (MVP)

---

## Story Description

**As a** plan sponsor
**I want** automated core (non-elective) contribution calculations
**So that** I can model employer contributions beyond match and support various plan designs

## Background

Core contributions (also called non-elective contributions) are employer contributions made regardless of employee deferrals. Unlike match contributions which depend on employee participation, core contributions are:

- **Plan-sponsored**: Determined by employer policy, not employee behavior
- **Typically percentage-based**: Usually 1-5% of eligible compensation
- **May vary by level**: Different rates for different job levels/bands
- **Subject to eligibility**: Often requires minimum hours and EOY active status
- **Event-sourced**: Must generate events for audit trails

Currently, the system only handles match contributions. This story implements the missing core contribution engine that integrates with the eligibility system and existing parameter management.

## Acceptance Criteria

### Functional Requirements
- ✅ **Percentage-based Calculations**: Core contributions as % of eligible compensation
- ✅ **Level-based Rates**: Different rates by job level/band via existing `stg_comp_levers` pattern
- ✅ **Eligibility Integration**: Only calculate for eligible employees
- ✅ **Multi-year Parameter Support**: Rate changes across simulation years
- ✅ **Event Generation**: Create EMPLOYER_CORE events for audit trails
- ✅ **Performance Optimization**: Handle 100K+ employees efficiently

### Technical Requirements
- ✅ **Calculation Model**: New `int_employee_core_contributions.sql`
- ✅ **Event Model**: New `fct_employer_core_events.sql`
- ✅ **Parameter Integration**: Leverage existing `stg_comp_levers` → `int_effective_parameters` pattern
- ✅ **Configuration Support**: Extend existing comp_levers.csv with `CORE_CONTRIB` event type
- ✅ **Testing**: Comprehensive validation of calculations and events

### Business Requirements
- ✅ **Audit Trail**: Complete event sourcing for compliance
- ✅ **Flexibility**: Support various core contribution plan designs
- ✅ **Analyst Control**: Parameter-driven configuration via comp_levers.csv
- ✅ **Cost Modeling**: Enable accurate employer cost projections

## Technical Design

### Data Model: `int_employee_core_contributions.sql`

```sql
{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'simulation_year'], 'unique': true}
    ],
    tags=['core_contributions', 'employer_contributions', 'critical']
) }}

/*
  Core Contribution Calculation Model - Story S039-03

  Calculates employer non-elective (core) contributions based on:
  - Configurable rates by job level from comp_levers.csv
  - Eligibility requirements (hours worked, EOY active)
  - Employee compensation from workforce snapshot

  Used by: fct_employer_core_events, fct_workforce_snapshot
  Depends on: int_employer_contribution_eligibility, int_employee_compensation_by_year
*/
```

### Core Calculation Logic

#### 1. Parameter Resolution (Leveraging Existing Framework)
```sql
-- Get core contribution rates by job level using existing pattern
WITH core_rates AS (
  SELECT
    job_level,
    parameter_value AS core_rate
  FROM {{ ref('int_effective_parameters') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND parameter_name = 'core_contribution_rate'
    AND event_type = 'CORE_CONTRIB'
),

-- Support for fixed dollar amounts (alternative to percentage)
core_flat_amounts AS (
  SELECT
    job_level,
    parameter_value AS core_flat_amount
  FROM {{ ref('int_effective_parameters') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND parameter_name = 'core_flat_amount'
    AND event_type = 'CORE_CONTRIB'
),

-- Default rate for levels not specifically configured
default_rate AS (
  SELECT parameter_value AS default_core_rate
  FROM {{ ref('int_effective_parameters') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND parameter_name = 'core_contribution_rate'
    AND event_type = 'CORE_CONTRIB'
    AND job_level IS NULL
  LIMIT 1
)
```

#### 2. Eligible Employee Base
```sql
-- Get eligible employees with compensation data
eligible_employees AS (
  SELECT
    ec.employee_id,
    ec.simulation_year,
    ec.prorated_annual_compensation AS eligible_compensation,
    ec.level_id,
    ec.employment_status,
    eligibility.eligible_for_core
  FROM {{ ref('int_employee_compensation_by_year') }} ec
  JOIN {{ ref('int_employer_contribution_eligibility') }} eligibility
    USING (employee_id, simulation_year)
  WHERE ec.simulation_year = {{ var('simulation_year') }}
    AND eligibility.eligible_for_core = TRUE
    AND ec.prorated_annual_compensation > 0
)
```

#### 3. Rate Application (Supporting Both Percentage and Fixed Dollar)
```sql
-- Apply core contribution rates with support for both percentage and fixed amounts
core_calculations AS (
  SELECT
    ee.employee_id,
    ee.simulation_year,
    ee.eligible_compensation,
    ee.level_id,

    -- Get applicable rate and fixed amount (level-specific or default)
    COALESCE(cr.core_rate, dr.default_core_rate, 0.02) AS core_rate,
    COALESCE(cfa.core_flat_amount, 0) AS core_flat_amount,

    -- Calculate core contribution amount (percentage or fixed, not both)
    CASE
      WHEN cfa.core_flat_amount IS NOT NULL THEN cfa.core_flat_amount
      ELSE ee.eligible_compensation * COALESCE(cr.core_rate, dr.default_core_rate, 0.02)
    END AS core_contribution_amount,

    -- Track calculation method for audit
    CASE
      WHEN cfa.core_flat_amount IS NOT NULL THEN 'fixed_dollar'
      WHEN cr.core_rate IS NOT NULL THEN 'level_specific_rate'
      WHEN dr.default_core_rate IS NOT NULL THEN 'default_rate'
      ELSE 'hardcoded_fallback'
    END AS rate_source

  FROM eligible_employees ee
  LEFT JOIN core_rates cr ON ee.level_id = cr.job_level
  LEFT JOIN core_flat_amounts cfa ON ee.level_id = cfa.job_level
  CROSS JOIN default_rate dr
)
```

### Event Generation: `fct_employer_core_events.sql`

```sql
{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    incremental_strategy='delete+insert',
    tags=['events', 'core_contributions', 'audit_trail']
) }}

/*
  Core Contribution Event Generation - Story S039-03

  Generates EMPLOYER_CORE events from core contribution calculations
  for event sourcing and audit trail purposes.
*/

SELECT
  -- Event identification
  {{ generate_event_uuid('employee_id', 'simulation_year', "'EMPLOYER_CORE'") }} AS event_id,
  employee_id,
  'EMPLOYER_CORE' AS event_type,
  simulation_year,

  -- Event timing (typically end of year for core contributions)
  DATE({{ var('simulation_year') }} || '-12-31') AS effective_date,
  1 AS event_sequence,  -- Core contributions typically single annual event

  -- Event details
  ROUND(core_contribution_amount, 2) AS compensation_amount,
  level_id,
  JSON_OBJECT(
    'core_rate', core_rate,
    'eligible_compensation', eligible_compensation,
    'rate_source', rate_source,
    'calculation_method', 'annual_percentage'
  ) AS event_details,

  -- Metadata
  CURRENT_TIMESTAMP AS created_at,
  '{{ var("scenario_id", "default") }}' AS scenario_id,
  '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id,
  'core_contribution_engine' AS data_source

FROM {{ ref('int_employee_core_contributions') }}
WHERE core_contribution_amount > 0

{% if is_incremental() %}
  AND simulation_year = {{ var('simulation_year') }}
{% endif %}
```

## Configuration Schema

### simulation_config.yaml Extensions
```yaml
# Core contribution configuration
employer_contributions:
  core:
    enabled: true
    default_rate: 0.02          # 2% default rate
    min_contribution: 0.00      # Minimum dollar amount
    max_contribution: null      # Maximum dollar amount (null = no cap)

    # Integration with existing eligibility system
    eligibility:
      min_hours_worked: 1000
      require_active_eoy: true
```

### comp_levers.csv Extensions (Existing Pattern)
```csv
scenario_id,fiscal_year,event_type,parameter_name,job_level,parameter_value
# Core contribution rates by level (consistent with existing stg_comp_levers pattern)
default,2025,CORE_CONTRIB,core_contribution_rate,,0.020
default,2025,CORE_CONTRIB,core_contribution_rate,1,0.015
default,2025,CORE_CONTRIB,core_contribution_rate,2,0.020
default,2025,CORE_CONTRIB,core_contribution_rate,3,0.025
default,2025,CORE_CONTRIB,core_contribution_rate,4,0.030
default,2025,CORE_CONTRIB,core_contribution_rate,5,0.035

# Alternative: Fixed dollar amounts (mutually exclusive with rates)
default,2025,CORE_CONTRIB,core_flat_amount,1,1000.00
default,2025,CORE_CONTRIB,core_flat_amount,2,1500.00
default,2025,CORE_CONTRIB,core_flat_amount,3,2000.00

# Alternative scenario with higher rates
generous,2025,CORE_CONTRIB,core_contribution_rate,,0.030
generous,2025,CORE_CONTRIB,core_contribution_rate,1,0.025
generous,2025,CORE_CONTRIB,core_contribution_rate,2,0.030
generous,2025,CORE_CONTRIB,core_contribution_rate,3,0.035

# Multi-year progression
default,2026,CORE_CONTRIB,core_contribution_rate,,0.022
default,2027,CORE_CONTRIB,core_contribution_rate,,0.024
```

## Output Schema

### `int_employee_core_contributions` Columns
```sql
employee_id VARCHAR NOT NULL,
simulation_year INTEGER NOT NULL,
eligible_compensation DECIMAL(12,2) NOT NULL,
level_id INTEGER NOT NULL,
core_rate DECIMAL(6,4) NOT NULL,
core_contribution_amount DECIMAL(10,2) NOT NULL,
rate_source VARCHAR(50) NOT NULL,
is_eligible BOOLEAN NOT NULL,
calculation_date DATE NOT NULL,

-- Audit fields
created_at TIMESTAMP NOT NULL,
scenario_id VARCHAR(50) NOT NULL,
parameter_scenario_id VARCHAR(50) NOT NULL,

-- Composite unique key
UNIQUE (employee_id, simulation_year)
```

### `fct_employer_core_events` Schema
Follows existing `fct_yearly_events` pattern with:
- `event_type = 'EMPLOYER_CORE'`
- `compensation_amount` = core contribution amount
- `event_details` = JSON with calculation metadata

## Business Logic Examples

### Scenario 1: Standard Core Plan
```yaml
# 2% core for all eligible employees
default_rate: 0.02
level_rates: null  # Use default for all levels
```

**Example Calculation:**
- Employee with $100,000 compensation → $2,000 core contribution
- Employee with $50,000 compensation → $1,000 core contribution

### Scenario 2: Tiered Core by Level
```yaml
# Different rates by management level
level_1: 1.5%  # Individual contributors
level_2: 2.0%  # Team leads
level_3: 2.5%  # Managers
level_4: 3.0%  # Directors
level_5: 3.5%  # Executives
```

**Example Calculation:**
- Level 1: $80,000 × 1.5% = $1,200
- Level 3: $120,000 × 2.5% = $3,000
- Level 5: $200,000 × 3.5% = $7,000

### Scenario 3: Progressive Multi-Year
```yaml
# Increasing rates over time
2025: 2.0%
2026: 2.2%
2027: 2.4%
2028: 2.5%
```

## Performance Considerations

### Optimization Strategies
- **Efficient Parameter Joins**: Use indexed parameter resolution
- **Minimal Data Movement**: Calculate only for eligible employees
- **Batch Event Generation**: Process all employees in single operation
- **Incremental Events**: Only generate events for current simulation year

### Expected Performance
- **100K employees**: <15 seconds for calculation + event generation
- **Memory usage**: <2GB for full calculation and event pipeline
- **Incremental builds**: <8 seconds for year-over-year updates

## Integration Points

### Upstream Dependencies
- `int_employer_contribution_eligibility` - Eligibility determination
- `int_employee_compensation_by_year` - Compensation data
- `int_effective_parameters` - Rate configuration (from existing `stg_comp_levers` \u2192 parameter pipeline)
- `stg_comp_levers` - Core contribution parameter source (event_type='CORE_CONTRIB')
- Configuration system - Core contribution settings

### Downstream Usage
- `fct_workforce_snapshot` - Core contribution amounts
- `fct_yearly_events` - Event sourcing integration
- Analytics models - Cost analysis and projections
- Compliance reporting - Contribution audit trails

### Integration Pattern
```sql
-- Workforce snapshot integration
LEFT JOIN {{ ref('int_employee_core_contributions') }} core
  ON base.employee_id = core.employee_id
  AND base.simulation_year = core.simulation_year

-- Include core contribution amount with null handling
COALESCE(core.core_contribution_amount, 0) AS employer_core_amount
```

## Testing Strategy

### Unit Tests
1. **Rate Application**: Verify correct rates applied by level
2. **Eligibility Gating**: Only eligible employees get contributions
3. **Parameter Resolution**: Level-specific vs default rates
4. **Edge Cases**: Zero compensation, missing levels
5. **Multi-year**: Rate changes across simulation years

### Integration Tests
1. **Event Generation**: Contributions create proper events
2. **Upstream Consistency**: Matches eligibility determinations
3. **Configuration Sensitivity**: Parameter changes affect calculations
4. **Performance**: Large dataset processing times

### Business Validation
1. **Cost Accuracy**: Total core costs match expected budget
2. **Level Distribution**: Appropriate rate progression by level
3. **Eligibility Impact**: Ineligible employees excluded correctly
4. **Multi-year Growth**: Progressive rate increases work correctly

## Schema Tests

### Data Quality Tests
```yaml
models:
  - name: int_employee_core_contributions
    tests:
      - unique:
          column_name: "concat(employee_id, '_', simulation_year)"
      - not_null:
          column_name: employee_id
      - relationships:
          to: ref('int_employer_contribution_eligibility')
          field: employee_id
    columns:
      - name: core_contribution_amount
        description: "Annual core contribution amount"
        tests:
          - not_null
          - accepted_range:
              min_value: 0
              max_value: 100000  # Reasonable maximum
      - name: core_rate
        description: "Core contribution rate applied"
        tests:
          - not_null
          - accepted_range:
              min_value: 0
              max_value: 0.20    # 20% maximum rate
```

### Business Logic Tests
```sql
-- Test: Core amounts match rate × compensation
SELECT * FROM {{ ref('int_employee_core_contributions') }}
WHERE ABS(core_contribution_amount - (eligible_compensation * core_rate)) > 0.01
-- Should return 0 rows

-- Test: Only eligible employees receive contributions
SELECT ce.employee_id
FROM {{ ref('int_employee_core_contributions') }} ce
LEFT JOIN {{ ref('int_employer_contribution_eligibility') }} el
  USING (employee_id, simulation_year)
WHERE el.eligible_for_core = FALSE
-- Should return 0 rows
```

## Documentation Requirements

### Model Documentation
- Core contribution calculation methodology
- Parameter configuration and resolution
- Eligibility integration and business rules
- Event generation and audit trail purpose

### Analyst Guide
- How to configure core contribution rates
- Understanding rate hierarchy (level vs default)
- Multi-year parameter planning
- Cost projection and budgeting

### Integration Guide
- How to consume core contribution data
- Event sourcing integration patterns
- Workforce snapshot updates
- Analytics model integration

## Delivery Checklist

- [ ] `int_employee_core_contributions.sql` model created
- [ ] `fct_employer_core_events.sql` event model created
- [ ] Parameter integration with `int_effective_parameters` implemented
- [ ] Configuration schema updated in simulation_config.yaml
- [ ] comp_levers.csv example data created
- [ ] Schema tests implemented and passing
- [ ] Business logic validation tests created
- [ ] Performance testing completed (100K employees <15s)
- [ ] Integration with eligibility system tested
- [ ] Event generation tested and validated
- [ ] Model documentation added to schema.yml

## Success Criteria

### Technical Success
- ✅ Accurate core contribution calculations for all eligible employees
- ✅ Performance targets met (<15 seconds for 100K employees)
- ✅ All schema and business logic tests pass
- ✅ Proper event generation for audit trails
- ✅ Parameter-driven configuration working correctly

### Business Success
- ✅ Enables complete employer contribution cost modeling
- ✅ Supports flexible plan design configurations
- ✅ Provides compliance-ready audit trails
- ✅ Foundation for workforce snapshot integration

---

**Next Story**: S039-04 - Match Integration into Workforce Snapshot (integrates existing match calculations)
