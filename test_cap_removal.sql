-- E066 Cap Removal Testing
-- Validate that removing hard caps allows legitimate annualization while maintaining quality monitoring

WITH test_scenarios AS (
    -- Test employee EMP_2024_003851 specifically
    SELECT
        employee_id,
        employee_hire_date,
        employee_gross_compensation,
        employee_annualized_compensation,

        -- What would happen under different approaches
        'Current E066 Fix' as approach,
        COALESCE(employee_annualized_compensation, employee_gross_compensation) as computed_compensation,

        -- Days worked calculation
        CASE
            WHEN employee_hire_date >= '2024-01-01'
            THEN DATE_DIFF('day', employee_hire_date, '2024-12-31') + 1
            ELSE 365
        END as days_worked_2024,

        -- Annualization factor
        CASE
            WHEN employee_hire_date >= '2024-01-01'
            THEN 365.0 / (DATE_DIFF('day', employee_hire_date, '2024-12-31') + 1)
            ELSE 1.0
        END as annualization_factor,

        -- Expected quality flag under new logic
        CASE
            WHEN COALESCE(employee_annualized_compensation, employee_gross_compensation) > 50000000 THEN 'CRITICAL_OVER_50M'
            WHEN COALESCE(employee_annualized_compensation, employee_gross_compensation) > 20000000 THEN 'CRITICAL_OVER_20M'
            WHEN COALESCE(employee_annualized_compensation, employee_gross_compensation) > 10000000 THEN 'CRITICAL_OVER_10M'
            WHEN COALESCE(employee_annualized_compensation, employee_gross_compensation) > 5000000 THEN 'SEVERE_OVER_5M'
            WHEN COALESCE(employee_annualized_compensation, employee_gross_compensation) > 2000000 THEN
                CASE
                    -- Late hire annualization (Nov-Dec)
                    WHEN employee_hire_date >= '2024-11-01' THEN 'WARNING_ANNUALIZED_LATE_HIRE'
                    ELSE 'WARNING_OVER_2M'
                END
            ELSE 'NORMAL'
        END as expected_quality_flag

    FROM {{ ref('stg_census_data') }}
    WHERE employee_id = 'EMP_2024_003851'
        OR employee_hire_date >= '2024-11-01'  -- All late hires
        OR employee_annualized_compensation > 2000000  -- High annualized cases

    UNION ALL

    -- Compare with old E060 approach (with caps)
    SELECT
        employee_id,
        employee_hire_date,
        employee_gross_compensation,
        employee_annualized_compensation,

        'Old E060 Capped' as approach,
        CASE
            WHEN COALESCE(employee_gross_compensation, employee_annualized_compensation) > 2000000
            THEN 2000000  -- E060 cap
            ELSE COALESCE(employee_gross_compensation, employee_annualized_compensation)
        END as computed_compensation,

        CASE
            WHEN employee_hire_date >= '2024-01-01'
            THEN DATE_DIFF('day', employee_hire_date, '2024-12-31') + 1
            ELSE 365
        END as days_worked_2024,

        CASE
            WHEN employee_hire_date >= '2024-01-01'
            THEN 365.0 / (DATE_DIFF('day', employee_hire_date, '2024-12-31') + 1)
            ELSE 1.0
        END as annualization_factor,

        -- Would be capped at $2M
        'ARTIFICIALLY_CAPPED' as expected_quality_flag

    FROM {{ ref('stg_census_data') }}
    WHERE employee_id = 'EMP_2024_003851'
        OR employee_hire_date >= '2024-11-01'  -- All late hires
        OR employee_annualized_compensation > 2000000  -- High annualized cases
)

SELECT
    employee_id,
    TO_VARCHAR(employee_hire_date) as hire_date,
    days_worked_2024,
    ROUND(annualization_factor, 2) as annualization_factor,
    approach,

    -- Original values
    ROUND(employee_gross_compensation, 0) as gross_comp,
    ROUND(employee_annualized_compensation, 0) as annualized_comp,

    -- Computed compensation under each approach
    ROUND(computed_compensation, 0) as final_compensation,

    expected_quality_flag,

    -- Impact analysis
    CASE
        WHEN approach = 'Current E066 Fix' AND computed_compensation > 2000000
        THEN 'ALLOWS_LEGITIMATE_HIGH_COMP'
        WHEN approach = 'Old E060 Capped' AND computed_compensation = 2000000
        THEN 'ARTIFICIALLY_CAPPED'
        ELSE 'NORMAL_RANGE'
    END as impact_assessment

FROM test_scenarios
ORDER BY
    employee_id,
    CASE approach WHEN 'Current E066 Fix' THEN 1 ELSE 2 END
