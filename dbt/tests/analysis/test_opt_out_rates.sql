-- Converted from validation model to test
-- Added simulation_year filter for performance

/*
Data quality validation for opt-out rates in enrollment events.

Monitors opt-out rates by demographics to ensure they remain within
industry-standard ranges (5-15% for well-designed auto-enrollment programs).

Returns only records with WARNING status (rates outside expected bounds).
0 rows = all opt-out rates are within expected ranges.
*/

WITH opt_out_events AS (
    SELECT
        employee_id,
        simulation_year,
        event_type,
        effective_date
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'enrollment_opt_out'
      AND simulation_year = {{ var('simulation_year') }}
),

enrolled_population AS (
    SELECT
        w.employee_id,
        w.simulation_year,
        w.age_band AS age_segment,
        -- Derive income segment based on level/compensation
        CASE
            WHEN w.level_id >= 5 OR w.current_compensation >= 250000 THEN 'executive'
            WHEN w.level_id >= 4 OR w.current_compensation >= 150000 THEN 'high'
            WHEN w.level_id >= 3 OR w.current_compensation >= 100000 THEN 'moderate'
            ELSE 'low_income'
        END AS income_segment,
        w.participation_status
    FROM {{ ref('fct_workforce_snapshot') }} w
    WHERE w.simulation_year = {{ var('simulation_year') }}
      AND w.employment_status = 'active'
      AND (w.participation_status = 'participating'
           OR w.participation_status_detail LIKE '%opted out%')
),

opt_out_rates_by_demographics AS (
    SELECT
        p.age_segment,
        p.income_segment,
        COUNT(*) as total_eligible,
        COUNT(o.employee_id) as opted_out_count,
        ROUND(
            COALESCE(COUNT(o.employee_id) * 100.0 / NULLIF(COUNT(*), 0), 0),
            2
        ) as opt_out_rate_pct
    FROM enrolled_population p
    LEFT JOIN opt_out_events o
      ON p.employee_id = o.employee_id
     AND p.simulation_year = o.simulation_year
    GROUP BY p.age_segment, p.income_segment
),

validation_results AS (
    SELECT
        age_segment,
        income_segment,
        total_eligible,
        opted_out_count,
        opt_out_rate_pct,
        CASE
            WHEN opt_out_rate_pct > 15.0 THEN 'HIGH'
            WHEN opt_out_rate_pct < 2.0 AND total_eligible > 50 THEN 'LOW'
            WHEN opt_out_rate_pct BETWEEN 2.0 AND 15.0 THEN 'NORMAL'
            ELSE 'INSUFFICIENT_DATA'
        END as rate_classification,
        CASE
            WHEN opt_out_rate_pct > 15.0
                THEN 'Opt-out rate exceeds 15% industry benchmark'
            WHEN opt_out_rate_pct < 2.0 AND total_eligible > 50
                THEN 'Opt-out rate unusually low, may indicate data quality issue'
            WHEN total_eligible < 10
                THEN 'Sample size too small for reliable analysis'
            ELSE 'Opt-out rate within expected range'
        END as validation_message
    FROM opt_out_rates_by_demographics
)

-- Return only records with WARNING status (0 rows = all rates are normal)
SELECT
    {{ var('simulation_year') }} as simulation_year,
    age_segment,
    income_segment,
    total_eligible,
    opted_out_count,
    opt_out_rate_pct,
    rate_classification,
    validation_message,
    'WARNING' as validation_status,
    CURRENT_TIMESTAMP as validation_timestamp
FROM validation_results
WHERE rate_classification IN ('HIGH', 'LOW')
ORDER BY
    CASE age_segment
        WHEN 'young' THEN 1
        WHEN 'mid_career' THEN 2
        WHEN 'mature' THEN 3
        WHEN 'senior' THEN 4
        ELSE 5
    END,
    CASE income_segment
        WHEN 'low_income' THEN 1
        WHEN 'moderate' THEN 2
        WHEN 'high' THEN 3
        WHEN 'executive' THEN 4
        ELSE 5
    END
