{{ config(
  materialized='ephemeral',
  tags=['EVENT_GENERATION', 'E068A_EPHEMERAL']
) }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', var('simulation_year')) | int %}

-- Generate termination events using hazard-based probability selection
-- Refactored to use int_workforce_needs for termination targets

WITH workforce_needs AS (
    -- Get termination targets from centralized workforce planning
    SELECT
        workforce_needs_id,
        scenario_id,
        simulation_year,
        expected_experienced_terminations,
        experienced_termination_rate,
        starting_experienced_count
    FROM {{ ref('int_workforce_needs') }}
    WHERE simulation_year = {{ simulation_year }}
      AND scenario_id = '{{ var('scenario_id', 'default') }}'
),

active_workforce AS (
    -- Use consistent data source with other event models
    -- IMPORTANT: Exclude current-year new hires so experienced terminations
    -- are selected only from prior-year active employees. This keeps
    -- experienced terminations aligned with workforce needs targets and avoids
    -- overlap with new-hire terminations.
    SELECT
        employee_id,
        employee_ssn,
        employee_hire_date,
        employee_compensation AS employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        'experienced' AS employee_type
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employment_status = 'active'
      AND employee_hire_date < CAST('{{ simulation_year }}-01-01' AS DATE)
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
    FROM active_workforce
),


-- SIMPLIFIED APPROACH: Use basic probability-based selection
eligible_for_termination AS (
    SELECT
        w.*,
        wn.experienced_termination_rate AS termination_rate,
        -- Generate deterministic random number for probability comparison
        (ABS(HASH(w.employee_id)) % 1000) / 1000.0 AS random_value
    FROM workforce_with_bands w
    CROSS JOIN workforce_needs wn
),

-- SOPHISTICATED APPROACH: Hazard-based terminations + quota gap-filling to achieve target from workforce needs
final_experienced_terminations AS (
    -- Use centralized target from workforce needs
    WITH target_calculation AS (
        SELECT expected_experienced_terminations AS target_count
        FROM workforce_needs
    )
    SELECT
        w.employee_id,
        w.employee_ssn,
        'termination' AS event_type,
        {{ simulation_year }} AS simulation_year,
        (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(w.employee_id)) % 365)) DAY) AS effective_date,
        CASE
            WHEN e.random_value IS NOT NULL AND e.random_value < e.termination_rate THEN 'hazard_termination'
            ELSE 'gap_filling_termination'
        END AS termination_reason,
        w.employee_gross_compensation AS final_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.age_band,
        w.tenure_band,
        w.employee_type,
        COALESCE(e.termination_rate, 0.0) AS termination_rate,
        COALESCE(e.random_value, (ABS(HASH(w.employee_id)) % 1000) / 1000.0) AS random_value,
        CASE
            WHEN e.random_value IS NOT NULL AND e.random_value < e.termination_rate THEN 'hazard_termination'
            ELSE 'gap_filling'
        END AS termination_type
    FROM workforce_with_bands w
    LEFT JOIN eligible_for_termination e ON w.employee_id = e.employee_id
    CROSS JOIN target_calculation
    -- FIXED: Apply only to experienced employees (previous year new hires handled separately)
    WHERE w.employee_type = 'experienced'
    QUALIFY ROW_NUMBER() OVER (
        ORDER BY
            -- Prioritize hazard-based terminations first
            CASE WHEN e.random_value IS NOT NULL AND e.random_value < e.termination_rate THEN 0 ELSE 1 END,
            COALESCE(e.random_value, (ABS(HASH(w.employee_id)) % 1000) / 1000.0)
    ) <= target_calculation.target_count
),

-- Return the hazard-based terminations with workforce planning reference
final_result AS (
  SELECT
    fet.employee_id,
    fet.employee_ssn,
    fet.event_type,
    fet.simulation_year,
    fet.effective_date,
    'Termination - ' || fet.termination_reason || ' (final compensation: $' || CAST(ROUND(fet.final_compensation, 0) AS VARCHAR) || ')' AS event_details,
    fet.final_compensation AS compensation_amount,
    fet.final_compensation AS previous_compensation,
    NULL::DECIMAL(5,4) AS employee_deferral_rate,
    NULL::DECIMAL(5,4) AS prev_employee_deferral_rate,
    fet.current_age AS employee_age,
    fet.current_tenure AS employee_tenure,
    fet.level_id,
    fet.age_band,
    fet.tenure_band,
    fet.termination_rate AS event_probability,
    'termination' AS event_category
  FROM final_experienced_terminations fet
  CROSS JOIN workforce_needs wn
)

SELECT * FROM final_result
