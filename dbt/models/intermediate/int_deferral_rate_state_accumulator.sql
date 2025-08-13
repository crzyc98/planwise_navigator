{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['employee_id', 'simulation_year'],
    on_schema_change='sync_all_columns'
) }}

/*
  Deferral Rate State Accumulator - OPTIMIZED for DuckDB Performance

  Epic E036 Story S036-03: Temporal State Tracking Implementation
  Target: <2 seconds execution per year (improved from <5s baseline)

  PERFORMANCE OPTIMIZATIONS:
  - Early filtering by simulation_year using DuckDB column-store advantages
  - Efficient temporal JOIN patterns with proper column ordering
  - Vectorized processing for multi-year state transitions
  - Optimized data types for analytical workloads (DECIMAL precision, proper casting)
  - Incremental strategy: delete+insert keyed by year for idempotent re-runs
  - Removed physical indexes (unsupported by dbt-duckdb) in favor of logical partitioning

  ARCHITECTURE:
  - Uses only int_employee_compensation_by_year and int_deferral_rate_escalation_events
  - Eliminates circular dependency: int_employee_contributions → this model (no circular dependency)
  - Temporal accumulation pattern: Year N uses Year N-1 state + Year N events
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- Performance optimization: Early year filtering for DuckDB columnar processing

WITH enrolled_employees AS (
    -- Employees that are enrolled based on compensation table (direct source)
    SELECT
        employee_id,
        employee_enrollment_date as enrollment_date
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employment_status = 'active'
      AND is_enrolled_flag = true
      AND employee_id IS NOT NULL
),

base_active AS (
    -- Active employees from compensation table (may exclude current-year hires in first year)
    SELECT
        employee_id::VARCHAR as employee_id,
        employee_ssn::VARCHAR as employee_ssn,
        employee_compensation::DECIMAL(12,2) as employee_compensation,
        current_age::SMALLINT as current_age,
        level_id::SMALLINT as level_id,
        {{ simulation_year }}::INTEGER as simulation_year,
        is_enrolled_flag::BOOLEAN as baseline_is_enrolled,
        employee_enrollment_date as baseline_enrollment_date
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employment_status = 'active'
      AND employee_id IS NOT NULL
),

new_hires_current_year AS (
    -- Attributes for current-year hires (fills gap for first-year where base_active lacks NH_YYYY)
    SELECT
        he.employee_id::VARCHAR as employee_id,
        he.employee_ssn::VARCHAR as employee_ssn,
        he.compensation_amount::DECIMAL(12,2) as employee_compensation,
        he.employee_age::SMALLINT as current_age,
        he.level_id::SMALLINT as level_id
    FROM {{ ref('int_hiring_events') }} he
    WHERE he.simulation_year = {{ simulation_year }}
),

current_workforce AS (
    -- Union attributes for all enrolled employees this year, preferring base_active attrs
    -- FIXED: Only include employees that exist in compensation table to fix relationship test
    SELECT
        e.employee_id,
        COALESCE(b.employee_ssn, nh.employee_ssn) as employee_ssn,
        COALESCE(b.employee_compensation, nh.employee_compensation) as employee_compensation,
        COALESCE(b.current_age, nh.current_age) as current_age,
        COALESCE(b.level_id, nh.level_id) as level_id,
        {{ simulation_year }}::INTEGER as simulation_year,
        true as is_enrolled_flag,
        COALESCE(e.enrollment_date, b.baseline_enrollment_date) as employee_enrollment_date
    FROM enrolled_employees e
    LEFT JOIN base_active b ON e.employee_id = b.employee_id
    LEFT JOIN new_hires_current_year nh ON e.employee_id = nh.employee_id
    -- CRITICAL FIX: Ensure all employees exist in compensation table
    WHERE (b.employee_id IS NOT NULL OR nh.employee_id IS NOT NULL)
),

-- OPTIMIZED: Pre-filter escalation events by year range for better JOIN performance
escalation_events_filtered AS (
    SELECT
        employee_id::VARCHAR as employee_id,
        simulation_year::INTEGER as simulation_year,
        effective_date::DATE as effective_date,
        new_deferral_rate::DECIMAL(5,4) as new_deferral_rate,
        escalation_rate::DECIMAL(5,4) as escalation_rate,
        new_escalation_count::INTEGER as new_escalation_count,
        event_details::VARCHAR as event_details
    FROM {{ ref('int_deferral_rate_escalation_events') }}
    WHERE simulation_year <= {{ simulation_year }}
        AND employee_id IS NOT NULL  -- Prevent NULL joins
),

-- OPTIMIZED: Vectorized age/income segmentation for better DuckDB performance
employee_deferral_rate_mapping AS (
    SELECT
        w.employee_id,
        w.current_age,
        w.employee_compensation,
        -- OPTIMIZED: Use CASE expressions for vectorized processing
        CASE
            WHEN w.current_age < 30 THEN 'young'::VARCHAR
            WHEN w.current_age < 45 THEN 'mid_career'::VARCHAR
            WHEN w.current_age < 55 THEN 'senior'::VARCHAR
            ELSE 'mature'::VARCHAR
        END as age_segment,
        CASE
            WHEN w.level_id >= 5 OR w.employee_compensation >= 250000 THEN 'executive'::VARCHAR
            WHEN w.level_id >= 4 OR w.employee_compensation >= 150000 THEN 'high'::VARCHAR
            WHEN w.level_id >= 3 OR w.employee_compensation >= 100000 THEN 'moderate'::VARCHAR
            ELSE 'low_income'::VARCHAR
        END as income_segment
    FROM current_workforce w
),

-- OPTIMIZED: Efficient baseline rate lookup with proper JOIN ordering
employee_baseline_rates AS (
    SELECT
        m.employee_id,
        m.age_segment,
        m.income_segment,
        COALESCE(d.default_rate, 0.03::DECIMAL(5,4)) as baseline_deferral_rate,
        COALESCE(d.auto_escalate, false) as auto_escalate,
        COALESCE(d.auto_escalate_rate, 0.01::DECIMAL(5,4)) as auto_escalate_rate,
        COALESCE(d.max_rate, 0.50::DECIMAL(5,4)) as max_rate
    FROM employee_deferral_rate_mapping m
    LEFT JOIN (
        -- Pre-filter default rates for better JOIN performance
        SELECT age_segment, income_segment, default_rate, auto_escalate, auto_escalate_rate, max_rate,
               ROW_NUMBER() OVER (PARTITION BY age_segment, income_segment ORDER BY effective_date DESC) as rn
        FROM default_deferral_rates
        WHERE scenario_id = 'default'
          AND effective_date <= '{{ simulation_year }}-01-01'::DATE
    ) d ON m.age_segment = d.age_segment
        AND m.income_segment = d.income_segment
        AND d.rn = 1
),

-- OPTIMIZED: Vectorized escalation summary with efficient aggregations
employee_escalation_summary AS (
    SELECT
        employee_id,
        COUNT(*)::INTEGER as total_escalations,
        MAX(effective_date) as last_escalation_date,
        SUM(escalation_rate)::DECIMAL(5,4) as total_escalation_amount,
        MAX(new_deferral_rate)::DECIMAL(5,4) as latest_deferral_rate,
        MIN(effective_date) as first_escalation_date,
        -- OPTIMIZED: Use boolean aggregation for better performance
        BOOL_OR(simulation_year = {{ simulation_year }}) as had_escalation_this_year,
        MAX(CASE WHEN simulation_year = {{ simulation_year }} THEN event_details END) as latest_escalation_details
    FROM escalation_events_filtered
    GROUP BY employee_id
),

-- OPTIMIZED: Final state with efficient JOINs and proper data types
-- FIX: Ensure ALL enrolled employees get proper baseline deferral rates
final_state AS (
    SELECT
        w.employee_id,
        w.simulation_year,

        -- FIX: Current deferral rate with proper baseline mapping for ALL enrolled employees
        COALESCE(
            e.latest_deferral_rate,
            b.baseline_deferral_rate,
            -- Fallback based on age/income segmentation if no baseline rate mapped
            CASE
                WHEN w.current_age < 30 AND w.level_id <= 2 THEN 0.03::DECIMAL(5,4)  -- young, low_income
                WHEN w.current_age < 30 AND w.level_id <= 3 THEN 0.03::DECIMAL(5,4)  -- young, moderate
                WHEN w.current_age < 30 AND w.level_id <= 4 THEN 0.04::DECIMAL(5,4)  -- young, high
                WHEN w.current_age < 30 THEN 0.06::DECIMAL(5,4)                     -- young, executive
                WHEN w.current_age < 45 AND w.level_id <= 2 THEN 0.04::DECIMAL(5,4)  -- mid_career, low_income
                WHEN w.current_age < 45 AND w.level_id <= 3 THEN 0.06::DECIMAL(5,4)  -- mid_career, moderate
                WHEN w.current_age < 45 AND w.level_id <= 4 THEN 0.08::DECIMAL(5,4)  -- mid_career, high
                WHEN w.current_age < 45 THEN 0.10::DECIMAL(5,4)                     -- mid_career, executive
                WHEN w.current_age < 55 AND w.level_id <= 2 THEN 0.05::DECIMAL(5,4)  -- mature, low_income
                WHEN w.current_age < 55 AND w.level_id <= 3 THEN 0.08::DECIMAL(5,4)  -- mature, moderate
                WHEN w.current_age < 55 AND w.level_id <= 4 THEN 0.10::DECIMAL(5,4)  -- mature, high
                WHEN w.current_age < 55 THEN 0.12::DECIMAL(5,4)                     -- mature, executive
                WHEN w.level_id <= 2 THEN 0.06::DECIMAL(5,4)                        -- senior, low_income
                WHEN w.level_id <= 3 THEN 0.10::DECIMAL(5,4)                        -- senior, moderate
                WHEN w.level_id <= 4 THEN 0.12::DECIMAL(5,4)                        -- senior, high
                ELSE 0.15::DECIMAL(5,4)                                             -- senior, executive
            END
        ) as current_deferral_rate,

        -- OPTIMIZED: Escalation tracking with proper data types
        COALESCE(e.total_escalations, 0::INTEGER) as escalations_received,
        e.last_escalation_date,
        (COALESCE(e.total_escalations, 0) > 0) as has_escalations,
        'int_deferral_rate_escalation_events'::VARCHAR as escalation_source,

        -- OPTIMIZED: Current year activity flags
        COALESCE(e.had_escalation_this_year, false) as had_escalation_this_year,
        CASE WHEN COALESCE(e.had_escalation_this_year, false) THEN 1 ELSE 0 END as escalation_events_this_year,
        e.latest_escalation_details,

        -- OPTIMIZED: Rate analysis with safe division - use actual baseline rate for comparison
        COALESCE(b.baseline_deferral_rate, 0.05::DECIMAL(5,4)) as original_deferral_rate,
        CASE
            WHEN COALESCE(b.baseline_deferral_rate, 0.05) > 0.0001  -- Avoid division by very small numbers
            THEN ((COALESCE(e.latest_deferral_rate, b.baseline_deferral_rate, 0.05) - COALESCE(b.baseline_deferral_rate, 0.05)) / COALESCE(b.baseline_deferral_rate, 0.05))::DECIMAL(8,4)
            ELSE NULL
        END as escalation_rate_change_pct,
        COALESCE(e.total_escalation_amount, 0.0000::DECIMAL(5,4)) as total_escalation_amount,

        -- OPTIMIZED: Time-based metrics with efficient date arithmetic
        CASE
            WHEN e.first_escalation_date IS NOT NULL
            THEN ({{ simulation_year }} - EXTRACT('year' FROM e.first_escalation_date))::INTEGER
            ELSE NULL
        END as years_since_first_escalation,
        CASE
            WHEN e.last_escalation_date IS NOT NULL
            THEN (DATE '{{ simulation_year }}-12-31' - e.last_escalation_date)::INTEGER
            ELSE NULL
        END as days_since_last_escalation,

        -- Enrollment status (already filtered in workforce CTE)
        w.is_enrolled_flag,
        w.employee_enrollment_date,

        -- OPTIMIZED: Metadata with proper types
        CURRENT_TIMESTAMP as created_at,
        'default'::VARCHAR as scenario_id,
        CASE
            WHEN w.employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
            WHEN COALESCE(e.latest_deferral_rate, b.baseline_deferral_rate, 0.05) < 0 OR COALESCE(e.latest_deferral_rate, b.baseline_deferral_rate, 0.05) > 1 THEN 'INVALID_RATE'
            WHEN COALESCE(e.total_escalations, 0) < 0 THEN 'INVALID_ESCALATION_COUNT'
            ELSE 'VALID'
        END as data_quality_flag

    FROM current_workforce w
    LEFT JOIN employee_baseline_rates b
        ON w.employee_id = b.employee_id
    LEFT JOIN employee_escalation_summary e
        ON w.employee_id = e.employee_id
    -- FIX: Now ALL enrolled employees will have a deferral rate, not just those with escalation events
)

-- OPTIMIZED: Final output with incremental strategy
SELECT * FROM final_state

{% if is_incremental() %}
    -- OPTIMIZED: Incremental processing - delete+insert strategy keyed by year
    WHERE simulation_year = {{ simulation_year }}
{% endif %}
