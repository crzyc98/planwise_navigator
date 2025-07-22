{{ config(
    materialized='table'
) }}

-- Variance validation analysis to detect workforce count discrepancies
-- This model validates that event application produces correct workforce counts
-- Created as part of workforce variance fix implementation

WITH simulation_years AS (
    SELECT DISTINCT simulation_year
    FROM {{ ref('fct_yearly_events') }}
    ORDER BY simulation_year
),

-- Calculate expected workforce changes from events
event_summary AS (
    SELECT
        simulation_year,
        SUM(CASE WHEN event_type = 'hire' THEN 1 ELSE 0 END) AS hire_events,
        SUM(CASE
            WHEN event_type = 'termination'
            THEN 1
            ELSE 0
        END) AS termination_events,
        -- Expected net change: hires minus terminations
        SUM(CASE WHEN event_type = 'hire' THEN 1 ELSE 0 END) -
        SUM(CASE WHEN event_type = 'termination' THEN 1 ELSE 0 END) AS expected_net_change
    FROM {{ ref('fct_yearly_events') }}
    GROUP BY simulation_year
),

-- Calculate actual workforce counts by year
workforce_counts AS (
    SELECT
        simulation_year,
        COUNT(CASE WHEN employment_status = 'active' THEN 1 END) AS active_count,
        COUNT(CASE WHEN employment_status = 'terminated' THEN 1 END) AS terminated_count,
        COUNT(*) AS total_count
    FROM {{ ref('fct_workforce_snapshot') }}
    GROUP BY simulation_year
),

-- Get baseline workforce count for comparison
baseline_count AS (
    SELECT COUNT(*) AS baseline_active_count
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employment_status = 'active'
),

-- Calculate actual workforce changes between years
workforce_changes AS (
    SELECT
        wc.simulation_year,
        wc.active_count,
        LAG(wc.active_count, 1, bc.baseline_active_count)
            OVER (ORDER BY wc.simulation_year) AS previous_active_count,
        wc.active_count - LAG(wc.active_count, 1, bc.baseline_active_count)
            OVER (ORDER BY wc.simulation_year) AS actual_net_change
    FROM workforce_counts wc
    CROSS JOIN baseline_count bc
),

-- Detailed termination breakdown for diagnostics
termination_breakdown AS (
    SELECT
        simulation_year,
        SUM(CASE
            WHEN detailed_status_code = 'experienced_termination'
            THEN 1
            ELSE 0
        END) AS experienced_terminations,
        SUM(CASE
            WHEN detailed_status_code = 'new_hire_termination'
            THEN 1
            ELSE 0
        END) AS new_hire_terminations,
        SUM(CASE
            WHEN detailed_status_code = 'new_hire_active'
            THEN 1
            ELSE 0
        END) AS new_hire_active,
        SUM(CASE
            WHEN detailed_status_code = 'continuous_active'
            THEN 1
            ELSE 0
        END) AS continuous_active
    FROM {{ ref('fct_workforce_snapshot') }}
    GROUP BY simulation_year
),

-- Combine all metrics for variance analysis
variance_analysis AS (
    SELECT
        es.simulation_year,
        wc.previous_active_count,
        wc.active_count,
        es.hire_events,
        es.termination_events,
        es.expected_net_change,
        wc.actual_net_change,
        -- Calculate variance
        ABS(es.expected_net_change - wc.actual_net_change) AS variance_abs,
        CASE
            WHEN es.expected_net_change != 0
            THEN ABS(es.expected_net_change - wc.actual_net_change) * 100.0 / ABS(es.expected_net_change)
            ELSE 0
        END AS variance_percentage,
        -- Flag problematic years
        CASE
            WHEN ABS(es.expected_net_change - wc.actual_net_change) > 10
                OR (es.expected_net_change != 0 AND
                    ABS(es.expected_net_change - wc.actual_net_change) * 100.0 / ABS(es.expected_net_change) > 5.0)
            THEN true
            ELSE false
        END AS variance_flag,
        -- Include detailed breakdown
        tb.experienced_terminations,
        tb.new_hire_terminations,
        tb.new_hire_active,
        tb.continuous_active
    FROM event_summary es
    INNER JOIN workforce_changes wc ON es.simulation_year = wc.simulation_year
    INNER JOIN termination_breakdown tb ON es.simulation_year = tb.simulation_year
)

SELECT
    simulation_year,
    previous_active_count,
    active_count,
    hire_events,
    termination_events,
    expected_net_change,
    actual_net_change,
    variance_abs,
    ROUND(variance_percentage, 2) AS variance_percentage,
    variance_flag,
    experienced_terminations,
    new_hire_terminations,
    new_hire_active,
    continuous_active,
    CURRENT_TIMESTAMP AS analysis_created_at
FROM variance_analysis
ORDER BY simulation_year
