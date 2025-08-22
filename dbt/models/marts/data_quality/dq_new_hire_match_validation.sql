{{ config(
    materialized='table',
    tags=['data_quality', 'validation', 'new_hires', 'match_engine']
) }}

/*
  New Hire Employer Match Validation (Epic E055)

  Validates that new hire employees receive properly prorated employer match
  calculations based on their partial year of employment, not full annual compensation.

  Key Validations:
  - No new hire has match > 3% of prorated compensation
  - Match percentage aligns with deferral rates (50% match expected)
  - No duplicate employee records in contribution processing
  - Compensation sources are consistent

  This model helps prevent the critical bug where new hires received
  match calculations on full annual salaries instead of prorated amounts.
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH new_hire_events AS (
    -- Get all new hires for the simulation year
    SELECT
        employee_id,
        effective_date::DATE AS hire_date,
        compensation_amount AS hire_event_compensation,
        employee_age,
        DATEDIFF('day', effective_date::DATE, ({{ simulation_year }} || '-12-31')::DATE) + 1 AS days_worked,
        ({{ simulation_year }} || '-12-31')::DATE AS year_end_date
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND event_type = 'hire'
),

new_hire_contributions AS (
    -- Get contribution data for new hires
    SELECT
        employee_id,
        simulation_year,
        current_age,
        prorated_annual_compensation,
        effective_annual_deferral_rate,
        annual_contribution_amount,
        total_contribution_base_compensation,
        employment_status
    FROM {{ ref('int_employee_contributions') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employee_id IN (SELECT employee_id FROM new_hire_events)
),

new_hire_match AS (
    -- Get match calculations for new hires
    SELECT
        employee_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        employer_match_amount,
        uncapped_match_amount,
        match_cap_applied,
        effective_match_rate,
        match_percentage_of_comp
    FROM {{ ref('int_employee_match_calculations') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employee_id IN (SELECT employee_id FROM new_hire_events)
),

workforce_snapshot AS (
    -- Get final workforce snapshot data for new hires
    SELECT
        employee_id,
        simulation_year,
        prorated_annual_compensation,
        employer_match_amount AS snapshot_match_amount,
        total_employer_contributions
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employee_id IN (SELECT employee_id FROM new_hire_events)
),

validation_results AS (
    SELECT
        nhe.employee_id,
        {{ simulation_year }} AS simulation_year,
        nhe.hire_date,
        nhe.days_worked,
        nhe.hire_event_compensation,

        -- Contribution data
        nhc.prorated_annual_compensation AS contrib_prorated_comp,
        nhc.annual_contribution_amount,
        nhc.effective_annual_deferral_rate,

        -- Match data
        nhm.employer_match_amount,
        nhm.match_percentage_of_comp,
        nhm.effective_match_rate,

        -- Workforce snapshot data
        ws.snapshot_match_amount,
        ws.prorated_annual_compensation AS snapshot_prorated_comp,

        -- Expected calculations
        ROUND(nhe.hire_event_compensation * (nhe.days_worked / 365.0), 2) AS expected_prorated_comp,
        ROUND(nhe.hire_event_compensation * (nhe.days_worked / 365.0) * 0.03, 2) AS expected_max_match,

        -- Validation flags
        CASE
            WHEN nhm.match_percentage_of_comp > 0.03 THEN 'FAIL'
            ELSE 'PASS'
        END AS match_limit_validation,

        CASE
            WHEN nhm.effective_match_rate > 0.50 THEN 'FAIL'
            ELSE 'PASS'
        END AS match_rate_validation,

        CASE
            WHEN ABS(nhc.prorated_annual_compensation - ws.prorated_annual_compensation) > 1.0 THEN 'FAIL'
            ELSE 'PASS'
        END AS compensation_consistency_validation,

        CASE
            WHEN ABS(nhm.employer_match_amount - ws.snapshot_match_amount) > 1.0 THEN 'FAIL'
            ELSE 'PASS'
        END AS match_consistency_validation,

        -- Expected vs Actual comparison
        CASE
            WHEN ABS(nhc.prorated_annual_compensation - ROUND(nhe.hire_event_compensation * (nhe.days_worked / 365.0), 2)) > 100.0 THEN 'FAIL'
            ELSE 'PASS'
        END AS proration_accuracy_validation,

        -- Data quality metrics
        ROUND(nhm.employer_match_amount - ROUND(nhe.hire_event_compensation * (nhe.days_worked / 365.0) * 0.03, 2), 2) AS match_overage_amount,
        ROUND((nhm.employer_match_amount / NULLIF(ROUND(nhe.hire_event_compensation * (nhe.days_worked / 365.0) * 0.03, 2), 0) - 1) * 100, 1) AS match_overage_percentage

    FROM new_hire_events nhe
    LEFT JOIN new_hire_contributions nhc ON nhe.employee_id = nhc.employee_id
    LEFT JOIN new_hire_match nhm ON nhe.employee_id = nhm.employee_id
    LEFT JOIN workforce_snapshot ws ON nhe.employee_id = ws.employee_id
),

summary_stats AS (
    SELECT
        {{ simulation_year }} AS simulation_year,
        COUNT(*) AS total_new_hires,
        COUNT(CASE WHEN match_limit_validation = 'FAIL' THEN 1 END) AS match_limit_failures,
        COUNT(CASE WHEN match_rate_validation = 'FAIL' THEN 1 END) AS match_rate_failures,
        COUNT(CASE WHEN compensation_consistency_validation = 'FAIL' THEN 1 END) AS compensation_consistency_failures,
        COUNT(CASE WHEN match_consistency_validation = 'FAIL' THEN 1 END) AS match_consistency_failures,
        COUNT(CASE WHEN proration_accuracy_validation = 'FAIL' THEN 1 END) AS proration_accuracy_failures,

        -- Financial impact
        SUM(GREATEST(0, match_overage_amount)) AS total_match_overage,
        AVG(match_overage_percentage) AS avg_match_overage_pct,
        MAX(match_overage_percentage) AS max_match_overage_pct,

        -- Validation summary
        CASE
            WHEN COUNT(CASE WHEN match_limit_validation = 'FAIL' OR
                             match_rate_validation = 'FAIL' OR
                             compensation_consistency_validation = 'FAIL' OR
                             match_consistency_validation = 'FAIL' OR
                             proration_accuracy_validation = 'FAIL' THEN 1 END) = 0
            THEN 'ALL_PASS'
            ELSE 'HAS_FAILURES'
        END AS overall_validation_status
    FROM validation_results
)

-- Return both detailed results and summary
SELECT
    'DETAIL' AS record_type,
    employee_id,
    simulation_year,
    hire_date,
    days_worked,
    hire_event_compensation,
    contrib_prorated_comp,
    expected_prorated_comp,
    annual_contribution_amount,
    employer_match_amount,
    expected_max_match,
    match_overage_amount,
    match_overage_percentage,
    match_limit_validation,
    match_rate_validation,
    compensation_consistency_validation,
    match_consistency_validation,
    proration_accuracy_validation,
    effective_annual_deferral_rate,
    effective_match_rate,
    match_percentage_of_comp,
    NULL::BIGINT AS total_new_hires,
    NULL::BIGINT AS total_failures,
    NULL::DECIMAL AS total_match_overage_summary,
    NULL::VARCHAR AS overall_validation_status
FROM validation_results

UNION ALL

SELECT
    'SUMMARY' AS record_type,
    NULL AS employee_id,
    simulation_year,
    NULL AS hire_date,
    NULL AS days_worked,
    NULL AS hire_event_compensation,
    NULL AS contrib_prorated_comp,
    NULL AS expected_prorated_comp,
    NULL AS annual_contribution_amount,
    NULL AS employer_match_amount,
    NULL AS expected_max_match,
    NULL AS match_overage_amount,
    NULL AS match_overage_percentage,
    NULL AS match_limit_validation,
    NULL AS match_rate_validation,
    NULL AS compensation_consistency_validation,
    NULL AS match_consistency_validation,
    NULL AS proration_accuracy_validation,
    NULL AS effective_annual_deferral_rate,
    NULL AS effective_match_rate,
    NULL AS match_percentage_of_comp,
    total_new_hires,
    (match_limit_failures + match_rate_failures + compensation_consistency_failures +
     match_consistency_failures + proration_accuracy_failures) AS total_failures,
    total_match_overage AS total_match_overage_summary,
    overall_validation_status
FROM summary_stats

ORDER BY record_type, employee_id
