{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'unique': False}
    ],
    tags=["snapshot_processing", "critical", "hiring"]
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

workforce_after_merit AS (
    SELECT * FROM {{ ref('int_snapshot_merit') }}
),

-- Get all events for current simulation year
current_year_events AS (
    SELECT *
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
),

-- Extract merit and promotion events for salary data
merit_events AS (
    SELECT
        CAST(employee_id AS VARCHAR) AS employee_id,
        compensation_amount AS merit_new_salary
    FROM current_year_events
    WHERE event_type = 'raise'
        AND employee_id IS NOT NULL
),

promotion_events AS (
    SELECT
        CAST(employee_id AS VARCHAR) AS employee_id,
        compensation_amount AS promo_new_salary
    FROM current_year_events
    WHERE event_type = 'promotion'
        AND employee_id IS NOT NULL
),

-- Extract termination events for better performance and readability
termination_events AS (
    SELECT
        CAST(employee_id AS VARCHAR) AS employee_id,
        effective_date,
        event_details,
        simulation_year
    FROM current_year_events
    WHERE UPPER(event_type) = 'TERMINATION'
        AND employee_id IS NOT NULL
        AND EXTRACT(YEAR FROM effective_date) = (SELECT current_year FROM simulation_parameters)
),

-- Extract the hiring logic from fct_workforce_snapshot.sql lines 156-189
new_hires AS (
    SELECT
        CAST(ye.employee_id AS VARCHAR) AS employee_id,
        ye.employee_ssn,
        -- Calculate birth date from age (approximate)
        CAST(CONCAT((SELECT current_year FROM simulation_parameters), '-01-01') AS DATE) - INTERVAL (ye.employee_age * 365) DAY AS employee_birth_date,
        ye.effective_date AS employee_hire_date,
        ye.compensation_amount AS employee_gross_compensation,
        ye.employee_age AS current_age,
        0 AS current_tenure, -- New hires start with 0 tenure
        ye.level_id,
        -- Check if this new hire has a termination event in the same year
        CAST(term.effective_date AS TIMESTAMP) AS termination_date,
        CASE WHEN term.employee_id IS NOT NULL THEN 'terminated' ELSE 'active' END AS employment_status,
        term.event_details AS termination_reason,
        (SELECT current_year FROM simulation_parameters) AS simulation_year,
        CURRENT_TIMESTAMP AS snapshot_created_at,
        'new_hire' AS record_source
    FROM current_year_events ye
    LEFT JOIN termination_events term
        ON CAST(ye.employee_id AS VARCHAR) = term.employee_id
        AND ye.employee_id IS NOT NULL
    WHERE ye.event_type = 'hire'
),

-- Combine existing workforce with new hires and add salary event data
combined_workforce AS (
    -- Existing workforce from merit processing with event salary data
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,
        w.employee_gross_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.termination_date,
        w.employment_status,
        w.termination_reason,
        w.simulation_year,
        w.snapshot_created_at,
        'existing' AS record_source,
        -- Add merit and promotion salary data for downstream consumers
        m.merit_new_salary,
        p.promo_new_salary
    FROM workforce_after_merit w
    LEFT JOIN merit_events m ON CAST(w.employee_id AS VARCHAR) = m.employee_id
    LEFT JOIN promotion_events p ON CAST(w.employee_id AS VARCHAR) = p.employee_id

    UNION ALL

    -- New hires with salary event data (will be NULL for new hires)
    SELECT
        nh.employee_id,
        nh.employee_ssn,
        nh.employee_birth_date,
        nh.employee_hire_date,
        nh.employee_gross_compensation,
        nh.current_age,
        nh.current_tenure,
        nh.level_id,
        nh.termination_date,
        nh.employment_status,
        nh.termination_reason,
        nh.simulation_year,
        nh.snapshot_created_at,
        nh.record_source,
        -- New hires won't have merit/promotion events in the same year they're hired
        NULL AS merit_new_salary,
        NULL AS promo_new_salary
    FROM new_hires nh
),

-- Apply deduplication with prioritization (existing employees over new hires)
final_workforce AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        termination_date,
        employment_status,
        termination_reason,
        simulation_year,
        snapshot_created_at,
        merit_new_salary,
        promo_new_salary,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY
                CASE WHEN record_source = 'existing' THEN 1 ELSE 2 END,
                employee_gross_compensation DESC,
                termination_date ASC NULLS LAST
        ) AS row_num
    FROM combined_workforce
)

SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    employee_gross_compensation,
    current_age,
    current_tenure,
    level_id,
    termination_date,
    employment_status,
    termination_reason,
    simulation_year,
    snapshot_created_at,
    merit_new_salary,
    promo_new_salary
FROM final_workforce
WHERE row_num = 1
