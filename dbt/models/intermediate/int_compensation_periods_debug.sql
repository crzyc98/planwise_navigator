{{ config(
    materialized='table',
    tags=['debug', 'audit', 'compensation']
) }}

{#
    Debug model for compensation period calculations

    This model exposes the intermediate compensation_periods calculation
    from fct_workforce_snapshot for audit trail and debugging purposes.

    Use this model to:
    - Validate period calculations for specific employees
    - Debug overlapping period issues
    - Audit proration calculations step-by-step
    - Monitor data quality in compensation periods
#}

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

-- Replicate the same logic as in fct_workforce_snapshot for debugging
current_year_events AS (
    SELECT
        employee_id,
        event_type,
        effective_date,
        compensation_amount,
        previous_compensation,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date,
            CASE
                WHEN event_type = 'hire' THEN 1
                WHEN event_type = 'promotion' THEN 2
                WHEN event_type = 'raise' THEN 3
                WHEN event_type = 'termination' THEN 4
                ELSE 5
            END
        ) AS event_sequence
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND event_type IN ('hire', 'promotion', 'raise', 'termination')
      AND employee_id IS NOT NULL
),

comp_events_for_periods AS (
    SELECT
        employee_id,
        event_type,
        effective_date,
        compensation_amount,
        previous_compensation,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date, event_type
        ) AS event_sequence_in_year
    FROM current_year_events
    WHERE event_type IN ('hire', 'promotion', 'raise', 'termination')
),

-- **FIXED**: Termination-aware compensation periods to prevent overlapping periods
all_compensation_periods AS (
    -- Get termination dates for each employee to use in period calculations
    WITH employee_termination_dates AS (
        SELECT
            employee_id,
            effective_date AS termination_date
        FROM comp_events_for_periods
        WHERE event_type = 'termination'
    ),

    -- For RAISE events: create BEFORE period (start of year to raise date - 1)
    raise_before_periods AS (
        SELECT
            r.employee_id,
            1 AS period_sequence,
            'raise_before' AS period_type,
            '{{ simulation_year }}-01-01'::DATE AS period_start,
            r.effective_date - INTERVAL 1 DAY AS period_end,
            r.previous_compensation AS period_salary,
            'Salary before raise on ' || r.effective_date AS period_description
        FROM comp_events_for_periods r
        WHERE r.event_type = 'raise'
          AND r.previous_compensation IS NOT NULL
          AND r.previous_compensation > 0
    ),

    -- For RAISE events: create AFTER period (raise date to termination or year-end)
    raise_after_periods AS (
        SELECT
            r.employee_id,
            2 AS period_sequence,
            'raise_after' AS period_type,
            r.effective_date AS period_start,
            -- **KEY FIX**: Use termination date if exists, otherwise year-end
            COALESCE(t.termination_date, '{{ simulation_year }}-12-31'::DATE) AS period_end,
            r.compensation_amount AS period_salary,
            'Salary after raise on ' || r.effective_date ||
            CASE WHEN t.termination_date IS NOT NULL
                 THEN ' (truncated at termination ' || t.termination_date || ')'
                 ELSE ' (through year-end)'
            END AS period_description
        FROM comp_events_for_periods r
        LEFT JOIN employee_termination_dates t ON r.employee_id = t.employee_id
        WHERE r.event_type = 'raise'
          AND r.compensation_amount > 0
    ),

    -- For hire events: period from hire date to next event, termination, or year-end
    hire_periods AS (
        SELECT
            h.employee_id,
            1 AS period_sequence,
            'hire' AS period_type,
            h.effective_date AS period_start,
            COALESCE(
                LEAD(h.effective_date - INTERVAL 1 DAY) OVER (PARTITION BY h.employee_id ORDER BY h.effective_date),
                t.termination_date,
                '{{ simulation_year }}-12-31'::DATE
            ) AS period_end,
            h.compensation_amount AS period_salary,
            'Salary from hire on ' || h.effective_date ||
            CASE WHEN t.termination_date IS NOT NULL
                 THEN ' (terminated ' || t.termination_date || ')'
                 ELSE ' (active through year-end)'
            END AS period_description
        FROM comp_events_for_periods h
        LEFT JOIN employee_termination_dates t ON h.employee_id = t.employee_id
        WHERE h.event_type = 'hire'
    ),

    -- For promotion events: period from promotion date to termination or year-end
    promotion_periods AS (
        SELECT
            p.employee_id,
            1 AS period_sequence,
            'promotion' AS period_type,
            p.effective_date AS period_start,
            COALESCE(
                LEAD(p.effective_date - INTERVAL 1 DAY) OVER (PARTITION BY p.employee_id ORDER BY p.effective_date),
                t.termination_date,
                '{{ simulation_year }}-12-31'::DATE
            ) AS period_end,
            p.compensation_amount AS period_salary,
            'Salary from promotion on ' || p.effective_date ||
            CASE WHEN t.termination_date IS NOT NULL
                 THEN ' (terminated ' || t.termination_date || ')'
                 ELSE ' (active through year-end)'
            END AS period_description
        FROM comp_events_for_periods p
        LEFT JOIN employee_termination_dates t ON p.employee_id = t.employee_id
        WHERE p.event_type = 'promotion'
    )

    -- Combine all period types (removed overlapping termination periods)
    SELECT * FROM raise_before_periods
    UNION ALL
    SELECT * FROM raise_after_periods
    UNION ALL
    SELECT * FROM hire_periods
    UNION ALL
    SELECT * FROM promotion_periods
),

-- Final cleaned periods with calculations
compensation_periods_final AS (
    SELECT
        employee_id,
        period_sequence,
        period_type,
        period_start,
        period_end,
        period_salary,
        period_description,
        -- Calculate period length and contribution
        DATE_DIFF('day', period_start, period_end) + 1 AS period_days,
        ROUND(period_salary * (DATE_DIFF('day', period_start, period_end) + 1) / 365.0, 2) AS period_contribution,
        -- Add validation flags
        CASE
            WHEN period_start > period_end THEN 'ERROR: Start after end'
            WHEN period_salary <= 0 THEN 'ERROR: Invalid salary'
            WHEN DATE_DIFF('day', period_start, period_end) < 0 THEN 'ERROR: Negative days'
            ELSE 'VALID'
        END AS validation_status
    FROM all_compensation_periods
    WHERE period_start IS NOT NULL
      AND period_end IS NOT NULL
      AND period_salary IS NOT NULL
      AND period_salary > 0
      AND period_start <= period_end
      AND period_start >= '{{ simulation_year }}-01-01'::DATE
      AND period_end <= '{{ simulation_year }}-12-31'::DATE
)

SELECT
    employee_id,
    period_sequence,
    period_type,
    period_start,
    period_end,
    period_days,
    period_salary,
    period_contribution,
    period_description,
    validation_status,
    {{ simulation_year }} AS simulation_year,
    CURRENT_TIMESTAMP AS debug_created_at
FROM compensation_periods_final
ORDER BY employee_id, period_start, period_sequence
