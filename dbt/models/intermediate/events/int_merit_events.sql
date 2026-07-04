{{ config(
  materialized='table',
  tags=['EVENT_GENERATION', 'E068A_EPHEMERAL']
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

-- Workforce with current compensation (no cross-references to other event models in fused approach)
workforce_with_current_compensation AS (
    SELECT
        aw.employee_id,
        aw.employee_ssn,
        aw.employee_hire_date,
        aw.employee_gross_compensation,
        aw.current_age,
        aw.current_tenure,
        aw.level_id,
        FALSE AS was_promoted_this_year  -- Simplified for fused approach
    FROM active_workforce aw
),

workforce_with_bands AS (
    SELECT
        *,
        -- Age bands for hazard lookup
        {{ assign_age_band('current_age') }} AS age_band,
        -- Tenure bands for hazard lookup
        {{ assign_tenure_band('current_tenure') }} AS tenure_band
    FROM workforce_with_current_compensation
),

-- Termination dates for the current year, to prevent post-termination raises.
-- Both termination models build earlier in the EVENT_GENERATION stage, so this
-- introduces no circular dependency. (Issue #383: this CTE was previously a
-- WHERE FALSE stub, so employees terminated in e.g. March still received a
-- July raise that then inflated their final snapshot compensation.)
termination_dates AS (
    SELECT
        employee_id,
        MIN(effective_date) AS termination_date
    FROM (
        SELECT employee_id, effective_date
        FROM {{ ref('int_termination_events') }}
        WHERE simulation_year = {{ simulation_year }}
        UNION ALL
        SELECT employee_id, effective_date
        FROM {{ ref('int_new_hire_termination_events') }}
        WHERE simulation_year = {{ simulation_year }}
    ) AS all_terminations
    GROUP BY employee_id
),

-- Apply merit to all eligible workforce, excluding terminated employees
merit_candidates AS (
    SELECT
        w.*,
        h.merit_raise,
        -- Compute the raise date once so termination filtering compares each
        -- employee's own raise date (methodology-dependent), not a fixed day.
        {{ get_realistic_raise_date('w.employee_id', simulation_year) }} AS raise_effective_date,
        t.termination_date
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
),

eligible_for_merit AS (
    SELECT *
    FROM merit_candidates
    -- Exclude employees who terminate before their raise takes effect
    WHERE termination_date IS NULL OR termination_date >= raise_effective_date
),

-- Apply COLA adjustments using dynamic parameter system
cola_adjustments AS (
    SELECT
        {{ simulation_year }} AS year,
        {{ get_parameter_value('1', 'RAISE', 'cola_rate', simulation_year) }} AS cola_rate
)

SELECT
    e.employee_id,
    e.employee_ssn,
    'raise' AS event_type,
    {{ simulation_year }} AS simulation_year,
    -- Raise timing computed once in merit_candidates (legacy/realistic modes)
    e.raise_effective_date AS effective_date,
    -- Event details for audit trail
    'Merit raise: ' || ROUND(e.merit_raise * 100, 1) || '%, COLA: ' || ROUND(c.cola_rate * 100, 1) || '%' AS event_details,
    -- Schema alignment for fct_yearly_events consumption
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
    ) AS compensation_amount,
    e.employee_gross_compensation AS previous_compensation,
    NULL::DECIMAL(5,4) AS employee_deferral_rate,
    NULL::DECIMAL(5,4) AS prev_employee_deferral_rate,
    e.current_age AS employee_age,
    e.current_tenure AS employee_tenure,
    e.level_id,
    e.age_band,
    e.tenure_band,
    e.merit_raise AS event_probability,
    'raise' AS event_category
FROM eligible_for_merit e
CROSS JOIN cola_adjustments c
