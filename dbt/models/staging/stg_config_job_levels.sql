{{ config(materialized='table') }}

-- Job levels configuration from seed data
-- Maps compensation ranges to organizational levels for workforce simulation
-- Now includes promotion probabilities and compensation factors

SELECT
    level_id,
    name AS level_name,
    min_compensation,
    max_compensation,
    description,
    job_families,
    avg_annual_merit_increase,
    promotion_probability,
    target_bonus_percent,
    comp_age_factor,
    comp_base_salary,
    comp_stochastic_std_dev,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_job_levels') }}
ORDER BY level_id
