{{ config(
    materialized='table',
    tags=['data_quality', 'epic_e057', 'new_hire_termination', 'critical']
) }}

-- Epic E057: Comprehensive Data Quality Validation for New Hire Termination and Proration Fixes
--
-- This model validates the comprehensive fixes implemented in Epic E057:
-- 1. Termination date generation fixes in int_new_hire_termination_events.sql
-- 2. Prorated compensation fixes in fct_workforce_snapshot.sql
-- 3. Regression testing for existing functionality
--
-- VALIDATION CATEGORIES:
-- A. Termination Date Validation (future dates, dates before hire)
-- B. Prorated Compensation Validation (with 1-day tolerance)
-- C. New Hire Specific Validations
-- D. Regression Testing (existing functionality unchanged)
-- E. Multi-year Consistency Checks
--
-- Returns only failing records for review - empty result indicates all validations passed

{% set simulation_year = var('simulation_year', 2025) %}

WITH validation_base AS (
    -- Get workforce snapshot data for validation
    SELECT
        employee_id,
        employee_ssn,
        simulation_year,
        employee_hire_date,
        termination_date,
        employment_status,
        detailed_status_code,
        current_compensation,
        prorated_annual_compensation,
        full_year_equivalent_compensation,
        current_age,
        current_tenure,
        level_id
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- VALIDATION A: Termination Date Validation
termination_date_failures AS (
    SELECT
        employee_id,
        simulation_year,
        'termination_date_validation' AS validation_category,
        CASE
            WHEN employment_status = 'terminated' AND EXTRACT(YEAR FROM termination_date) > simulation_year
                THEN 'future_termination'
            WHEN termination_date IS NOT NULL AND termination_date < employee_hire_date
                THEN 'termination_before_hire'
            WHEN detailed_status_code = 'new_hire_termination' AND termination_date IS NULL
                THEN 'new_hire_termination_missing_date'
            WHEN detailed_status_code = 'new_hire_termination' AND EXTRACT(YEAR FROM termination_date) != simulation_year
                THEN 'new_hire_termination_wrong_year'
            WHEN detailed_status_code = 'new_hire_termination' AND termination_date <= employee_hire_date
                THEN 'new_hire_termination_invalid_sequence'
        END AS validation_rule,
        CASE
            WHEN employment_status = 'terminated' AND EXTRACT(YEAR FROM termination_date) > simulation_year
                THEN 'ERROR: Termination date (' || termination_date || ') is in future year beyond simulation year (' || simulation_year || ')'
            WHEN termination_date IS NOT NULL AND termination_date < employee_hire_date
                THEN 'ERROR: Termination date (' || termination_date || ') is before hire date (' || employee_hire_date || ')'
            WHEN detailed_status_code = 'new_hire_termination' AND termination_date IS NULL
                THEN 'ERROR: New hire termination has no termination date'
            WHEN detailed_status_code = 'new_hire_termination' AND EXTRACT(YEAR FROM termination_date) != simulation_year
                THEN 'ERROR: New hire termination date (' || termination_date || ') not in simulation year (' || simulation_year || ')'
            WHEN detailed_status_code = 'new_hire_termination' AND termination_date <= employee_hire_date
                THEN 'ERROR: New hire termination date (' || termination_date || ') must be after hire date (' || employee_hire_date || ')'
        END AS validation_message,
        'ERROR' AS severity,
        CAST(termination_date AS VARCHAR) AS actual_value,
        CASE
            WHEN employment_status = 'terminated' AND EXTRACT(YEAR FROM termination_date) > simulation_year
                THEN CAST(simulation_year || '-12-31' AS VARCHAR)
            WHEN termination_date IS NOT NULL AND termination_date < employee_hire_date
                THEN CAST(employee_hire_date + INTERVAL 1 DAY AS VARCHAR)
            ELSE NULL
        END AS expected_value
    FROM validation_base
    WHERE (
        (employment_status = 'terminated' AND EXTRACT(YEAR FROM termination_date) > simulation_year) OR
        (termination_date IS NOT NULL AND termination_date < employee_hire_date) OR
        (detailed_status_code = 'new_hire_termination' AND termination_date IS NULL) OR
        (detailed_status_code = 'new_hire_termination' AND EXTRACT(YEAR FROM termination_date) != simulation_year) OR
        (detailed_status_code = 'new_hire_termination' AND termination_date <= employee_hire_date)
    )
),

-- VALIDATION B: Prorated Compensation Validation (with 1-day tolerance)
prorated_compensation_failures AS (
    SELECT
        wb.employee_id,
        wb.simulation_year,
        'prorated_compensation_validation' AS validation_category,
        CASE
            WHEN ABS(expected_days - actual_days) > 1 THEN 'prorated_compensation_mismatch'
            WHEN wb.prorated_annual_compensation > wb.current_compensation * 1.01 THEN 'prorated_exceeds_annual'
            WHEN wb.employment_status = 'terminated' AND wb.prorated_annual_compensation = wb.current_compensation THEN 'terminated_not_prorated'
        END AS validation_rule,
        CASE
            WHEN ABS(expected_days - actual_days) > 1
                THEN 'ERROR: Prorated compensation calculation incorrect - expected ' || expected_days || ' days but calculated ' || actual_days || ' days (tolerance: 1 day)'
            WHEN wb.prorated_annual_compensation > wb.current_compensation * 1.01
                THEN 'ERROR: Prorated compensation (' || wb.prorated_annual_compensation || ') exceeds annual compensation (' || wb.current_compensation || ') with tolerance'
            WHEN wb.employment_status = 'terminated' AND wb.prorated_annual_compensation = wb.current_compensation
                THEN 'WARNING: Terminated employee has full annual compensation, may need proration'
        END AS validation_message,
        CASE
            WHEN ABS(expected_days - actual_days) > 1 THEN 'ERROR'
            WHEN wb.prorated_annual_compensation > wb.current_compensation * 1.01 THEN 'ERROR'
            WHEN wb.employment_status = 'terminated' AND wb.prorated_annual_compensation = wb.current_compensation THEN 'WARNING'
        END AS severity,
        CAST(COALESCE(actual_days, 0) AS VARCHAR) AS actual_value,
        CAST(expected_days AS VARCHAR) AS expected_value
    FROM (
        SELECT
            wb.*,
            CASE
                WHEN wb.employment_status = 'terminated' AND wb.termination_date IS NOT NULL AND wb.employee_hire_date IS NOT NULL
                    THEN DATEDIFF('day',
                        GREATEST(wb.employee_hire_date, CAST(wb.simulation_year || '-01-01' AS DATE)),
                        wb.termination_date
                    ) + 1
                WHEN EXTRACT(YEAR FROM wb.employee_hire_date) = wb.simulation_year
                    THEN DATEDIFF('day',
                        wb.employee_hire_date,
                        LEAST(COALESCE(wb.termination_date, CAST(wb.simulation_year || '-12-31' AS DATE)), CAST(wb.simulation_year || '-12-31' AS DATE))
                    ) + 1
                ELSE 365 -- Full year for continuing employees
            END AS expected_days,
            CASE
                WHEN wb.current_compensation > 0 AND wb.prorated_annual_compensation > 0
                    THEN ROUND(wb.prorated_annual_compensation / NULLIF(wb.current_compensation, 0) * 365)
                ELSE 0
            END AS actual_days
        FROM validation_base wb
    ) wb
    WHERE wb.employee_id LIKE 'NH_' || wb.simulation_year || '_%' -- Focus on new hires
        AND (
            ABS(expected_days - actual_days) > 1 OR
            wb.prorated_annual_compensation > wb.current_compensation * 1.01 OR
            (wb.employment_status = 'terminated' AND wb.prorated_annual_compensation = wb.current_compensation)
        )
),

-- VALIDATION C: New Hire Specific Validations
new_hire_specific_failures AS (
    SELECT
        employee_id,
        simulation_year,
        'new_hire_specific_validation' AS validation_category,
        CASE
            WHEN detailed_status_code = 'new_hire_termination' AND employment_status != 'terminated'
                THEN 'new_hire_termination_status_mismatch'
            WHEN employment_status = 'terminated' AND EXTRACT(YEAR FROM employee_hire_date) = simulation_year AND detailed_status_code != 'new_hire_termination'
                THEN 'terminated_new_hire_wrong_status'
            WHEN employee_id LIKE 'NH_' || simulation_year || '_%' AND EXTRACT(YEAR FROM employee_hire_date) != simulation_year
                THEN 'new_hire_id_date_mismatch'
        END AS validation_rule,
        CASE
            WHEN detailed_status_code = 'new_hire_termination' AND employment_status != 'terminated'
                THEN 'ERROR: Employee with new_hire_termination status not marked as terminated'
            WHEN employment_status = 'terminated' AND EXTRACT(YEAR FROM employee_hire_date) = simulation_year AND detailed_status_code != 'new_hire_termination'
                THEN 'ERROR: Terminated employee hired in current year not classified as new_hire_termination'
            WHEN employee_id LIKE 'NH_' || simulation_year || '_%' AND EXTRACT(YEAR FROM employee_hire_date) != simulation_year
                THEN 'ERROR: New hire ID indicates current year but hire date in different year'
        END AS validation_message,
        'ERROR' AS severity,
        CAST(detailed_status_code AS VARCHAR) AS actual_value,
        CASE
            WHEN detailed_status_code = 'new_hire_termination' AND employment_status != 'terminated'
                THEN 'terminated'
            WHEN employment_status = 'terminated' AND EXTRACT(YEAR FROM employee_hire_date) = simulation_year AND detailed_status_code != 'new_hire_termination'
                THEN 'new_hire_termination'
            ELSE detailed_status_code
        END AS expected_value
    FROM validation_base
    WHERE (
        (detailed_status_code = 'new_hire_termination' AND employment_status != 'terminated') OR
        (employment_status = 'terminated' AND EXTRACT(YEAR FROM employee_hire_date) = simulation_year AND detailed_status_code != 'new_hire_termination') OR
        (employee_id LIKE 'NH_' || simulation_year || '_%' AND EXTRACT(YEAR FROM employee_hire_date) != simulation_year)
    )
),

-- VALIDATION D: Regression Testing - Existing Employee Validation
regression_testing_failures AS (
    SELECT
        employee_id,
        simulation_year,
        'regression_testing' AS validation_category,
        CASE
            WHEN NOT employee_id LIKE 'NH_%' AND employment_status = 'terminated' AND detailed_status_code NOT IN ('experienced_termination', 'new_hire_termination')
                THEN 'existing_employee_wrong_termination_status'
            WHEN NOT employee_id LIKE 'NH_%' AND employment_status = 'active' AND detailed_status_code NOT IN ('continuous_active', 'new_hire_active')
                THEN 'existing_employee_wrong_active_status'
            WHEN current_compensation <= 0 AND employment_status = 'active'
                THEN 'active_employee_zero_compensation'
        END AS validation_rule,
        CASE
            WHEN NOT employee_id LIKE 'NH_%' AND employment_status = 'terminated' AND detailed_status_code NOT IN ('experienced_termination', 'new_hire_termination')
                THEN 'ERROR: Existing employee termination not properly classified'
            WHEN NOT employee_id LIKE 'NH_%' AND employment_status = 'active' AND detailed_status_code NOT IN ('continuous_active', 'new_hire_active')
                THEN 'ERROR: Existing active employee not properly classified'
            WHEN current_compensation <= 0 AND employment_status = 'active'
                THEN 'ERROR: Active employee has zero or negative compensation'
        END AS validation_message,
        'ERROR' AS severity,
        CAST(detailed_status_code AS VARCHAR) AS actual_value,
        CASE
            WHEN NOT employee_id LIKE 'NH_%' AND employment_status = 'terminated'
                THEN 'experienced_termination'
            WHEN NOT employee_id LIKE 'NH_%' AND employment_status = 'active'
                THEN 'continuous_active'
            ELSE detailed_status_code
        END AS expected_value
    FROM validation_base
    WHERE (
        (NOT employee_id LIKE 'NH_%' AND employment_status = 'terminated' AND detailed_status_code NOT IN ('experienced_termination', 'new_hire_termination')) OR
        (NOT employee_id LIKE 'NH_%' AND employment_status = 'active' AND detailed_status_code NOT IN ('continuous_active', 'new_hire_active')) OR
        (current_compensation <= 0 AND employment_status = 'active')
    )
),

-- Combine all validation failures
all_validation_failures AS (
    SELECT * FROM termination_date_failures
    UNION ALL
    SELECT * FROM prorated_compensation_failures
    UNION ALL
    SELECT * FROM new_hire_specific_failures
    UNION ALL
    SELECT * FROM regression_testing_failures
)

-- Final output with summary statistics
SELECT
    avf.employee_id,
    avf.simulation_year,
    avf.validation_category,
    avf.validation_rule,
    avf.validation_message,
    avf.severity,
    avf.actual_value,
    avf.expected_value,
    CURRENT_TIMESTAMP AS validation_timestamp,
    'dq_e057_new_hire_termination_validation' AS validation_source,
    -- Add severity ranking for prioritization
    CASE
        WHEN avf.severity = 'ERROR' THEN 1
        WHEN avf.severity = 'WARNING' THEN 2
        ELSE 3
    END AS severity_rank,
    -- Add validation summary
    (
        SELECT COUNT(*)
        FROM validation_base
        WHERE employee_id LIKE 'NH_' || {{ simulation_year }} || '_%'
    ) AS total_new_hires_examined,
    (
        SELECT COUNT(*)
        FROM validation_base
        WHERE employee_id LIKE 'NH_' || {{ simulation_year }} || '_%'
            AND employment_status = 'terminated'
    ) AS total_new_hire_terminations_examined,
    -- Add Epic context
    'E057' AS epic_number,
    'New hire termination date and proration validation' AS epic_description
FROM all_validation_failures avf
ORDER BY
    CASE
        WHEN avf.severity = 'ERROR' THEN 1
        WHEN avf.severity = 'WARNING' THEN 2
        ELSE 3
    END ASC,
    avf.validation_category ASC,
    avf.employee_id ASC
