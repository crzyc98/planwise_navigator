# Story S036-02: Design Deferral Rate State Accumulator Model

**Epic**: E036 - Deferral Rate State Accumulator Architecture
**Story Points**: 3
**Priority**: Critical
**Sprint**: Infrastructure Fix
**Owner**: Technical Architecture Team
**Status**: 🔵 Ready for Implementation
**Type**: Architecture Design

## Story

**As a** platform engineer
**I want** to design the `int_deferral_rate_state_accumulator.sql` model following Epic E023 pattern
**So that** I can eliminate circular dependencies and enable proper temporal state tracking

## Business Context

Following the successful Epic E023 Enrollment Architecture Fix, this story designs the deferral rate state accumulator that will break the circular dependency between `int_employee_contributions` and `fct_yearly_events`. The accumulator will track deferral rate state across simulation years using a proven temporal pattern.

## Acceptance Criteria

### Architecture Design
- [ ] **State accumulator model designed** following Epic E023 proven pattern
- [ ] **Temporal state tracking schema defined** with proper primary keys and grain
- [ ] **Multi-year state transition logic planned** for Year N using Year N-1 data
- [ ] **Data lineage and audit trail requirements documented** for compliance

### Circular Dependency Elimination
- [ ] **Source only from int_* models** - NEVER from `fct_yearly_events` to avoid circular dependency
- [ ] **Define upstream dependencies** clearly: enrollment events, escalation events, baseline workforce
- [ ] **Plan downstream integration** with `int_employee_contributions` model
- [ ] **Orchestration order defined** to ensure proper execution sequence

### Technical Design Specifications
- [ ] **Primary key schema** defined for composite uniqueness constraints
- [ ] **Data types and precision** specified for deferral rates and temporal fields
- [ ] **Materialization strategy** planned (incremental with DuckDB optimizations)
- [ ] **Performance requirements** defined (<5 second execution target)

## Architecture Design

### Core Pattern (Epic E023 Proven Approach)

```sql
-- int_deferral_rate_state_accumulator.sql
-- CRITICAL: Source from int_* models, NEVER from fct_yearly_events to avoid circular dependency

WITH previous_year_state AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    current_deferral_rate, effective_date,
    simulation_year, last_updated_at
  FROM {{ ref('int_deferral_rate_state_accumulator') }}
  WHERE simulation_year = {{ var('simulation_year') }} - 1
),

current_year_enrollment_changes AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    employee_deferral_rate as new_deferral_rate, effective_date,
    'enrollment' as source_type, event_id as source_event_id
  FROM {{ ref('int_enrollment_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employee_deferral_rate IS NOT NULL
),

current_year_escalation_changes AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    new_deferral_rate, effective_date,
    'escalation' as source_type, event_id as source_event_id
  FROM {{ ref('int_deferral_rate_escalation_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND new_deferral_rate IS NOT NULL
),

baseline_defaults AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    baseline_deferral_rate as new_deferral_rate,
    employee_hire_date as effective_date,
    'baseline' as source_type, NULL as source_event_id
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employment_status = 'active'
    -- Only include employees not in prior state and without current-year changes
    AND employee_id NOT IN (
      SELECT DISTINCT employee_id FROM previous_year_state
      UNION
      SELECT DISTINCT employee_id FROM current_year_enrollment_changes
      UNION
      SELECT DISTINCT employee_id FROM current_year_escalation_changes
    )
),

-- Combine all deferral rate changes with proper precedence
-- Enrollment (1) > escalation (2) > baseline (3)
unified_state_changes AS (
  SELECT *, 1 as event_priority FROM current_year_enrollment_changes
  UNION ALL
  SELECT *, 2 as event_priority FROM current_year_escalation_changes
  UNION ALL
  SELECT *, 3 as event_priority FROM baseline_defaults
),

-- Deterministic precedence: enrollment > escalation > baseline, then latest effective_date
final_state_by_employee AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY scenario_id, plan_design_id, employee_id
      ORDER BY event_priority ASC, effective_date DESC, source_event_id NULLS LAST
    ) as rn
  FROM unified_state_changes
)

SELECT
  scenario_id,
  plan_design_id,
  employee_id,
  new_deferral_rate as current_deferral_rate,
  effective_date,
  {{ var('simulation_year') }} as simulation_year,
  source_type,
  source_event_id,
  -- Temporal grain and audit fields
  DATE_TRUNC('month', effective_date) as as_of_month,
  TRUE as is_current,
  event_priority,
  ROW_NUMBER() OVER (
    PARTITION BY scenario_id, plan_design_id, employee_id
    ORDER BY effective_date, event_priority
  ) as state_version,
  -- Deterministic timestamp based on effective_date
  effective_date as applied_at,
  effective_date as last_updated_at
FROM final_state_by_employee
WHERE rn = 1
```

### Schema Design Specifications

#### Primary Keys & Uniqueness
```sql
-- Enforce via dbt tests, not DDL constraints
-- Primary key uniqueness test
{{ dbt_utils.unique_combination_of_columns(
    columns=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year', 'as_of_month']
) }}

-- Ensure exactly one current row per employee/year
{{ test_exactly_one_current_state_per_employee_year() }}
```

#### Column Specifications
```sql
-- Core identification
scenario_id           VARCHAR(50)      NOT NULL
plan_design_id        VARCHAR(50)      NOT NULL
employee_id           VARCHAR(50)      NOT NULL
simulation_year       INTEGER          NOT NULL

-- Deferral rate state
current_deferral_rate DECIMAL(5,4)     NOT NULL  -- 0.0000 to 1.0000 (0% to 100%)
effective_date        DATE             NOT NULL
source_type           VARCHAR(20)      NOT NULL  -- 'enrollment', 'escalation', 'baseline'

-- Temporal tracking
as_of_month           DATE             NOT NULL  -- DATE_TRUNC('month', effective_date)
is_current            BOOLEAN          NOT NULL  -- TRUE for end-of-period state
is_active             BOOLEAN          NOT NULL  -- FALSE for terminated employees

-- Audit trail (JSON as TEXT for portability)
source_event_id       VARCHAR(50)      NULL      -- Single source event UUID
source_event_types    TEXT             NULL      -- JSON-encoded array of event types
state_version         INTEGER          NOT NULL  -- ROW_NUMBER() over changes per employee
applied_at            DATE             NOT NULL  -- Deterministic, derived from effective_date
last_updated_at       DATE             NOT NULL  -- Deterministic, same as effective_date
```

### Temporal State Transition Logic

#### Year N State Calculation
```sql
-- Year N uses Year N-1 accumulator data + Year N events
-- No circular dependencies - accumulator reads from int_* sources only

Year 1: baseline_workforce → state_accumulator
Year 2: (Year 1 accumulator + Year 2 events) → Year 2 accumulator
Year 3: (Year 2 accumulator + Year 3 events) → Year 3 accumulator
```

#### State Precedence Rules
1. **Enrollment events** (priority=1): New enrollments or rate changes
2. **Escalation events** (priority=2): Automatic deferral rate increases
3. **Baseline defaults** (priority=3): Initial rates for new hires
4. **Effective date**: Latest date wins within same priority
5. **Tie-breaking**: For same effective_date and priority, order by `source_event_id NULLS LAST`
6. **Monthly state**: If monthly grain needed, generate months CTE and use `LAST_VALUE(...) IGNORE NULLS`

### Data Lineage & Audit Trail

#### Source Data Tracking
```sql
-- Audit trail fields for complete data lineage
source_event_id:      "uuid1"                       -- Single source event UUID
source_event_types:   '["enrollment", "escalation"]' -- JSON-encoded event types as TEXT
state_version:        1, 2, 3...                    -- ROW_NUMBER() over changes per employee
applied_at:           2025-03-15                    -- Deterministic date from effective_date
```

#### Historical Reconstruction
```sql
-- Any employee's deferral rate history can be reconstructed
SELECT employee_id, current_deferral_rate, effective_date, source_type
FROM int_deferral_rate_state_accumulator
WHERE employee_id = '12345' AND scenario_id = 'base'
ORDER BY simulation_year, effective_date
```

## Design Specifications

### Performance Requirements
- [ ] **Execution time**: <5 seconds per simulation year
- [ ] **Memory efficiency**: Incremental materialization with `merge` strategy
- [ ] **Query optimization**: Filter by `simulation_year` to avoid full table scans
- [ ] **Filtering strategy**: Early filtering by `simulation_year` for performance

### Edge Case Handling & Data Quality Tests

#### dbt Tests for Data Validation
```sql
-- Deferral rate bounds validation
{{ dbt_expectations.expect_column_values_to_be_between(
    column_name='current_deferral_rate',
    min_value=0,
    max_value=1
) }}

-- Relationship validation (avoid circular dependencies)
{{ dbt_utils.relationships_where(
    to_ref('int_baseline_workforce'),
    field='employee_id',
    from_field='employee_id'
) }}

-- Exactly one current state per employee/scenario/year
SELECT scenario_id, plan_design_id, employee_id, simulation_year, COUNT(*)
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE is_current = TRUE
GROUP BY 1, 2, 3, 4
HAVING COUNT(*) > 1
```

#### Business Logic Edge Cases
- [ ] **Explicit 0% vs NULL**: Distinguish intentional opt-outs (0%) from missing data
- [ ] **New hires without explicit rate**: Use plan defaults from baseline or plan minimum
- [ ] **Same-timestamp tie-breaking**: enrollment > escalation > baseline, then by source_event_id
- [ ] **Plan min/max bounds**: Apply plan-level rate bounds validation in upstream models
- [ ] **Employee lifecycle**: Join to `int_workforce_active_for_events` to determine `is_active` status

### Integration Points

#### Upstream Dependencies (Sources)
1. `int_enrollment_events` - enrollment deferral rates
2. `int_deferral_escalation_events` - automatic rate increases
3. `int_baseline_workforce` - default rates for new hires
4. Previous year's `int_deferral_rate_state_accumulator` - temporal state

#### Downstream Integration (Consumers)
1. `int_employee_contributions` - contribution calculations
2. Future compliance/reporting models
3. Analytics and dashboards

### Materialization Strategy

#### DuckDB Incremental Configuration
```sql
{{ config(
    materialized='incremental',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year', 'as_of_month'],
    incremental_strategy='insert_overwrite',
    partition_by='simulation_year'
) }}
```

#### Performance Optimizations
- **Filter early** with `WHERE simulation_year = {{ var('simulation_year') }}`
- **Avoid full table scans** with targeted selectors in orchestration
- **Narrow joins** using specific column filters rather than broad table scans
- **DuckDB ignores index configs** - rely on efficient filtering and join strategies

## Technical Tasks

### Phase 1: Core Architecture Design
- [ ] **Finalize schema design** with all required columns and constraints
- [ ] **Define temporal state transition logic** with clear precedence rules
- [ ] **Plan materialization strategy** with DuckDB optimizations
- [ ] **Design audit trail tracking** for complete data lineage

### Phase 2: Integration Planning
- [ ] **Map upstream dependencies** from enrollment and escalation events
- [ ] **Plan downstream integration** with employee contributions model
- [ ] **Define orchestration requirements** for proper execution order
- [ ] **Plan edge case handling** for all identified scenarios

### Phase 3: Performance & Quality Design
- [ ] **Define performance benchmarks** and optimization strategies
- [ ] **Plan data quality validations** and integrity checks
- [ ] **Design testing approach** for state accumulation logic
- [ ] **Document rollback and recovery** procedures

## Dependencies

### Story Dependencies
- **S036-01**: Circular Dependency Analysis (needs dependency mapping)

### Technical Dependencies
- Epic E023 enrollment architecture patterns (proven approach)
- `int_enrollment_events` model existence and schema
- `int_deferral_escalation_events` model (if exists)
- `int_baseline_workforce` model structure

### Blocking for Other Stories
- **S036-03**: Temporal State Tracking Implementation (needs design)
- **S036-04**: Employee Contributions Refactoring (needs integration plan)

## Success Metrics

### Design Quality
- [ ] **Architecture follows Epic E023 pattern** with no circular dependencies
- [ ] **Schema supports all requirements** with proper constraints and data types
- [ ] **Performance design meets targets** with <5 second execution time
- [ ] **Edge cases are properly handled** with documented logic

### Integration Readiness
- [ ] **Upstream dependencies clearly defined** with no missing sources
- [ ] **Downstream integration planned** with existing models
- [ ] **Orchestration requirements documented** for proper execution
- [ ] **Data quality validations designed** for state consistency

## Definition of Done

- [ ] **Complete schema design documented** with all columns and constraints
- [ ] **Temporal state logic fully specified** with precedence rules
- [ ] **Materialization strategy finalized** with DuckDB optimizations
- [ ] **Integration points clearly defined** for upstream and downstream models
- [ ] **Edge case handling documented** for all scenarios
- [ ] **Performance requirements specified** with optimization strategies
- [ ] **Design reviewed and approved** by technical architecture team
- [ ] **Ready for implementation** in Story S036-03

## Improved SQL Implementation Pattern

### Unified Schema Approach
```sql
-- All change CTEs normalized to common schema
WITH enrollment_changes AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    employee_deferral_rate AS new_deferral_rate,
    effective_date, 'enrollment' AS source_type,
    event_id AS source_event_id
  FROM {{ ref('int_enrollment_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

escalation_changes AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    new_deferral_rate, effective_date, 'escalation' AS source_type,
    event_id AS source_event_id
  FROM {{ ref('int_deferral_rate_escalation_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

baseline_defaults AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    baseline_deferral_rate AS new_deferral_rate,
    employee_hire_date AS effective_date, 'baseline' AS source_type,
    NULL AS source_event_id
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employment_status = 'active'
    -- Anti-join: only for employees without prior state or current changes
    AND employee_id NOT IN (
      SELECT employee_id FROM previous_year_state
      UNION SELECT employee_id FROM enrollment_changes
      UNION SELECT employee_id FROM escalation_changes
    )
),

-- Combine with proper precedence
all_changes AS (
  SELECT *, 1 AS event_priority FROM enrollment_changes
  UNION ALL
  SELECT *, 2 AS event_priority FROM escalation_changes
  UNION ALL
  SELECT *, 3 AS event_priority FROM baseline_defaults
),

-- Deterministic precedence resolution
ranked_changes AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY scenario_id, plan_design_id, employee_id
      ORDER BY event_priority ASC, effective_date DESC, source_event_id NULLS LAST
    ) AS rn
  FROM all_changes
)

SELECT
  scenario_id, plan_design_id, employee_id,
  new_deferral_rate AS current_deferral_rate,
  effective_date, source_type, source_event_id,
  {{ var('simulation_year') }} AS simulation_year,
  DATE_TRUNC('month', effective_date) AS as_of_month,
  TRUE AS is_current,
  ROW_NUMBER() OVER (
    PARTITION BY scenario_id, plan_design_id, employee_id
    ORDER BY effective_date, event_priority
  ) AS state_version,
  effective_date AS applied_at,
  effective_date AS last_updated_at
FROM ranked_changes
WHERE rn = 1
```

### Monthly State Expansion (Optional)
```sql
-- If monthly grain is required, expand to monthly states
WITH month_spine AS (
  SELECT DATE_TRUNC('month', DATE '{{ var("simulation_year") }}-01-01' + INTERVAL (n) MONTH) AS month_date
  FROM GENERATE_SERIES(0, 11) AS t(n)
),

employee_months AS (
  SELECT DISTINCT e.scenario_id, e.plan_design_id, e.employee_id, m.month_date
  FROM ranked_changes e
  CROSS JOIN month_spine m
),

monthly_state AS (
  SELECT
    em.*,
    LAST_VALUE(rc.current_deferral_rate) IGNORE NULLS OVER (
      PARTITION BY em.scenario_id, em.plan_design_id, em.employee_id
      ORDER BY em.month_date
      ROWS UNBOUNDED PRECEDING
    ) AS current_deferral_rate,
    em.month_date = DATE_TRUNC('month', DATE '{{ var("simulation_year") }}-12-31') AS is_current
  FROM employee_months em
  LEFT JOIN ranked_changes rc
    ON em.scenario_id = rc.scenario_id
    AND em.plan_design_id = rc.plan_design_id
    AND em.employee_id = rc.employee_id
    AND DATE_TRUNC('month', rc.effective_date) = em.month_date
)
```

## Notes

This design story is critical for ensuring the state accumulator implementation follows proven patterns from Epic E023 while addressing the specific requirements of deferral rate tracking. The design must eliminate circular dependencies while maintaining data consistency and audit trail requirements.

### Key Implementation Notes
- **Upstream model reference corrected**: `int_deferral_rate_escalation_events` (not `int_deferral_escalation_events`)
- **Schema normalization**: All CTEs use common schema with `scenario_id`, `plan_design_id` propagation
- **Deterministic precedence**: enrollment > escalation > baseline, then latest effective_date
- **Baseline seeding**: Anti-join approach prevents all baseline records after Year 1
- **Materialization**: `merge` strategy with proper unique_key, not `insert_overwrite`
- **Audit fields**: Deterministic timestamps, single source_event_id, JSON as TEXT for portability
