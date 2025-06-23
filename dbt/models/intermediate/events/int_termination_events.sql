{{ config(materialized='table') }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', var('simulation_year')) | int %}
{% set exp_term_rate = var('total_termination_rate', 0.12) %}

-- Generate termination events implementing Epic 11.5 precise sequence:
-- 1. Process experienced employee terminations first
-- 2. Calculate additional terminations needed for total_termination_rate
-- 3. Later: new hire terminations will be handled separately after hiring

WITH simulation_config AS (
    SELECT
        {{ simulation_year }} AS current_year,
        {{ exp_term_rate }} AS experienced_termination_rate,
        {{ var('target_growth_rate', 0.03) }} AS target_growth_rate
),

incumbent_pool AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        employment_status,
        termination_date
    FROM {{ ref('int_previous_year_workforce') }}
    WHERE employment_status = 'active'
),

active_workforce AS (
    -- Use int_previous_year_workforce which handles the dependency logic properly
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        -- Flag new hires vs experienced employees (hired in previous year vs earlier)
        CASE
            WHEN EXTRACT(YEAR FROM employee_hire_date) = (SELECT current_year - 1 FROM simulation_config)
            THEN 'new_hire'
            ELSE 'experienced'
        END AS employee_type
    FROM incumbent_pool
    WHERE employment_status = 'active'
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

-- Get experienced population (hired before current simulation year)
experienced_population AS (
    SELECT w.*
    FROM workforce_with_bands w
    WHERE w.employee_type = 'experienced'
),

-- Calculate termination quota
quota AS (
    SELECT CEIL(COUNT(*) * {{ exp_term_rate }}) AS target_terminations
    FROM experienced_population
),

-- Generate hazard-based terminations
experienced_workforce_with_hazards AS (
    SELECT
        w.*,
        h.termination_rate,
        -- Simple deterministic "random" value based on employee_id hash
        (ABS(HASH(w.employee_id)) % 1000) / 1000.0 AS random_value
    FROM experienced_population w
    JOIN {{ ref('dim_hazard_table') }} h
        ON w.level_id = h.level_id
        AND w.age_band = h.age_band
        AND w.tenure_band = h.tenure_band
        AND h.year = {{ simulation_year }}
),

-- Hazard sample (probabilistic terminations)
hazard_sample AS (
    SELECT
        ewh.*,
        (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(ewh.employee_id)) % 365)) DAY) AS effective_date,
        ROW_NUMBER() OVER (ORDER BY ABS(HASH(ewh.employee_id))) AS rn
    FROM experienced_workforce_with_hazards ewh
    WHERE ewh.random_value < ewh.termination_rate
),

-- Cap hazard sample to quota if it exceeds
capped_hazard_sample AS (
    SELECT *
    FROM hazard_sample
    WHERE rn <= (SELECT target_terminations FROM quota)
),

-- Count actual hazard terminations vs quota
counts AS (
    SELECT
        (SELECT target_terminations FROM quota) AS quota_needed,
        COUNT(*) AS hazard_count
    FROM capped_hazard_sample
),

-- Calculate shortfall
shortfall AS (
    SELECT
        quota_needed,
        hazard_count,
        GREATEST(0, quota_needed - hazard_count) AS additional_needed
    FROM counts
),

-- Fill shortfall with random additional terminations
extra_terms AS (
    SELECT
        ep.employee_id,
        ep.employee_ssn,
        'termination' AS event_type,
        sc.current_year AS simulation_year,
        (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(ep.employee_id)) % 365)) DAY) AS effective_date,
        'quota_fill' AS termination_reason,
        ep.employee_gross_compensation AS final_compensation,
        ep.current_age,
        ep.current_tenure,
        ep.level_id,
        ep.age_band,
        ep.tenure_band,
        ep.employee_type,
        NULL AS termination_rate,
        (ABS(HASH(ep.employee_id)) % 1000) / 1000.0 AS random_value,
        'additional_termination' AS termination_type
    FROM experienced_population ep
    CROSS JOIN simulation_config sc
    LEFT JOIN capped_hazard_sample chs ON ep.employee_id = chs.employee_id
    WHERE chs.employee_id IS NULL  -- Not already in hazard sample
    QUALIFY ROW_NUMBER() OVER (ORDER BY ABS(HASH(ep.employee_id)) + 1000) <= (SELECT additional_needed FROM shortfall)
),

-- Combine hazard terminations with quota fill
experienced_terminations AS (
    SELECT
        chs.employee_id,
        chs.employee_ssn,
        'termination' AS event_type,
        sc.current_year AS simulation_year,
        chs.effective_date,
        'hazard_exit' AS termination_reason,
        chs.employee_gross_compensation AS final_compensation,
        chs.current_age,
        chs.current_tenure,
        chs.level_id,
        chs.age_band,
        chs.tenure_band,
        chs.employee_type,
        chs.termination_rate,
        chs.random_value,
        'experienced_termination' AS termination_type
    FROM capped_hazard_sample chs
    CROSS JOIN simulation_config sc

    UNION ALL

    SELECT * FROM extra_terms
)

-- Return only experienced terminations (capped at experienced_termination_rate)
SELECT * FROM experienced_terminations
