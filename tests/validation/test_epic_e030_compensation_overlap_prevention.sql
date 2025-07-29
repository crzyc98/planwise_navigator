-- Epic E030 Validation Test: Verify No Overlapping Compensation Periods
-- This test ensures the prorated compensation fix prevents double-counting

{{ config(
    severity = 'error',
    error_if = '>0'
) }}

WITH compensation_periods AS (
    SELECT
        employee_id,
        period_sequence,
        period_type,
        period_start,
        period_end,
        period_salary,
        -- Calculate period duration in days
        DATE_DIFF('day', period_start, period_end) + 1 AS period_days
    FROM (
        -- Recreate the compensation periods logic from fct_workforce_snapshot
        WITH comp_events_for_periods AS (
            SELECT DISTINCT
                employee_id,
                effective_date,
                event_type,
                compensation_amount,
                previous_compensation
            FROM {{ ref('fct_yearly_events') }}
            WHERE event_type IN ('hire', 'promotion', 'raise', 'termination')
              AND simulation_year = {{ var('simulation_year', 2025) }}
        ),

        employee_compensation_timeline AS (
            SELECT
                employee_id,
                effective_date AS event_date,
                event_type,
                compensation_amount AS new_compensation,
                previous_compensation,
                ROW_NUMBER() OVER (
                    PARTITION BY employee_id 
                    ORDER BY effective_date, 
                    CASE event_type
                        WHEN 'hire' THEN 1
                        WHEN 'promotion' THEN 2  
                        WHEN 'raise' THEN 3
                        WHEN 'termination' THEN 4
                    END
                ) AS event_sequence
            FROM comp_events_for_periods
        ),

        employee_timeline_with_boundaries AS (
            SELECT
                employee_id,
                event_date,
                event_type,
                new_compensation,
                previous_compensation,
                event_sequence,
                LEAD(event_date) OVER (
                    PARTITION BY employee_id 
                    ORDER BY event_sequence
                ) AS next_event_date
            FROM employee_compensation_timeline
        ),

        all_compensation_periods AS (
            -- Baseline periods
            SELECT
                t.employee_id,
                0 AS period_sequence,
                'baseline' AS period_type,
                '{{ var('simulation_year', 2025) }}-01-01'::DATE AS period_start,
                t.event_date - INTERVAL 1 DAY AS period_end,
                COALESCE(t.previous_compensation, 50000) AS period_salary
            FROM employee_timeline_with_boundaries t
            WHERE t.event_sequence = 1
              AND t.event_date > '{{ var('simulation_year', 2025) }}-01-01'::DATE
              AND t.event_type != 'hire'

            UNION ALL

            -- Event periods
            SELECT
                employee_id,
                event_sequence AS period_sequence,
                event_type || '_period' AS period_type,
                event_date AS period_start,
                COALESCE(
                    next_event_date - INTERVAL 1 DAY,
                    '{{ var('simulation_year', 2025) }}-12-31'::DATE
                ) AS period_end,
                new_compensation AS period_salary
            FROM employee_timeline_with_boundaries
            WHERE event_type IN ('hire', 'promotion', 'raise')
              AND new_compensation IS NOT NULL
              AND new_compensation > 0
        )

        SELECT * FROM all_compensation_periods
        WHERE period_start IS NOT NULL
          AND period_end IS NOT NULL
          AND period_salary IS NOT NULL
          AND period_salary > 0
          AND period_start <= period_end
    )
),

-- Check for overlapping periods within each employee
overlap_detection AS (
    SELECT
        cp1.employee_id,
        cp1.period_sequence AS period1_seq,
        cp1.period_type AS period1_type,
        cp1.period_start AS period1_start,
        cp1.period_end AS period1_end,
        cp2.period_sequence AS period2_seq,
        cp2.period_type AS period2_type,
        cp2.period_start AS period2_start,
        cp2.period_end AS period2_end,
        -- Detect overlap conditions
        CASE
            WHEN cp1.period_start <= cp2.period_end AND cp1.period_end >= cp2.period_start
                THEN 'OVERLAP_DETECTED'
            ELSE 'NO_OVERLAP'
        END AS overlap_status
    FROM compensation_periods cp1
    JOIN compensation_periods cp2 
        ON cp1.employee_id = cp2.employee_id
        AND cp1.period_sequence != cp2.period_sequence  -- Different periods
),

-- Check total period days vs expected employment days
period_day_validation AS (
    SELECT
        employee_id,
        SUM(period_days) AS total_period_days,
        -- Calculate expected employment days for the year
        365 AS max_possible_days,
        CASE
            WHEN SUM(period_days) > 365 THEN 'EXCESSIVE_DAYS'
            WHEN SUM(period_days) = 0 THEN 'NO_PERIODS'
            ELSE 'VALID_DAYS'
        END AS day_validation_status
    FROM compensation_periods
    GROUP BY employee_id
)

-- Return any validation failures
SELECT
    'OVERLAP_VALIDATION' AS test_type,
    employee_id,
    period1_seq,
    period1_type,
    period1_start,
    period1_end,
    period2_seq,
    period2_type,
    period2_start,
    period2_end,
    overlap_status AS issue_description
FROM overlap_detection
WHERE overlap_status = 'OVERLAP_DETECTED'

UNION ALL

SELECT
    'DAY_COUNT_VALIDATION' AS test_type,
    employee_id,
    NULL AS period1_seq,
    CAST(total_period_days AS VARCHAR) AS period1_type,
    NULL AS period1_start,
    NULL AS period1_end,
    NULL AS period2_seq,
    CAST(max_possible_days AS VARCHAR) AS period2_type,
    NULL AS period2_start,
    NULL AS period2_end,
    day_validation_status AS issue_description
FROM period_day_validation
WHERE day_validation_status IN ('EXCESSIVE_DAYS', 'NO_PERIODS')