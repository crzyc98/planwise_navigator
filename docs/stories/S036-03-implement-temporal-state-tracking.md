# Story S036-03: Implement Temporal State Tracking

**Epic**: E036 - Deferral Rate State Accumulator Architecture
**Story Points**: 5
**Priority**: Critical
**Sprint**: Infrastructure Fix
**Owner**: Technical Architecture Team
**Status**: 🔵 Ready for Implementation
**Type**: Implementation

## Story

**As a** platform engineer
**I want** to implement the `int_deferral_rate_state_accumulator.sql` model with temporal state tracking
**So that** deferral rate state is properly maintained across simulation years without circular dependencies

## Business Context

This is the core implementation story that creates the `int_deferral_rate_state_accumulator.sql` model. Following the design from S036-02, this model will track deferral rate state across simulation years using the proven Epic E023 temporal accumulator pattern, eliminating the circular dependency that currently prevents multi-year simulation execution.

## Acceptance Criteria

### Core Model Implementation
- [ ] **Create `int_deferral_rate_state_accumulator.sql`** with incremental materialization
- [ ] **Implement monthly temporal grain** with 12 rows per employee per year using forward-fill logic
- [ ] **Define composite primary keys** preventing duplicate states: `(scenario_id, plan_design_id, employee_id, simulation_year, as_of_month)`
- [ ] **Handle all edge cases** including explicit 0% vs NULL, opt-out escalation suppression, plan min/max bounds

### Year 0 Seeding & Multi-Year Logic
- [ ] **Year 0 seeding logic** with explicit behavior when prior state is absent (seed from `int_baseline_workforce`)
- [ ] **Multi-year state transition** where Year N uses Year N-1 accumulator data + Year N events
- [ ] **Precedence rules implemented** with `event_priority` (enrollment=1, escalation=2, baseline=3) + `effective_date`
- [ ] **Employee lifecycle handling** including termination (`is_active=false`) and rehire scenarios

## Technical Implementation

### Model Structure

```sql
-- dbt/models/intermediate/int_deferral_rate_state_accumulator.sql
-- CRITICAL: Source from int_* models, NEVER from fct_yearly_events to avoid circular dependency

{{ config(
    materialized='incremental',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year', 'as_of_month'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
) }}

-- Monthly grain expansion for temporal state tracking
WITH months AS (
  SELECT DATE_TRUNC('month', DATE '{{ var("simulation_year") }}-01-01') + i * INTERVAL 1 month AS as_of_month
  FROM range(0, 12) AS t(i)
),

previous_year_state AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    current_deferral_rate, effective_date,
    as_of_month, is_active,
    source_type, source_event_ids, source_event_types,
    state_version, applied_at
  FROM {{ ref('int_deferral_rate_state_accumulator') }}
  WHERE simulation_year = {{ var('simulation_year') }} - 1
    AND is_current = TRUE
),

current_year_enrollment_changes AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    employee_deferral_rate,
    effective_date,
    'enrollment' as source_type,
    event_id,
    1 as event_priority
  FROM {{ ref('int_enrollment_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employee_deferral_rate IS NOT NULL
),

current_year_escalation_changes AS (
  SELECT
    esc.scenario_id,
    esc.plan_design_id,
    esc.employee_id,
    esc.new_deferral_rate as employee_deferral_rate,
    esc.effective_date,
    'escalation' as source_type,
    esc.event_id,
    2 as event_priority
  FROM {{ ref('int_deferral_rate_escalation_events') }} esc
  LEFT JOIN {{ ref('int_enrollment_events') }} enr
    ON esc.scenario_id = enr.scenario_id
    AND esc.plan_design_id = enr.plan_design_id
    AND esc.employee_id = enr.employee_id
    AND esc.simulation_year = enr.simulation_year
  WHERE esc.simulation_year = {{ var('simulation_year') }}
    AND esc.new_deferral_rate IS NOT NULL
    -- Escalation suppression: exclude if employee opted out or has explicit suppression
    AND NOT (enr.employee_deferral_rate = 0.0000 OR enr.escalation_opt_out = TRUE)
),

baseline_defaults AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    COALESCE(baseline_deferral_rate, 0.0300) as employee_deferral_rate,  -- Default 3% if null
    employee_hire_date as effective_date,
    'baseline' as source_type,
    NULL as event_id,
    3 as event_priority
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employment_status = 'active'
),

-- Year 0/Initial State: When prior_year_state is empty (e.g., Year 1), seed from baseline
-- For later years: merge prior state for existing employees + baseline for new hires
unified_state_changes AS (
  -- Current year changes from enrollment events
  SELECT
    scenario_id, plan_design_id, employee_id,
    employee_deferral_rate, effective_date, source_type, event_id, event_priority
  FROM current_year_enrollment_changes

  UNION ALL

  -- Current year changes from escalation events
  SELECT
    scenario_id, plan_design_id, employee_id,
    employee_deferral_rate, effective_date, source_type, event_id, event_priority
  FROM current_year_escalation_changes

  UNION ALL

  -- Baseline for new hires in any year (Year 1 or employees not in prior state)
  SELECT
    bd.scenario_id, bd.plan_design_id, bd.employee_id,
    bd.employee_deferral_rate, bd.effective_date, bd.source_type, bd.event_id, bd.event_priority
  FROM baseline_defaults bd
  LEFT JOIN previous_year_state pys
    ON bd.scenario_id = pys.scenario_id
    AND bd.plan_design_id = pys.plan_design_id
    AND bd.employee_id = pys.employee_id
  WHERE pys.employee_id IS NULL  -- New employees not in previous year state

  UNION ALL

  -- Carry forward previous year state for employees with no current year changes
  SELECT
    pys.scenario_id, pys.plan_design_id, pys.employee_id,
    pys.current_deferral_rate as employee_deferral_rate,
    DATE('{{ var("simulation_year") }}-01-01') as effective_date,  -- Start of current year
    'carryforward' as source_type,
    NULL as event_id,
    4 as event_priority  -- Lowest priority
  FROM previous_year_state pys
  WHERE pys.is_active = TRUE
    AND NOT EXISTS (
      -- No enrollment changes for this employee
      SELECT 1 FROM current_year_enrollment_changes cyec
      WHERE cyec.employee_id = pys.employee_id
    )
    AND NOT EXISTS (
      -- No escalation changes for this employee
      SELECT 1 FROM current_year_escalation_changes cyesc
      WHERE cyesc.employee_id = pys.employee_id
    )
),

-- Apply plan min/max bounds and handle edge cases
bounded_state_changes AS (
  SELECT *,
    -- Apply plan bounds (example: 0% to 50% allowed)
    CASE
      WHEN employee_deferral_rate < 0.0000 THEN 0.0000
      WHEN employee_deferral_rate > 0.5000 THEN 0.5000  -- 50% max
      ELSE ROUND(employee_deferral_rate, 4)
    END as bounded_deferral_rate
  FROM unified_state_changes
),

-- Deterministic precedence: latest effective_date wins, then event_priority breaks ties
final_state_by_employee AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY scenario_id, plan_design_id, employee_id
      ORDER BY effective_date DESC, event_priority ASC, event_id ASC
    ) as rn
  FROM bounded_state_changes
),

-- Employee lifecycle status from baseline workforce (for is_active determination)
employee_status AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    employment_status,
    termination_date
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
)

-- Employee-month combinations for forward-fill logic
employee_months AS (
  SELECT DISTINCT
    fse.scenario_id, fse.plan_design_id, fse.employee_id,
    m.as_of_month
  FROM final_state_by_employee fse
  CROSS JOIN months m
  WHERE fse.rn = 1
),

-- Monthly state with forward-fill logic
monthly_state AS (
  SELECT
    em.*,
    LAST_VALUE(fse.bounded_deferral_rate) IGNORE NULLS OVER (
      PARTITION BY em.scenario_id, em.plan_design_id, em.employee_id
      ORDER BY em.as_of_month
      ROWS UNBOUNDED PRECEDING
    ) AS current_deferral_rate,
    LAST_VALUE(fse.source_type) IGNORE NULLS OVER (
      PARTITION BY em.scenario_id, em.plan_design_id, em.employee_id
      ORDER BY em.as_of_month
      ROWS UNBOUNDED PRECEDING
    ) AS source_type,
    LAST_VALUE(fse.effective_date) IGNORE NULLS OVER (
      PARTITION BY em.scenario_id, em.plan_design_id, em.employee_id
      ORDER BY em.as_of_month
      ROWS UNBOUNDED PRECEDING
    ) AS effective_date,
    LAST_VALUE(fse.event_id) IGNORE NULLS OVER (
      PARTITION BY em.scenario_id, em.plan_design_id, em.employee_id
      ORDER BY em.as_of_month
      ROWS UNBOUNDED PRECEDING
    ) AS event_id,
    em.as_of_month = DATE_TRUNC('month', DATE '{{ var("simulation_year") }}-12-31') AS is_current
  FROM employee_months em
  LEFT JOIN final_state_by_employee fse
    ON em.scenario_id = fse.scenario_id
    AND em.plan_design_id = fse.plan_design_id
    AND em.employee_id = fse.employee_id
    AND DATE_TRUNC('month', fse.effective_date) = em.as_of_month
    AND fse.rn = 1
)

-- Final materialization with monthly temporal grain
SELECT
  ms.scenario_id,
  ms.plan_design_id,
  ms.employee_id,
  ms.current_deferral_rate,
  ms.effective_date,
  {{ var('simulation_year') }} as simulation_year,
  ms.source_type,

  -- Temporal grain fields
  ms.as_of_month,
  ms.is_current,
  CASE
    WHEN es.employment_status = 'active' AND
         (es.termination_date IS NULL OR es.termination_date > ms.as_of_month)
    THEN TRUE
    ELSE FALSE
  END as is_active,

  -- Audit trail fields (DuckDB-compatible)
  CASE
    WHEN ms.event_id IS NOT NULL THEN to_json([ms.event_id])
    ELSE to_json([])
  END as source_event_ids,
  to_json([ms.source_type]) as source_event_types,
  DENSE_RANK() OVER (
    PARTITION BY ms.scenario_id, ms.plan_design_id, ms.employee_id
    ORDER BY ms.effective_date, ms.as_of_month
  ) as state_version,
  ms.effective_date as applied_at,  -- Deterministic
  CURRENT_TIMESTAMP as last_updated_at  -- Non-deterministic audit timestamp

FROM monthly_state ms
LEFT JOIN employee_status es
  ON ms.scenario_id = es.scenario_id
  AND ms.plan_design_id = es.plan_design_id
  AND ms.employee_id = es.employee_id
WHERE ms.current_deferral_rate IS NOT NULL  -- Only months with valid state
```

### Schema Definition

```yaml
# dbt/models/intermediate/schema.yml
version: 2

models:
  - name: int_deferral_rate_state_accumulator
    description: "Temporal state accumulator tracking deferral rate changes across simulation years"

    config:
      contract:
        enforced: true

    columns:
      - name: scenario_id
        description: "Simulation scenario identifier"
        data_type: varchar(50)
        constraints:
          - type: not_null

      - name: plan_design_id
        description: "DC plan design identifier"
        data_type: varchar(50)
        constraints:
          - type: not_null

      - name: employee_id
        description: "Unique employee identifier"
        data_type: varchar(50)
        constraints:
          - type: not_null

      - name: simulation_year
        description: "Simulation year for this state"
        data_type: integer
        constraints:
          - type: not_null

      - name: current_deferral_rate
        description: "Current deferral rate (0.0000 to 1.0000 representing 0% to 100%)"
        data_type: decimal(5,4)
        constraints:
          - type: not_null

      - name: effective_date
        description: "Date when this deferral rate became effective"
        data_type: date
        constraints:
          - type: not_null

      - name: source_type
        description: "Source of deferral rate: enrollment, escalation, baseline, carryforward"
        data_type: varchar(20)
        constraints:
          - type: not_null
          - type: accepted_values
            values: ['enrollment', 'escalation', 'baseline', 'carryforward']

      - name: as_of_month
        description: "Month-level temporal grain for state tracking"
        data_type: date
        constraints:
          - type: not_null

      - name: is_current
        description: "Flag indicating if this is the current state for the employee/year"
        data_type: boolean
        constraints:
          - type: not_null

      - name: is_active
        description: "Flag indicating if employee is active (not terminated)"
        data_type: boolean
        constraints:
          - type: not_null

      - name: source_event_ids
        description: "JSON array of source event UUIDs for audit trail"
        data_type: varchar

      - name: source_event_types
        description: "JSON array of source event types for audit trail"
        data_type: varchar

      - name: state_version
        description: "Version number for state changes (incremental)"
        data_type: integer
        constraints:
          - type: not_null

      - name: applied_at
        description: "Deterministic timestamp when state was calculated"
        data_type: timestamp
        constraints:
          - type: not_null

      - name: last_updated_at
        description: "System timestamp for record creation/update"
        data_type: timestamp
        constraints:
          - type: not_null

    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - scenario_id
            - plan_design_id
            - employee_id
            - simulation_year
            - as_of_month
      - dbt_expectations.expect_table_row_count_to_be_between:
          min_value: 1
          max_value: 100000  # Reasonable upper bound
```

## Edge Case Handling Implementation

### Explicit 0% vs NULL/Missing
```sql
-- Distinguish intentional opt-outs (0%) from missing data
CASE
  WHEN employee_deferral_rate = 0.0000 THEN 0.0000  -- Explicit 0% opt-out
  WHEN employee_deferral_rate IS NULL AND source_type = 'enrollment' THEN 0.0000  -- NULL enrollment = opt-out
  WHEN employee_deferral_rate IS NULL AND source_type = 'baseline' THEN 0.0300  -- 3% default for new hires
  ELSE employee_deferral_rate
END as processed_deferral_rate
```

### Multiple Changes Per Year
```sql
-- Deterministic precedence handling: latest effective_date primary, priority secondary
ROW_NUMBER() OVER (
  PARTITION BY scenario_id, plan_design_id, employee_id
  ORDER BY
    effective_date DESC,        -- Latest date wins (primary)
    event_priority ASC,         -- enrollment=1 > escalation=2 > baseline=3 (tie-breaker)
    event_id ASC                -- Final tie-breaker for same-timestamp events
) as rn
```

### Employee Lifecycle Transitions
```sql
-- Termination handling with monthly precision
CASE
  WHEN es.employment_status = 'terminated' THEN FALSE
  WHEN es.termination_date IS NOT NULL AND es.termination_date <= ms.as_of_month THEN FALSE
  ELSE TRUE
END as is_active,

-- Rehire logic: if employee was terminated and returns, seed from baseline or restore prior rate
rehire_state AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    -- Check if employee exists in baseline but was terminated in prior year
    CASE
      WHEN bd.employee_id IS NOT NULL AND pys.employment_status = 'terminated'
      THEN 'rehire'
      ELSE 'new_hire'
    END as hire_type,
    -- For rehires, use plan default; could be enhanced to restore prior rate if available
    COALESCE(bd.baseline_deferral_rate, 0.0300) as deferral_rate
  FROM {{ ref('int_baseline_workforce') }} bd
  LEFT JOIN previous_year_state pys USING (scenario_id, plan_design_id, employee_id)
  WHERE bd.simulation_year = {{ var('simulation_year') }}
)
```

### Plan Min/Max Bounds Validation
```sql
-- Apply plan-level bounds with violation flagging
bounded_deferral_rate,
CASE
  WHEN employee_deferral_rate < 0.0000 THEN 'below_minimum'  -- Cannot be negative
  WHEN employee_deferral_rate > 0.5000 THEN 'above_maximum'  -- Example 50% max
  ELSE 'within_bounds'
END as bounds_validation_status,

-- Bounds applied in bounded_state_changes CTE
CASE
  WHEN employee_deferral_rate < 0.0000 THEN 0.0000
  WHEN employee_deferral_rate > 0.5000 THEN 0.5000
  ELSE ROUND(employee_deferral_rate, 4)
END as bounded_deferral_rate
```

## Performance Optimization

### Data Types & Precision
```sql
-- Use DECIMAL(5,4) for deferral rates to avoid float drift
current_deferral_rate DECIMAL(5,4)     -- 0.0000 to 1.0000 (0% to 100%)

-- Round consistently to prevent precision drift
ROUND(employee_deferral_rate, 4) as bounded_deferral_rate
```

### Query Optimization
```sql
-- Filter by simulation_year to avoid full scans
WHERE simulation_year = {{ var('simulation_year') }}

-- Use targeted EXISTS checks instead of large JOINs
WHERE NOT EXISTS (
  SELECT 1 FROM current_year_enrollment_changes cyec
  WHERE cyec.employee_id = pys.employee_id
)
```

### Materialization Strategy
```sql
{{ config(
    materialized='incremental',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year', 'as_of_month'],
    incremental_strategy='delete+insert',    -- DuckDB compatible
    on_schema_change='sync_all_columns'      -- Handle schema evolution
) }}
```

## Implementation Tasks

### Phase 1: Core Model Creation
- [ ] **Create model file** `dbt/models/intermediate/int_deferral_rate_state_accumulator.sql`
- [ ] **Implement temporal state logic** following Epic E023 pattern
- [ ] **Add schema definition** with proper contracts and constraints
- [ ] **Configure materialization** with incremental strategy and partitioning

### Phase 2: Edge Case Implementation
- [ ] **Implement precedence rules** with deterministic ordering
- [ ] **Add edge case handling** for 0% vs NULL, employee lifecycle, plan bounds
- [ ] **Add audit trail tracking** with source events and state versioning
- [ ] **Implement Year 0 seeding** logic for initial state

### Phase 3: Performance & Quality
- [ ] **Add performance optimizations** with proper indexing and filtering
- [ ] **Implement data quality checks** within model logic
- [ ] **Add comprehensive testing** for edge cases and state transitions
- [ ] **Validate performance targets** with <3 second execution time

## Dependencies

### Story Dependencies
- **S036-01**: Dependency Analysis (needs completed analysis)
- **S036-02**: Design State Accumulator (needs design specification)

### Model Dependencies
- `int_enrollment_events` (source for enrollment deferral rates and opt-out flags)
- `int_deferral_rate_escalation_events` (source for automatic rate increases)
- `int_baseline_workforce` (source for default rates, employee status, and new hire detection)

### Blocking for Other Stories
- **S036-04**: Refactor Employee Contributions (needs working accumulator)
- **S036-05**: Update Orchestrator (needs model ready for orchestration)

## Success Metrics

### Functionality
- [ ] **Model executes successfully** without circular dependency errors
- [ ] **Temporal state tracking works** across multiple simulation years
- [ ] **Edge cases handled correctly** with proper business logic
- [ ] **Data consistency maintained** with proper state transitions

### Performance
- [ ] **Execution time <3 seconds** per simulation year (target from design)
- [ ] **Memory efficiency** with incremental materialization
- [ ] **Query optimization** with proper filtering and indexing
- [ ] **Scalability** for 10K+ employees across multiple years

### Data Quality
- [ ] **No duplicate states** per composite primary key
- [ ] **State consistency** across year boundaries
- [ ] **Audit trail completeness** with proper source tracking
- [ ] **Edge case validation** with comprehensive test coverage

## Testing Strategy

### Unit Testing
```sql
-- Test monthly grain: each employee should have 12 monthly rows
SELECT employee_id, COUNT(*) as month_count
FROM int_deferral_rate_state_accumulator
WHERE simulation_year = {{ var('simulation_year') }}
GROUP BY employee_id
HAVING COUNT(*) != 12

-- Test forward-fill logic: no NULL deferral rates in monthly progression
SELECT employee_id, as_of_month, current_deferral_rate
FROM int_deferral_rate_state_accumulator
WHERE simulation_year = {{ var('simulation_year') }}
  AND current_deferral_rate IS NULL

-- Test Year 1 new hire seeding from baseline
SELECT COUNT(*) FROM int_deferral_rate_state_accumulator
WHERE simulation_year = 1 AND source_type = 'baseline'

-- Test Year N new hire detection (not in prior year)
SELECT DISTINCT employee_id FROM int_deferral_rate_state_accumulator
WHERE simulation_year = 2 AND source_type = 'baseline'

-- Test precedence: latest effective_date wins, then enrollment > escalation
WITH precedence_test AS (
  SELECT employee_id, source_type, effective_date,
    RANK() OVER (PARTITION BY employee_id ORDER BY effective_date DESC,
      CASE source_type WHEN 'enrollment' THEN 1 WHEN 'escalation' THEN 2 ELSE 3 END) as precedence_rank
  FROM int_deferral_rate_state_accumulator
  WHERE simulation_year = {{ var('simulation_year') }} AND is_current = TRUE
)
SELECT * FROM precedence_test WHERE precedence_rank > 1  -- Should be empty

-- Test escalation suppression: no escalation events for opt-out employees
SELECT esc.employee_id
FROM int_deferral_rate_state_accumulator esc
JOIN {{ ref('int_enrollment_events') }} enr
  ON esc.employee_id = enr.employee_id
  AND esc.simulation_year = enr.simulation_year
WHERE esc.source_type = 'escalation'
  AND (enr.employee_deferral_rate = 0.0000 OR enr.escalation_opt_out = TRUE)

-- Test bounds validation: all rates within [0, 0.5] range
SELECT employee_id, current_deferral_rate
FROM int_deferral_rate_state_accumulator
WHERE simulation_year = {{ var('simulation_year') }}
  AND (current_deferral_rate < 0 OR current_deferral_rate > 0.5000)
```

### Integration Testing
- Test with `int_employee_contributions` integration
- Validate multi-year simulation workflow
- Test orchestration execution order
- Verify performance under load

## Definition of Done

- [ ] **`int_deferral_rate_state_accumulator.sql` model created** with complete implementation
- [ ] **All acceptance criteria met** including temporal grain and edge cases
- [ ] **Schema definition complete** with contracts and constraints
- [ ] **Edge case handling implemented** for all identified scenarios
- [ ] **Performance optimizations applied** with <3 second execution target
- [ ] **Comprehensive testing completed** with unit and integration tests
- [ ] **Data quality validations working** with proper constraints
- [ ] **Ready for orchestration integration** in subsequent story

## Implementation Notes & Design Decisions

### Monthly vs. Payroll-Period Grain
This implementation uses **monthly grain** for simplicity and broad applicability. Each employee gets 12 rows per simulation year with forward-fill logic to maintain state consistency. If payroll-period awareness is needed later, the months CTE can be replaced with a payroll calendar dimension.

### Escalation Suppression Strategy
Escalation events are suppressed for employees who:
- Have `employee_deferral_rate = 0.0000` in enrollment events (explicit opt-out)
- Have `escalation_opt_out = TRUE` flag in enrollment events
- This prevents unwanted automatic increases for employees who explicitly opted out

### Precedence Rules Clarification
- **Primary**: Latest `effective_date` wins (most recent decision)
- **Secondary**: `event_priority` breaks ties (enrollment=1 > escalation=2 > baseline=3)
- **Tertiary**: `event_id` for final tie-breaking (deterministic)

### Rehire and Lifecycle Handling
- **New hires**: Seeded from baseline in any year if not in previous_year_state
- **Rehires**: Detected via baseline presence + prior termination; use baseline rate (could be enhanced to restore prior rate)
- **Terminations**: `is_active = FALSE` when termination_date <= as_of_month
- **Monthly precision**: State changes tracked at month level for payroll integration

### DuckDB Compatibility
- **JSON arrays**: Use `to_json([value])` instead of `JSON_ARRAY()`
- **No partitioning**: DuckDB ignores `partition_by`; rely on year filtering
- **No indexes**: DuckDB ignores index configs; optimize via WHERE clauses
- **Incremental**: `delete+insert` strategy works reliably with unique_key

### Audit and Determinism
- **source_event_ids**: JSON array of contributing event UUIDs
- **state_version**: DENSE_RANK over change points per employee (deterministic)
- **applied_at**: Deterministic, derived from effective_date
- **last_updated_at**: Non-deterministic system timestamp (acceptable for audit)

This implementation story is the technical heart of the Epic E036 solution. The model properly handles temporal state accumulation without creating circular dependencies, while maintaining monthly precision and comprehensive audit trails.
