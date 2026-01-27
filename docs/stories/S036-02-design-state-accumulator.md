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
-- DUCKDB PERFORMANCE OPTIMIZATION: Vectorized columnar processing with memory-efficient joins
-- CRITICAL: Source from int_* models, NEVER from fct_yearly_events to avoid circular dependency

{{ config(
    materialized='incremental',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    incremental_strategy='merge'
) }}

-- DuckDB Performance Settings (applied at session level)
{% if var('duckdb_optimize', true) %}
  {{ log("Applying DuckDB performance optimizations", info=true) }}
{% endif %}

-- OPTIMIZED: Use projected columns only, leverage columnar compression
WITH previous_year_state AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    current_deferral_rate, effective_date, employment_status,
    hce_status, plan_transfer_reason, is_retroactive_adjustment,
    simulation_year, last_updated_at,
    -- Pre-computed derived columns for faster joins
    year_month, employee_year
  FROM {{ ref('int_deferral_rate_state_accumulator') }}
  WHERE simulation_year = {{ var('simulation_year') }} - 1
    -- DUCKDB OPTIMIZATION: Early filtering for columnar efficiency
    AND is_current = true  -- Only current state records
),

-- OPTIMIZED: Employment lifecycle with hash join optimization
current_year_employment_status AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    -- Use TINYINT enums for memory efficiency
    CASE employment_status
      WHEN 'active' THEN 1::TINYINT
      WHEN 'terminated' THEN 2::TINYINT
      WHEN 'rehired' THEN 3::TINYINT
      ELSE 4::TINYINT
    END as employment_status,
    termination_date, rehire_date,
    -- Convert termination reasons to TINYINT enums
    CASE termination_reason
      WHEN 'voluntary' THEN 1::TINYINT
      WHEN 'involuntary' THEN 2::TINYINT
      WHEN 'retirement' THEN 3::TINYINT
      WHEN 'death' THEN 4::TINYINT
      ELSE 5::TINYINT
    END as termination_reason,
    eligibility_start_date,
    -- Pre-computed composite keys for faster joins
    hash(employee_id) as employee_id_hash,
    ({{ var('simulation_year') }} * 100000 + hash(employee_id) % 100000)::BIGINT as employee_year
  FROM {{ ref('int_workforce_active_for_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    -- DUCKDB OPTIMIZATION: Filter early to reduce join data volume
    AND employment_status IN ('active', 'terminated', 'rehired')
),

-- HCE status determination for rate restrictions
current_year_hce_status AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    hce_status, hce_determination_date, annual_compensation,
    ownership_percentage, officer_status
  FROM {{ ref('int_hce_determination') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

-- Plan transfer tracking for M&A scenarios
current_year_plan_transfers AS (
  SELECT
    scenario_id, employee_id,
    old_plan_design_id, new_plan_design_id,
    transfer_date, transfer_reason,
    rate_preservation_flag, event_id as transfer_event_id
  FROM {{ ref('int_plan_transfer_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

-- Retroactive adjustment tracking for backdated changes
current_year_retroactive_adjustments AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    original_deferral_rate, adjusted_deferral_rate,
    original_effective_date, adjustment_effective_date,
    adjustment_reason, event_id as adjustment_event_id
  FROM {{ ref('int_retroactive_deferral_adjustments') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

current_year_enrollment_changes AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    employee_deferral_rate as new_deferral_rate, effective_date,
    'enrollment' as source_type, event_id as source_event_id,
    FALSE as is_retroactive_adjustment
  FROM {{ ref('int_enrollment_events') }} e
  INNER JOIN current_year_employment_status emp
    ON e.employee_id = emp.employee_id
    AND e.scenario_id = emp.scenario_id
    AND e.plan_design_id = emp.plan_design_id
  WHERE e.simulation_year = {{ var('simulation_year') }}
    AND e.employee_deferral_rate IS NOT NULL
    AND emp.employment_status = 'active'
    -- Only include enrollments within eligibility window
    AND e.effective_date >= emp.eligibility_start_date
),

current_year_escalation_changes AS (
  SELECT
    scenario_id, plan_design_id, employee_id,
    new_deferral_rate, effective_date,
    'escalation' as source_type, event_id as source_event_id,
    FALSE as is_retroactive_adjustment
  FROM {{ ref('int_deferral_rate_escalation_events') }} esc
  INNER JOIN current_year_employment_status emp
    ON esc.employee_id = emp.employee_id
    AND esc.scenario_id = emp.scenario_id
    AND esc.plan_design_id = emp.plan_design_id
  WHERE esc.simulation_year = {{ var('simulation_year') }}
    AND esc.new_deferral_rate IS NOT NULL
    AND emp.employment_status = 'active'
    -- Escalations only apply to active participants
    AND (emp.termination_date IS NULL OR esc.effective_date <= emp.termination_date)
),

-- HCE rate restriction application
hce_restricted_changes AS (
  SELECT
    c.scenario_id, c.plan_design_id, c.employee_id,
    -- Apply HCE rate restrictions based on plan limits
    CASE
      WHEN hce.hce_status = TRUE AND pd.hce_max_deferral_rate IS NOT NULL
      THEN LEAST(c.new_deferral_rate, pd.hce_max_deferral_rate)
      ELSE c.new_deferral_rate
    END as new_deferral_rate,
    c.effective_date, c.source_type, c.source_event_id, c.is_retroactive_adjustment
  FROM (
    SELECT * FROM current_year_enrollment_changes
    UNION ALL
    SELECT * FROM current_year_escalation_changes
  ) c
  LEFT JOIN current_year_hce_status hce
    ON c.employee_id = hce.employee_id
    AND c.scenario_id = hce.scenario_id
    AND c.plan_design_id = hce.plan_design_id
  LEFT JOIN {{ ref('dim_plan_design') }} pd
    ON c.plan_design_id = pd.plan_design_id
),

-- Plan transfer deferral rate preservation logic
plan_transfer_adjustments AS (
  SELECT
    pt.scenario_id, pt.new_plan_design_id as plan_design_id, pt.employee_id,
    CASE
      WHEN pt.rate_preservation_flag = TRUE
      THEN pys.current_deferral_rate  -- Preserve rate from old plan
      ELSE npd.default_deferral_rate  -- Use new plan default
    END as new_deferral_rate,
    pt.transfer_date as effective_date,
    'plan_transfer' as source_type,
    pt.transfer_event_id as source_event_id,
    FALSE as is_retroactive_adjustment
  FROM current_year_plan_transfers pt
  LEFT JOIN previous_year_state pys
    ON pt.employee_id = pys.employee_id
    AND pt.scenario_id = pys.scenario_id
    AND pt.old_plan_design_id = pys.plan_design_id
  LEFT JOIN {{ ref('dim_plan_design') }} npd
    ON pt.new_plan_design_id = npd.plan_design_id
),

-- Retroactive adjustment processing for backdated changes
retroactive_adjustment_changes AS (
  SELECT
    ra.scenario_id, ra.plan_design_id, ra.employee_id,
    ra.adjusted_deferral_rate as new_deferral_rate,
    ra.adjustment_effective_date as effective_date,
    'retroactive_adjustment' as source_type,
    ra.adjustment_event_id as source_event_id,
    TRUE as is_retroactive_adjustment
  FROM current_year_retroactive_adjustments ra
  INNER JOIN current_year_employment_status emp
    ON ra.employee_id = emp.employee_id
    AND ra.scenario_id = emp.scenario_id
    AND ra.plan_design_id = emp.plan_design_id
  WHERE emp.employment_status IN ('active', 'terminated')  -- Allow adjustments for terminated employees
),

baseline_defaults AS (
  SELECT
    bw.scenario_id, bw.plan_design_id, bw.employee_id,
    bw.baseline_deferral_rate as new_deferral_rate,
    bw.employee_hire_date as effective_date,
    'baseline' as source_type, NULL as source_event_id,
    FALSE as is_retroactive_adjustment
  FROM {{ ref('int_baseline_workforce') }} bw
  INNER JOIN current_year_employment_status emp
    ON bw.employee_id = emp.employee_id
    AND bw.scenario_id = emp.scenario_id
    AND bw.plan_design_id = emp.plan_design_id
  WHERE bw.simulation_year = {{ var('simulation_year') }}
    AND bw.employment_status = 'active'
    AND emp.employment_status = 'active'
    -- Only include employees eligible for participation
    AND bw.employee_hire_date >= emp.eligibility_start_date
  ),

existing_employees AS (
  SELECT DISTINCT employee_id FROM previous_year_state
  UNION
  SELECT DISTINCT employee_id FROM hce_restricted_changes WHERE employee_id IS NOT NULL
  UNION
  SELECT DISTINCT employee_id FROM plan_transfer_adjustments WHERE employee_id IS NOT NULL
  UNION
  SELECT DISTINCT employee_id FROM retroactive_adjustment_changes WHERE employee_id IS NOT NULL
),

filtered_baseline_defaults AS (
  SELECT
    b.scenario_id, b.plan_design_id, b.employee_id,
    b.baseline_deferral_rate as new_deferral_rate,
    b.employee_hire_date as effective_date,
    'baseline' as source_type, NULL as source_event_id,
    FALSE as is_retroactive_adjustment
  FROM {{ ref('int_baseline_workforce') }} b
  LEFT JOIN existing_employees e ON b.employee_id = e.employee_id
  WHERE b.simulation_year = {{ var('simulation_year') }}
    AND b.employment_status = 'active'
    AND e.employee_id IS NULL  -- Anti-join: only new employees
),

-- Combine all deferral rate changes with enhanced precedence
-- Retroactive adjustments (0) > Enrollment (1) > Plan transfers (2) > escalation (3) > baseline (4)
unified_state_changes AS (
  SELECT *, 0 as event_priority FROM retroactive_adjustment_changes
  UNION ALL
  SELECT *, 1 as event_priority FROM hce_restricted_changes
  UNION ALL
  SELECT *, 2 as event_priority FROM plan_transfer_adjustments
  UNION ALL
  SELECT *, 4 as event_priority FROM filtered_baseline_defaults
),

-- Deterministic precedence: enrollment > escalation > baseline, then latest effective_date
-- Enhanced with proper NULL handling and deterministic tie-breaking
final_state_by_employee AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY scenario_id, plan_design_id, employee_id
      ORDER BY
        event_priority ASC,
        effective_date DESC NULLS LAST,
        COALESCE(source_event_id, 'BASELINE') ASC  -- Deterministic NULL handling
    ) as rn
  FROM unified_state_changes
)

SELECT
  -- Primary UUID and core identification
  gen_random_uuid() as accumulator_id,
  fse.scenario_id,
  fse.plan_design_id,
  fse.employee_id,
  fse.new_deferral_rate as current_deferral_rate,
  fse.effective_date,
  {{ var('simulation_year') }} as simulation_year,
  fse.source_type,
  fse.source_event_id,
  fse.is_retroactive_adjustment,

  -- Employment lifecycle integration
  COALESCE(emp.employment_status, 'unknown') as employment_status,
  emp.termination_date,
  emp.rehire_date,
  emp.termination_reason,
  emp.eligibility_start_date,

  -- HCE status integration with rate restrictions
  COALESCE(hce.hce_status, FALSE) as hce_status,
  hce.hce_determination_date,
  hce.annual_compensation,
  hce.ownership_percentage,
  hce.officer_status,

  -- Plan transfer tracking for M&A scenarios
  pt.old_plan_design_id as previous_plan_design_id,
  pt.transfer_date as plan_transfer_date,
  pt.transfer_reason as plan_transfer_reason,
  pt.rate_preservation_flag,

  -- Retroactive adjustment tracking
  ra.original_deferral_rate,
  ra.original_effective_date,
  ra.adjustment_reason,

  -- COMPREHENSIVE COST ATTRIBUTION FRAMEWORK
  -- ==============================================

  -- Primary cost tracking identifiers
  gen_random_uuid() as cost_allocation_id,
  gen_random_uuid() as cost_event_id,
  gen_random_uuid() as cost_driver_id,

  -- Temporal cost periods with microsecond precision
  CAST(fse.effective_date AS TIMESTAMP(6)) as cost_period_start,
  CAST(DATE_ADD('month', 1, fse.effective_date) - INTERVAL 1 MICROSECOND AS TIMESTAMP(6)) as cost_period_end,
  DATE_TRUNC('month', fse.effective_date) as cost_allocation_month,
  DATE_TRUNC('quarter', fse.effective_date) as cost_allocation_quarter,

  -- ORGANIZATIONAL HIERARCHY INTEGRATION
  -- ====================================

  -- Primary organizational dimensions
  COALESCE(bw.department_code, 'UNK') as department_code,
  COALESCE(bw.department_name, 'Unknown Department') as department_name,
  COALESCE(bw.cost_center_id, 'CC_DEFAULT') as cost_center_id,
  COALESCE(bw.cost_center_name, 'Default Cost Center') as cost_center_name,

  -- Geographic attribution
  COALESCE(bw.work_location_code, 'REMOTE') as work_location_code,
  COALESCE(bw.work_location_name, 'Remote/Unknown') as work_location_name,
  COALESCE(bw.region_code, 'GLOBAL') as region_code,
  COALESCE(bw.region_name, 'Global Region') as region_name,
  COALESCE(bw.country_code, 'US') as country_code,

  -- Functional organization
  COALESCE(bw.division_code, 'CORP') as division_code,
  COALESCE(bw.division_name, 'Corporate') as division_name,
  COALESCE(bw.business_unit_code, 'BU_DEFAULT') as business_unit_code,
  COALESCE(bw.business_unit_name, 'Default Business Unit') as business_unit_name,

  -- Management hierarchy for cost rollup
  COALESCE(bw.manager_employee_id, 'MGR_UNKNOWN') as manager_employee_id,
  COALESCE(bw.manager_cost_center, bw.cost_center_id, 'CC_DEFAULT') as manager_cost_center,
  COALESCE(bw.org_level, 1) as org_hierarchy_level,

  -- MULTI-DIMENSIONAL COST ATTRIBUTION
  -- ===================================

  -- Primary cost allocation type with enhanced granularity
  CASE
    WHEN fse.source_type = 'retroactive_adjustment' THEN 'compliance_adjustment'
    WHEN fse.source_type = 'plan_transfer' THEN 'administrative_transfer'
    WHEN fse.source_type = 'enrollment' THEN 'participant_enrollment'
    WHEN fse.source_type = 'escalation' THEN 'automatic_escalation'
    WHEN fse.source_type = 'baseline' THEN 'new_hire_setup'
    ELSE 'operational_standard'
  END as cost_allocation_type,

  -- Project-based cost attribution
  COALESCE(bw.project_code, 'OVERHEAD') as project_code,
  COALESCE(bw.project_name, 'General Overhead') as project_name,
  CASE
    WHEN bw.project_code IS NOT NULL THEN 'project_direct'
    WHEN bw.department_code IN ('IT', 'TECH', 'ENG') THEN 'operational_direct'
    ELSE 'overhead_allocated'
  END as project_cost_type,

  -- Team-based attribution for agile organizations
  COALESCE(bw.team_id, 'TEAM_UNKNOWN') as team_id,
  COALESCE(bw.team_name, 'Unknown Team') as team_name,
  COALESCE(bw.squad_id, bw.team_id, 'SQUAD_UNKNOWN') as squad_id,
  CASE
    WHEN bw.team_id IS NOT NULL THEN bw.team_id
    WHEN bw.department_code IS NOT NULL THEN CONCAT(bw.department_code, '_DEFAULT_TEAM')
    ELSE 'UNASSIGNED_TEAM'
  END as cost_attribution_team,

  -- Functional cost drivers with detailed breakdown
  CASE
    WHEN fse.source_type = 'enrollment' AND hce.hce_status = TRUE THEN 'hce_enrollment_driver'
    WHEN fse.source_type = 'enrollment' AND hce.hce_status = FALSE THEN 'nhce_enrollment_driver'
    WHEN fse.source_type = 'escalation' THEN 'automatic_escalation_driver'
    WHEN fse.source_type = 'retroactive_adjustment' AND ra.adjustment_reason = 'compliance' THEN 'compliance_driver'
    WHEN fse.source_type = 'plan_transfer' THEN 'ma_integration_driver'
    ELSE 'standard_operational_driver'
  END as cost_driver_category,

  -- FINANCIAL REPORTING INTEGRATION
  -- ================================

  -- Fiscal year and period mapping
  {{ var('simulation_year') }} as financial_year,
  CASE
    WHEN MONTH(fse.effective_date) IN (1,2,3) THEN 1
    WHEN MONTH(fse.effective_date) IN (4,5,6) THEN 2
    WHEN MONTH(fse.effective_date) IN (7,8,9) THEN 3
    ELSE 4
  END as financial_quarter,

  -- Budget period alignment
  CONCAT({{ var('simulation_year') }}, '-Q',
    CASE
      WHEN MONTH(fse.effective_date) IN (1,2,3) THEN '1'
      WHEN MONTH(fse.effective_date) IN (4,5,6) THEN '2'
      WHEN MONTH(fse.effective_date) IN (7,8,9) THEN '3'
      ELSE '4'
    END
  ) as budget_period,

  -- GL Account mapping for financial systems
  CASE
    WHEN fse.source_type = 'retroactive_adjustment' THEN '6201-001' -- Compliance adjustments
    WHEN fse.source_type = 'plan_transfer' THEN '6202-001'         -- M&A integration costs
    WHEN fse.source_type = 'enrollment' THEN '6200-001'            -- Standard enrollment costs
    WHEN fse.source_type = 'escalation' THEN '6200-002'            -- Escalation processing costs
    ELSE '6200-999'                                                -- Miscellaneous HR costs
  END as gl_account_code,

  CASE
    WHEN fse.source_type = 'retroactive_adjustment' THEN 'Retirement Plan Compliance Adjustments'
    WHEN fse.source_type = 'plan_transfer' THEN 'M&A Plan Integration Costs'
    WHEN fse.source_type = 'enrollment' THEN 'Retirement Plan Enrollment Processing'
    WHEN fse.source_type = 'escalation' THEN 'Automatic Deferral Rate Escalation'
    ELSE 'General Retirement Plan Administration'
  END as gl_account_description,

  -- Cost center budget allocation mapping
  CONCAT(COALESCE(bw.cost_center_id, 'CC_DEFAULT'), '-', {{ var('simulation_year') }}) as budget_allocation_key,

  -- COST BASIS AND ATTRIBUTION CALCULATIONS
  -- =======================================

  -- Primary cost basis with employee lifecycle awareness
  COALESCE(bw.annual_salary, 50000.0000) as cost_basis_amount,

  -- Cost attribution rate with multi-dimensional weighting
  CASE
    -- High attribution for compliance-driven changes
    WHEN fse.source_type = 'retroactive_adjustment' THEN CAST(1.500000 AS DECIMAL(8,6))
    -- Standard attribution for enrollment activities
    WHEN fse.source_type = 'enrollment' THEN CAST(1.000000 AS DECIMAL(8,6))
    -- Medium attribution for plan transfers (shared cost)
    WHEN fse.source_type = 'plan_transfer' THEN CAST(0.750000 AS DECIMAL(8,6))
    -- Lower attribution for automated escalations
    WHEN fse.source_type = 'escalation' THEN CAST(0.500000 AS DECIMAL(8,6))
    -- Minimal attribution for baseline setup
    WHEN fse.source_type = 'baseline' THEN CAST(0.250000 AS DECIMAL(8,6))
    ELSE CAST(1.000000 AS DECIMAL(8,6))
  END as cost_attribution_rate,

  -- Calculated cost allocation amounts
  ROUND(
    COALESCE(bw.annual_salary, 50000.0000) *
    CASE
      WHEN fse.source_type = 'retroactive_adjustment' THEN 1.500000
      WHEN fse.source_type = 'enrollment' THEN 1.000000
      WHEN fse.source_type = 'plan_transfer' THEN 0.750000
      WHEN fse.source_type = 'escalation' THEN 0.500000
      WHEN fse.source_type = 'baseline' THEN 0.250000
      ELSE 1.000000
    END * 0.001, -- Convert to cost per thousand of salary
    2
  ) as allocated_cost_amount,

  -- Department-level cost sharing calculations
  CASE
    WHEN bw.department_code IN ('HR', 'ADMIN') THEN 1.000000 -- Full allocation to administrative depts
    WHEN bw.department_code IN ('IT', 'TECH') THEN 0.800000  -- Reduced for technology depts
    WHEN bw.department_code IN ('SALES', 'MKT') THEN 0.600000 -- Further reduced for revenue depts
    ELSE 0.750000 -- Standard allocation for other departments
  END as department_cost_share_rate,

  -- Temporal grain and audit fields with microsecond precision
  DATE_TRUNC('month', fse.effective_date) as as_of_month,
  TRUE as is_current,
  fse.event_priority,
  ROW_NUMBER() OVER (
    PARTITION BY fse.scenario_id, fse.plan_design_id, fse.employee_id
    ORDER BY fse.effective_date, fse.event_priority
  ) as state_version,

  -- Enhanced audit trail with UUID tracking
  CAST(fse.effective_date AS TIMESTAMP(6)) as applied_at,
  CURRENT_TIMESTAMP(6) as last_updated_at,
  CURRENT_TIMESTAMP(6) as created_at,
  gen_random_uuid() as audit_trail_id,

  -- Financial audit compliance fields with enhanced data integrity
  ENCODE(SHA256(
    CONCAT(
      COALESCE(CAST(fse.employee_id AS VARCHAR), ''),
      COALESCE(CAST(fse.new_deferral_rate AS VARCHAR), ''),
      COALESCE(CAST(fse.effective_date AS VARCHAR), ''),
      COALESCE(fse.source_type, ''),
      COALESCE(CAST({{ var('simulation_year') }} AS VARCHAR), ''),
      COALESCE(CAST(fse.is_retroactive_adjustment AS VARCHAR), ''),
      COALESCE(CAST(COALESCE(emp.employment_status, 'unknown') AS VARCHAR), ''),
      COALESCE(CAST(COALESCE(hce.hce_status, FALSE) AS VARCHAR), '')
    )
  ), 'hex') as financial_audit_hash,

  -- Regulatory flags for compliance monitoring
  CASE
    WHEN fse.source_type = 'retroactive_adjustment' THEN TRUE
    WHEN hce.hce_status = TRUE AND fse.new_deferral_rate > pd.hce_max_deferral_rate THEN TRUE
    WHEN emp.employment_status = 'terminated' AND fse.effective_date > emp.termination_date THEN TRUE
    ELSE FALSE
  END as regulatory_flag,
  '2.0' as compliance_version,

  -- Employment status determination with lifecycle awareness
  CASE
    WHEN emp.employment_status = 'active' THEN TRUE
    WHEN emp.employment_status = 'terminated' AND fse.effective_date <= COALESCE(emp.termination_date, fse.effective_date) THEN TRUE
    WHEN emp.rehire_date IS NOT NULL AND fse.effective_date >= emp.rehire_date THEN TRUE
    ELSE FALSE
  END as is_active,

  -- Cross-year continuity validation fields
  pys.current_deferral_rate as previous_year_rate,
  pys.effective_date as previous_year_effective_date,
  pys.simulation_year as previous_simulation_year,

  -- State consistency flags for validation
  CASE
    WHEN pys.employee_id IS NULL THEN 'new_employee'
    WHEN pys.current_deferral_rate != fse.new_deferral_rate THEN 'rate_changed'
    WHEN pys.plan_design_id != fse.plan_design_id THEN 'plan_transferred'
    ELSE 'no_change'
  END as state_change_type

FROM final_state_by_employee fse

-- Employment lifecycle integration
LEFT JOIN current_year_employment_status emp
  ON fse.employee_id = emp.employee_id
  AND fse.scenario_id = emp.scenario_id
  AND fse.plan_design_id = emp.plan_design_id

-- HCE status integration
LEFT JOIN current_year_hce_status hce
  ON fse.employee_id = hce.employee_id
  AND fse.scenario_id = hce.scenario_id
  AND fse.plan_design_id = hce.plan_design_id

-- Plan transfer tracking
LEFT JOIN current_year_plan_transfers pt
  ON fse.employee_id = pt.employee_id
  AND fse.scenario_id = pt.scenario_id
  AND fse.source_event_id = pt.transfer_event_id

-- Retroactive adjustment tracking
LEFT JOIN current_year_retroactive_adjustments ra
  ON fse.employee_id = ra.employee_id
  AND fse.scenario_id = ra.scenario_id
  AND fse.plan_design_id = ra.plan_design_id
  AND fse.source_event_id = ra.adjustment_event_id

-- Baseline workforce data for cost attribution
LEFT JOIN {{ ref('int_baseline_workforce') }} bw
  ON fse.employee_id = bw.employee_id
  AND bw.simulation_year = {{ var('simulation_year') }}

-- Plan design for HCE restrictions
LEFT JOIN {{ ref('dim_plan_design') }} pd
  ON fse.plan_design_id = pd.plan_design_id

-- Previous year state for continuity validation
LEFT JOIN previous_year_state pys
  ON fse.employee_id = pys.employee_id
  AND fse.scenario_id = pys.scenario_id
  AND fse.plan_design_id = pys.plan_design_id

WHERE fse.rn = 1
```

### Schema Design Specifications

#### Primary Keys & Uniqueness
```sql
-- Enforce via dbt tests, not DDL constraints
-- Primary key uniqueness test
{{ dbt_utils.unique_combination_of_columns(
    columns=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year']
) }}

-- Ensure exactly one current row per employee/year
{{ test_exactly_one_current_state_per_employee_year() }}
```

#### DuckDB-Optimized Column Specifications
```sql
-- DUCKDB PERFORMANCE OPTIMIZATIONS:
-- 1. Use smaller integer types for memory efficiency
-- 2. Use HUGEINT for UUIDs (16-byte native type)
-- 3. Minimize VARCHAR lengths based on actual data
-- 4. Use INTEGER dates where appropriate for faster joins
-- 5. Group frequently-accessed columns for columnar efficiency

-- Primary HUGEINT UUID for optimal columnar storage
accumulator_id        HUGEINT          NOT NULL DEFAULT random() -- DuckDB native 16-byte UUID

-- Core identification with memory-optimized types
scenario_id           VARCHAR(36)      NOT NULL  -- UUID standard length
plan_design_id        VARCHAR(36)      NOT NULL  -- UUID standard length
employee_id           VARCHAR(20)      NOT NULL  -- Typical employee ID length
simulation_year       SMALLINT         NOT NULL  -- Years fit in SMALLINT (saves 2 bytes per row)

-- Deferral rate state with optimal precision for DuckDB
current_deferral_rate FLOAT            NOT NULL  -- DuckDB FLOAT more efficient than DECIMAL for rates
effective_date        DATE             NOT NULL
effective_date_int    INTEGER          NOT NULL  -- Pre-computed epoch days for faster joins
source_type           TINYINT          NOT NULL  -- Enum: 1=enrollment, 2=escalation, 3=baseline, 4=plan_transfer, 5=retroactive
is_retroactive_adjustment BOOLEAN      NOT NULL DEFAULT FALSE

-- Employment lifecycle with compact representations
employment_status     TINYINT          NOT NULL  -- Enum: 1=active, 2=terminated, 3=rehired, 4=unknown
termination_date      DATE             NULL
rehire_date          DATE             NULL
termination_reason    TINYINT          NULL      -- Enum for common termination reasons
eligibility_start_date DATE            NULL

-- HCE status with memory-efficient types
hce_status            BOOLEAN          NOT NULL DEFAULT FALSE
hce_determination_date DATE            NULL
annual_compensation   INTEGER          NULL      -- Whole dollars, no cents needed
ownership_percentage  FLOAT            NULL      -- More efficient than DECIMAL for percentages
officer_status        BOOLEAN          NULL

-- Plan transfer tracking
previous_plan_design_id VARCHAR(36)    NULL      -- UUID standard length
plan_transfer_date    DATE             NULL
plan_transfer_reason  TINYINT          NULL      -- Enum for transfer reasons
rate_preservation_flag BOOLEAN         NULL

-- Retroactive adjustment tracking
original_deferral_rate FLOAT           NULL      -- Consistent with current_deferral_rate
original_effective_date DATE           NULL
adjustment_reason     TINYINT          NULL      -- Enum for adjustment reasons

-- COMPREHENSIVE COST ATTRIBUTION SCHEMA (UUID-based precision)
-- =============================================================

-- Primary cost tracking identifiers with UUID precision
cost_allocation_id    HUGEINT          NOT NULL DEFAULT random() -- DuckDB native UUID
cost_event_id         HUGEINT          NOT NULL DEFAULT random() -- Cost event tracking UUID
cost_driver_id        HUGEINT          NOT NULL DEFAULT random() -- Cost driver attribution UUID

-- Temporal cost periods with enhanced precision
cost_period_start     TIMESTAMP(6)     NOT NULL  -- Microsecond precision for cost periods
cost_period_end       TIMESTAMP(6)     NOT NULL  -- Microsecond precision cost period end
cost_allocation_month DATE             NOT NULL  -- Month-level cost allocation
cost_allocation_quarter DATE           NOT NULL  -- Quarter-level cost allocation

-- ORGANIZATIONAL HIERARCHY FIELDS (optimized for analytics)
-- ==========================================================

-- Primary organizational dimensions with efficient types
department_code       VARCHAR(10)      NOT NULL  -- Department code (e.g., 'IT', 'HR', 'SALES')
department_name       VARCHAR(100)     NOT NULL  -- Department full name
cost_center_id        VARCHAR(20)      NOT NULL  -- Cost center identifier
cost_center_name      VARCHAR(100)     NOT NULL  -- Cost center full name

-- Geographic attribution fields
work_location_code    VARCHAR(10)      NOT NULL  -- Location code (e.g., 'NYC', 'SF', 'REMOTE')
work_location_name    VARCHAR(100)     NOT NULL  -- Location full name
region_code           VARCHAR(10)      NOT NULL  -- Region code (e.g., 'NAM', 'EMEA', 'APAC')
region_name           VARCHAR(50)      NOT NULL  -- Region full name
country_code          VARCHAR(3)       NOT NULL  -- ISO country code

-- Functional organization hierarchy
division_code         VARCHAR(10)      NOT NULL  -- Division code
division_name         VARCHAR(100)     NOT NULL  -- Division full name
business_unit_code    VARCHAR(20)      NOT NULL  -- Business unit code
business_unit_name    VARCHAR(100)     NOT NULL  -- Business unit full name

-- Management hierarchy for cost rollup
manager_employee_id   VARCHAR(20)      NOT NULL  -- Manager employee ID
manager_cost_center   VARCHAR(20)      NOT NULL  -- Manager's cost center
org_hierarchy_level   TINYINT          NOT NULL  -- Organizational level (1-10)

-- MULTI-DIMENSIONAL COST ATTRIBUTION FIELDS
-- ==========================================

-- Enhanced cost allocation types with granular categorization
cost_allocation_type  VARCHAR(30)      NOT NULL  -- Enhanced: compliance_adjustment, administrative_transfer, etc.

-- Project-based cost attribution
project_code          VARCHAR(20)      NOT NULL  -- Project code for direct attribution
project_name          VARCHAR(100)     NOT NULL  -- Project full name
project_cost_type     VARCHAR(20)      NOT NULL  -- Enum: project_direct, operational_direct, overhead_allocated

-- Team-based attribution for agile organizations
team_id               VARCHAR(20)      NOT NULL  -- Team identifier
team_name             VARCHAR(100)     NOT NULL  -- Team full name
squad_id              VARCHAR(20)      NOT NULL  -- Squad/sub-team identifier
cost_attribution_team VARCHAR(50)      NOT NULL  -- Cost attribution team mapping

-- Cost driver categorization with detailed breakdown
cost_driver_category  VARCHAR(30)      NOT NULL  -- Detailed cost driver (hce_enrollment_driver, etc.)

-- FINANCIAL REPORTING INTEGRATION
-- ================================

-- Enhanced financial reporting fields
financial_year        SMALLINT         NOT NULL  -- Financial year
financial_quarter     TINYINT          NOT NULL  -- Financial quarter (1-4)
budget_period         VARCHAR(10)      NOT NULL  -- Budget period (YYYY-Q#)

-- GL Account mapping for financial systems integration
gl_account_code       VARCHAR(20)      NOT NULL  -- GL account code (e.g., '6200-001')
gl_account_description VARCHAR(200)    NOT NULL  -- GL account description
budget_allocation_key VARCHAR(50)      NOT NULL  -- Budget allocation key (cost_center-year)

-- COST BASIS AND ATTRIBUTION CALCULATIONS
-- =======================================

-- Primary cost calculations with enhanced precision
cost_basis_amount     DECIMAL(12,4)    NOT NULL  -- Primary cost basis (salary)
cost_attribution_rate DECIMAL(8,6)     NOT NULL  -- Multi-dimensional attribution rate
allocated_cost_amount DECIMAL(12,2)    NOT NULL  -- Calculated allocated cost
department_cost_share_rate DECIMAL(6,6) NOT NULL -- Department-level cost sharing rate

-- Temporal tracking with optimal data types
as_of_month           DATE             NOT NULL  -- Month truncation
as_of_month_int       INTEGER          NOT NULL  -- Pre-computed for faster grouping
is_current            BOOLEAN          NOT NULL
is_active             BOOLEAN          NOT NULL
event_priority        TINYINT          NOT NULL  -- Priorities 0-4 fit in TINYINT

-- Cross-year continuity validation
previous_year_rate    FLOAT            NULL      -- Consistent with current_deferral_rate
previous_year_effective_date DATE      NULL
previous_simulation_year SMALLINT      NULL      -- Years fit in SMALLINT
state_change_type     TINYINT          NOT NULL  -- Enum: 1=new_employee, 2=rate_changed, 3=plan_transferred, 4=no_change

-- Enhanced audit trail with DuckDB-optimized types
source_event_id       HUGEINT          NULL      -- DuckDB native UUID
state_version         SMALLINT         NOT NULL  -- Version numbers fit in SMALLINT
applied_at            TIMESTAMP        NOT NULL  -- Standard timestamp precision sufficient
last_updated_at       TIMESTAMP        NOT NULL  -- Standard timestamp precision
created_at            TIMESTAMP        NOT NULL DEFAULT NOW()
audit_trail_id        HUGEINT          NOT NULL DEFAULT random() -- DuckDB native UUID
financial_audit_hash  BLOB             NOT NULL  -- Binary hash storage more efficient than VARCHAR
regulatory_flag       BOOLEAN          NOT NULL DEFAULT FALSE
compliance_version    VARCHAR(10)      NOT NULL DEFAULT '2.0' -- Reduced from VARCHAR(20)

-- DuckDB PERFORMANCE ENHANCEMENTS:
-- Pre-computed derived columns for faster analytics
year_month            INTEGER          NOT NULL  -- YYYYMM format for fast time-series queries
cost_center_year      INTEGER          NOT NULL  -- Composite key for cost center analytics
employee_year         BIGINT           NOT NULL  -- Composite key: employee_id hash + year

-- Columnar optimization: Group related fields for better compression
-- Core business fields (accessed together)
COMMENT ON COLUMN current_deferral_rate IS 'Core business rate - accessed with effective_date and source_type';
COMMENT ON COLUMN effective_date IS 'Core business date - accessed with rate and source';
COMMENT ON COLUMN source_type IS 'Core business source - accessed with rate and date';

-- Audit fields (accessed together for compliance)
COMMENT ON COLUMN applied_at IS 'Audit timestamp - accessed with audit_trail_id and financial_audit_hash';
COMMENT ON COLUMN audit_trail_id IS 'Audit identifier - accessed with applied_at for compliance';
COMMENT ON COLUMN financial_audit_hash IS 'Audit integrity - accessed with timestamps for validation';
```

### Temporal State Transition Logic

#### Year N State Calculation with Employee Lifecycle Integration
```sql
-- Year N uses Year N-1 accumulator data + Year N events + employment status changes
-- No circular dependencies - accumulator reads from int_* sources only

Year 1: baseline_workforce + employment_status + hce_determination → state_accumulator
Year 2: (Year 1 accumulator + Year 2 events + lifecycle_changes + plan_transfers) → Year 2 accumulator
Year 3: (Year 2 accumulator + Year 3 events + retroactive_adjustments + lifecycle_changes) → Year 3 accumulator

-- Cross-year validation ensures continuity:
-- 1. Employment status changes properly update is_active flag
-- 2. Plan transfers preserve or reset deferral rates based on business rules
-- 3. HCE status changes apply rate restrictions retroactively if required
-- 4. Terminated employees can still receive retroactive adjustments
```

#### Enhanced State Precedence Rules with Lifecycle Integration
1. **Retroactive adjustments** (priority=0): Backdated changes with compliance implications
2. **Enrollment events** (priority=1): New enrollments or rate changes (HCE-restricted)
3. **Plan transfers** (priority=2): M&A scenarios with rate preservation logic
4. **Escalation events** (priority=3): Automatic deferral rate increases (employment-status aware)
5. **Baseline defaults** (priority=4): Initial rates for new hires (eligibility-filtered)
6. **Effective date**: Latest date wins within same priority
7. **Employment status filtering**: Events only apply if employee is eligible/active on effective date
8. **HCE rate restrictions**: Applied automatically to all rate changes for HCE employees
9. **Tie-breaking**: For same effective_date and priority, order by `source_event_id NULLS LAST`
10. **Cross-year validation**: State changes must be consistent with employment lifecycle

### Data Lineage & Audit Trail

#### Source Data Tracking with UUID Precision and Lifecycle Integration
```sql
-- Enhanced audit trail fields for financial compliance with employment lifecycle data
accumulator_id:        "550e8400-e29b-41d4-a716-446655440000"  -- Primary UUID for cost modeling
source_event_id:       "6ba7b810-9dad-11d1-80b4-00c04fd430c8"  -- Single source event UUID
cost_allocation_id:    "6ba7b811-9dad-11d1-80b4-00c04fd430c8"  -- Cost event tracking UUID
audit_trail_id:        "6ba7b812-9dad-11d1-80b4-00c04fd430c8"  -- Audit event UUID
source_type:           'enrollment', 'plan_transfer', 'retroactive_adjustment' -- Extended source types
state_version:         1, 2, 3...                             -- ROW_NUMBER() over changes per employee
applied_at:            2025-03-15 14:30:25.123456             -- Microsecond precision timestamp
last_updated_at:       2025-03-15 14:30:25.123456             -- Microsecond precision last update
created_at:            2025-03-15 14:30:25.123456             -- Record creation timestamp

-- Enhanced financial audit hash includes employment lifecycle data
financial_audit_hash:  "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3" -- SHA-256 with employment data
cost_period_start:     2025-03-01 00:00:00.000000             -- Microsecond precision cost period
cost_period_end:       2025-03-31 23:59:59.999999             -- Microsecond precision cost period

-- Employment lifecycle audit fields
employment_status:     'active', 'terminated', 'rehired'      -- Current employment status
termination_date:      2025-06-15                             -- Termination date if applicable
hce_status:           TRUE/FALSE                              -- HCE status for compliance
plan_transfer_date:   2025-04-01                              -- Plan transfer date if applicable
state_change_type:    'rate_changed', 'plan_transferred', 'new_employee' -- Change classification
```

#### Historical Reconstruction with Cost Attribution
```sql
-- Complete employee deferral rate and cost history reconstruction with comprehensive cost attribution
SELECT
    employee_id,
    accumulator_id,
    current_deferral_rate,
    effective_date,
    source_type,
    -- Cost attribution identifiers
    cost_allocation_id,
    cost_event_id,
    cost_driver_id,
    -- Organizational attribution
    department_code,
    department_name,
    cost_center_id,
    cost_center_name,
    work_location_code,
    region_code,
    -- Multi-dimensional cost attribution
    cost_allocation_type,
    project_code,
    team_id,
    cost_driver_category,
    -- Financial integration
    cost_attribution_rate,
    cost_basis_amount,
    allocated_cost_amount,
    gl_account_code,
    budget_allocation_key,
    financial_year,
    financial_quarter,
    budget_period,
    applied_at,
    financial_audit_hash
FROM int_deferral_rate_state_accumulator
WHERE employee_id = '12345' AND scenario_id = 'base'
ORDER BY simulation_year, applied_at, accumulator_id

-- ORGANIZATIONAL COST ATTRIBUTION ANALYSIS
-- =========================================

-- Cost attribution audit trail by organizational hierarchy
SELECT
    division_code,
    division_name,
    department_code,
    department_name,
    cost_center_id,
    cost_center_name,
    cost_allocation_type,
    COUNT(*) as event_count,
    COUNT(DISTINCT employee_id) as unique_employees,
    SUM(allocated_cost_amount) as total_allocated_cost,
    AVG(cost_attribution_rate) as avg_attribution_rate,
    SUM(cost_basis_amount) as total_cost_basis,
    MIN(cost_period_start) as earliest_cost_period,
    MAX(cost_period_end) as latest_cost_period
FROM int_deferral_rate_state_accumulator
WHERE financial_year = 2025
GROUP BY 1,2,3,4,5,6,7
ORDER BY total_allocated_cost DESC

-- Geographic cost distribution analysis
SELECT
    region_code,
    region_name,
    country_code,
    work_location_code,
    work_location_name,
    cost_driver_category,
    COUNT(*) as cost_events,
    COUNT(DISTINCT employee_id) as employees_affected,
    SUM(allocated_cost_amount) as location_cost_total,
    AVG(department_cost_share_rate) as avg_dept_share_rate,
    ROUND(
        SUM(allocated_cost_amount) /
        (SELECT SUM(allocated_cost_amount) FROM int_deferral_rate_state_accumulator WHERE financial_year = 2025) * 100,
        2
    ) as cost_percentage_of_total
FROM int_deferral_rate_state_accumulator
WHERE financial_year = 2025
GROUP BY 1,2,3,4,5,6
ORDER BY location_cost_total DESC

-- MULTI-DIMENSIONAL COST DRIVER ANALYSIS
-- =======================================

-- Project-based cost attribution breakdown
SELECT
    project_code,
    project_name,
    project_cost_type,
    cost_driver_category,
    COUNT(*) as project_events,
    COUNT(DISTINCT employee_id) as project_employees,
    COUNT(DISTINCT cost_center_id) as cost_centers_involved,
    SUM(allocated_cost_amount) as project_total_cost,
    AVG(cost_attribution_rate) as avg_project_attribution,
    MIN(cost_period_start) as project_start_period,
    MAX(cost_period_end) as project_end_period
FROM int_deferral_rate_state_accumulator
WHERE financial_year = 2025
  AND project_code != 'OVERHEAD'
GROUP BY 1,2,3,4
ORDER BY project_total_cost DESC

-- Team-based cost analysis for agile organizations
SELECT
    team_id,
    team_name,
    squad_id,
    cost_attribution_team,
    department_code,
    COUNT(*) as team_cost_events,
    COUNT(DISTINCT employee_id) as team_members_affected,
    SUM(allocated_cost_amount) as team_cost_total,
    AVG(cost_basis_amount) as avg_team_salary_basis,
    AVG(cost_attribution_rate) as avg_team_attribution,
    -- Team cost efficiency metrics
    ROUND(SUM(allocated_cost_amount) / COUNT(DISTINCT employee_id), 2) as cost_per_team_member,
    ROUND(AVG(cost_attribution_rate) * 100, 2) as team_attribution_percentage
FROM int_deferral_rate_state_accumulator
WHERE financial_year = 2025
  AND team_id != 'TEAM_UNKNOWN'
GROUP BY 1,2,3,4,5
ORDER BY team_cost_total DESC

-- FINANCIAL REPORTING INTEGRATION QUERIES
-- ========================================

-- GL Account cost rollup for financial systems
SELECT
    gl_account_code,
    gl_account_description,
    financial_quarter,
    budget_period,
    COUNT(*) as transaction_count,
    COUNT(DISTINCT employee_id) as employees_affected,
    COUNT(DISTINCT cost_center_id) as cost_centers,
    SUM(allocated_cost_amount) as gl_account_total,
    AVG(cost_attribution_rate) as avg_attribution_rate,
    -- Financial reporting metrics
    MIN(cost_period_start) as period_start,
    MAX(cost_period_end) as period_end,
    ROUND(
        SUM(allocated_cost_amount) /
        LAG(SUM(allocated_cost_amount)) OVER (
            PARTITION BY gl_account_code
            ORDER BY financial_quarter
        ) - 1, 4
    ) as quarter_over_quarter_growth
FROM int_deferral_rate_state_accumulator
WHERE financial_year = 2025
GROUP BY 1,2,3,4
ORDER BY gl_account_code, financial_quarter

-- Budget allocation analysis by cost center
SELECT
    cost_center_id,
    cost_center_name,
    budget_allocation_key,
    division_code,
    financial_quarter,
    COUNT(*) as budget_events,
    COUNT(DISTINCT employee_id) as budgeted_employees,
    SUM(allocated_cost_amount) as quarterly_budget_impact,
    SUM(cost_basis_amount) as salary_basis_total,
    -- Budget variance analysis
    AVG(department_cost_share_rate) as avg_dept_cost_share,
    ROUND(
        SUM(allocated_cost_amount) / SUM(cost_basis_amount) * 100, 4
    ) as cost_as_percent_of_salary,
    -- Quarter progression tracking
    ROW_NUMBER() OVER (
        PARTITION BY cost_center_id
        ORDER BY financial_quarter
    ) as quarter_sequence
FROM int_deferral_rate_state_accumulator
WHERE financial_year = 2025
GROUP BY 1,2,3,4,5
ORDER BY cost_center_id, financial_quarter

-- COST VARIANCE ANALYSIS AND ATTRIBUTION ACCURACY
-- ================================================

-- Cost driver performance attribution analysis
SELECT
    cost_driver_category,
    cost_allocation_type,
    source_type,
    COUNT(*) as driver_events,
    COUNT(DISTINCT employee_id) as affected_employees,
    COUNT(DISTINCT cost_center_id) as cost_centers_impacted,
    SUM(allocated_cost_amount) as driver_total_cost,
    AVG(cost_attribution_rate) as avg_driver_attribution,
    STDDEV(cost_attribution_rate) as attribution_rate_variance,
    -- Cost driver efficiency metrics
    ROUND(SUM(allocated_cost_amount) / COUNT(*), 2) as cost_per_event,
    ROUND(SUM(allocated_cost_amount) / COUNT(DISTINCT employee_id), 2) as cost_per_employee,
    -- Attribution accuracy indicators
    CASE
        WHEN STDDEV(cost_attribution_rate) < 0.1 THEN 'HIGH_CONSISTENCY'
        WHEN STDDEV(cost_attribution_rate) < 0.3 THEN 'MEDIUM_CONSISTENCY'
        ELSE 'HIGH_VARIANCE'
    END as attribution_consistency
FROM int_deferral_rate_state_accumulator
WHERE financial_year = 2025
GROUP BY 1,2,3
ORDER BY driver_total_cost DESC

-- Management hierarchy cost rollup analysis
SELECT
    manager_employee_id,
    manager_cost_center,
    org_hierarchy_level,
    COUNT(*) as subordinate_cost_events,
    COUNT(DISTINCT employee_id) as direct_reports_affected,
    COUNT(DISTINCT department_code) as departments_managed,
    SUM(allocated_cost_amount) as management_span_cost,
    AVG(cost_basis_amount) as avg_subordinate_salary,
    AVG(department_cost_share_rate) as avg_dept_share,
    -- Management cost efficiency
    ROUND(SUM(allocated_cost_amount) / COUNT(DISTINCT employee_id), 2) as cost_per_direct_report,
    ROUND(
        SUM(allocated_cost_amount) /
        (SELECT SUM(allocated_cost_amount)
         FROM int_deferral_rate_state_accumulator
         WHERE financial_year = 2025
         AND org_hierarchy_level <= main.org_hierarchy_level) * 100,
        2
    ) as percentage_of_org_level_cost
FROM int_deferral_rate_state_accumulator main
WHERE financial_year = 2025
  AND manager_employee_id != 'MGR_UNKNOWN'
GROUP BY 1,2,3
ORDER BY management_span_cost DESC

-- Financial audit hash verification with cost attribution validation
SELECT
    accumulator_id,
    employee_id,
    cost_allocation_id,
    cost_event_id,
    cost_driver_id,
    financial_audit_hash,
    applied_at,
    -- Hash integrity validation
    CASE
        WHEN LENGTH(financial_audit_hash) = 64
             AND financial_audit_hash ~ '^[a-f0-9]+$'
        THEN 'VALID'
        ELSE 'INVALID'
    END as hash_status,
    -- Cost attribution completeness validation
    CASE
        WHEN cost_allocation_id IS NOT NULL
             AND cost_event_id IS NOT NULL
             AND cost_driver_id IS NOT NULL
             AND allocated_cost_amount > 0
        THEN 'COMPLETE_ATTRIBUTION'
        ELSE 'INCOMPLETE_ATTRIBUTION'
    END as attribution_completeness,
    -- Regulatory compliance validation
    regulatory_flag,
    cost_driver_category,
    allocated_cost_amount
FROM int_deferral_rate_state_accumulator
WHERE regulatory_flag = TRUE
   OR allocated_cost_amount > 1000 -- Material cost threshold
ORDER BY applied_at DESC, allocated_cost_amount DESC
```

## Cost Attribution Architecture & Framework

### Comprehensive Cost Attribution Design Principles

The deferral rate state accumulator incorporates a comprehensive cost attribution framework that enables precise tracking, allocation, and reporting of workforce simulation costs across multiple organizational dimensions. This framework supports enterprise-grade cost modeling with full audit trails and regulatory compliance.

#### Core Cost Attribution Principles

1. **UUID-Based Precision Tracking**: Every cost event, allocation, and driver is tracked with unique identifiers for complete audit trails
2. **Multi-Dimensional Attribution**: Support for organizational hierarchy, geographic, project-based, team-based, and functional cost allocation
3. **Temporal Cost Precision**: Microsecond-level timestamp tracking for accurate cost period attribution
4. **Financial System Integration**: GL account mapping, budget period alignment, and cost center integration
5. **Regulatory Compliance**: Enhanced audit trails with financial hash validation and compliance flagging
6. **Performance Attribution**: Cost variance analysis and attribution accuracy metrics for continuous improvement

### Organizational Hierarchy Integration Architecture

#### Primary Organizational Dimensions

The cost attribution framework integrates seamlessly with organizational hierarchies to provide comprehensive cost visibility:

```sql
-- ORGANIZATIONAL HIERARCHY COST ATTRIBUTION PATTERN
-- =================================================

-- 1. DEPARTMENTAL COST ATTRIBUTION
-- Tracks costs by department with full organizational context
WITH departmental_cost_attribution AS (
  SELECT
    department_code,
    department_name,
    cost_center_id,
    cost_center_name,
    division_code,
    business_unit_code,
    -- Calculate department-specific cost attribution rates
    CASE
      WHEN department_code IN ('HR', 'ADMIN', 'LEGAL') THEN 1.200000 -- Higher attribution for administrative functions
      WHEN department_code IN ('IT', 'TECH', 'ENG') THEN 0.900000    -- Moderate attribution for technology functions
      WHEN department_code IN ('SALES', 'MKT', 'BIZ') THEN 0.700000  -- Lower attribution for revenue-generating functions
      ELSE 1.000000 -- Standard attribution for other departments
    END as department_attribution_multiplier,

    -- Department cost sharing based on organizational structure
    CASE
      WHEN division_code = 'CORPORATE' THEN 1.000000 -- Full allocation for corporate functions
      WHEN division_code = 'OPERATIONS' THEN 0.850000 -- Reduced for operational divisions
      WHEN division_code = 'REVENUE' THEN 0.600000   -- Further reduced for revenue divisions
      ELSE 0.750000 -- Standard allocation for other divisions
    END as division_cost_share_rate

  FROM int_deferral_rate_state_accumulator
  WHERE financial_year = {{ var('simulation_year') }}
),

-- 2. GEOGRAPHIC COST ATTRIBUTION
-- Enables location-based cost analysis and allocation
geographic_cost_attribution AS (
  SELECT
    region_code,
    region_name,
    country_code,
    work_location_code,
    work_location_name,
    -- Geographic cost adjustment factors
    CASE
      WHEN region_code = 'NAM' AND country_code = 'US' THEN 1.000000 -- Baseline for US operations
      WHEN region_code = 'EMEA' THEN 1.150000 -- Higher costs for European operations
      WHEN region_code = 'APAC' THEN 0.850000 -- Lower costs for Asia-Pacific
      WHEN work_location_code = 'REMOTE' THEN 0.750000 -- Reduced costs for remote workers
      ELSE 1.000000 -- Standard geographic attribution
    END as geographic_cost_multiplier,

    -- Location-based cost center mapping
    CASE
      WHEN work_location_code IN ('NYC', 'SF', 'LON') THEN 'HIGH_COST_LOCATION'
      WHEN work_location_code IN ('ATL', 'DAL', 'PHX') THEN 'MEDIUM_COST_LOCATION'
      WHEN work_location_code = 'REMOTE' THEN 'REMOTE_COST_LOCATION'
      ELSE 'STANDARD_COST_LOCATION'
    END as location_cost_category

  FROM int_deferral_rate_state_accumulator
  WHERE financial_year = {{ var('simulation_year') }}
),

-- 3. MANAGEMENT HIERARCHY COST ROLLUP
-- Enables cost attribution up the management chain
management_hierarchy_attribution AS (
  SELECT
    employee_id,
    manager_employee_id,
    manager_cost_center,
    org_hierarchy_level,
    -- Management span calculation for cost distribution
    COUNT(*) OVER (PARTITION BY manager_employee_id) as management_span,

    -- Hierarchical cost attribution rates
    CASE
      WHEN org_hierarchy_level = 1 THEN 1.000000 -- Individual contributor baseline
      WHEN org_hierarchy_level = 2 THEN 1.100000 -- First-line manager premium
      WHEN org_hierarchy_level = 3 THEN 1.250000 -- Mid-level manager premium
      WHEN org_hierarchy_level >= 4 THEN 1.500000 -- Senior leadership premium
      ELSE 1.000000 -- Default attribution
    END as hierarchy_attribution_rate,

    -- Management overhead allocation
    ROUND(1.0 / NULLIF(COUNT(*) OVER (PARTITION BY manager_employee_id), 0), 6) as management_overhead_share

  FROM int_deferral_rate_state_accumulator
  WHERE financial_year = {{ var('simulation_year') }}
    AND manager_employee_id != 'MGR_UNKNOWN'
)

SELECT
  acc.*,
  -- Enhanced organizational cost attribution
  dept.department_attribution_multiplier,
  dept.division_cost_share_rate,
  geo.geographic_cost_multiplier,
  geo.location_cost_category,
  mgmt.hierarchy_attribution_rate,
  mgmt.management_overhead_share,

  -- Composite cost attribution calculation
  ROUND(
    acc.cost_attribution_rate *
    dept.department_attribution_multiplier *
    dept.division_cost_share_rate *
    geo.geographic_cost_multiplier *
    mgmt.hierarchy_attribution_rate,
    6
  ) as composite_cost_attribution_rate,

  -- Final allocated cost with organizational adjustments
  ROUND(
    acc.cost_basis_amount *
    acc.cost_attribution_rate *
    dept.department_attribution_multiplier *
    dept.division_cost_share_rate *
    geo.geographic_cost_multiplier *
    mgmt.hierarchy_attribution_rate * 0.001, -- Convert to cost per thousand
    2
  ) as organization_adjusted_cost

FROM int_deferral_rate_state_accumulator acc
LEFT JOIN departmental_cost_attribution dept
  ON acc.department_code = dept.department_code
  AND acc.cost_center_id = dept.cost_center_id
LEFT JOIN geographic_cost_attribution geo
  ON acc.region_code = geo.region_code
  AND acc.work_location_code = geo.work_location_code
LEFT JOIN management_hierarchy_attribution mgmt
  ON acc.employee_id = mgmt.employee_id

WHERE acc.financial_year = {{ var('simulation_year') }}
```

### Multi-Dimensional Cost Attribution Framework

#### Project-Based Cost Attribution

The framework supports sophisticated project-based cost allocation for matrix organizations and project-driven work:

```sql
-- PROJECT-BASED COST ATTRIBUTION ARCHITECTURE
-- ===========================================

WITH project_cost_attribution AS (
  SELECT
    project_code,
    project_name,
    project_cost_type,
    cost_driver_category,

    -- Project phase-based attribution
    CASE
      WHEN project_code LIKE 'PROJ_%_INIT' THEN 1.500000 -- Higher attribution for project initiation
      WHEN project_code LIKE 'PROJ_%_EXEC' THEN 1.200000 -- Standard attribution for execution
      WHEN project_code LIKE 'PROJ_%_CLOSE' THEN 0.800000 -- Lower attribution for project closure
      WHEN project_code = 'OVERHEAD' THEN 0.500000       -- Minimal attribution for overhead
      ELSE 1.000000 -- Standard project attribution
    END as project_phase_multiplier,

    -- Project complexity cost adjustment
    CASE
      WHEN cost_driver_category LIKE '%compliance%' THEN 1.750000 -- High complexity for compliance projects
      WHEN cost_driver_category LIKE '%integration%' THEN 1.400000 -- Medium-high for integration projects
      WHEN cost_driver_category LIKE '%enrollment%' THEN 1.000000  -- Standard for enrollment projects
      WHEN cost_driver_category LIKE '%escalation%' THEN 0.600000  -- Lower for automated escalation
      ELSE 1.000000 -- Standard complexity attribution
    END as project_complexity_multiplier,

    -- Direct vs. overhead allocation
    CASE
      WHEN project_cost_type = 'project_direct' THEN 1.000000    -- Full allocation for direct project costs
      WHEN project_cost_type = 'operational_direct' THEN 0.750000 -- Partial allocation for operational costs
      WHEN project_cost_type = 'overhead_allocated' THEN 0.250000 -- Minimal allocation for overhead
      ELSE 0.500000 -- Default allocation
    END as project_directness_rate

  FROM int_deferral_rate_state_accumulator
  WHERE financial_year = {{ var('simulation_year') }}
    AND project_code IS NOT NULL
),

-- TEAM-BASED COST ATTRIBUTION (Agile Organizations)
-- =================================================

team_cost_attribution AS (
  SELECT
    team_id,
    team_name,
    squad_id,
    cost_attribution_team,
    department_code,

    -- Team velocity-based cost attribution
    COUNT(*) OVER (PARTITION BY team_id) as team_size,
    COUNT(DISTINCT cost_driver_category) OVER (PARTITION BY team_id) as team_complexity,

    -- Team efficiency multiplier
    CASE
      WHEN COUNT(*) OVER (PARTITION BY team_id) BETWEEN 5 AND 9 THEN 1.100000 -- Optimal team size premium
      WHEN COUNT(*) OVER (PARTITION BY team_id) BETWEEN 3 AND 4 THEN 1.000000 -- Small team baseline
      WHEN COUNT(*) OVER (PARTITION BY team_id) >= 10 THEN 0.900000           -- Large team discount
      ELSE 0.800000 -- Very small or very large team adjustment
    END as team_size_efficiency_multiplier,

    -- Cross-functional team premium
    CASE
      WHEN COUNT(DISTINCT department_code) OVER (PARTITION BY team_id) > 2 THEN 1.200000 -- Cross-functional premium
      WHEN COUNT(DISTINCT department_code) OVER (PARTITION BY team_id) = 2 THEN 1.100000 -- Multi-department bonus
      ELSE 1.000000 -- Single department baseline
    END as team_cross_functional_multiplier

  FROM int_deferral_rate_state_accumulator
  WHERE financial_year = {{ var('simulation_year') }}
    AND team_id IS NOT NULL
    AND team_id != 'TEAM_UNKNOWN'
)

SELECT
  acc.*,
  -- Project cost attribution enhancements
  proj.project_phase_multiplier,
  proj.project_complexity_multiplier,
  proj.project_directness_rate,

  -- Team cost attribution enhancements
  team.team_size_efficiency_multiplier,
  team.team_cross_functional_multiplier,
  team.team_size,
  team.team_complexity,

  -- Multi-dimensional cost calculation
  ROUND(
    acc.cost_attribution_rate *
    COALESCE(proj.project_phase_multiplier, 1.0) *
    COALESCE(proj.project_complexity_multiplier, 1.0) *
    COALESCE(proj.project_directness_rate, 1.0) *
    COALESCE(team.team_size_efficiency_multiplier, 1.0) *
    COALESCE(team.team_cross_functional_multiplier, 1.0),
    6
  ) as multi_dimensional_attribution_rate,

  -- Final project-team adjusted cost allocation
  ROUND(
    acc.cost_basis_amount *
    acc.cost_attribution_rate *
    COALESCE(proj.project_phase_multiplier, 1.0) *
    COALESCE(proj.project_complexity_multiplier, 1.0) *
    COALESCE(proj.project_directness_rate, 1.0) *
    COALESCE(team.team_size_efficiency_multiplier, 1.0) *
    COALESCE(team.team_cross_functional_multiplier, 1.0) * 0.001,
    2
  ) as project_team_adjusted_cost

FROM int_deferral_rate_state_accumulator acc
LEFT JOIN project_cost_attribution proj
  ON acc.project_code = proj.project_code
LEFT JOIN team_cost_attribution team
  ON acc.team_id = team.team_id

WHERE acc.financial_year = {{ var('simulation_year') }}
```

### Financial Reporting Integration Patterns

#### GL Account Mapping and Budget Integration

The cost attribution framework provides seamless integration with enterprise financial systems:

```sql
-- FINANCIAL REPORTING INTEGRATION ARCHITECTURE
-- ============================================

WITH financial_reporting_integration AS (
  SELECT
    gl_account_code,
    gl_account_description,
    budget_allocation_key,
    budget_period,
    financial_quarter,

    -- GL account cost category mapping
    CASE
      WHEN gl_account_code LIKE '6200%' THEN 'OPERATIONAL_HR_COSTS'
      WHEN gl_account_code LIKE '6201%' THEN 'COMPLIANCE_COSTS'
      WHEN gl_account_code LIKE '6202%' THEN 'INTEGRATION_COSTS'
      WHEN gl_account_code LIKE '6203%' THEN 'TECHNOLOGY_COSTS'
      ELSE 'MISCELLANEOUS_HR_COSTS'
    END as gl_cost_category,

    -- Budget variance tracking
    COUNT(*) OVER (PARTITION BY budget_allocation_key, budget_period) as budget_transactions,
    SUM(allocated_cost_amount) OVER (PARTITION BY budget_allocation_key, budget_period) as budget_period_total,

    -- Quarter-over-quarter cost tracking
    LAG(SUM(allocated_cost_amount)) OVER (
      PARTITION BY gl_account_code, cost_center_id
      ORDER BY financial_quarter
    ) as prior_quarter_cost,

    -- Year-over-year comparison
    LAG(SUM(allocated_cost_amount), 4) OVER (
      PARTITION BY gl_account_code, cost_center_id
      ORDER BY financial_quarter
    ) as prior_year_same_quarter_cost

  FROM int_deferral_rate_state_accumulator
  WHERE financial_year = {{ var('simulation_year') }}
  GROUP BY 1,2,3,4,5
),

-- COST CENTER BUDGET ANALYSIS
-- ===========================

cost_center_budget_analysis AS (
  SELECT
    cost_center_id,
    cost_center_name,
    department_code,
    budget_allocation_key,
    financial_quarter,

    -- Budget utilization metrics
    SUM(allocated_cost_amount) as quarterly_actual_cost,
    COUNT(DISTINCT employee_id) as employees_in_cost_center,
    AVG(cost_basis_amount) as avg_salary_basis,

    -- Cost efficiency metrics
    ROUND(SUM(allocated_cost_amount) / COUNT(DISTINCT employee_id), 2) as cost_per_employee,
    ROUND(SUM(allocated_cost_amount) / SUM(cost_basis_amount) * 100, 4) as cost_as_percent_of_payroll,

    -- Department cost distribution
    SUM(allocated_cost_amount) /
      SUM(SUM(allocated_cost_amount)) OVER (PARTITION BY department_code) as dept_cost_share,

    -- Quarterly cost progression
    ROW_NUMBER() OVER (PARTITION BY cost_center_id ORDER BY financial_quarter) as quarter_sequence

  FROM int_deferral_rate_state_accumulator
  WHERE financial_year = {{ var('simulation_year') }}
  GROUP BY 1,2,3,4,5
)

-- Final comprehensive financial reporting view
SELECT
  acc.*,
  fin.gl_cost_category,
  fin.budget_period_total,
  fin.prior_quarter_cost,
  fin.prior_year_same_quarter_cost,

  -- Budget variance calculations
  CASE
    WHEN fin.prior_quarter_cost IS NOT NULL AND fin.prior_quarter_cost > 0 THEN
      ROUND((acc.allocated_cost_amount - fin.prior_quarter_cost) / fin.prior_quarter_cost * 100, 2)
    ELSE NULL
  END as quarter_over_quarter_variance_percent,

  CASE
    WHEN fin.prior_year_same_quarter_cost IS NOT NULL AND fin.prior_year_same_quarter_cost > 0 THEN
      ROUND((acc.allocated_cost_amount - fin.prior_year_same_quarter_cost) / fin.prior_year_same_quarter_cost * 100, 2)
    ELSE NULL
  END as year_over_year_variance_percent,

  -- Cost center analysis
  cc.cost_per_employee,
  cc.cost_as_percent_of_payroll,
  cc.dept_cost_share,
  cc.quarter_sequence,

  -- Financial reporting flags
  CASE
    WHEN acc.allocated_cost_amount > 1000 THEN 'MATERIAL_COST_EVENT'
    WHEN acc.regulatory_flag = TRUE THEN 'REGULATORY_COST_EVENT'
    WHEN acc.cost_driver_category LIKE '%compliance%' THEN 'COMPLIANCE_COST_EVENT'
    ELSE 'STANDARD_COST_EVENT'
  END as financial_reporting_flag

FROM int_deferral_rate_state_accumulator acc
LEFT JOIN financial_reporting_integration fin
  ON acc.gl_account_code = fin.gl_account_code
  AND acc.budget_period = fin.budget_period
LEFT JOIN cost_center_budget_analysis cc
  ON acc.cost_center_id = cc.cost_center_id
  AND acc.financial_quarter = cc.financial_quarter

WHERE acc.financial_year = {{ var('simulation_year') }}
```

### Cost Variance Analysis and Performance Attribution

#### Attribution Accuracy Metrics and Continuous Improvement

The framework includes sophisticated metrics to measure and improve cost attribution accuracy:

```sql
-- COST VARIANCE ANALYSIS AND ATTRIBUTION ACCURACY FRAMEWORK
-- =========================================================

WITH attribution_accuracy_analysis AS (
  SELECT
    cost_driver_category,
    cost_allocation_type,
    source_type,
    department_code,
    financial_quarter,

    -- Statistical measures of attribution consistency
    COUNT(*) as total_cost_events,
    AVG(cost_attribution_rate) as mean_attribution_rate,
    STDDEV(cost_attribution_rate) as attribution_rate_stddev,
    MIN(cost_attribution_rate) as min_attribution_rate,
    MAX(cost_attribution_rate) as max_attribution_rate,

    -- Attribution consistency scoring
    CASE
      WHEN STDDEV(cost_attribution_rate) <= 0.05 THEN 'EXCELLENT_CONSISTENCY'
      WHEN STDDEV(cost_attribution_rate) <= 0.10 THEN 'GOOD_CONSISTENCY'
      WHEN STDDEV(cost_attribution_rate) <= 0.20 THEN 'ACCEPTABLE_CONSISTENCY'
      ELSE 'POOR_CONSISTENCY'
    END as attribution_consistency_score,

    -- Cost prediction accuracy (comparing actual vs. expected)
    AVG(ABS(cost_attribution_rate - 1.000000)) as mean_absolute_deviation_from_baseline,

    -- Outlier detection for cost attribution rates
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY cost_attribution_rate) as q1_attribution_rate,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY cost_attribution_rate) as q3_attribution_rate,

    -- Cost efficiency metrics
    SUM(allocated_cost_amount) / COUNT(DISTINCT employee_id) as cost_per_unique_employee,
    SUM(allocated_cost_amount) / COUNT(*) as cost_per_event

  FROM int_deferral_rate_state_accumulator
  WHERE financial_year = {{ var('simulation_year') }}
  GROUP BY 1,2,3,4,5
),

-- PERFORMANCE ATTRIBUTION ANALYSIS
-- =================================

performance_attribution AS (
  SELECT
    cost_driver_category,
    source_type,
    department_code,

    -- Performance metrics calculation
    COUNT(*) as driver_event_count,
    SUM(allocated_cost_amount) as total_driver_cost,
    AVG(allocated_cost_amount) as avg_cost_per_event,

    -- Driver efficiency ranking
    RANK() OVER (ORDER BY SUM(allocated_cost_amount) / COUNT(*) ASC) as cost_efficiency_rank,
    RANK() OVER (ORDER BY COUNT(*) DESC) as volume_rank,
    RANK() OVER (ORDER BY STDDEV(cost_attribution_rate) ASC) as consistency_rank,

    -- Combined performance score (lower is better)
    (
      RANK() OVER (ORDER BY SUM(allocated_cost_amount) / COUNT(*) ASC) +
      RANK() OVER (ORDER BY STDDEV(cost_attribution_rate) ASC) +
      CASE
        WHEN COUNT(*) >= 100 THEN 1  -- Volume bonus for high-frequency drivers
        WHEN COUNT(*) >= 50 THEN 2
        WHEN COUNT(*) >= 10 THEN 3
        ELSE 4
      END
    ) as composite_performance_score,

    -- Attribution accuracy indicators
    CASE
      WHEN STDDEV(cost_attribution_rate) < 0.1 AND COUNT(*) >= 10 THEN 'HIGH_ACCURACY_HIGH_VOLUME'
      WHEN STDDEV(cost_attribution_rate) < 0.1 AND COUNT(*) < 10 THEN 'HIGH_ACCURACY_LOW_VOLUME'
      WHEN STDDEV(cost_attribution_rate) >= 0.1 AND COUNT(*) >= 10 THEN 'LOW_ACCURACY_HIGH_VOLUME'
      ELSE 'LOW_ACCURACY_LOW_VOLUME'
    END as attribution_performance_category

  FROM int_deferral_rate_state_accumulator
  WHERE financial_year = {{ var('simulation_year') }}
  GROUP BY 1,2,3
)

-- Final performance attribution and accuracy reporting
SELECT
  acc.*,

  -- Attribution accuracy metrics
  aa.attribution_consistency_score,
  aa.mean_absolute_deviation_from_baseline,
  aa.q1_attribution_rate,
  aa.q3_attribution_rate,

  -- Performance attribution metrics
  pa.cost_efficiency_rank,
  pa.volume_rank,
  pa.consistency_rank,
  pa.composite_performance_score,
  pa.attribution_performance_category,

  -- Improvement recommendations
  CASE
    WHEN aa.attribution_consistency_score = 'POOR_CONSISTENCY' THEN 'REVIEW_ATTRIBUTION_RULES'
    WHEN pa.cost_efficiency_rank > 10 THEN 'OPTIMIZE_COST_ALLOCATION'
    WHEN pa.volume_rank <= 3 AND aa.attribution_consistency_score IN ('GOOD_CONSISTENCY', 'EXCELLENT_CONSISTENCY') THEN 'ATTRIBUTION_MODEL_EXEMPLAR'
    WHEN aa.mean_absolute_deviation_from_baseline > 0.3 THEN 'INVESTIGATE_ATTRIBUTION_OUTLIERS'
    ELSE 'ATTRIBUTION_PERFORMING_NORMALLY'
  END as attribution_improvement_recommendation,

  -- Cost variance flags for management attention
  CASE
    WHEN acc.allocated_cost_amount > (aa.mean_attribution_rate + 2 * aa.attribution_rate_stddev) * acc.cost_basis_amount * 0.001 THEN 'HIGH_COST_VARIANCE'
    WHEN acc.allocated_cost_amount < (aa.mean_attribution_rate - 2 * aa.attribution_rate_stddev) * acc.cost_basis_amount * 0.001 THEN 'LOW_COST_VARIANCE'
    ELSE 'NORMAL_COST_VARIANCE'
  END as cost_variance_flag

FROM int_deferral_rate_state_accumulator acc
LEFT JOIN attribution_accuracy_analysis aa
  ON acc.cost_driver_category = aa.cost_driver_category
  AND acc.cost_allocation_type = aa.cost_allocation_type
  AND acc.source_type = aa.source_type
  AND acc.department_code = aa.department_code
  AND acc.financial_quarter = aa.financial_quarter
LEFT JOIN performance_attribution pa
  ON acc.cost_driver_category = pa.cost_driver_category
  AND acc.source_type = pa.source_type
  AND acc.department_code = pa.department_code

WHERE acc.financial_year = {{ var('simulation_year') }}
```

This comprehensive cost attribution framework provides enterprise-grade cost modeling capabilities with full organizational integration, multi-dimensional attribution, financial system integration, and continuous performance monitoring. The framework supports real-time cost variance analysis and attribution accuracy measurement for optimal workforce simulation cost modeling.

## Employee Lifecycle Integration Business Logic

### Employment Status Integration with int_workforce_active_for_events

#### Termination/Rehire Scenarios
```sql
-- Business rules for employment status changes affecting deferral rates
CASE
  -- Active employees: all rate changes apply normally
  WHEN emp.employment_status = 'active' THEN
    'apply_rate_change'

  -- Terminated employees: only retroactive adjustments allowed
  WHEN emp.employment_status = 'terminated' AND source_type = 'retroactive_adjustment' THEN
    'apply_retroactive_only'

  -- Terminated employees: block new enrollments/escalations after termination
  WHEN emp.employment_status = 'terminated' AND effective_date > emp.termination_date THEN
    'block_future_changes'

  -- Rehired employees: reset to baseline rates unless rate preservation flag is set
  WHEN emp.rehire_date IS NOT NULL AND effective_date >= emp.rehire_date THEN
    CASE
      WHEN rate_preservation_flag = TRUE THEN 'preserve_previous_rate'
      ELSE 'reset_to_baseline'
    END

  ELSE 'default_processing'
END
```

#### Eligibility Window Logic
```sql
-- Enrollment events must occur within eligibility window
WHERE e.effective_date >= emp.eligibility_start_date
  AND (emp.termination_date IS NULL OR e.effective_date <= emp.termination_date)
```

### Plan Transfer Logic for M&A Scenarios

#### Rate Preservation Decision Matrix
```sql
-- Plan transfer deferral rate logic based on business rules
CASE
  -- Preserve rate: M&A with explicit rate preservation
  WHEN pt.rate_preservation_flag = TRUE
    AND pt.transfer_reason IN ('merger', 'acquisition', 'spinoff')
  THEN pys.current_deferral_rate

  -- Reset to new plan default: restructuring scenarios
  WHEN pt.rate_preservation_flag = FALSE
    OR pt.transfer_reason IN ('restructure', 'plan_termination')
  THEN npd.default_deferral_rate

  -- Apply HCE restrictions to transferred rates
  WHEN hce.hce_status = TRUE
    AND pys.current_deferral_rate > npd.hce_max_deferral_rate
  THEN npd.hce_max_deferral_rate

  -- Default to preserved rate with validation
  ELSE COALESCE(pys.current_deferral_rate, npd.default_deferral_rate)
END
```

#### Plan Design Compatibility Validation
```sql
-- Ensure transferred rates comply with new plan limits
WITH plan_validation AS (
  SELECT
    pt.employee_id,
    pt.new_plan_design_id,
    pys.current_deferral_rate,
    npd.min_deferral_rate,
    npd.max_deferral_rate,
    CASE
      WHEN pys.current_deferral_rate < npd.min_deferral_rate
      THEN npd.min_deferral_rate
      WHEN pys.current_deferral_rate > npd.max_deferral_rate
      THEN npd.max_deferral_rate
      ELSE pys.current_deferral_rate
    END as adjusted_rate
  FROM current_year_plan_transfers pt
  JOIN previous_year_state pys ON pt.employee_id = pys.employee_id
  JOIN dim_plan_design npd ON pt.new_plan_design_id = npd.plan_design_id
)
```

### Retroactive Adjustment Support for Backdated Changes

#### Compliance-Driven Adjustment Logic
```sql
-- Retroactive adjustments require special handling for audit compliance
WITH retroactive_processing AS (
  SELECT
    ra.employee_id,
    ra.original_deferral_rate,
    ra.adjusted_deferral_rate,
    ra.adjustment_effective_date,
    -- Calculate impact on previous contribution calculations
    CASE
      WHEN ra.adjustment_effective_date < DATE_TRUNC('year', CURRENT_DATE)
      THEN 'prior_year_impact'
      WHEN ra.adjustment_effective_date < DATE_TRUNC('month', CURRENT_DATE)
      THEN 'current_year_impact'
      ELSE 'future_adjustment'
    END as adjustment_scope,

    -- Flag for regulatory review if material change
    CASE
      WHEN ABS(ra.adjusted_deferral_rate - ra.original_deferral_rate) > 0.02 -- 2% threshold
      THEN TRUE
      ELSE FALSE
    END as material_change_flag

  FROM current_year_retroactive_adjustments ra
)
```

#### Temporal Consistency Validation
```sql
-- Ensure retroactive adjustments don't violate temporal consistency
SELECT
  ra.employee_id,
  ra.adjustment_effective_date,
  ra.adjustment_reason
FROM current_year_retroactive_adjustments ra
LEFT JOIN previous_year_state pys
  ON ra.employee_id = pys.employee_id
  AND ra.adjustment_effective_date >= DATE_TRUNC('year', pys.effective_date)
WHERE pys.employee_id IS NULL
  AND ra.adjustment_effective_date < DATE_TRUNC('year', CURRENT_DATE)
-- Flag adjustments for periods without prior state records
```

### HCE Status Integration with Rate Restrictions

#### Automatic HCE Rate Limitation
```sql
-- Apply HCE restrictions automatically to all rate changes
WITH hce_rate_application AS (
  SELECT
    c.*,
    hce.hce_status,
    pd.hce_max_deferral_rate,
    pd.nhce_max_deferral_rate,

    -- Apply appropriate rate limits based on HCE status
    CASE
      WHEN hce.hce_status = TRUE THEN
        CASE
          WHEN pd.hce_max_deferral_rate IS NOT NULL
          THEN LEAST(c.new_deferral_rate, pd.hce_max_deferral_rate)
          ELSE c.new_deferral_rate
        END
      ELSE
        CASE
          WHEN pd.nhce_max_deferral_rate IS NOT NULL
          THEN LEAST(c.new_deferral_rate, pd.nhce_max_deferral_rate)
          ELSE c.new_deferral_rate
        END
    END as restricted_deferral_rate,

    -- Flag rate reductions due to HCE restrictions for audit
    CASE
      WHEN hce.hce_status = TRUE
        AND c.new_deferral_rate > pd.hce_max_deferral_rate
      THEN TRUE
      ELSE FALSE
    END as hce_rate_reduction_applied

  FROM unified_rate_changes c
  LEFT JOIN current_year_hce_status hce ON c.employee_id = hce.employee_id
  LEFT JOIN dim_plan_design pd ON c.plan_design_id = pd.plan_design_id
)
```

#### HCE Status Change Impact Analysis
```sql
-- Track impact of HCE status changes on existing deferral rates
WITH hce_status_impact AS (
  SELECT
    hce.employee_id,
    hce.hce_determination_date,
    pys.current_deferral_rate as prior_rate,
    pd.hce_max_deferral_rate,

    -- Calculate rate impact of HCE status change
    CASE
      WHEN hce.hce_status = TRUE
        AND pys.current_deferral_rate > pd.hce_max_deferral_rate
      THEN pd.hce_max_deferral_rate - pys.current_deferral_rate
      ELSE 0
    END as rate_reduction_amount,

    -- Flag employees requiring rate reduction due to new HCE status
    CASE
      WHEN hce.hce_status = TRUE
        AND pys.current_deferral_rate > pd.hce_max_deferral_rate
      THEN 'rate_reduction_required'
      ELSE 'no_change_required'
    END as hce_impact_type

  FROM current_year_hce_status hce
  JOIN previous_year_state pys ON hce.employee_id = pys.employee_id
  JOIN dim_plan_design pd ON pys.plan_design_id = pd.plan_design_id
  WHERE hce.hce_status = TRUE -- Focus on newly identified HCEs
)
```

### Cross-Year State Continuity Validation

This comprehensive validation framework ensures perfect state integrity across multi-year simulations by implementing automated monitoring, anomaly detection, and complete audit trail verification.

#### State Consistency Validation Framework

**Core Validation Principles:**
1. **State Immutability**: No state records can be orphaned or lost across years
2. **Employment Lifecycle Integrity**: All employment transitions must have proper audit trails
3. **Rate Change Lineage**: Every deferral rate change must have traceable source attribution
4. **Temporal Consistency**: All dates and effective periods must maintain logical progression
5. **Multi-Year Coherence**: State accumulation must be mathematically consistent across simulation years

#### 1. State Consistency Validation

```sql
-- COMPREHENSIVE STATE CONSISTENCY VALIDATION
-- Detects orphaned states, missing transitions, and data integrity issues
CREATE OR REPLACE VIEW validate_state_consistency AS
WITH state_transitions AS (
  SELECT
    curr.accumulator_id,
    curr.employee_id,
    curr.scenario_id,
    curr.simulation_year,
    curr.employment_status,
    curr.current_deferral_rate,
    curr.state_change_type,
    curr.source_type,
    curr.is_active,

    -- Previous year state
    prev.accumulator_id as prev_accumulator_id,
    prev.employment_status as prev_employment_status,
    prev.current_deferral_rate as prev_deferral_rate,
    prev.is_active as prev_is_active,

    -- State transition classification
    CASE
      WHEN prev.employee_id IS NULL THEN 'new_hire'
      WHEN prev.employment_status = 'active' AND curr.employment_status = 'terminated' THEN 'termination'
      WHEN prev.employment_status = 'terminated' AND curr.employment_status = 'active' THEN 'rehire'
      WHEN prev.employment_status = 'active' AND curr.employment_status = 'active' THEN 'continued'
      WHEN prev.employment_status = 'terminated' AND curr.employment_status = 'terminated' THEN 'remain_terminated'
      ELSE 'invalid_transition'
    END as transition_type,

    -- Orphaned state detection
    CASE
      WHEN curr.simulation_year > (SELECT MIN(simulation_year) FROM int_deferral_rate_state_accumulator WHERE scenario_id = curr.scenario_id)
        AND prev.employee_id IS NULL
        AND curr.state_change_type != 'new_employee'
      THEN 'orphaned_employee_state'
      WHEN curr.is_active = TRUE AND curr.employment_status != 'active'
      THEN 'invalid_active_flag'
      WHEN curr.employment_status = 'terminated' AND curr.termination_date IS NULL
      THEN 'missing_termination_data'
      WHEN curr.state_change_type = 'plan_transferred' AND curr.previous_plan_design_id IS NULL
      THEN 'missing_transfer_source'
      ELSE 'state_consistent'
    END as consistency_status,

    -- Rate change validation
    CASE
      WHEN ABS(curr.current_deferral_rate - COALESCE(prev.current_deferral_rate, 0)) > 0.75
      THEN 'extreme_rate_change'
      WHEN curr.current_deferral_rate > 1.0 OR curr.current_deferral_rate < 0.0
      THEN 'invalid_rate_bounds'
      WHEN curr.state_change_type = 'rate_changed'
        AND curr.source_type NOT IN ('enrollment', 'escalation', 'retroactive_adjustment', 'compliance_adjustment')
      THEN 'invalid_rate_source'
      ELSE 'rate_valid'
    END as rate_validation_status

  FROM int_deferral_rate_state_accumulator curr
  LEFT JOIN int_deferral_rate_state_accumulator prev
    ON curr.employee_id = prev.employee_id
    AND curr.scenario_id = prev.scenario_id
    AND prev.simulation_year = curr.simulation_year - 1
)

SELECT
  simulation_year,
  transition_type,
  consistency_status,
  rate_validation_status,
  COUNT(*) as record_count,
  COUNT(CASE WHEN consistency_status != 'state_consistent' THEN 1 END) as inconsistent_records,
  COUNT(CASE WHEN rate_validation_status != 'rate_valid' THEN 1 END) as invalid_rate_records,
  ROUND(100.0 * COUNT(CASE WHEN consistency_status = 'state_consistent' THEN 1 END) / COUNT(*), 2) as consistency_percentage
FROM state_transitions
GROUP BY simulation_year, transition_type, consistency_status, rate_validation_status
ORDER BY simulation_year, transition_type;
```

#### 2. Employment Transition Validation

```sql
-- EMPLOYMENT LIFECYCLE TRANSITION VALIDATION
-- Ensures all employment status changes follow valid business rules
CREATE OR REPLACE VIEW validate_employment_transitions AS
WITH employment_flow AS (
  SELECT
    curr.employee_id,
    curr.scenario_id,
    curr.simulation_year,
    curr.employment_status,
    curr.hire_date,
    curr.termination_date,
    curr.rehire_date,
    curr.is_active,

    prev.employment_status as prev_status,
    prev.is_active as prev_is_active,

    -- Transition validation logic
    CASE
      WHEN prev.employee_id IS NULL AND curr.employment_status = 'active'
        AND curr.hire_date IS NOT NULL
      THEN 'valid_new_hire'

      WHEN prev.employment_status = 'active' AND curr.employment_status = 'terminated'
        AND curr.termination_date IS NOT NULL
        AND curr.termination_date >= prev.effective_date
      THEN 'valid_termination'

      WHEN prev.employment_status = 'terminated' AND curr.employment_status = 'active'
        AND curr.rehire_date IS NOT NULL
        AND curr.rehire_date > COALESCE(prev.termination_date, '1900-01-01'::DATE)
      THEN 'valid_rehire'

      WHEN prev.employment_status = 'active' AND curr.employment_status = 'active'
        AND curr.hire_date IS NOT NULL
      THEN 'valid_continuation'

      WHEN prev.employment_status = 'terminated' AND curr.employment_status = 'terminated'
      THEN 'valid_remain_terminated'

      -- Invalid transitions
      WHEN prev.employee_id IS NULL AND curr.employment_status != 'active'
      THEN 'invalid_initial_status'

      WHEN prev.employment_status = 'active' AND curr.employment_status = 'terminated'
        AND curr.termination_date IS NULL
      THEN 'missing_termination_date'

      WHEN prev.employment_status = 'terminated' AND curr.employment_status = 'active'
        AND curr.rehire_date IS NULL
      THEN 'missing_rehire_date'

      WHEN curr.employment_status = 'active' AND curr.is_active = FALSE
      THEN 'active_status_inactive_flag_mismatch'

      WHEN curr.employment_status = 'terminated' AND curr.is_active = TRUE
      THEN 'terminated_status_active_flag_mismatch'

      ELSE 'undefined_transition'
    END as transition_validation,

    -- Date consistency validation
    CASE
      WHEN curr.hire_date > curr.effective_date
      THEN 'hire_date_future_effective'
      WHEN curr.termination_date IS NOT NULL AND curr.termination_date > curr.effective_date
        AND curr.source_type != 'retroactive_adjustment'
      THEN 'termination_date_future_effective'
      WHEN curr.rehire_date IS NOT NULL AND curr.rehire_date > curr.effective_date
      THEN 'rehire_date_future_effective'
      WHEN curr.termination_date IS NOT NULL AND curr.rehire_date IS NOT NULL
        AND curr.rehire_date <= curr.termination_date
      THEN 'rehire_before_termination'
      ELSE 'date_consistent'
    END as date_consistency

  FROM int_deferral_rate_state_accumulator curr
  LEFT JOIN int_deferral_rate_state_accumulator prev
    ON curr.employee_id = prev.employee_id
    AND curr.scenario_id = prev.scenario_id
    AND prev.simulation_year = curr.simulation_year - 1
)

SELECT
  simulation_year,
  transition_validation,
  date_consistency,
  COUNT(*) as record_count,
  COUNT(DISTINCT employee_id) as unique_employees,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY simulation_year), 2) as percentage_of_year
FROM employment_flow
GROUP BY simulation_year, transition_validation, date_consistency
ORDER BY simulation_year, record_count DESC;
```

#### 3. Rate Change Validation with Source Lineage

```sql
-- DEFERRAL RATE CHANGE VALIDATION WITH COMPLETE SOURCE LINEAGE
-- Validates rate changes maintain proper source attribution and business logic
CREATE OR REPLACE VIEW validate_rate_changes AS
WITH rate_change_analysis AS (
  SELECT
    curr.accumulator_id,
    curr.employee_id,
    curr.scenario_id,
    curr.simulation_year,
    curr.current_deferral_rate,
    curr.source_type,
    curr.state_change_type,
    curr.is_retroactive_adjustment,
    curr.adjustment_reason,

    prev.current_deferral_rate as prev_rate,
    prev.source_type as prev_source_type,

    -- Rate change magnitude
    curr.current_deferral_rate - COALESCE(prev.current_deferral_rate, 0) as rate_change_amount,
    ABS(curr.current_deferral_rate - COALESCE(prev.current_deferral_rate, 0)) as rate_change_magnitude,

    -- Source type progression validation
    CASE
      WHEN prev.employee_id IS NULL AND curr.source_type = 'enrollment'
      THEN 'valid_initial_enrollment'

      WHEN prev.source_type = 'enrollment' AND curr.source_type = 'escalation'
        AND curr.current_deferral_rate > prev.current_deferral_rate
      THEN 'valid_escalation'

      WHEN prev.source_type IN ('enrollment', 'escalation') AND curr.source_type = 'enrollment'
        AND curr.state_change_type = 'rate_changed'
      THEN 'valid_participant_change'

      WHEN curr.source_type = 'retroactive_adjustment'
        AND curr.is_retroactive_adjustment = TRUE
        AND curr.adjustment_reason IS NOT NULL
      THEN 'valid_retroactive_adjustment'

      WHEN curr.source_type = 'plan_transfer'
        AND curr.state_change_type = 'plan_transferred'
        AND curr.previous_plan_design_id IS NOT NULL
      THEN 'valid_plan_transfer'

      WHEN curr.source_type = 'baseline'
        AND curr.state_change_type = 'no_change'
        AND curr.current_deferral_rate = COALESCE(prev.current_deferral_rate, 0)
      THEN 'valid_baseline_continuation'

      -- Invalid source progressions
      WHEN curr.source_type = 'escalation' AND prev.source_type NOT IN ('enrollment', 'escalation')
      THEN 'invalid_escalation_source'

      WHEN curr.source_type = 'enrollment' AND curr.state_change_type != 'rate_changed'
        AND curr.state_change_type != 'new_employee'
      THEN 'invalid_enrollment_state_change'

      WHEN curr.is_retroactive_adjustment = TRUE AND curr.source_type != 'retroactive_adjustment'
      THEN 'invalid_retroactive_source'

      ELSE 'source_progression_unclear'
    END as source_progression_status,

    -- Rate change reasonableness validation
    CASE
      WHEN curr.current_deferral_rate < 0 OR curr.current_deferral_rate > 1
      THEN 'rate_out_of_bounds'

      WHEN ABS(curr.current_deferral_rate - COALESCE(prev.current_deferral_rate, 0)) > 0.5
        AND curr.source_type != 'plan_transfer'
        AND curr.is_retroactive_adjustment = FALSE
      THEN 'extreme_rate_change'

      WHEN curr.source_type = 'escalation'
        AND curr.current_deferral_rate <= COALESCE(prev.current_deferral_rate, 0)
      THEN 'escalation_rate_decrease'

      WHEN curr.state_change_type = 'no_change'
        AND ABS(curr.current_deferral_rate - COALESCE(prev.current_deferral_rate, 0)) > 0.001
      THEN 'no_change_with_rate_difference'

      WHEN curr.current_deferral_rate = 0.0
        AND curr.source_type IN ('enrollment', 'escalation')
        AND curr.employment_status = 'active'
      THEN 'zero_rate_with_enrollment'

      ELSE 'rate_change_reasonable'
    END as rate_reasonableness_status

  FROM int_deferral_rate_state_accumulator curr
  LEFT JOIN int_deferral_rate_state_accumulator prev
    ON curr.employee_id = prev.employee_id
    AND curr.scenario_id = prev.scenario_id
    AND prev.simulation_year = curr.simulation_year - 1
  WHERE curr.state_change_type != 'no_change'
     OR ABS(curr.current_deferral_rate - COALESCE(prev.current_deferral_rate, 0)) > 0.001
)

SELECT
  simulation_year,
  source_type,
  state_change_type,
  source_progression_status,
  rate_reasonableness_status,
  COUNT(*) as change_count,
  COUNT(DISTINCT employee_id) as unique_employees,
  ROUND(AVG(rate_change_magnitude), 4) as avg_change_magnitude,
  ROUND(MIN(rate_change_amount), 4) as min_change,
  ROUND(MAX(rate_change_amount), 4) as max_change,
  COUNT(CASE WHEN source_progression_status LIKE 'valid_%' THEN 1 END) as valid_progressions,
  COUNT(CASE WHEN rate_reasonableness_status = 'rate_change_reasonable' THEN 1 END) as reasonable_changes
FROM rate_change_analysis
GROUP BY simulation_year, source_type, state_change_type, source_progression_status, rate_reasonableness_status
ORDER BY simulation_year, change_count DESC;
```

#### 4. Data Lineage & Audit Trail Validation

```sql
-- COMPREHENSIVE DATA LINEAGE AND AUDIT TRAIL VALIDATION
-- Ensures complete traceability across multi-year simulations
CREATE OR REPLACE VIEW validate_audit_lineage AS
WITH lineage_validation AS (
  SELECT
    curr.accumulator_id,
    curr.employee_id,
    curr.scenario_id,
    curr.simulation_year,
    curr.effective_date,
    curr.source_event_id,
    curr.financial_audit_hash,
    curr.cost_allocation_id,
    curr.cost_event_id,

    -- UUID validation
    CASE
      WHEN curr.accumulator_id IS NULL
        OR NOT regexp_matches(curr.accumulator_id, '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
      THEN 'invalid_accumulator_id'

      WHEN curr.source_event_id IS NOT NULL
        AND NOT regexp_matches(curr.source_event_id, '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
      THEN 'invalid_source_event_id'

      WHEN curr.cost_allocation_id IS NOT NULL
        AND NOT regexp_matches(curr.cost_allocation_id, '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
      THEN 'invalid_cost_allocation_id'

      ELSE 'uuid_valid'
    END as uuid_validation_status,

    -- Audit hash validation
    CASE
      WHEN curr.financial_audit_hash IS NULL
      THEN 'missing_audit_hash'

      WHEN LENGTH(curr.financial_audit_hash) != 64
        OR NOT regexp_matches(curr.financial_audit_hash, '^[a-f0-9]{64}$')
      THEN 'invalid_audit_hash_format'

      ELSE 'audit_hash_valid'
    END as audit_hash_status,

    -- Source event linkage validation
    CASE
      WHEN curr.state_change_type != 'no_change' AND curr.source_event_id IS NULL
      THEN 'missing_source_event_for_change'

      WHEN curr.state_change_type = 'no_change' AND curr.source_event_id IS NOT NULL
      THEN 'unexpected_source_event_for_no_change'

      WHEN curr.is_retroactive_adjustment = TRUE
        AND (curr.source_event_id IS NULL OR curr.adjustment_reason IS NULL)
      THEN 'incomplete_retroactive_adjustment_audit'

      ELSE 'source_linkage_valid'
    END as source_linkage_status,

    -- Cost allocation completeness
    CASE
      WHEN curr.is_active = TRUE
        AND (curr.cost_allocation_id IS NULL OR curr.cost_event_id IS NULL)
      THEN 'missing_cost_allocation_for_active'

      WHEN curr.employment_status = 'active'
        AND curr.allocated_cost_amount IS NULL
      THEN 'missing_cost_amount_for_active'

      WHEN curr.cost_attribution_rate IS NOT NULL
        AND (curr.cost_attribution_rate <= 0 OR curr.cost_attribution_rate > 999.999999)
      THEN 'invalid_cost_attribution_rate'

      ELSE 'cost_allocation_complete'
    END as cost_allocation_status

  FROM int_deferral_rate_state_accumulator curr
),

-- Cross-year audit hash integrity check
hash_continuity AS (
  SELECT
    curr.employee_id,
    curr.scenario_id,
    curr.simulation_year,
    curr.financial_audit_hash,
    prev.financial_audit_hash as prev_hash,

    CASE
      WHEN curr.financial_audit_hash = prev.financial_audit_hash
        AND curr.state_change_type != 'no_change'
      THEN 'unchanged_hash_with_state_change'

      WHEN curr.financial_audit_hash != prev.financial_audit_hash
        AND curr.state_change_type = 'no_change'
      THEN 'changed_hash_with_no_state_change'

      ELSE 'hash_consistency_valid'
    END as hash_consistency_status

  FROM int_deferral_rate_state_accumulator curr
  LEFT JOIN int_deferral_rate_state_accumulator prev
    ON curr.employee_id = prev.employee_id
    AND curr.scenario_id = prev.scenario_id
    AND prev.simulation_year = curr.simulation_year - 1
  WHERE prev.employee_id IS NOT NULL
)

SELECT
  'UUID Validation' as validation_category,
  l.simulation_year,
  l.uuid_validation_status as status,
  COUNT(*) as record_count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY l.simulation_year), 2) as percentage
FROM lineage_validation l
GROUP BY l.simulation_year, l.uuid_validation_status

UNION ALL

SELECT
  'Audit Hash Status' as validation_category,
  l.simulation_year,
  l.audit_hash_status as status,
  COUNT(*) as record_count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY l.simulation_year), 2) as percentage
FROM lineage_validation l
GROUP BY l.simulation_year, l.audit_hash_status

UNION ALL

SELECT
  'Source Linkage' as validation_category,
  l.simulation_year,
  l.source_linkage_status as status,
  COUNT(*) as record_count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY l.simulation_year), 2) as percentage
FROM lineage_validation l
GROUP BY l.simulation_year, l.source_linkage_status

UNION ALL

SELECT
  'Cost Allocation' as validation_category,
  l.simulation_year,
  l.cost_allocation_status as status,
  COUNT(*) as record_count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY l.simulation_year), 2) as percentage
FROM lineage_validation l
GROUP BY l.simulation_year, l.cost_allocation_status

UNION ALL

SELECT
  'Hash Continuity' as validation_category,
  h.simulation_year,
  h.hash_consistency_status as status,
  COUNT(*) as record_count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY h.simulation_year), 2) as percentage
FROM hash_continuity h
GROUP BY h.simulation_year, h.hash_consistency_status

ORDER BY validation_category, simulation_year, record_count DESC;
```

#### 5. Automated Monitoring & Alert System

```sql
-- AUTOMATED STATE CONTINUITY MONITORING SYSTEM
-- Proactive detection of state inconsistencies with alert thresholds
CREATE OR REPLACE VIEW monitor_state_continuity AS
WITH monitoring_metrics AS (
  SELECT
    scenario_id,
    simulation_year,
    COUNT(*) as total_records,

    -- Consistency metrics
    COUNT(CASE WHEN employment_status = 'active' AND is_active = FALSE THEN 1 END) as active_status_inactive_flag,
    COUNT(CASE WHEN employment_status = 'terminated' AND termination_date IS NULL THEN 1 END) as terminated_missing_date,
    COUNT(CASE WHEN current_deferral_rate < 0 OR current_deferral_rate > 1 THEN 1 END) as invalid_rate_bounds,
    COUNT(CASE WHEN financial_audit_hash IS NULL THEN 1 END) as missing_audit_hashes,
    COUNT(CASE WHEN source_event_id IS NULL AND state_change_type != 'no_change' THEN 1 END) as missing_source_events,

    -- Rate change anomalies
    COUNT(CASE WHEN ABS(current_deferral_rate - LAG(current_deferral_rate)
      OVER (PARTITION BY employee_id, scenario_id ORDER BY simulation_year)) > 0.5 THEN 1 END) as extreme_rate_changes,

    -- Employment transition anomalies
    COUNT(CASE WHEN employment_status = 'active' AND hire_date IS NULL AND simulation_year > 2025 THEN 1 END) as active_missing_hire_date,
    COUNT(CASE WHEN state_change_type = 'plan_transferred' AND previous_plan_design_id IS NULL THEN 1 END) as invalid_plan_transfers,

    -- Cost allocation issues
    COUNT(CASE WHEN is_active = TRUE AND (cost_allocation_id IS NULL OR allocated_cost_amount IS NULL) THEN 1 END) as missing_cost_allocation,

    -- Data quality percentages
    ROUND(100.0 * COUNT(CASE WHEN employment_status IN ('active', 'terminated') THEN 1 END) / COUNT(*), 2) as valid_employment_status_pct,
    ROUND(100.0 * COUNT(CASE WHEN current_deferral_rate BETWEEN 0 AND 1 THEN 1 END) / COUNT(*), 2) as valid_rate_bounds_pct,
    ROUND(100.0 * COUNT(CASE WHEN financial_audit_hash IS NOT NULL THEN 1 END) / COUNT(*), 2) as audit_hash_completeness_pct

  FROM int_deferral_rate_state_accumulator
  GROUP BY scenario_id, simulation_year
),

-- Alert threshold evaluation
alert_evaluation AS (
  SELECT
    *,
    -- CRITICAL ALERTS (>5% threshold)
    CASE WHEN (active_status_inactive_flag::DECIMAL / total_records) > 0.05
      THEN 'CRITICAL: Active/Inactive Flag Mismatch > 5%' END as alert_active_flag,
    CASE WHEN (invalid_rate_bounds::DECIMAL / total_records) > 0.05
      THEN 'CRITICAL: Invalid Rate Bounds > 5%' END as alert_rate_bounds,
    CASE WHEN valid_employment_status_pct < 95.0
      THEN 'CRITICAL: Employment Status Validity < 95%' END as alert_employment_status,

    -- WARNING ALERTS (>1% threshold)
    CASE WHEN (terminated_missing_date::DECIMAL / total_records) > 0.01
      THEN 'WARNING: Missing Termination Dates > 1%' END as alert_termination_dates,
    CASE WHEN (missing_source_events::DECIMAL / total_records) > 0.01
      THEN 'WARNING: Missing Source Events > 1%' END as alert_source_events,
    CASE WHEN (extreme_rate_changes::DECIMAL / total_records) > 0.01
      THEN 'WARNING: Extreme Rate Changes > 1%' END as alert_rate_changes,

    -- INFO ALERTS (>0.1% threshold)
    CASE WHEN (missing_cost_allocation::DECIMAL / total_records) > 0.001
      THEN 'INFO: Missing Cost Allocation > 0.1%' END as alert_cost_allocation,
    CASE WHEN audit_hash_completeness_pct < 99.9
      THEN 'INFO: Audit Hash Completeness < 99.9%' END as alert_audit_hashes

  FROM monitoring_metrics
)

SELECT
  scenario_id,
  simulation_year,
  total_records,

  -- Alert summary
  COALESCE(alert_active_flag, alert_rate_bounds, alert_employment_status, 'NO CRITICAL ALERTS') as critical_alerts,
  COALESCE(alert_termination_dates, alert_source_events, alert_rate_changes, 'NO WARNINGS') as warning_alerts,
  COALESCE(alert_cost_allocation, alert_audit_hashes, 'NO INFO ALERTS') as info_alerts,

  -- Key metrics for monitoring dashboards
  valid_employment_status_pct,
  valid_rate_bounds_pct,
  audit_hash_completeness_pct,

  -- Issue counts for detailed investigation
  active_status_inactive_flag,
  terminated_missing_date,
  invalid_rate_bounds,
  missing_audit_hashes,
  missing_source_events,
  extreme_rate_changes,
  missing_cost_allocation,

  -- Overall health score (0-100)
  ROUND((valid_employment_status_pct + valid_rate_bounds_pct + audit_hash_completeness_pct) / 3.0, 1) as overall_health_score,

  CURRENT_TIMESTAMP as monitoring_timestamp

FROM alert_evaluation
ORDER BY scenario_id, simulation_year;
```

#### 6. Data Quality Tests for dbt Implementation

```sql
-- DBT TEST: Cross-year state continuity comprehensive validation
-- File: tests/validate_cross_year_state_continuity.sql

WITH validation_summary AS (
  SELECT
    scenario_id,
    simulation_year,
    COUNT(*) as total_records,
    COUNT(CASE WHEN employment_status NOT IN ('active', 'terminated') THEN 1 END) as invalid_employment_status,
    COUNT(CASE WHEN current_deferral_rate NOT BETWEEN 0 AND 1 THEN 1 END) as invalid_rates,
    COUNT(CASE WHEN financial_audit_hash IS NULL THEN 1 END) as missing_hashes,
    COUNT(CASE WHEN is_active = TRUE AND employment_status != 'active' THEN 1 END) as active_flag_mismatches
  FROM {{ ref('int_deferral_rate_state_accumulator') }}
  GROUP BY scenario_id, simulation_year
)

SELECT scenario_id, simulation_year, 'invalid_employment_status' as issue_type, invalid_employment_status as issue_count
FROM validation_summary WHERE invalid_employment_status > 0
UNION ALL
SELECT scenario_id, simulation_year, 'invalid_rates' as issue_type, invalid_rates as issue_count
FROM validation_summary WHERE invalid_rates > 0
UNION ALL
SELECT scenario_id, simulation_year, 'missing_hashes' as issue_type, missing_hashes as issue_count
FROM validation_summary WHERE missing_hashes > 0
UNION ALL
SELECT scenario_id, simulation_year, 'active_flag_mismatches' as issue_type, active_flag_mismatches as issue_count
FROM validation_summary WHERE active_flag_mismatches > 0;

-- DBT TEST: Employment transition validation
-- File: tests/validate_employment_transitions.sql

WITH invalid_transitions AS (
  SELECT
    curr.employee_id,
    curr.scenario_id,
    curr.simulation_year,
    curr.employment_status,
    prev.employment_status as prev_status,
    'Invalid employment transition' as issue_description
  FROM {{ ref('int_deferral_rate_state_accumulator') }} curr
  LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} prev
    ON curr.employee_id = prev.employee_id
    AND curr.scenario_id = prev.scenario_id
    AND prev.simulation_year = curr.simulation_year - 1
  WHERE (
    -- Invalid transitions that shouldn't occur
    (prev.employment_status = 'terminated' AND curr.employment_status = 'terminated'
     AND curr.state_change_type = 'new_employee') OR
    (curr.employment_status = 'active' AND curr.hire_date IS NULL AND curr.simulation_year > 2025) OR
    (curr.employment_status = 'terminated' AND curr.termination_date IS NULL) OR
    (prev.employment_status = 'terminated' AND curr.employment_status = 'active'
     AND curr.rehire_date IS NULL)
  )
)

SELECT * FROM invalid_transitions;

-- DBT TEST: Rate change source validation
-- File: tests/validate_rate_change_sources.sql

SELECT
  employee_id,
  scenario_id,
  simulation_year,
  current_deferral_rate,
  source_type,
  state_change_type,
  'Invalid rate change source' as issue_description
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE (
  -- Rate changed but source type doesn't support changes
  (state_change_type = 'rate_changed' AND source_type NOT IN ('enrollment', 'escalation', 'retroactive_adjustment', 'compliance_adjustment')) OR

  -- Escalation source but rate didn't increase
  (source_type = 'escalation' AND current_deferral_rate <= LAG(current_deferral_rate)
   OVER (PARTITION BY employee_id, scenario_id ORDER BY simulation_year)) OR

  -- No change but rate is different
  (state_change_type = 'no_change' AND ABS(current_deferral_rate - LAG(current_deferral_rate)
   OVER (PARTITION BY employee_id, scenario_id ORDER BY simulation_year)) > 0.001)
);
```

#### 7. Performance-Optimized Monitoring Queries

```sql
-- HIGH-PERFORMANCE CONTINUOUS MONITORING QUERIES
-- Optimized for real-time state continuity monitoring during simulation execution

-- Quick health check (executes in <100ms)
CREATE OR REPLACE VIEW quick_health_check AS
SELECT
  scenario_id,
  simulation_year,
  COUNT(*) as total_records,
  COUNT(CASE WHEN employment_status IN ('active', 'terminated') THEN 1 END) as valid_status_count,
  COUNT(CASE WHEN current_deferral_rate BETWEEN 0 AND 1 THEN 1 END) as valid_rate_count,
  COUNT(CASE WHEN financial_audit_hash IS NOT NULL THEN 1 END) as hash_present_count,
  ROUND(100.0 * COUNT(CASE WHEN employment_status IN ('active', 'terminated') THEN 1 END) / COUNT(*), 1) as health_percentage
FROM int_deferral_rate_state_accumulator
GROUP BY scenario_id, simulation_year
HAVING health_percentage < 99.0  -- Only show problematic scenarios
ORDER BY health_percentage ASC;

-- Anomaly detection for immediate alerting (executes in <200ms)
CREATE OR REPLACE VIEW anomaly_detection AS
WITH rate_changes AS (
  SELECT
    employee_id,
    scenario_id,
    simulation_year,
    current_deferral_rate,
    LAG(current_deferral_rate) OVER (PARTITION BY employee_id, scenario_id ORDER BY simulation_year) as prev_rate,
    source_type,
    state_change_type
  FROM int_deferral_rate_state_accumulator
)
SELECT
  scenario_id,
  simulation_year,
  'extreme_rate_change' as anomaly_type,
  COUNT(*) as anomaly_count,
  MIN(ABS(current_deferral_rate - prev_rate)) as min_change,
  MAX(ABS(current_deferral_rate - prev_rate)) as max_change
FROM rate_changes
WHERE ABS(current_deferral_rate - COALESCE(prev_rate, 0)) > 0.5
  AND source_type != 'plan_transfer'  -- Plan transfers can have large changes
GROUP BY scenario_id, simulation_year
HAVING anomaly_count > 0;
```

This comprehensive cross-year state continuity validation framework provides:

1. **Complete State Consistency Validation** - Detects orphaned states and missing transitions
2. **Employment Transition Validation** - Ensures all lifecycle changes follow business rules
3. **Rate Change Validation** - Validates source lineage and change reasonableness
4. **Data Lineage Validation** - Verifies complete audit trail continuity
5. **Automated Monitoring** - Proactive anomaly detection with alert thresholds
6. **dbt Test Integration** - Comprehensive data quality tests for CI/CD
7. **Performance-Optimized Monitoring** - Real-time health checks and anomaly detection

The validation system maintains the highest data quality standards while providing clear visibility into any state continuity issues across multi-year simulations.

## Design Specifications

### DuckDB Performance Requirements & Optimization Targets

#### Performance Benchmarks
- [ ] **Execution time**: <2 seconds per simulation year (50% improvement from 5s target)
- [ ] **Memory usage**: <500MB peak memory for 100K employee dataset
- [ ] **Throughput**: Process 50K employees/second during state accumulation
- [ ] **Join performance**: <200ms for largest employment status join operations
- [ ] **Aggregation speed**: <100ms for year-over-year rate change calculations

#### DuckDB-Specific Optimizations
- [ ] **Columnar processing**: Leverage vectorized operations for deferral rate calculations
- [ ] **Memory management**: Use DuckDB's automatic memory management with 80% available RAM
- [ ] **Parallel execution**: Enable multi-threading with `SET threads=4` for 100K+ employee datasets
- [ ] **Query pushdown**: Optimize filter pushdown for `simulation_year` partitions
- [ ] **Join optimization**: Use DuckDB's hash join optimization for employee lifecycle joins

#### Memory-Efficient Data Types Impact
```sql
-- Memory savings from optimized types (per 1M rows):
-- HUGEINT vs UUID string: 50MB savings (16 bytes vs 36+ bytes)
-- TINYINT vs VARCHAR enums: 300MB savings (1 byte vs 10+ bytes avg)
-- FLOAT vs DECIMAL(5,4): 200MB savings (4 bytes vs 8 bytes)
-- INTEGER date vs TIMESTAMP: 400MB savings (4 bytes vs 8 bytes)
-- Total estimated memory reduction: ~950MB per 1M rows (60% improvement)
```

#### DuckDB Configuration for Optimal Performance
```sql
-- Memory and threading configuration
SET memory_limit = '80%';  -- Use 80% of available system memory
SET threads = 4;           -- Optimize for 4-core systems (adjust as needed)
SET enable_optimizer = true;
SET enable_http_metadata_cache = true;

-- Query optimization settings
SET force_parallelism = true;      -- Enable parallel query execution
SET preserve_insertion_order = false;  -- Allow query reordering for performance
SET enable_object_cache = true;    -- Cache objects for better performance

-- Storage optimization
SET checkpoint_threshold = '1GB';  -- Optimize for large datasets
```

### Edge Case Handling & Data Quality Tests

#### dbt Tests for Data Validation with Employment Lifecycle Integration
```sql
-- Deferral rate bounds validation
{{ dbt_expectations.expect_column_values_to_be_between(
    column_name='current_deferral_rate',
    min_value=0,
    max_value=1
) }}

-- Employment status validation
{{ dbt_expectations.expect_column_values_to_be_in_set(
    column_name='employment_status',
    value_set=['active', 'terminated', 'rehired', 'unknown']
) }}

-- Source type validation with enhanced lifecycle sources
{{ dbt_expectations.expect_column_values_to_be_in_set(
    column_name='source_type',
    value_set=['enrollment', 'escalation', 'baseline', 'plan_transfer', 'retroactive_adjustment']
) }}

-- State change type validation
{{ dbt_expectations.expect_column_values_to_be_in_set(
    column_name='state_change_type',
    value_set=['new_employee', 'rate_changed', 'plan_transferred', 'no_change']
) }}

-- Cost attribution rate precision validation
{{ dbt_expectations.expect_column_values_to_be_between(
    column_name='cost_attribution_rate',
    min_value=0,
    max_value=999.999999
) }}

-- UUID field validation for audit compliance
{{ dbt_expectations.expect_column_values_to_match_regex(
    column_name='accumulator_id',
    regex='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
) }}

-- Employment lifecycle consistency validation
SELECT accumulator_id, employee_id, employment_status, termination_date, is_active
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE employment_status = 'terminated'
  AND termination_date IS NULL

-- HCE status consistency validation
SELECT accumulator_id, employee_id, hce_status, hce_determination_date
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE hce_status = TRUE
  AND hce_determination_date IS NULL

-- Plan transfer consistency validation
SELECT accumulator_id, employee_id, state_change_type, previous_plan_design_id, plan_transfer_date
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE state_change_type = 'plan_transferred'
  AND (previous_plan_design_id IS NULL OR plan_transfer_date IS NULL)

-- Retroactive adjustment consistency validation
SELECT accumulator_id, employee_id, is_retroactive_adjustment, original_deferral_rate, adjustment_reason
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE is_retroactive_adjustment = TRUE
  AND (original_deferral_rate IS NULL OR adjustment_reason IS NULL)

-- Employment eligibility window validation
SELECT accumulator_id, employee_id, effective_date, eligibility_start_date, termination_date
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE effective_date < eligibility_start_date
   OR (termination_date IS NOT NULL AND effective_date > termination_date AND source_type != 'retroactive_adjustment')

-- HCE rate restriction validation
SELECT d.accumulator_id, d.employee_id, d.current_deferral_rate, d.hce_status, pd.hce_max_deferral_rate
FROM {{ ref('int_deferral_rate_state_accumulator') }} d
JOIN {{ ref('dim_plan_design') }} pd ON d.plan_design_id = pd.plan_design_id
WHERE d.hce_status = TRUE
  AND pd.hce_max_deferral_rate IS NOT NULL
  AND d.current_deferral_rate > pd.hce_max_deferral_rate

-- Cross-year continuity validation for employment transitions
WITH year_transitions AS (
  SELECT
    curr.employee_id,
    curr.employment_status as current_status,
    prev.employment_status as previous_status,
    curr.simulation_year
  FROM {{ ref('int_deferral_rate_state_accumulator') }} curr
  LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} prev
    ON curr.employee_id = prev.employee_id
    AND curr.scenario_id = prev.scenario_id
    AND prev.simulation_year = curr.simulation_year - 1
)
SELECT employee_id, current_status, previous_status, simulation_year
FROM year_transitions
WHERE (previous_status = 'terminated' AND current_status = 'active' AND rehire_date IS NULL)
   OR (previous_status = 'active' AND current_status = 'terminated' AND termination_date IS NULL)

-- Financial audit hash integrity validation with lifecycle data
{{ dbt_expectations.expect_column_values_to_match_regex(
    column_name='financial_audit_hash',
    regex='^[a-f0-9]{64}$'
) }}

-- Cost allocation completeness for active records
SELECT accumulator_id, employee_id, is_active, employment_status
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE is_active = TRUE
  AND employment_status != 'active'

-- COMPREHENSIVE COST ATTRIBUTION VALIDATION TESTS
-- ================================================

-- Cost attribution UUID uniqueness validation
{{ dbt_utils.unique_combination_of_columns(
    columns=['cost_allocation_id']
) }}

{{ dbt_utils.unique_combination_of_columns(
    columns=['cost_event_id']
) }}

{{ dbt_utils.unique_combination_of_columns(
    columns=['cost_driver_id']
) }}

-- Organizational hierarchy data completeness validation
SELECT accumulator_id, employee_id, department_code, cost_center_id
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE department_code IS NULL
   OR cost_center_id IS NULL
   OR work_location_code IS NULL
   OR region_code IS NULL

-- Cost attribution rate bounds validation
{{ dbt_expectations.expect_column_values_to_be_between(
    column_name='cost_attribution_rate',
    min_value=0.000001,
    max_value=3.000000
) }}

-- Allocated cost amount non-negative validation
{{ dbt_expectations.expect_column_values_to_be_of_type(
    column_name='allocated_cost_amount',
    type_='decimal'
) }}

SELECT accumulator_id, employee_id, allocated_cost_amount
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE allocated_cost_amount < 0

-- Department cost share rate validation
{{ dbt_expectations.expect_column_values_to_be_between(
    column_name='department_cost_share_rate',
    min_value=0.000001,
    max_value=1.500000
) }}

-- GL Account code format validation
{{ dbt_expectations.expect_column_values_to_match_regex(
    column_name='gl_account_code',
    regex='^[0-9]{4}-[0-9]{3}$'
) }}

-- Budget period format validation
{{ dbt_expectations.expect_column_values_to_match_regex(
    column_name='budget_period',
    regex='^[0-9]{4}-Q[1-4]$'
) }}

-- Cost period temporal consistency validation
SELECT accumulator_id, employee_id, cost_period_start, cost_period_end
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE cost_period_start >= cost_period_end
   OR cost_period_start IS NULL
   OR cost_period_end IS NULL

-- Project code consistency validation
SELECT accumulator_id, employee_id, project_code, project_cost_type
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE project_code = 'OVERHEAD'
  AND project_cost_type != 'overhead_allocated'

-- Team-based attribution consistency
SELECT accumulator_id, employee_id, team_id, cost_attribution_team
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE team_id != 'TEAM_UNKNOWN'
  AND cost_attribution_team = 'UNASSIGNED_TEAM'

-- Cost driver category enumeration validation
{{ dbt_expectations.expect_column_values_to_be_in_set(
    column_name='cost_driver_category',
    value_set=['hce_enrollment_driver', 'nhce_enrollment_driver', 'automatic_escalation_driver',
               'compliance_driver', 'ma_integration_driver', 'standard_operational_driver']
) }}

-- Cost allocation type enumeration validation
{{ dbt_expectations.expect_column_values_to_be_in_set(
    column_name='cost_allocation_type',
    value_set=['compliance_adjustment', 'administrative_transfer', 'participant_enrollment',
               'automatic_escalation', 'new_hire_setup', 'operational_standard']
) }}

-- Geographic attribution consistency validation
SELECT accumulator_id, employee_id, region_code, country_code, work_location_code
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE (region_code = 'NAM' AND country_code NOT IN ('US', 'CA', 'MX'))
   OR (region_code = 'EMEA' AND country_code NOT IN ('GB', 'DE', 'FR', 'IT', 'ES', 'NL'))
   OR (region_code = 'APAC' AND country_code NOT IN ('JP', 'CN', 'IN', 'AU', 'SG'))

-- Management hierarchy consistency validation
SELECT accumulator_id, employee_id, manager_employee_id, org_hierarchy_level
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE manager_employee_id = employee_id -- Self-reporting validation
   OR (org_hierarchy_level = 1 AND manager_employee_id = 'MGR_UNKNOWN')
   OR (org_hierarchy_level > 1 AND manager_employee_id != 'MGR_UNKNOWN' AND manager_employee_id IS NULL)

-- Cost basis amount reasonableness validation
SELECT accumulator_id, employee_id, cost_basis_amount, department_code
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE cost_basis_amount < 20000 -- Below minimum wage threshold
   OR cost_basis_amount > 1000000 -- Above reasonable executive threshold

-- Financial quarter and cost period alignment validation
SELECT accumulator_id, employee_id, financial_quarter, cost_allocation_quarter, effective_date
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE EXTRACT(QUARTER FROM effective_date) != financial_quarter
   OR DATE_TRUNC('quarter', effective_date) != cost_allocation_quarter

-- Cost attribution rate vs allocated cost consistency validation
WITH cost_consistency_check AS (
  SELECT
    accumulator_id,
    employee_id,
    cost_basis_amount,
    cost_attribution_rate,
    allocated_cost_amount,
    -- Calculate expected allocated cost
    ROUND(cost_basis_amount * cost_attribution_rate * 0.001, 2) as expected_allocated_cost,
    -- Allow for minor rounding differences
    ABS(allocated_cost_amount - ROUND(cost_basis_amount * cost_attribution_rate * 0.001, 2)) as cost_variance
  FROM {{ ref('int_deferral_rate_state_accumulator') }}
)
SELECT accumulator_id, employee_id, allocated_cost_amount, expected_allocated_cost, cost_variance
FROM cost_consistency_check
WHERE cost_variance > 0.50 -- Allow 50 cent variance for rounding

-- Cross-year cost attribution consistency validation
WITH yearly_cost_comparison AS (
  SELECT
    employee_id,
    cost_center_id,
    cost_driver_category,
    simulation_year,
    AVG(cost_attribution_rate) as avg_yearly_attribution_rate,
    COUNT(*) as yearly_events
  FROM {{ ref('int_deferral_rate_state_accumulator') }}
  GROUP BY 1,2,3,4
),
year_over_year_variance AS (
  SELECT
    employee_id,
    cost_center_id,
    cost_driver_category,
    simulation_year,
    avg_yearly_attribution_rate,
    LAG(avg_yearly_attribution_rate) OVER (
      PARTITION BY employee_id, cost_center_id, cost_driver_category
      ORDER BY simulation_year
    ) as prior_year_attribution_rate,
    ABS(avg_yearly_attribution_rate - LAG(avg_yearly_attribution_rate) OVER (
      PARTITION BY employee_id, cost_center_id, cost_driver_category
      ORDER BY simulation_year
    )) as year_over_year_attribution_variance
  FROM yearly_cost_comparison
)
SELECT employee_id, cost_center_id, cost_driver_category, simulation_year,
       avg_yearly_attribution_rate, prior_year_attribution_rate, year_over_year_attribution_variance
FROM year_over_year_variance
WHERE year_over_year_attribution_variance > 0.5 -- Flag major attribution changes year-over-year
  AND prior_year_attribution_rate IS NOT NULL

-- Exactly one current state per employee/scenario/year
SELECT scenario_id, plan_design_id, employee_id, simulation_year, COUNT(*)
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE is_current = TRUE
GROUP BY 1, 2, 3, 4
HAVING COUNT(*) > 1

-- UUID uniqueness across all audit fields
{{ dbt_utils.unique_combination_of_columns(
    columns=['accumulator_id']
) }}

-- Cross-year state consistency validation
WITH state_consistency AS (
  SELECT
    curr.employee_id,
    curr.simulation_year,
    curr.previous_year_rate,
    prev.current_deferral_rate as actual_prev_rate,
    curr.state_change_type
  FROM {{ ref('int_deferral_rate_state_accumulator') }} curr
  LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} prev
    ON curr.employee_id = prev.employee_id
    AND curr.scenario_id = prev.scenario_id
    AND prev.simulation_year = curr.simulation_year - 1
)
SELECT employee_id, simulation_year, previous_year_rate, actual_prev_rate, state_change_type
FROM state_consistency
WHERE ABS(COALESCE(previous_year_rate, 0) - COALESCE(actual_prev_rate, 0)) > 0.001 -- Allow for rounding differences
  AND actual_prev_rate IS NOT NULL

-- Material change flag validation for regulatory compliance
SELECT accumulator_id, employee_id, regulatory_flag, source_type,
       ABS(COALESCE(current_deferral_rate, 0) - COALESCE(original_deferral_rate, 0)) as rate_change
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE source_type = 'retroactive_adjustment'
  AND ABS(COALESCE(current_deferral_rate, 0) - COALESCE(original_deferral_rate, 0)) > 0.02 -- 2% threshold
  AND regulatory_flag = FALSE
```

#### Business Logic Edge Cases with Lifecycle Integration
- [ ] **Explicit 0% vs NULL**: Distinguish intentional opt-outs (0%) from missing data
- [ ] **New hires without explicit rate**: Use plan defaults from baseline with eligibility window validation
- [ ] **Enhanced timestamp tie-breaking**: retroactive > enrollment > plan_transfer > escalation > baseline, then by source_event_id
- [ ] **Plan min/max bounds**: Apply plan-level rate bounds validation with HCE restrictions
- [ ] **Employee lifecycle integration**: Comprehensive employment status validation through `int_workforce_active_for_events`
- [ ] **Termination scenarios**: Allow retroactive adjustments for terminated employees, block future enrollments
- [ ] **Rehire scenarios**: Reset to baseline or preserve rates based on business rules and rate_preservation_flag
- [ ] **Plan transfer scenarios**: Handle M&A rate preservation with plan design compatibility validation
- [ ] **HCE status changes**: Automatic rate restriction application when employees become HCEs
- [ ] **Cross-year continuity**: Validate employment transitions and state consistency across simulation years
- [ ] **Retroactive adjustment scope**: Handle backdated changes with proper compliance flagging
- [ ] **Eligibility window enforcement**: Ensure all rate changes occur within valid employment/participation periods

### Enhanced Integration Points with Employment Lifecycle

#### Upstream Dependencies (Sources)
1. `int_enrollment_events` - enrollment deferral rates (filtered by employment status)
2. `int_deferral_rate_escalation_events` - automatic rate increases (employment-status aware)
3. `int_baseline_workforce` - default rates for new hires (eligibility-filtered)
4. `int_workforce_active_for_events` - employment status, termination/rehire tracking
5. `int_hce_determination` - HCE status for rate restrictions
6. `int_plan_transfer_events` - M&A scenarios with rate preservation logic
7. `int_retroactive_deferral_adjustments` - backdated changes with compliance tracking
8. Previous year's `int_deferral_rate_state_accumulator` - temporal state with lifecycle continuity

#### Downstream Integration (Consumers)
1. `int_employee_contributions` - contribution calculations with lifecycle-aware active status
2. `validate_deferral_rate_continuity` - cross-year state consistency validation
3. `fct_workforce_snapshot` - final workforce state with comprehensive employment tracking
4. Compliance/reporting models - regulatory flagging and audit trail
5. Analytics dashboards - employment lifecycle impact analysis
6. Cost attribution models - lifecycle-aware cost allocation

### Materialization Strategy

#### DuckDB-Optimized Incremental Configuration
```sql
{{ config(
    materialized='incremental',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    incremental_strategy='merge',
    -- DuckDB-specific optimizations
    pre_hook=[
      "SET memory_limit = '80%'",
      "SET threads = 4",
      "SET force_parallelism = true",
      "SET enable_optimizer = true"
    ],
    post_hook=[
      "ANALYZE {{ this }}",  -- Update statistics for query optimizer
      "CHECKPOINT"           -- Force checkpoint for optimal storage
    ]
) }}

-- DuckDB Query Hints for Optimal Execution
/*+ USE_HASH_JOIN(current_year_employment_status) */
/*+ PARALLEL_HASH_JOIN */
```

#### DuckDB Performance Optimizations
- **Vectorized processing**: DuckDB automatically vectorizes arithmetic operations on deferral rates
- **Columnar compression**: Pre-computed derived columns reduce repeated calculations
- **Hash join optimization**: Use employee_id_hash for faster join performance
- **Memory-aware processing**: Automatic spill-to-disk for datasets exceeding memory
- **Parallel execution**: Multi-threaded processing for employee lifecycle joins
- **Early materialization**: Compute enum conversions once for reuse across CTEs

#### Advanced DuckDB Features
```sql
-- Use DuckDB's advanced analytical functions for state transitions
WITH optimized_state_changes AS (
  SELECT *,
    -- Window functions optimized for columnar storage
    LAG(current_deferral_rate) OVER (
      PARTITION BY employee_id
      ORDER BY simulation_year, effective_date
    ) as previous_rate,

    -- Use DuckDB's fast aggregation for rate change detection
    COUNT(*) OVER (
      PARTITION BY employee_id
      ORDER BY simulation_year
      ROWS UNBOUNDED PRECEDING
    ) as change_sequence,

    -- Leverage DuckDB's efficient date arithmetic
    DATE_DIFF('month', effective_date, CURRENT_DATE) as months_elapsed

  FROM unified_state_changes
)

-- DuckDB automatic query optimization will:
-- 1. Push filters down to storage layer
-- 2. Optimize join order based on cardinality
-- 3. Use columnar vectorization for aggregations
-- 4. Parallelize window function computation
```

#### Memory Management Strategy
```sql
-- Monitor memory usage during execution
SELECT
  'Memory Usage' as metric,
  current_setting('memory_limit') as memory_limit,
  pg_size_pretty(pg_total_relation_size('{{ this }}')) as table_size
FROM (VALUES (1)) as dummy(x);

-- DuckDB automatic memory management:
-- - Spills to disk when memory threshold exceeded
-- - Compresses columnar data automatically
-- - Uses memory mapping for large datasets
-- - Optimizes memory allocation per thread
```

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
  ),

-- Fixed anti-join with proper NULL handling
existing_employees_v2 AS (
  SELECT DISTINCT employee_id FROM previous_year_state WHERE employee_id IS NOT NULL
  UNION
  SELECT DISTINCT employee_id FROM enrollment_changes WHERE employee_id IS NOT NULL
  UNION
  SELECT DISTINCT employee_id FROM escalation_changes WHERE employee_id IS NOT NULL
),

filtered_baseline_defaults_v2 AS (
  SELECT
    b.scenario_id, b.plan_design_id, b.employee_id,
    b.baseline_deferral_rate AS new_deferral_rate,
    b.employee_hire_date AS effective_date,
    'baseline' AS source_type,
    NULL AS source_event_id
  FROM {{ ref('int_baseline_workforce') }} b
  LEFT JOIN existing_employees_v2 e ON b.employee_id = e.employee_id
  WHERE b.simulation_year = {{ var('simulation_year') }}
    AND b.employment_status = 'active'
    AND e.employee_id IS NULL  -- Anti-join with LEFT JOIN + NULL check
),

-- Combine with proper precedence
all_changes AS (
  SELECT *, 1 AS event_priority FROM enrollment_changes
  UNION ALL
  SELECT *, 2 AS event_priority FROM escalation_changes
  UNION ALL
  SELECT *, 3 AS event_priority FROM filtered_baseline_defaults_v2
),

-- Deterministic precedence resolution with enhanced NULL handling
ranked_changes AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY scenario_id, plan_design_id, employee_id
      ORDER BY
        event_priority ASC,
        effective_date DESC NULLS LAST,
        COALESCE(source_event_id, 'BASELINE_' || employee_id) ASC  -- Deterministic NULL handling
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

## DuckDB Performance Monitoring & Benchmarking

### Real-Time Performance Monitoring Queries
```sql
-- 1. Execution time monitoring with microsecond precision
WITH performance_metrics AS (
  SELECT
    'State Accumulator Execution' as operation,
    NOW() as start_time,
    (SELECT COUNT(*) FROM {{ this }}) as row_count
)
SELECT
  operation,
  row_count,
  EXTRACT(EPOCH FROM (NOW() - start_time)) * 1000 as execution_time_ms,
  CASE
    WHEN EXTRACT(EPOCH FROM (NOW() - start_time)) * 1000 < 2000 THEN 'EXCELLENT'
    WHEN EXTRACT(EPOCH FROM (NOW() - start_time)) * 1000 < 5000 THEN 'GOOD'
    ELSE 'NEEDS_OPTIMIZATION'
  END as performance_rating
FROM performance_metrics;

-- 2. Memory usage analysis per year
SELECT
  simulation_year,
  COUNT(*) as employee_count,
  COUNT(DISTINCT employee_id) as unique_employees,
  pg_size_pretty(pg_total_relation_size('{{ this }}')) as table_size,
  ROUND(pg_total_relation_size('{{ this }}') / COUNT(*)::FLOAT, 2) as bytes_per_row,
  -- Memory efficiency score (lower is better)
  CASE
    WHEN pg_total_relation_size('{{ this }}') / COUNT(*)::FLOAT < 200 THEN 'EXCELLENT'
    WHEN pg_total_relation_size('{{ this }}') / COUNT(*)::FLOAT < 400 THEN 'GOOD'
    ELSE 'NEEDS_OPTIMIZATION'
  END as memory_efficiency
FROM {{ this }}
GROUP BY simulation_year
ORDER BY simulation_year;

-- 3. Join performance analysis
EXPLAIN ANALYZE
SELECT
  COUNT(*) as total_records,
  COUNT(DISTINCT emp.employee_id) as employees_with_status,
  COUNT(DISTINCT acc.employee_id) as employees_with_accumulator,
  AVG(EXTRACT(EPOCH FROM (acc.last_updated_at - acc.created_at))) as avg_processing_time_seconds
FROM {{ this }} acc
LEFT JOIN {{ ref('int_workforce_active_for_events') }} emp
  ON acc.employee_id = emp.employee_id
  AND acc.scenario_id = emp.scenario_id
  AND emp.simulation_year = {{ var('simulation_year') }};

-- 4. Columnar compression effectiveness
SELECT
  'Compression Analysis' as metric,
  pg_size_pretty(pg_total_relation_size('{{ this }}')) as actual_size,
  pg_size_pretty(COUNT(*) * 500) as estimated_uncompressed_size, -- 500 bytes per row estimate
  ROUND(
    (1 - pg_total_relation_size('{{ this }}')::FLOAT / (COUNT(*) * 500)) * 100, 2
  ) as compression_ratio_percent
FROM {{ this }};
```

### DuckDB-Specific Performance Benchmarks
```sql
-- Benchmark 1: Vectorized deferral rate calculations
WITH rate_calculation_benchmark AS (
  SELECT
    simulation_year,
    COUNT(*) as total_calculations,
    NOW() as start_time
  FROM (
    SELECT
      simulation_year,
      -- DuckDB vectorized operations
      current_deferral_rate * cost_basis_amount as calculated_contribution,
      current_deferral_rate + 0.01 as escalated_rate,
      CASE WHEN hce_status THEN LEAST(current_deferral_rate, 0.15) ELSE current_deferral_rate END as restricted_rate
    FROM {{ this }}
    WHERE simulation_year = {{ var('simulation_year') }}
  ) calcs
  GROUP BY simulation_year
)
SELECT
  simulation_year,
  total_calculations,
  EXTRACT(EPOCH FROM (NOW() - start_time)) * 1000 as vectorization_time_ms,
  total_calculations / (EXTRACT(EPOCH FROM (NOW() - start_time)) + 0.001) as calculations_per_second,
  CASE
    WHEN total_calculations / (EXTRACT(EPOCH FROM (NOW() - start_time)) + 0.001) > 100000 THEN 'EXCELLENT'
    WHEN total_calculations / (EXTRACT(EPOCH FROM (NOW() - start_time)) + 0.001) > 50000 THEN 'GOOD'
    ELSE 'NEEDS_OPTIMIZATION'
  END as vectorization_performance
FROM rate_calculation_benchmark;

-- Benchmark 2: Hash join efficiency test
EXPLAIN (ANALYZE, BUFFERS)
SELECT
  acc.simulation_year,
  COUNT(*) as matched_records,
  AVG(acc.current_deferral_rate) as avg_deferral_rate
FROM {{ this }} acc
INNER JOIN {{ ref('int_baseline_workforce') }} bw
  ON acc.employee_id = bw.employee_id
  AND acc.scenario_id = bw.scenario_id
WHERE acc.simulation_year = {{ var('simulation_year') }}
GROUP BY acc.simulation_year;

-- Benchmark 3: Window function performance on columnar data
WITH window_performance_test AS (
  SELECT
    employee_id,
    simulation_year,
    current_deferral_rate,
    -- Test DuckDB's window function optimization
    LAG(current_deferral_rate) OVER (PARTITION BY employee_id ORDER BY simulation_year) as prev_rate,
    LEAD(current_deferral_rate) OVER (PARTITION BY employee_id ORDER BY simulation_year) as next_rate,
    AVG(current_deferral_rate) OVER (PARTITION BY employee_id ORDER BY simulation_year ROWS 2 PRECEDING) as moving_avg,
    ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY simulation_year) as row_num
  FROM {{ this }}
  WHERE simulation_year BETWEEN {{ var('simulation_year') }} - 2 AND {{ var('simulation_year') }}
)
SELECT
  'Window Function Performance' as test_name,
  COUNT(*) as rows_processed,
  COUNT(DISTINCT employee_id) as employees_processed,
  -- Performance should be >10K rows per second for window functions
  CASE
    WHEN COUNT(*) > 50000 THEN 'LARGE_DATASET'
    WHEN COUNT(*) > 10000 THEN 'MEDIUM_DATASET'
    ELSE 'SMALL_DATASET'
  END as dataset_size
FROM window_performance_test;
```

### Automated Performance Regression Detection
```sql
-- Create performance baseline table (run once)
CREATE OR REPLACE TABLE deferral_rate_performance_baselines AS
SELECT
  '{{ var("simulation_year") }}' as test_year,
  NOW() as baseline_date,
  COUNT(*) as baseline_row_count,
  pg_total_relation_size('{{ this }}') as baseline_size_bytes,
  2000 as target_execution_time_ms,  -- 2 second target
  500000000 as target_memory_bytes   -- 500MB target
FROM {{ this }};

-- Performance regression check (run with each execution)
WITH current_performance AS (
  SELECT
    COUNT(*) as current_row_count,
    pg_total_relation_size('{{ this }}') as current_size_bytes
  FROM {{ this }}
  WHERE simulation_year = {{ var('simulation_year') }}
),
regression_analysis AS (
  SELECT
    cp.current_row_count,
    cp.current_size_bytes,
    bp.baseline_row_count,
    bp.baseline_size_bytes,
    bp.target_memory_bytes,
    -- Calculate regression ratios
    ROUND(cp.current_size_bytes::FLOAT / bp.baseline_size_bytes, 2) as size_ratio,
    ROUND(cp.current_row_count::FLOAT / bp.baseline_row_count, 2) as row_ratio,
    cp.current_size_bytes <= bp.target_memory_bytes as memory_target_met
  FROM current_performance cp
  CROSS JOIN deferral_rate_performance_baselines bp
  WHERE bp.test_year = '{{ var("simulation_year") }}'
)
SELECT
  'Performance Regression Check' as check_type,
  current_row_count,
  pg_size_pretty(current_size_bytes) as current_size,
  size_ratio,
  row_ratio,
  memory_target_met,
  CASE
    WHEN size_ratio <= 1.1 AND memory_target_met THEN 'PASS'
    WHEN size_ratio <= 1.3 THEN 'WARNING'
    ELSE 'FAIL'
  END as performance_status,
  CASE
    WHEN size_ratio > 1.3 THEN 'Memory usage increased by ' || ROUND((size_ratio - 1) * 100) || '%'
    WHEN NOT memory_target_met THEN 'Memory target of 500MB exceeded'
    ELSE 'Performance within acceptable bounds'
  END as recommendation
FROM regression_analysis;
```

## Notes

This DuckDB-optimized design provides significant performance improvements over the original specification:

### Key DuckDB Optimizations Applied
1. **Memory-Efficient Data Types**: 60% memory reduction using HUGEINT, TINYINT, and FLOAT types
2. **Vectorized Processing**: Leverages DuckDB's columnar architecture for 10x faster calculations
3. **Hash Join Optimization**: Pre-computed hash keys and composite indexes for faster joins
4. **Parallel Execution**: Multi-threaded processing with automatic memory management
5. **Advanced Monitoring**: Real-time performance tracking with regression detection

### Performance Improvement Targets
- **Execution Time**: <2 seconds per year (50% improvement from 5s baseline)
- **Memory Usage**: <500MB for 100K employees (60% reduction through optimized types)
- **Throughput**: 50K employees/second processing (10x improvement through vectorization)
- **Join Performance**: <200ms for largest employment joins (5x improvement through hash optimization)

This design ensures the state accumulator implementation follows proven Epic E023 patterns while maximizing DuckDB analytical performance capabilities for sub-second workforce simulation queries.

### Key Implementation Notes
- **Upstream model reference corrected**: `int_deferral_rate_escalation_events` (not `int_deferral_escalation_events`)
- **Schema normalization**: All CTEs use common schema with `scenario_id`, `plan_design_id` propagation
- **Deterministic precedence**: enrollment > escalation > baseline, then latest effective_date
- **Baseline seeding**: Anti-join approach prevents all baseline records after Year 1
- **Materialization**: `merge` strategy with proper unique_key, not `insert_overwrite`
- **Audit fields**: Deterministic timestamps, single source_event_id, JSON as TEXT for portability
