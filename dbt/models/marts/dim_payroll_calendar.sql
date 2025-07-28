{{ config(
    materialized = 'table',
    tags = ['foundation', 'calendar', 'payroll']
) }}

{#
    Flexible payroll calendar dimension that generates bi-weekly pay periods
    for the simulation year, handling both 26 and 27 pay period years.

    This model creates a complete calendar of pay periods with:
    - Bi-weekly periods starting from the first Friday of January
    - Dynamic period count (26 or 27) based on calendar year
    - Total periods per year for accurate compensation calculations
#}

WITH calendar_config AS (
    SELECT
        {{ var('simulation_year') }} AS simulation_year,
        -- First Friday of January (can be made configurable via var)
        CAST(simulation_year || '-01-' ||
            CASE
                WHEN EXTRACT(DOW FROM CAST(simulation_year || '-01-01' AS DATE)) <= 5
                THEN 6 - EXTRACT(DOW FROM CAST(simulation_year || '-01-01' AS DATE))
                ELSE 13 - EXTRACT(DOW FROM CAST(simulation_year || '-01-01' AS DATE))
            END AS DATE) AS first_pay_date,
        CAST(simulation_year || '-12-31' AS DATE) AS year_end_date
),

pay_periods AS (
    -- Generate bi-weekly periods using recursive CTE
    WITH RECURSIVE period_generator AS (
        -- Anchor: First pay period
        SELECT
            1 AS pay_period_number,
            first_pay_date AS pay_period_end_date,
            first_pay_date - INTERVAL 13 DAY AS pay_period_start_date,
            simulation_year,
            year_end_date
        FROM calendar_config

        UNION ALL

        -- Recursive: Generate subsequent periods
        SELECT
            pay_period_number + 1,
            pay_period_end_date + INTERVAL 14 DAY,
            pay_period_end_date + INTERVAL 1 DAY,
            simulation_year,
            year_end_date
        FROM period_generator
        WHERE pay_period_end_date + INTERVAL 14 DAY <= year_end_date
    )

    SELECT * FROM period_generator
),

final AS (
    SELECT
        pay_period_number,
        pay_period_end_date,
        pay_period_start_date,
        simulation_year,
        -- Calculate total periods dynamically
        COUNT(*) OVER (PARTITION BY simulation_year) AS total_periods_in_year
    FROM pay_periods
)

SELECT * FROM final
ORDER BY pay_period_number
