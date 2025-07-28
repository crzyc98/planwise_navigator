{{ config(
    materialized = 'table',
    tags = ['critical', 'payroll', 'ledger']
) }}

{#
    Optimized payroll ledger fact table that simulates bi-weekly payroll
    with performance considerations and comprehensive edge case handling.

    This model creates a detailed audit trail by:
    - Pre-filtering employee-period combinations for performance
    - Simulating bi-weekly pay periods with accurate salary calculations
    - Handling dynamic period counts (26 or 27 per year)
    - Providing granular earnings data for workforce analytics
#}

WITH active_employee_periods AS (
    -- Performance optimization: pre-filter valid employee-period combinations
    SELECT
        base.employee_id,
        base.simulation_year,
        base.employee_hire_date,
        base.termination_date,
        base.employee_gross_compensation AS starting_salary,
        calendar.pay_period_number,
        calendar.pay_period_end_date,
        calendar.pay_period_start_date,
        calendar.total_periods_in_year
    FROM {{ ref('int_snapshot_base') }} base
    CROSS JOIN {{ ref('dim_payroll_calendar') }} calendar
    WHERE
        -- Only include periods where employee was active
        calendar.pay_period_end_date > base.employee_hire_date
        AND (
            base.termination_date IS NULL
            OR calendar.pay_period_end_date < base.termination_date
        )
        AND calendar.simulation_year = base.simulation_year
),

salary_calculations AS (
    SELECT
        employee_id,
        simulation_year,
        pay_period_number,
        pay_period_end_date,
        pay_period_start_date,
        total_periods_in_year,
        employee_hire_date,
        termination_date,

        -- Calculate salary rate as of pay period end date
        {{ get_salary_as_of_date(
            'employee_id',
            'pay_period_end_date',
            ref('fct_yearly_events'),
            'starting_salary'
        ) }} AS annual_salary_rate_on_pay_date,

        -- Audit flags for edge case identification
        CASE
            WHEN pay_period_end_date <= employee_hire_date + INTERVAL 14 DAY
            THEN TRUE
            ELSE FALSE
        END AS is_first_period_after_hire,

        CASE
            WHEN termination_date IS NOT NULL
                AND pay_period_end_date >= termination_date - INTERVAL 14 DAY
            THEN TRUE
            ELSE FALSE
        END AS is_last_period_before_termination

    FROM active_employee_periods
),

final AS (
    SELECT
        employee_id,
        simulation_year,
        pay_period_number,
        pay_period_end_date,
        pay_period_start_date,
        total_periods_in_year,
        annual_salary_rate_on_pay_date,

        -- Calculate period earnings: annual salary / dynamic period count
        ROUND(
            annual_salary_rate_on_pay_date / total_periods_in_year,
            2
        ) AS period_earnings,

        -- Audit and debugging fields
        is_first_period_after_hire,
        is_last_period_before_termination

    FROM salary_calculations
)

SELECT * FROM final
ORDER BY employee_id, simulation_year, pay_period_number
