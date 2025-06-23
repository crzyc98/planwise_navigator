{{ config(materialized='table') }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', var('simulation_year')) | int %}

-- Generate termination events implementing Epic 11.5 precise sequence:
-- 1. Process experienced employee terminations first
-- 2. Calculate additional terminations needed for total_termination_rate
-- 3. Later: new hire terminations will be handled separately after hiring

WITH simulation_config AS (
    SELECT
        {{ simulation_year }} AS current_year,
        {{ var('total_termination_rate', 0.12) }} AS total_termination_rate,
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

-- Step 1: Calculate allowed terminations for all active employees based on total_termination_rate
termination_cap AS (
    SELECT
        ROUND(COUNT(*) * (SELECT total_termination_rate FROM simulation_config)) ::INT AS allowed_terminations
    FROM active_workforce
),

-- Step 2: Generate experienced employee terminations using hazard rates
experienced_workforce_with_hazards AS (
    SELECT
        w.*,
        h.termination_rate,
        -- Simple deterministic "random" value based on employee_id hash
        (ABS(HASH(w.employee_id)) % 1000) / 1000.0 AS random_value
    FROM workforce_with_bands w
    JOIN {{ ref('dim_hazard_table') }} h
        ON w.level_id = h.level_id
        AND w.age_band = h.age_band
        AND w.tenure_band = h.tenure_band
        AND h.year = {{ simulation_year }}
    -- Remove employee_type filter so cap applies to all employees
),

-- Capped sample of experienced hazards (apply termination cap)
capped_hazard_sample AS (
    SELECT
        ewh.*,
        (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(ewh.employee_id)) % 365)) DAY) AS effective_date,
        ROW_NUMBER() OVER (ORDER BY ABS(HASH(ewh.employee_id))) AS rn
    FROM experienced_workforce_with_hazards ewh
    WHERE ewh.random_value < ewh.termination_rate
),

capped_hazard_sample_limited AS (
    SELECT *
    FROM capped_hazard_sample
    WHERE rn <= (SELECT allowed_terminations FROM termination_cap)
),

/* ------------- experienced terminations (capped) ------------- */
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
    FROM capped_hazard_sample_limited chs
    CROSS JOIN simulation_config sc
),


-- Step 3: Calculate if additional terminations are needed to meet total rate
termination_gap_analysis AS (
    SELECT
        COUNT(*) AS total_workforce,
        COUNT(CASE WHEN employee_type = 'experienced' THEN 1 END) AS experienced_workforce,
        (SELECT COUNT(*) FROM experienced_terminations) AS experienced_terminations,
        -- Calculate target total terminations for the year
        ROUND(COUNT(*) * (SELECT total_termination_rate FROM simulation_config)) AS target_total_terminations,
        -- Calculate additional terminations needed
        GREATEST(0,
            ROUND(COUNT(*) * (SELECT total_termination_rate FROM simulation_config)) -
            (SELECT COUNT(*) FROM experienced_terminations)
        ) AS additional_terminations_needed
    FROM active_workforce
),

-- Step 4: Generate additional terminations if needed (from remaining experienced workforce)
remaining_experienced_workforce AS (
    SELECT w.*
    FROM workforce_with_bands w
    LEFT JOIN experienced_terminations et ON w.employee_id = et.employee_id
    WHERE w.employee_type = 'experienced'
      AND et.employee_id IS NULL -- Not already terminated
),

/* ------------- additional terminations (to meet target) ------------- */
ranked_remaining AS (
    SELECT
        rew.*,
        ROW_NUMBER() OVER (ORDER BY ABS(HASH(rew.employee_id))) AS rn
    FROM remaining_experienced_workforce rew
),

additional_terminations AS (
    SELECT
        rw.employee_id,
        rw.employee_ssn,
        'termination' AS event_type,
        sc.current_year AS simulation_year,
        (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(rw.employee_id)) % 365)) DAY) AS effective_date,
        'additional_to_meet_target_rate' AS termination_reason,
        rw.employee_gross_compensation AS final_compensation,
        rw.current_age,
        rw.current_tenure,
        rw.level_id,
        rw.age_band,
        rw.tenure_band,
        rw.employee_type,
        NULL AS termination_rate,
        (ABS(HASH(rw.employee_id)) % 1000) / 1000.0 AS random_value,
        'additional_termination' AS termination_type
    FROM ranked_remaining rw
    CROSS JOIN simulation_config sc
    WHERE rw.rn <= (SELECT additional_terminations_needed FROM termination_gap_analysis)
)

-- Combine all terminations for this year (experienced only - new hire terminations handled separately)
SELECT * FROM experienced_terminations
UNION ALL
SELECT * FROM additional_terminations
