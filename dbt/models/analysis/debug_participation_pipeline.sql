{{ config(
    materialized='table',
    tags=['DEBUG', 'analysis']
) }}

/*
  E096: Participation Pipeline Debug Dashboard

  Traces participation through every stage of the pipeline to identify
  where participants are being filtered out or lost.

  Usage:
    dbt run --select debug_participation_pipeline --vars '{simulation_year: 2025}'

  Then query:
    SELECT * FROM debug_participation_pipeline ORDER BY stage_order;
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

-- Stage 1: Census Input (stg_census_data)
WITH stage_1_census AS (
    SELECT
        1 AS stage_order,
        'Stage 1: Census Input' AS stage_name,
        'stg_census_data' AS source_model,
        COUNT(*) AS total_employees,
        COUNT(CASE WHEN employee_deferral_rate > 0 THEN 1 END) AS with_deferral_rate,
        COUNT(CASE WHEN employee_enrollment_date IS NOT NULL THEN 1 END) AS with_enrollment_date,
        COUNT(CASE WHEN employee_deferral_rate > 0 AND employee_enrollment_date IS NOT NULL THEN 1 END) AS fully_participating,
        ROUND(AVG(CASE WHEN employee_deferral_rate > 0 THEN employee_deferral_rate END) * 100, 2) AS avg_deferral_rate_pct,
        'Census employees with deferral_rate > 0 should carry participation forward' AS notes
    FROM {{ ref('stg_census_data') }}
    WHERE employee_termination_date IS NULL
),

-- Stage 2: Baseline Workforce (int_baseline_workforce)
stage_2_baseline AS (
    SELECT
        2 AS stage_order,
        'Stage 2: Baseline Workforce' AS stage_name,
        'int_baseline_workforce' AS source_model,
        COUNT(*) AS total_employees,
        COUNT(CASE WHEN employee_deferral_rate > 0 THEN 1 END) AS with_deferral_rate,
        COUNT(CASE WHEN employee_enrollment_date IS NOT NULL THEN 1 END) AS with_enrollment_date,
        COUNT(CASE WHEN is_enrolled_at_census = true THEN 1 END) AS fully_participating,
        ROUND(AVG(CASE WHEN employee_deferral_rate > 0 THEN employee_deferral_rate END) * 100, 2) AS avg_deferral_rate_pct,
        'is_enrolled_at_census should be true when deferral_rate > 0' AS notes
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employment_status = 'active'
),

-- Stage 3: Compensation by Year (int_employee_compensation_by_year)
stage_3_compensation AS (
    SELECT
        3 AS stage_order,
        'Stage 3: Compensation by Year' AS stage_name,
        'int_employee_compensation_by_year' AS source_model,
        COUNT(*) AS total_employees,
        COUNT(CASE WHEN is_enrolled_flag = true THEN 1 END) AS with_deferral_rate,
        COUNT(CASE WHEN employee_enrollment_date IS NOT NULL THEN 1 END) AS with_enrollment_date,
        COUNT(CASE WHEN is_enrolled_flag = true AND employee_enrollment_date IS NOT NULL THEN 1 END) AS fully_participating,
        NULL AS avg_deferral_rate_pct,
        'is_enrolled_flag derived from employee_enrollment_date IS NOT NULL' AS notes
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employment_status = 'active'
),

-- Stage 4: Enrollment Events Generated (fct_yearly_events)
stage_4_enrollment_events AS (
    SELECT
        4 AS stage_order,
        'Stage 4: Enrollment Events' AS stage_name,
        'fct_yearly_events (enrollment)' AS source_model,
        COUNT(DISTINCT employee_id) AS total_employees,
        COUNT(DISTINCT CASE WHEN LOWER(event_type) = 'enrollment' THEN employee_id END) AS with_deferral_rate,
        COUNT(DISTINCT CASE WHEN LOWER(event_type) = 'benefit_enrollment' THEN employee_id END) AS with_enrollment_date,
        COUNT(DISTINCT CASE WHEN LOWER(event_type) IN ('enrollment', 'benefit_enrollment') THEN employee_id END) AS fully_participating,
        ROUND(AVG(CASE WHEN LOWER(event_type) IN ('enrollment', 'benefit_enrollment') THEN employee_deferral_rate END) * 100, 2) AS avg_deferral_rate_pct,
        'enrollment = new events, benefit_enrollment = legacy. Both should be matched!' AS notes
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND LOWER(event_type) IN ('enrollment', 'benefit_enrollment', 'enrollment_change')
),

-- Stage 5: Deferral Rate Accumulator V2 (int_deferral_rate_state_accumulator_v2)
stage_5_deferral_accumulator AS (
    SELECT
        5 AS stage_order,
        'Stage 5: Deferral Rate Accumulator V2' AS stage_name,
        'int_deferral_rate_state_accumulator_v2' AS source_model,
        COUNT(*) AS total_employees,
        COUNT(CASE WHEN current_deferral_rate > 0 THEN 1 END) AS with_deferral_rate,
        COUNT(CASE WHEN is_enrolled_flag = true THEN 1 END) AS with_enrollment_date,
        COUNT(CASE WHEN current_deferral_rate > 0 AND is_enrolled_flag = true THEN 1 END) AS fully_participating,
        ROUND(AVG(CASE WHEN current_deferral_rate > 0 THEN current_deferral_rate END) * 100, 2) AS avg_deferral_rate_pct,
        'This is the source of truth for contributions. If 0 here, no participation!' AS notes
    FROM {{ ref('int_deferral_rate_state_accumulator_v2') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- Stage 6: Employee Contributions (int_employee_contributions)
stage_6_contributions AS (
    SELECT
        6 AS stage_order,
        'Stage 6: Employee Contributions' AS stage_name,
        'int_employee_contributions' AS source_model,
        COUNT(*) AS total_employees,
        COUNT(CASE WHEN final_deferral_rate > 0 THEN 1 END) AS with_deferral_rate,
        COUNT(CASE WHEN is_enrolled_flag = true THEN 1 END) AS with_enrollment_date,
        COUNT(CASE WHEN annual_contribution_amount > 0 THEN 1 END) AS fully_participating,
        ROUND(AVG(CASE WHEN final_deferral_rate > 0 THEN final_deferral_rate END) * 100, 2) AS avg_deferral_rate_pct,
        'Contributions calculated from accumulator. Check if deferral_rate flows through.' AS notes
    FROM {{ ref('int_employee_contributions') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- Stage 7: Workforce Snapshot (fct_workforce_snapshot)
stage_7_snapshot AS (
    SELECT
        7 AS stage_order,
        'Stage 7: Workforce Snapshot (Final)' AS stage_name,
        'fct_workforce_snapshot' AS source_model,
        COUNT(*) AS total_employees,
        COUNT(CASE WHEN current_deferral_rate > 0 THEN 1 END) AS with_deferral_rate,
        COUNT(CASE WHEN is_enrolled_flag = true THEN 1 END) AS with_enrollment_date,
        COUNT(CASE WHEN participation_status = 'participating' THEN 1 END) AS fully_participating,
        ROUND(AVG(CASE WHEN current_deferral_rate > 0 THEN current_deferral_rate END) * 100, 2) AS avg_deferral_rate_pct,
        'FINAL OUTPUT: participation_status should show participating employees' AS notes
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- Combine all stages
all_stages AS (
    SELECT * FROM stage_1_census
    UNION ALL SELECT * FROM stage_2_baseline
    UNION ALL SELECT * FROM stage_3_compensation
    UNION ALL SELECT * FROM stage_4_enrollment_events
    UNION ALL SELECT * FROM stage_5_deferral_accumulator
    UNION ALL SELECT * FROM stage_6_contributions
    UNION ALL SELECT * FROM stage_7_snapshot
)

SELECT
    stage_order,
    stage_name,
    source_model,
    total_employees,
    with_deferral_rate,
    with_enrollment_date,
    fully_participating,
    avg_deferral_rate_pct,
    -- Calculate drop-off from previous stage
    CASE
        WHEN stage_order = 1 THEN NULL
        ELSE fully_participating - LAG(fully_participating) OVER (ORDER BY stage_order)
    END AS participation_change,
    -- Flag significant drops
    CASE
        WHEN stage_order = 1 THEN 'BASELINE'
        WHEN fully_participating = 0 AND LAG(fully_participating) OVER (ORDER BY stage_order) > 0 THEN 'CRITICAL: ALL PARTICIPATION LOST!'
        WHEN fully_participating < LAG(fully_participating) OVER (ORDER BY stage_order) * 0.5 THEN 'WARNING: >50% DROP'
        WHEN fully_participating < LAG(fully_participating) OVER (ORDER BY stage_order) THEN 'INFO: Some drop'
        ELSE 'OK'
    END AS status_flag,
    notes,
    {{ simulation_year }} AS simulation_year,
    CURRENT_TIMESTAMP AS debug_run_at
FROM all_stages
ORDER BY stage_order
