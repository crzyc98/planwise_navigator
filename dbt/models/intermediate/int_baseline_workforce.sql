{{ config(materialized='table') }}

-- Baseline workforce for simulation start, driven by simulation parameters.
-- This model provides the initial state of the workforce for multi-year simulations.

{% set simulation_year = var('simulation_year', 2024) %} -- Default to 2024 if not provided
{% set simulation_effective_date_str = var('simulation_effective_date', '2024-12-31') %} -- Default for age/tenure calculation

SELECT
    stg.employee_id,
    stg.employee_ssn,
    stg.employee_birth_date,
    stg.employee_hire_date,
    stg.employee_gross_compensation AS current_compensation,
    -- Calculate age and tenure based on the simulation_effective_date
    EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date) AS current_age,
    EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date) AS current_tenure,
    -- **FIX**: Dynamically assign level_id with fallback for unmatched compensation ranges
    COALESCE(level_match.level_id, 1) AS level_id,
    -- Calculate age and tenure bands based on current_age and current_tenure
    CASE
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date)) < 25 THEN '< 25'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date)) < 35 THEN '25-34'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date)) < 45 THEN '35-44'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date)) < 55 THEN '45-54'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date)) < 65 THEN '55-64'
        ELSE '65+'
    END AS age_band,
    CASE
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date)) < 2 THEN '< 2'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date)) < 5 THEN '2-4'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date)) < 10 THEN '5-9'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date)) < 20 THEN '10-19'
        ELSE '20+'
    END AS tenure_band,
    'active' AS employment_status,
    NULL AS termination_date,
    NULL AS termination_reason,
    {{ simulation_year }} AS simulation_year, -- Dynamic simulation year
    CURRENT_TIMESTAMP AS snapshot_created_at
FROM {{ ref('stg_census_data') }} stg
-- **FIX**: Use a subquery to find the best matching level_id for each employee
LEFT JOIN (
    SELECT
        stg.employee_id,
        -- Select the level with the smallest min_compensation that still matches
        -- This ensures we get the most appropriate level for overlapping ranges
        MIN(levels.level_id) as level_id
    FROM {{ ref('stg_census_data') }} stg
    LEFT JOIN {{ ref('stg_config_job_levels') }} levels
        ON stg.employee_gross_compensation >= levels.min_compensation
       AND (stg.employee_gross_compensation < levels.max_compensation OR levels.max_compensation IS NULL)
    GROUP BY stg.employee_id
) level_match ON stg.employee_id = level_match.employee_id
WHERE
    stg.employee_termination_date IS NULL
ORDER BY
    stg.employee_id
