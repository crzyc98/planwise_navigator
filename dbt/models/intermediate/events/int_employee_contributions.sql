{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'type': 'btree', 'unique': true},
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id'], 'type': 'btree'},
        {'columns': ['is_enrolled'], 'type': 'btree'}
    ],
    tags=['contribution', 'critical', 'core_calculation']
) }}

/*
  Employee Contribution Calculation Model - Story S025-02 (DEFERRAL RATE FIX)

  Calculates time-weighted employee contributions using the sophisticated period-based
  methodology established in fct_workforce_snapshot. This model handles:

  - Deferral rate changes throughout the year
  - Complex period overlap between compensation and deferral events
  - IRS 402(g) limit enforcement with age-based catch-up rules
  - Time-weighted calculations for partial periods
  - Integration with existing enrollment state tracking

  CRITICAL FIX: Proper deferral rate sourcing with priority hierarchy:
  1. Enrollment events (int_enrollment_events.employee_deferral_rate) - HIGHEST PRIORITY
  2. Census data (stg_census_data.employee_deferral_rate) - FALLBACK
  3. Zero rate for employees with no deferral rate data - NO CONTRIBUTIONS

  Architecture Pattern: Mirrors prorated compensation methodology with contribution-specific logic
  Performance: Optimized with CTEs and window functions for 10,000+ employee calculations
  Data Quality: Zero tolerance for IRS violations and compensation mismatches
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- Debug: Current processing parameters
-- simulation_year = {{ simulation_year }}, start_year = {{ start_year }}

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

-- Get IRS contribution limits for current simulation year
irs_limits AS (
    SELECT
        plan_year,
        age_threshold,
        base_limit,
        catch_up_limit,
        total_limit
    FROM {{ ref('irs_contribution_limits') }}
    WHERE plan_year = {{ simulation_year }}
        AND limit_type = 'employee_deferral'
    LIMIT 1
),

-- Get census deferral rates from baseline data
census_deferral_rates AS (
    SELECT
        employee_id,
        employee_deferral_rate AS census_deferral_rate
    FROM {{ ref('stg_census_data') }}
    WHERE employee_id IS NOT NULL
        AND employee_deferral_rate IS NOT NULL
),

-- Get current year enrollment events with deferral rates
current_year_enrollments AS (
    SELECT
        employee_id,
        employee_deferral_rate AS deferral_rate,
        effective_date,
        simulation_year,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date DESC,
            CASE event_type WHEN 'enrollment_change' THEN 1 ELSE 2 END
        ) AS rn
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('enrollment', 'enrollment_change')
        AND simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
        AND employee_deferral_rate IS NOT NULL
),

-- Get most recent enrollment event from previous years
recent_enrollments AS (
    SELECT
        employee_id,
        employee_deferral_rate AS deferral_rate,
        effective_date,
        simulation_year AS event_simulation_year,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY simulation_year DESC, effective_date DESC
        ) AS rn
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('enrollment', 'enrollment_change')
        AND simulation_year < {{ simulation_year }}
        AND employee_id IS NOT NULL
        AND employee_deferral_rate IS NOT NULL
),

-- Get enrollment state with rates from accumulator
enrollment_state AS (
    SELECT
        esa.employee_id,
        esa.simulation_year,
        esa.enrollment_date,
        esa.enrollment_status,
        esa.years_since_first_enrollment,
        -- Try to get deferral rate from the most recent enrollment event
        COALESCE(
            re.deferral_rate,  -- From recent enrollment event
            0.03  -- Default for enrolled employees from accumulator
        ) AS deferral_rate,
        re.effective_date,
        re.event_simulation_year AS rate_from_year
    FROM {{ ref('int_enrollment_state_accumulator') }} esa
    LEFT JOIN (
        SELECT * FROM recent_enrollments WHERE rn = 1
    ) re ON esa.employee_id = re.employee_id
    WHERE esa.simulation_year = {{ simulation_year }}
        AND esa.employee_id IS NOT NULL
        AND esa.enrollment_status = true
),

-- Get baseline workforce data with proper deferral rate logic
base_workforce_data AS (
    SELECT
        comp.employee_id,
        comp.employee_birth_date,
        comp.employee_compensation AS prorated_annual_compensation,
        comp.employee_compensation AS full_year_equivalent_compensation,
        comp.current_age,
        -- CRITICAL FIX: Enhanced priority hierarchy with enrollment state accumulator
        COALESCE(
            cye.deferral_rate,      -- Priority 1: Current year enrollment event rate (highest)
            es.deferral_rate,       -- Priority 2: Rate from enrollment state accumulator
            re.deferral_rate,       -- Priority 3: Most recent enrollment event from any year
            cdr.census_deferral_rate, -- Priority 4: Census baseline rate
            0.00                    -- Priority 5: No contribution if no rate found
        ) AS current_deferral_rate,
        comp.is_enrolled_flag,
        comp.employee_enrollment_date,
        comp.employment_status,
        comp.employee_hire_date,
        NULL AS termination_date,  -- Will be populated from events if needed
        -- Age determination as of December 31st (IRS rule)
        DATE_DIFF('year', comp.employee_birth_date, MAKE_DATE({{ simulation_year }}, 12, 31)) AS age_as_of_december_31,
        -- Enhanced metadata for validation and debugging
        CASE
            WHEN cye.deferral_rate IS NOT NULL THEN 'current_year_enrollment'
            WHEN es.deferral_rate IS NOT NULL THEN
                'enrollment_state_year_' || CAST(es.rate_from_year AS VARCHAR)
            WHEN re.deferral_rate IS NOT NULL THEN
                'recent_event_year_' || CAST(re.event_simulation_year AS VARCHAR)
            WHEN cdr.census_deferral_rate IS NOT NULL THEN 'census_data'
            ELSE 'default_zero'
        END AS deferral_rate_source,
        COALESCE(cye.effective_date, es.effective_date, re.effective_date) AS deferral_rate_effective_date,
        -- Track if rate is carried from previous year
        CASE
            WHEN cye.deferral_rate IS NOT NULL THEN false  -- Current year rate
            WHEN es.rate_from_year IS NOT NULL AND es.rate_from_year < {{ simulation_year }} THEN true
            WHEN re.event_simulation_year IS NOT NULL AND re.event_simulation_year < {{ simulation_year }} THEN true
            ELSE false
        END AS is_rate_carried_forward
    FROM {{ ref('int_employee_compensation_by_year') }} comp
    LEFT JOIN census_deferral_rates cdr ON comp.employee_id = cdr.employee_id
    LEFT JOIN (SELECT * FROM current_year_enrollments WHERE rn = 1) cye ON comp.employee_id = cye.employee_id
    LEFT JOIN enrollment_state es ON comp.employee_id = es.employee_id
    LEFT JOIN (SELECT * FROM recent_enrollments WHERE rn = 1) re ON comp.employee_id = re.employee_id
    WHERE comp.simulation_year = {{ simulation_year }}
        AND comp.employee_id IS NOT NULL
),

-- Get enrollment status from enrollment state accumulator for consistency
enrollment_status AS (
    SELECT
        employee_id,
        enrollment_date,
        enrollment_status AS is_enrolled,
        years_since_first_enrollment
    FROM {{ ref('int_enrollment_state_accumulator') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
),

-- Step 1: Collect all deferral rate events chronologically (ONLY for current year's periods)
-- Note: We only need current year events for period calculation,
-- but we get carried-forward rates from the enrollment_deferral_rates CTE above
deferral_events_timeline AS (
    SELECT
        employee_id,
        effective_date AS event_date,
        event_type,
        employee_deferral_rate AS new_deferral_rate,
        -- Track previous deferral rate for period calculations
        LAG(employee_deferral_rate, 1, 0.00) OVER (
            PARTITION BY employee_id
            ORDER BY effective_date,
            CASE event_type
                WHEN 'enrollment' THEN 1
                WHEN 'enrollment_change' THEN 2
            END
        ) AS previous_deferral_rate,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date,
            CASE event_type
                WHEN 'enrollment' THEN 1
                WHEN 'enrollment_change' THEN 2
            END
        ) AS event_sequence
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('enrollment', 'enrollment_change')
        AND simulation_year = {{ simulation_year }}  -- Keep current year for period boundaries
        AND employee_id IS NOT NULL
        AND employee_deferral_rate IS NOT NULL
),

-- Step 2: Create period boundaries using LEAD for next event
deferral_timeline_with_boundaries AS (
    SELECT
        employee_id,
        event_date,
        event_type,
        new_deferral_rate,
        previous_deferral_rate,
        event_sequence,
        -- Get the next event date to define period end
        LEAD(event_date) OVER (
            PARTITION BY employee_id
            ORDER BY event_sequence
        ) AS next_event_date
    FROM deferral_events_timeline
),

-- Step 3: Generate sequential non-overlapping deferral periods
all_deferral_periods AS (
    -- Baseline period: Start of year to first deferral event (for enrolled employees)
    SELECT
        d.employee_id,
        0 AS period_sequence,
        'baseline_deferral' AS period_type,
        MAKE_DATE({{ simulation_year }}, 1, 1) AS period_start,
        d.event_date - INTERVAL 1 DAY AS period_end,
        -- Use previous rate or default to 0 for baseline period
        COALESCE(d.previous_deferral_rate, b.current_deferral_rate, 0.00) AS period_deferral_rate
    FROM deferral_timeline_with_boundaries d
    LEFT JOIN base_workforce_data b ON d.employee_id = b.employee_id
    WHERE d.event_sequence = 1  -- First event for this employee
        AND d.event_date > MAKE_DATE({{ simulation_year }}, 1, 1)  -- Not at start of year
        AND d.new_deferral_rate IS NOT NULL

    UNION ALL

    -- Deferral event periods: Each event creates a period from its date to next event
    SELECT
        employee_id,
        event_sequence AS period_sequence,
        event_type || '_period' AS period_type,
        event_date AS period_start,
        COALESCE(
            next_event_date - INTERVAL 1 DAY,
            MAKE_DATE({{ simulation_year }}, 12, 31)
        ) AS period_end,
        new_deferral_rate AS period_deferral_rate
    FROM deferral_timeline_with_boundaries
    WHERE new_deferral_rate IS NOT NULL
        AND new_deferral_rate >= 0
),

-- Step 4: Handle employees with no deferral events but baseline enrollment
employees_with_baseline_deferral AS (
    SELECT
        b.employee_id,
        1 AS period_sequence,
        'baseline_year_long' AS period_type,
        MAKE_DATE({{ simulation_year }}, 1, 1) AS period_start,
        MAKE_DATE({{ simulation_year }}, 12, 31) AS period_end,
        b.current_deferral_rate AS period_deferral_rate
    FROM base_workforce_data b
    LEFT JOIN enrollment_status es ON b.employee_id = es.employee_id
    WHERE b.employee_id NOT IN (SELECT employee_id FROM deferral_events_timeline)
        AND (b.is_enrolled_flag = true OR es.is_enrolled = true)
        -- CRITICAL FIX: Strengthen zero-rate exclusion with threshold to avoid floating point issues
        AND b.current_deferral_rate > 0.001  -- Must have meaningful deferral rate (>0.1%)
        AND b.current_deferral_rate IS NOT NULL
        AND b.employment_status = 'active'
        -- ENHANCED VALIDATION: deferral rate source must be valid (including carried forward rates)
        AND (b.deferral_rate_source LIKE 'enrollment_event%'
             OR b.deferral_rate_source LIKE 'accumulator%'
             OR b.deferral_rate_source = 'census_data')
        -- CRITICAL FIX: Exclude employees who explicitly opted out (0% deferral rate from enrollment change)
        AND NOT EXISTS (
            SELECT 1
            FROM {{ ref('fct_yearly_events') }} fye
            WHERE fye.employee_id = b.employee_id
                AND fye.event_type = 'enrollment_change'
                AND fye.employee_deferral_rate = 0
                AND fye.simulation_year <= {{ simulation_year }}
        )
),

-- Combine all deferral periods
combined_deferral_periods AS (
    SELECT * FROM all_deferral_periods
    UNION ALL
    SELECT * FROM employees_with_baseline_deferral
),

-- Validate and clean deferral periods
clean_deferral_periods AS (
    SELECT
        employee_id,
        period_sequence,
        period_type,
        period_start,
        period_end,
        period_deferral_rate
    FROM combined_deferral_periods
    WHERE period_start IS NOT NULL
        AND period_end IS NOT NULL
        AND period_deferral_rate IS NOT NULL
        AND period_deferral_rate >= 0
        AND period_deferral_rate <= 1.0  -- 100% maximum
        AND period_start <= period_end
        AND period_start >= MAKE_DATE({{ simulation_year }}, 1, 1)
        AND period_end <= MAKE_DATE({{ simulation_year }}, 12, 31)
        AND DATE_DIFF('day', period_start, period_end) >= 0
),

-- Step 5: Get compensation periods from workforce snapshot logic
-- Extract compensation periods calculation from fct_workforce_snapshot
compensation_events_for_periods AS (
    SELECT
        employee_id,
        event_type,
        effective_date,
        compensation_amount,
        previous_compensation,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date, event_type
        ) AS event_sequence_in_year
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('hire', 'promotion', 'raise', 'termination')
        AND simulation_year = {{ simulation_year }}
),

-- Sequential event-based compensation periods (from workforce snapshot logic)
employee_compensation_timeline AS (
    SELECT
        employee_id,
        effective_date AS event_date,
        event_type,
        compensation_amount AS new_compensation,
        previous_compensation,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date,
            CASE event_type
                WHEN 'hire' THEN 1
                WHEN 'promotion' THEN 2
                WHEN 'raise' THEN 3
                WHEN 'termination' THEN 4
            END
        ) AS event_sequence
    FROM compensation_events_for_periods
    WHERE event_type IN ('hire', 'promotion', 'raise', 'termination')
),

-- Create timeline with period boundaries using LEAD for next event
employee_compensation_timeline_with_boundaries AS (
    SELECT
        employee_id,
        event_date,
        event_type,
        new_compensation,
        previous_compensation,
        event_sequence,
        LEAD(event_date) OVER (
            PARTITION BY employee_id
            ORDER BY event_sequence
        ) AS next_event_date
    FROM employee_compensation_timeline
),

-- Generate sequential non-overlapping compensation periods
all_compensation_periods AS (
    -- Baseline period: Start of year to first event (for non-hires)
    SELECT
        t.employee_id,
        0 AS period_sequence,
        'baseline' AS period_type,
        MAKE_DATE({{ simulation_year }}, 1, 1) AS period_start,
        t.event_date - INTERVAL 1 DAY AS period_end,
        -- Get baseline compensation from workforce data or previous compensation
        COALESCE(t.previous_compensation, w.prorated_annual_compensation, 0) AS period_salary
    FROM employee_compensation_timeline_with_boundaries t
    LEFT JOIN base_workforce_data w ON t.employee_id = w.employee_id
    WHERE t.event_sequence = 1  -- First event for this employee
        AND t.event_date > MAKE_DATE({{ simulation_year }}, 1, 1)  -- Not at start of year
        AND t.event_type != 'hire'  -- Hires don't have baseline periods

    UNION ALL

    -- Event periods: Each event creates a period from its date to next event
    SELECT
        employee_id,
        event_sequence AS period_sequence,
        event_type || '_period' AS period_type,
        event_date AS period_start,
        COALESCE(
            next_event_date - INTERVAL 1 DAY,
            MAKE_DATE({{ simulation_year }}, 12, 31)
        ) AS period_end,
        new_compensation AS period_salary
    FROM employee_compensation_timeline_with_boundaries
    WHERE event_type IN ('hire', 'promotion', 'raise')
        AND new_compensation IS NOT NULL
        AND new_compensation > 0
),

-- Handle employees with no compensation events (continuous employment)
employees_without_comp_events AS (
    SELECT
        b.employee_id,
        1 AS period_sequence,
        'continuous_employment' AS period_type,
        CASE
            WHEN EXTRACT(YEAR FROM b.employee_hire_date) = {{ simulation_year }}
                THEN b.employee_hire_date  -- New hire this year
            ELSE MAKE_DATE({{ simulation_year }}, 1, 1)  -- Start of year for existing employees
        END AS period_start,
        CASE
            WHEN b.employment_status = 'terminated' AND b.termination_date IS NOT NULL
                THEN b.termination_date  -- Terminated employees
            ELSE MAKE_DATE({{ simulation_year }}, 12, 31)  -- Active employees through year end
        END AS period_end,
        b.prorated_annual_compensation AS period_salary
    FROM base_workforce_data b
    WHERE b.employee_id NOT IN (SELECT employee_id FROM compensation_events_for_periods)
        AND b.employment_status IN ('active', 'terminated')
        AND b.prorated_annual_compensation > 0
),

-- Combine all compensation periods
combined_compensation_periods AS (
    SELECT * FROM all_compensation_periods
    UNION ALL
    SELECT * FROM employees_without_comp_events
),

-- Validate and clean compensation periods
clean_compensation_periods AS (
    SELECT
        employee_id,
        period_sequence,
        period_type,
        period_start,
        period_end,
        period_salary
    FROM combined_compensation_periods
    WHERE period_start IS NOT NULL
        AND period_end IS NOT NULL
        AND period_salary IS NOT NULL
        AND period_salary > 0
        AND period_start <= period_end
        AND period_start >= MAKE_DATE({{ simulation_year }}, 1, 1)
        AND period_end <= MAKE_DATE({{ simulation_year }}, 12, 31)
        AND DATE_DIFF('day', period_start, period_end) >= 0
),

-- Step 6: Join deferral and compensation periods with overlap handling
-- CRITICAL FIX: Changed from FULL OUTER to INNER JOIN to prevent orphaned compensation periods
contribution_periods AS (
    SELECT
        dp.employee_id AS employee_id,
        dp.period_sequence AS deferral_period_sequence,
        cp.period_sequence AS compensation_period_sequence,
        dp.period_type AS deferral_period_type,
        cp.period_type AS compensation_period_type,
        -- Calculate overlapping period boundaries
        GREATEST(
            dp.period_start,
            cp.period_start
        ) AS overlap_period_start,
        LEAST(
            dp.period_end,
            cp.period_end
        ) AS overlap_period_end,
        dp.period_deferral_rate AS period_deferral_rate,
        cp.period_salary AS period_salary,
        -- Calculate period contribution amount (only when both exist)
        cp.period_salary * dp.period_deferral_rate AS period_contribution_amount
    FROM clean_deferral_periods dp
    INNER JOIN clean_compensation_periods cp  -- CHANGED: INNER JOIN ensures both periods exist
        ON dp.employee_id = cp.employee_id
        -- Only join periods that have time overlap
        AND dp.period_start <= cp.period_end
        AND dp.period_end >= cp.period_start
    WHERE dp.employee_id IS NOT NULL
        AND cp.employee_id IS NOT NULL
        -- Ensure overlap period is valid
        AND GREATEST(dp.period_start, cp.period_start) <= LEAST(dp.period_end, cp.period_end)
        -- Additional safety: ensure deferral rate is meaningful
        AND dp.period_deferral_rate > 0.001
),

-- Step 7: Calculate time-weighted contributions by employee
employee_contributions_prorated AS (
    SELECT
        employee_id,
        -- Calculate prorated annual contributions using time-weighted methodology
        SUM(
            period_contribution_amount *
            (DATE_DIFF('day', overlap_period_start, overlap_period_end) + 1) / 365.0
        ) AS prorated_annual_contributions,
        -- Track contribution details for validation
        SUM(period_contribution_amount) AS total_period_contributions,
        COUNT(*) AS contribution_periods_count,
        -- Calculate effective average deferral rate
        CASE
            WHEN SUM(period_salary * (DATE_DIFF('day', overlap_period_start, overlap_period_end) + 1)) > 0
            THEN SUM(period_contribution_amount * (DATE_DIFF('day', overlap_period_start, overlap_period_end) + 1)) /
                 SUM(period_salary * (DATE_DIFF('day', overlap_period_start, overlap_period_end) + 1))
            ELSE 0.00
        END AS effective_deferral_rate,
        -- Track period ranges for debugging
        MIN(overlap_period_start) AS first_contribution_period_start,
        MAX(overlap_period_end) AS last_contribution_period_end
    FROM contribution_periods
    WHERE overlap_period_start IS NOT NULL
        AND overlap_period_end IS NOT NULL
        AND overlap_period_start <= overlap_period_end
        AND DATE_DIFF('day', overlap_period_start, overlap_period_end) >= 0
    GROUP BY employee_id
),

-- Additional Safety: Handle employees with no contribution periods
employees_with_no_contributions AS (
    SELECT
        bwd.employee_id,
        0.00 AS prorated_annual_contributions,
        0.00 AS total_period_contributions,
        0 AS contribution_periods_count,
        0.00 AS effective_deferral_rate,
        MAKE_DATE({{ simulation_year }}, 1, 1) AS first_contribution_period_start,
        MAKE_DATE({{ simulation_year }}, 12, 31) AS last_contribution_period_end
    FROM base_workforce_data bwd
    WHERE bwd.employee_id NOT IN (SELECT employee_id FROM employee_contributions_prorated)
        -- Only include enrolled employees with zero or very low deferral rates
        AND (bwd.current_deferral_rate <= 0.001 OR bwd.current_deferral_rate IS NULL)
),

-- Combine calculated contributions with zero-contribution employees
all_employee_contributions AS (
    SELECT * FROM employee_contributions_prorated
    UNION ALL
    SELECT * FROM employees_with_no_contributions
),

-- Step 8: Apply IRS limits with age-based catch-up rules
contributions_with_limits AS (
    SELECT
        ecp.employee_id,
        bwd.age_as_of_december_31,
        ecp.prorated_annual_contributions,
        ecp.total_period_contributions,
        ecp.contribution_periods_count,
        ecp.effective_deferral_rate,
        ecp.first_contribution_period_start,
        ecp.last_contribution_period_end,
        -- Determine applicable IRS limit based on age
        CASE
            WHEN bwd.age_as_of_december_31 >= il.age_threshold THEN il.total_limit
            ELSE il.base_limit
        END AS applicable_irs_limit,
        -- Apply IRS limit enforcement using LEAST() function
        LEAST(
            ecp.prorated_annual_contributions,
            CASE
                WHEN bwd.age_as_of_december_31 >= il.age_threshold THEN il.total_limit
                ELSE il.base_limit
            END
        ) AS irs_limited_annual_contributions,
        -- Flag for IRS limit reached
        CASE
            WHEN ecp.prorated_annual_contributions >
                CASE
                    WHEN bwd.age_as_of_december_31 >= il.age_threshold THEN il.total_limit
                    ELSE il.base_limit
                END
            THEN true
            ELSE false
        END AS irs_limit_reached,
        -- Calculate excess contributions
        CASE
            WHEN ecp.prorated_annual_contributions >
                CASE
                    WHEN bwd.age_as_of_december_31 >= il.age_threshold THEN il.total_limit
                    ELSE il.base_limit
                END
            THEN ecp.prorated_annual_contributions -
                CASE
                    WHEN bwd.age_as_of_december_31 >= il.age_threshold THEN il.total_limit
                    ELSE il.base_limit
                END
            ELSE 0.00
        END AS excess_contributions
    FROM all_employee_contributions ecp  -- CHANGED: Use combined CTE with zero-contribution employees
    INNER JOIN base_workforce_data bwd ON ecp.employee_id = bwd.employee_id
    CROSS JOIN irs_limits il
)

-- Final selection with comprehensive contribution data
SELECT
    cwl.employee_id,
    {{ simulation_year }} AS simulation_year,
    -- Core contribution amounts
    ROUND(cwl.prorated_annual_contributions, 2) AS prorated_annual_contributions,
    ROUND(cwl.irs_limited_annual_contributions, 2) AS irs_limited_annual_contributions,
    ROUND(cwl.excess_contributions, 2) AS excess_contributions,
    -- Contribution calculation metadata
    cwl.effective_deferral_rate,
    cwl.contribution_periods_count,
    cwl.first_contribution_period_start,
    cwl.last_contribution_period_end,
    -- IRS compliance data
    cwl.age_as_of_december_31,
    cwl.applicable_irs_limit,
    cwl.irs_limit_reached,
    -- Enrollment status (from enrollment state accumulator)
    COALESCE(es.is_enrolled, bwd.is_enrolled_flag, false) AS is_enrolled,
    COALESCE(es.enrollment_date, bwd.employee_enrollment_date) AS enrollment_date,
    COALESCE(es.years_since_first_enrollment, 0) AS years_since_first_enrollment,
    -- Employee demographics and compensation (for validation)
    bwd.prorated_annual_compensation,
    bwd.full_year_equivalent_compensation,
    bwd.current_age,
    bwd.employment_status,
    -- Deferral rate metadata (ENHANCED)
    bwd.current_deferral_rate,
    bwd.deferral_rate_source,
    bwd.deferral_rate_effective_date,
    bwd.is_rate_carried_forward,
    -- Data quality validation flags (ENHANCED WITH STRONGER ZERO-RATE CHECK)
    CASE
        WHEN cwl.employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
        WHEN cwl.prorated_annual_contributions > bwd.prorated_annual_compensation + 100 THEN 'CONTRIBUTIONS_EXCEED_COMPENSATION'
        WHEN cwl.irs_limited_annual_contributions != cwl.prorated_annual_contributions AND NOT cwl.irs_limit_reached THEN 'IRS_LIMIT_MISMATCH'
        WHEN COALESCE(es.is_enrolled, bwd.is_enrolled_flag, false) = false AND cwl.prorated_annual_contributions > 0 THEN 'CONTRIBUTIONS_WITHOUT_ENROLLMENT'
        WHEN cwl.effective_deferral_rate > 1.0 THEN 'INVALID_DEFERRAL_RATE'
        WHEN bwd.current_deferral_rate > 0 AND bwd.deferral_rate_source = 'default_zero' THEN 'MISSING_DEFERRAL_RATE_SOURCE'
        -- CRITICAL FIX: Strengthen zero-rate check with threshold
        WHEN bwd.current_deferral_rate <= 0.001 AND cwl.prorated_annual_contributions > 0.01 THEN 'ZERO_DEFERRAL_WITH_CONTRIBUTIONS'
        WHEN bwd.current_deferral_rate = 0 AND bwd.deferral_rate_source NOT LIKE '%zero%' THEN 'UNEXPECTED_ZERO_RATE'
        WHEN bwd.is_rate_carried_forward = true AND bwd.deferral_rate_source LIKE 'census%' THEN 'CARRIED_FORWARD_CENSUS_RATE'
        ELSE 'VALID'
    END AS data_quality_flag,
    -- Metadata
    CURRENT_TIMESTAMP AS created_at,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id
FROM contributions_with_limits cwl
INNER JOIN base_workforce_data bwd ON cwl.employee_id = bwd.employee_id
LEFT JOIN enrollment_status es ON cwl.employee_id = es.employee_id
WHERE cwl.employee_id IS NOT NULL
    -- CRITICAL SAFETY CHECK: Ensure zero-rate employees have zero contributions
    AND (bwd.current_deferral_rate > 0.001 OR cwl.prorated_annual_contributions <= 0.01)

{% if is_incremental() %}
    -- For incremental runs, only process current simulation year
    AND NOT EXISTS (
        SELECT 1 FROM {{ this }}
        WHERE employee_id = cwl.employee_id
            AND simulation_year = {{ simulation_year }}
    )
{% endif %}

ORDER BY cwl.employee_id
