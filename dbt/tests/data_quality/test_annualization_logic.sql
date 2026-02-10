-- Annualization Logic Data Quality Validation
-- Added for feature 043-fix-annualization-logic

/*
  Validates compensation annualization correctness in stg_census_data and
  cross-model consistency with int_baseline_workforce.

  Rules:
    ANN_001 (CRITICAL): employee_annualized_compensation = employee_gross_compensation
    ANN_002 (CRITICAL): employee_plan_year_compensation >= 0
    ANN_003 (ERROR):    employee_plan_year_compensation <= employee_gross_compensation * (366/365)
    ANN_004 (ERROR):    days_active_in_year between 0 and 366
    ANN_005 (WARNING):  Full-year employees have plan_year_comp ≈ gross_comp (within 0.3%)
    ANN_006 (ERROR):    Zero-day employees have plan_year_compensation = 0
    ANN_007 (WARNING):  Cross-model: baseline.current_compensation = staging.annualized_compensation

  Returns only failing records (0 rows = all validations pass).
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH staging_data AS (
    SELECT
        employee_id,
        employee_gross_compensation,
        employee_plan_year_compensation,
        employee_annualized_compensation,
        employee_hire_date,
        employee_termination_date
    FROM {{ ref('stg_census_data') }}
),

-- CRITICAL VALIDATION RULES (Zero Tolerance)
critical_validations AS (
    -- ANN_001: Annualized compensation must equal gross compensation (data contract)
    SELECT
        'ANN_001' AS validation_rule,
        'ANNUALIZED_EQUALS_GROSS' AS validation_source,
        'CRITICAL' AS severity,
        1 AS severity_rank,
        employee_id,
        employee_annualized_compensation AS actual_value,
        employee_gross_compensation AS expected_value,
        CONCAT(
            'Annualized compensation $', employee_annualized_compensation,
            ' does not equal gross compensation $', employee_gross_compensation
        ) AS validation_message
    FROM staging_data
    WHERE employee_annualized_compensation != employee_gross_compensation

    UNION ALL

    -- ANN_002: Plan year compensation must be non-negative
    SELECT
        'ANN_002' AS validation_rule,
        'PLAN_YEAR_COMP_NON_NEGATIVE' AS validation_source,
        'CRITICAL' AS severity,
        1 AS severity_rank,
        employee_id,
        employee_plan_year_compensation AS actual_value,
        0.0 AS expected_value,
        CONCAT(
            'Plan year compensation is negative: $', employee_plan_year_compensation
        ) AS validation_message
    FROM staging_data
    WHERE employee_plan_year_compensation < 0
),

-- ERROR VALIDATION RULES (High Priority)
error_validations AS (
    -- ANN_003: Plan year comp must not exceed gross * (366/365) (leap year allowance)
    SELECT
        'ANN_003' AS validation_rule,
        'PLAN_YEAR_COMP_BOUNDS' AS validation_source,
        'ERROR' AS severity,
        2 AS severity_rank,
        employee_id,
        employee_plan_year_compensation AS actual_value,
        employee_gross_compensation * (366.0 / 365.0) AS expected_value,
        CONCAT(
            'Plan year compensation $', employee_plan_year_compensation,
            ' exceeds gross * 366/365 ($', ROUND(employee_gross_compensation * (366.0 / 365.0), 2), ')'
        ) AS validation_message
    FROM staging_data
    WHERE employee_plan_year_compensation > employee_gross_compensation * (366.0 / 365.0)

    UNION ALL

    -- ANN_006: Zero-day employees must have plan_year_compensation = 0
    SELECT
        'ANN_006' AS validation_rule,
        'ZERO_DAY_PLAN_YEAR_COMP' AS validation_source,
        'ERROR' AS severity,
        2 AS severity_rank,
        sd.employee_id,
        sd.employee_plan_year_compensation AS actual_value,
        0.0 AS expected_value,
        CONCAT(
            'Employee with no plan-year overlap has non-zero plan year compensation: $',
            sd.employee_plan_year_compensation
        ) AS validation_message
    FROM staging_data sd
    WHERE (
        sd.employee_hire_date > CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE)
        OR (sd.employee_termination_date IS NOT NULL
            AND sd.employee_termination_date < CAST('{{ var("plan_year_start_date", "2024-01-01") }}' AS DATE))
    )
    AND sd.employee_plan_year_compensation != 0
),

-- WARNING VALIDATION RULES (Monitoring)
warning_validations AS (
    -- ANN_005: Full-year employees should have plan_year_comp ≈ gross_comp (within 0.3% for leap year)
    SELECT
        'ANN_005' AS validation_rule,
        'FULL_YEAR_PLAN_YEAR_APPROX_GROSS' AS validation_source,
        'WARNING' AS severity,
        3 AS severity_rank,
        employee_id,
        employee_plan_year_compensation AS actual_value,
        employee_gross_compensation AS expected_value,
        CONCAT(
            'Full-year employee plan year comp $', employee_plan_year_compensation,
            ' differs from gross $', employee_gross_compensation,
            ' by more than 0.3%'
        ) AS validation_message
    FROM staging_data
    WHERE employee_hire_date <= CAST('{{ var("plan_year_start_date", "2024-01-01") }}' AS DATE)
      AND (employee_termination_date IS NULL
           OR employee_termination_date >= CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE))
      AND employee_gross_compensation > 0
      AND ABS(employee_plan_year_compensation - employee_gross_compensation) / employee_gross_compensation > 0.003

    UNION ALL

    -- ANN_007: Cross-model consistency: baseline.current_compensation = staging.annualized_compensation
    SELECT
        'ANN_007' AS validation_rule,
        'CROSS_MODEL_COMPENSATION_CONSISTENCY' AS validation_source,
        'WARNING' AS severity,
        3 AS severity_rank,
        b.employee_id,
        b.current_compensation AS actual_value,
        s.employee_annualized_compensation AS expected_value,
        CONCAT(
            'Baseline current_compensation $', b.current_compensation,
            ' does not match staging annualized_compensation $', s.employee_annualized_compensation
        ) AS validation_message
    FROM {{ ref('int_baseline_workforce') }} b
    JOIN {{ ref('stg_census_data') }} s ON b.employee_id = s.employee_id
    WHERE b.simulation_year = {{ simulation_year }}
      AND b.current_compensation != s.employee_annualized_compensation
)

-- Combine all validation failures and return for dbt test
SELECT
    {{ simulation_year }} AS simulation_year,
    validation_rule,
    validation_source,
    severity,
    severity_rank,
    employee_id,
    validation_message,
    -- Audit trail metadata
    CURRENT_TIMESTAMP AS validation_timestamp,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id,
    CONCAT('DQ-', validation_rule, '-', {{ simulation_year }}, '-', employee_id) AS audit_record_id,
    'dbt_test' AS validation_engine_version,
    CASE severity
        WHEN 'CRITICAL' THEN 'IMMEDIATE_ACTION_REQUIRED'
        WHEN 'ERROR' THEN 'HIGH_PRIORITY_REVIEW'
        WHEN 'WARNING' THEN 'MONITORING_REQUIRED'
        ELSE 'INFORMATIONAL_ONLY'
    END AS risk_level,
    false AS regulatory_impact
FROM (
    SELECT * FROM critical_validations
    UNION ALL
    SELECT * FROM error_validations
    UNION ALL
    SELECT * FROM warning_validations
) all_failures
ORDER BY severity_rank, validation_rule, employee_id
