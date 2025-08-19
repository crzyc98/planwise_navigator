{{ config(
    materialized='table'
) }}

{% set simulation_year = var('simulation_year') %}

-- Generate merit increase events for active workforce based on hazard rates
-- Applies merit raise percentages from dim_hazard_table to eligible employees

WITH active_workforce AS (
    -- MERIT EVENTS COMPOUNDING FIX: Use dedicated compensation table for consistent data
    -- This table pre-calculates the correct compensation for each year, eliminating timing issues
    SELECT
        employee_id,
        employee_ssn,
        employee_hire_date,
        employee_compensation AS employee_gross_compensation,
        current_age,
        current_tenure,
        level_id
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
    AND employment_status = 'active'
),

-- Check for promotion events that happened earlier in the year (February 1)
-- Merit events (July 15) should use post-promotion compensation AND level_id
promotion_events_this_year AS (
    SELECT
        employee_id,
        new_salary AS promotion_salary,
        to_level
    FROM {{ ref('int_promotion_events') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- Workforce with current compensation AND level_id (including promotions if they happened)
workforce_with_current_compensation AS (
    SELECT
        aw.employee_id,
        aw.employee_ssn,
        aw.employee_hire_date,
        -- Use promotion salary if employee was promoted, otherwise use baseline compensation
        COALESCE(p.promotion_salary, aw.employee_gross_compensation) AS employee_gross_compensation,
        aw.current_age,
        aw.current_tenure,
        -- Use post-promotion level_id if employee was promoted, otherwise use baseline level_id
        COALESCE(p.to_level, aw.level_id) AS level_id,
        CASE WHEN p.employee_id IS NOT NULL THEN TRUE ELSE FALSE END AS was_promoted_this_year
    FROM active_workforce aw
    LEFT JOIN promotion_events_this_year p ON aw.employee_id = p.employee_id
),

workforce_with_bands AS (
    SELECT
        *,
        -- Age bands for hazard lookup
        CASE
            WHEN current_age < 25 THEN '< 25'
            WHEN current_age < 35 THEN '25-34'
            WHEN current_age < 45 THEN '35-44'
            WHEN current_age < 55 THEN '45-54'
            WHEN current_age < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        -- Tenure bands for hazard lookup
        CASE
            WHEN current_tenure < 2 THEN '< 2'
            WHEN current_tenure < 5 THEN '2-4'
            WHEN current_tenure < 10 THEN '5-9'
            WHEN current_tenure < 20 THEN '10-19'
            ELSE '20+'
        END AS tenure_band
    FROM workforce_with_current_compensation
),

-- Get termination dates to prevent post-termination events
termination_dates AS (
    SELECT
        employee_id,
        effective_date as termination_date
    FROM {{ ref('int_termination_events') }}
    WHERE simulation_year <= {{ simulation_year }}
),

-- Apply merit to all eligible workforce, excluding terminated employees
eligible_for_merit AS (
    SELECT
        w.*,
        h.merit_raise
    FROM workforce_with_bands w
    JOIN {{ ref('int_hazard_merit') }} h
        ON w.level_id = h.level_id
        AND w.age_band = h.age_band
        AND w.tenure_band = h.tenure_band
        AND h.year = {{ simulation_year }}
    LEFT JOIN termination_dates t ON w.employee_id = t.employee_id
    WHERE
        -- Simple merit eligibility rules
        current_tenure >= 1 -- At least 1 year of service
        AND merit_raise > 0 -- Must have a merit increase defined
        -- Critical fix: Exclude employees who were terminated before merit date
        AND (t.termination_date IS NULL OR t.termination_date >= DATE '{{ simulation_year }}-07-15')
),

-- Apply COLA adjustments using dynamic parameter system
cola_adjustments AS (
    SELECT
        {{ simulation_year }} AS year,
        {{ get_parameter_value('1', 'raise', 'cola_rate', simulation_year) }} AS cola_rate
)

SELECT
    e.employee_id,
    e.employee_ssn,
    'RAISE' AS event_type,  -- Fixed: uppercase for test compatibility
    {{ simulation_year }} AS simulation_year,
    -- Use macro system for raise timing (supports both legacy and realistic modes)
    {{ get_realistic_raise_date('e.employee_id', simulation_year) }} AS effective_date,
    -- Event details for audit trail
    'merit_raise: ' || ROUND(e.merit_raise * 100, 1) || '%, cola: ' || ROUND(c.cola_rate * 100, 1) || '%' AS event_details,
    -- Schema alignment for fct_yearly_events consumption
    e.employee_gross_compensation AS previous_compensation,
    ROUND(
        LEAST(
            -- Cap at 50% total increase maximum
            e.employee_gross_compensation * 1.50,
            -- Cap at $250K absolute increase maximum for merit/COLA
            e.employee_gross_compensation + 250000,
            -- Validate input parameters are reasonable before applying
            CASE
                WHEN (e.merit_raise + c.cola_rate) > 0.50 THEN e.employee_gross_compensation * 1.50
                WHEN (e.merit_raise + c.cola_rate) < 0 THEN e.employee_gross_compensation
                ELSE e.employee_gross_compensation * (1 + e.merit_raise + c.cola_rate)
            END
        ), 2
    ) AS compensation_amount,  -- Fixed: renamed from new_salary for test compatibility
    e.merit_raise AS event_probability,  -- Reused for event sourcing pattern
    'RAISE' AS event_category,  -- Added for consistency
    e.current_age AS employee_age,  -- Aligned column name
    e.current_tenure AS employee_tenure,  -- Aligned column name
    e.level_id,
    e.age_band,
    e.tenure_band
FROM eligible_for_merit e
CROSS JOIN cola_adjustments c
