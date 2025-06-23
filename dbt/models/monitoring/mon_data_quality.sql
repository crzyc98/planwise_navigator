{{ config(materialized='table') }}

-- Data Quality Monitoring: Track data quality metrics across simulation runs
-- **FIX**: Added comprehensive NULL value handling to ensure metric_value is never NULL

WITH table_metadata AS (
    -- Define all monitored tables and their expected characteristics
    SELECT * FROM (VALUES
        ('fct_workforce_snapshot', 'fact', 'Core workforce state by year'),
        ('fct_yearly_events', 'fact', 'All workforce events by year'),
        ('mart_workforce_summary', 'mart', 'Business intelligence summary'),
        ('mart_cohort_analysis', 'mart', 'Cohort retention analysis'),
        ('mart_financial_impact', 'mart', 'Financial impact metrics'),
        ('stg_census_data', 'staging', 'Staged census input data')
    ) AS t(table_name, table_type, description)
),

-- Record count monitoring
record_counts AS (
    SELECT
        'fct_workforce_snapshot' AS table_name,
        simulation_year,
        employment_status,
        COUNT(*) AS record_count,
        COUNT(DISTINCT employee_id) AS unique_employees,
        MIN(snapshot_created_at) AS earliest_record,
        MAX(snapshot_created_at) AS latest_record
    FROM {{ ref('fct_workforce_snapshot') }}
    GROUP BY simulation_year, employment_status

    UNION ALL

    SELECT
        'fct_yearly_events' AS table_name,
        simulation_year,
        event_type AS employment_status,
        COUNT(*) AS record_count,
        COUNT(DISTINCT employee_id) AS unique_employees,
        MIN(created_at) AS earliest_record,
        MAX(created_at) AS latest_record
    FROM {{ ref('fct_yearly_events') }}
    GROUP BY simulation_year, event_type
),

-- Completeness monitoring for critical fields
completeness_checks AS (
    SELECT
        'fct_workforce_snapshot' AS table_name,
        simulation_year,
        'employee_id' AS field_name,
        COUNT(*) AS total_records,
        COUNT(employee_id) AS non_null_records,
        -- **FIX**: Use COALESCE to handle division by zero
        COALESCE(COUNT(employee_id) * 100.0 / NULLIF(COUNT(*), 0), 0) AS completeness_rate,
        CASE WHEN COALESCE(COUNT(employee_id) * 100.0 / NULLIF(COUNT(*), 0), 0) < 100 THEN 'FAIL' ELSE 'PASS' END AS quality_status
    FROM {{ ref('fct_workforce_snapshot') }}
    GROUP BY simulation_year

    UNION ALL

    SELECT
        'fct_workforce_snapshot' AS table_name,
        simulation_year,
        'current_compensation' AS field_name,
        COUNT(*) AS total_records,
        COUNT(current_compensation) AS non_null_records,
        -- **FIX**: Use COALESCE to handle division by zero
        COALESCE(COUNT(current_compensation) * 100.0 / NULLIF(COUNT(*), 0), 0) AS completeness_rate,
        CASE WHEN COALESCE(COUNT(current_compensation) * 100.0 / NULLIF(COUNT(*), 0), 0) < 95 THEN 'FAIL' ELSE 'PASS' END AS quality_status
    FROM {{ ref('fct_workforce_snapshot') }}
    GROUP BY simulation_year

    UNION ALL

    SELECT
        'fct_workforce_snapshot' AS table_name,
        simulation_year,
        'current_age' AS field_name,
        COUNT(*) AS total_records,
        COUNT(current_age) AS non_null_records,
        -- **FIX**: Use COALESCE to handle division by zero
        COALESCE(COUNT(current_age) * 100.0 / NULLIF(COUNT(*), 0), 0) AS completeness_rate,
        CASE WHEN COALESCE(COUNT(current_age) * 100.0 / NULLIF(COUNT(*), 0), 0) < 100 THEN 'FAIL' ELSE 'PASS' END AS quality_status
    FROM {{ ref('fct_workforce_snapshot') }}
    GROUP BY simulation_year

    UNION ALL

    SELECT
        'fct_yearly_events' AS table_name,
        simulation_year,
        'employee_id' AS field_name,
        COUNT(*) AS total_records,
        COUNT(employee_id) AS non_null_records,
        -- **FIX**: Use COALESCE to handle division by zero
        COALESCE(COUNT(employee_id) * 100.0 / NULLIF(COUNT(*), 0), 0) AS completeness_rate,
        CASE WHEN COALESCE(COUNT(employee_id) * 100.0 / NULLIF(COUNT(*), 0), 0) < 100 THEN 'FAIL' ELSE 'PASS' END AS quality_status
    FROM {{ ref('fct_yearly_events') }}
    GROUP BY simulation_year

    UNION ALL

    SELECT
        'fct_yearly_events' AS table_name,
        simulation_year,
        'event_type' AS field_name,
        COUNT(*) AS total_records,
        COUNT(event_type) AS non_null_records,
        -- **FIX**: Use COALESCE to handle division by zero
        COALESCE(COUNT(event_type) * 100.0 / NULLIF(COUNT(*), 0), 0) AS completeness_rate,
        CASE WHEN COALESCE(COUNT(event_type) * 100.0 / NULLIF(COUNT(*), 0), 0) < 100 THEN 'FAIL' ELSE 'PASS' END AS quality_status
    FROM {{ ref('fct_yearly_events') }}
    GROUP BY simulation_year
),

-- Business rule validation
business_rule_checks AS (
    -- Age validation: employees should be between 18 and 70
    SELECT
        'fct_workforce_snapshot' AS table_name,
        simulation_year,
        'age_range_validation' AS check_name,
        COUNT(*) AS total_records,
        COUNT(CASE WHEN current_age BETWEEN 18 AND 70 THEN 1 END) AS valid_records,
        COUNT(CASE WHEN current_age < 18 OR current_age > 70 THEN 1 END) AS invalid_records,
        -- **FIX**: Use COALESCE to handle division by zero
        COALESCE(COUNT(CASE WHEN current_age BETWEEN 18 AND 70 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 0) AS pass_rate,
        CASE WHEN COALESCE(COUNT(CASE WHEN current_age BETWEEN 18 AND 70 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 0) < 98 THEN 'FAIL' ELSE 'PASS' END AS quality_status
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE employment_status = 'active'
    GROUP BY simulation_year

    UNION ALL

    -- Compensation validation: reasonable salary ranges by level
    SELECT
        'fct_workforce_snapshot' AS table_name,
        simulation_year,
        'compensation_range_validation' AS check_name,
        COUNT(*) AS total_records,
        COUNT(CASE
            WHEN level_id = 1 AND current_compensation BETWEEN 30000 AND 80000 THEN 1
            WHEN level_id = 2 AND current_compensation BETWEEN 45000 AND 120000 THEN 1
            WHEN level_id = 3 AND current_compensation BETWEEN 70000 AND 160000 THEN 1
            WHEN level_id = 4 AND current_compensation BETWEEN 100000 AND 250000 THEN 1
            WHEN level_id = 5 AND current_compensation BETWEEN 150000 AND 500000 THEN 1
        END) AS valid_records,
        COUNT(CASE
            WHEN NOT (
                (level_id = 1 AND current_compensation BETWEEN 30000 AND 80000) OR
                (level_id = 2 AND current_compensation BETWEEN 45000 AND 120000) OR
                (level_id = 3 AND current_compensation BETWEEN 70000 AND 160000) OR
                (level_id = 4 AND current_compensation BETWEEN 100000 AND 250000) OR
                (level_id = 5 AND current_compensation BETWEEN 150000 AND 500000)
            ) THEN 1
        END) AS invalid_records,
        -- **FIX**: Use COALESCE to handle division by zero
        COALESCE(COUNT(CASE
            WHEN level_id = 1 AND current_compensation BETWEEN 30000 AND 80000 THEN 1
            WHEN level_id = 2 AND current_compensation BETWEEN 45000 AND 120000 THEN 1
            WHEN level_id = 3 AND current_compensation BETWEEN 70000 AND 160000 THEN 1
            WHEN level_id = 4 AND current_compensation BETWEEN 100000 AND 250000 THEN 1
            WHEN level_id = 5 AND current_compensation BETWEEN 150000 AND 500000 THEN 1
        END) * 100.0 / NULLIF(COUNT(*), 0), 0) AS pass_rate,
        CASE WHEN COALESCE(COUNT(CASE
            WHEN level_id = 1 AND current_compensation BETWEEN 30000 AND 80000 THEN 1
            WHEN level_id = 2 AND current_compensation BETWEEN 45000 AND 120000 THEN 1
            WHEN level_id = 3 AND current_compensation BETWEEN 70000 AND 160000 THEN 1
            WHEN level_id = 4 AND current_compensation BETWEEN 100000 AND 250000 THEN 1
            WHEN level_id = 5 AND current_compensation BETWEEN 150000 AND 500000 THEN 1
        END) * 100.0 / NULLIF(COUNT(*), 0), 0) < 95 THEN 'FAIL' ELSE 'PASS' END AS quality_status
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE employment_status = 'active'
    GROUP BY simulation_year

    UNION ALL

    -- Tenure validation: tenure should be reasonable given hire date
    SELECT
        'fct_workforce_snapshot' AS table_name,
        simulation_year,
        'tenure_consistency_validation' AS check_name,
        COUNT(*) AS total_records,
        COUNT(CASE WHEN current_tenure >= 0 AND current_tenure <= 50 THEN 1 END) AS valid_records,
        COUNT(CASE WHEN current_tenure < 0 OR current_tenure > 50 THEN 1 END) AS invalid_records,
        -- **FIX**: Use COALESCE to handle division by zero
        COALESCE(COUNT(CASE WHEN current_tenure >= 0 AND current_tenure <= 50 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 0) AS pass_rate,
        CASE WHEN COALESCE(COUNT(CASE WHEN current_tenure >= 0 AND current_tenure <= 50 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 0) < 99 THEN 'FAIL' ELSE 'PASS' END AS quality_status
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE employment_status = 'active'
    GROUP BY simulation_year

    UNION ALL

    -- Event validation: hiring events should have reasonable starting salaries
    SELECT
        'fct_yearly_events' AS table_name,
        simulation_year,
        'hire_compensation_validation' AS check_name,
        COUNT(*) AS total_records,
        COUNT(CASE WHEN compensation_amount BETWEEN 30000 AND 200000 THEN 1 END) AS valid_records,
        COUNT(CASE WHEN compensation_amount < 30000 OR compensation_amount > 200000 THEN 1 END) AS invalid_records,
        -- **FIX**: Use COALESCE to handle division by zero
        COALESCE(COUNT(CASE WHEN compensation_amount BETWEEN 30000 AND 200000 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 0) AS pass_rate,
        CASE WHEN COALESCE(COUNT(CASE WHEN compensation_amount BETWEEN 30000 AND 200000 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 0) < 95 THEN 'FAIL' ELSE 'PASS' END AS quality_status
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'hire'
    GROUP BY simulation_year
),

-- Outlier detection
-- First flag outliers at the row level to satisfy DuckDB aggregate restrictions
comp_outlier_flags AS (
    SELECT
        simulation_year,
        level_id,
        current_compensation,
        -- **FIX**: Handle potential NULL in z-score calculation
        CASE
            WHEN STDDEV(current_compensation) OVER (PARTITION BY simulation_year, level_id) = 0
                 OR STDDEV(current_compensation) OVER (PARTITION BY simulation_year, level_id) IS NULL
            THEN FALSE
            ELSE ABS(current_compensation - AVG(current_compensation) OVER (PARTITION BY simulation_year, level_id)) /
                STDDEV(current_compensation) OVER (PARTITION BY simulation_year, level_id) > 3
        END AS is_comp_outlier
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE employment_status = 'active'
),

age_outlier_flags AS (
    SELECT
        simulation_year,
        current_age,
        -- **FIX**: Handle potential NULL in z-score calculation
        CASE
            WHEN STDDEV(current_age) OVER (PARTITION BY simulation_year) = 0
                 OR STDDEV(current_age) OVER (PARTITION BY simulation_year) IS NULL
            THEN FALSE
            ELSE ABS(current_age - AVG(current_age) OVER (PARTITION BY simulation_year)) /
                STDDEV(current_age) OVER (PARTITION BY simulation_year) > 3
        END AS is_age_outlier
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE employment_status = 'active'
),

outlier_detection AS (
    -- Compensation outliers aggregated
    SELECT
        'fct_workforce_snapshot' AS table_name,
        simulation_year,
        level_id,
        'compensation_outliers' AS outlier_type,
        COUNT(*) AS total_records,
        -- **FIX**: Use COALESCE to ensure SUM never returns NULL
        COALESCE(SUM(CASE WHEN is_comp_outlier THEN 1 ELSE 0 END), 0) AS outlier_count,
        COALESCE(SUM(CASE WHEN is_comp_outlier THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 0) AS outlier_rate,
        CASE WHEN COALESCE(SUM(CASE WHEN is_comp_outlier THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 0) > 5 THEN 'WARN' ELSE 'PASS' END AS quality_status
    FROM comp_outlier_flags
    GROUP BY simulation_year, level_id

    UNION ALL

    -- Age outliers aggregated
    SELECT
        'fct_workforce_snapshot' AS table_name,
        simulation_year,
        NULL AS level_id,
        'age_outliers' AS outlier_type,
        COUNT(*) AS total_records,
        -- **FIX**: Use COALESCE to ensure SUM never returns NULL
        COALESCE(SUM(CASE WHEN is_age_outlier THEN 1 ELSE 0 END), 0) AS outlier_count,
        COALESCE(SUM(CASE WHEN is_age_outlier THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 0) AS outlier_rate,
        CASE WHEN COALESCE(SUM(CASE WHEN is_age_outlier THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 0) > 2 THEN 'WARN' ELSE 'PASS' END AS quality_status
    FROM age_outlier_flags
    GROUP BY simulation_year
),

-- Year-over-year consistency checks (separated aggregation and windowing for DuckDB)
-- First aggregate headcount per year
yearly_headcount AS (
    SELECT
        simulation_year,
        COUNT(*) AS headcount
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE employment_status = 'active'
    GROUP BY simulation_year
),

-- Then apply window functions on the aggregated result
yoy_consistency AS (
    SELECT
        simulation_year,
        'headcount_consistency' AS check_name,
        headcount AS current_year_count,
        LAG(headcount) OVER (ORDER BY simulation_year) AS prev_year_count,
        -- **FIX**: Replace NULL with 0 when no previous year data exists
        COALESCE(
            CASE
                WHEN LAG(headcount) OVER (ORDER BY simulation_year) > 0 THEN
                    ABS(headcount - LAG(headcount) OVER (ORDER BY simulation_year)) * 100.0 /
                    LAG(headcount) OVER (ORDER BY simulation_year)
                ELSE 0
            END,
            0
        ) AS yoy_change_percent,
        CASE
            WHEN LAG(headcount) OVER (ORDER BY simulation_year) > 0 AND
                 ABS(headcount - LAG(headcount) OVER (ORDER BY simulation_year)) * 100.0 /
                 LAG(headcount) OVER (ORDER BY simulation_year) > 50 THEN 'WARN'
            ELSE 'PASS'
        END AS quality_status
    FROM yearly_headcount
),

-- Data freshness checks
freshness_checks AS (
    SELECT
        'fct_workforce_snapshot' AS table_name,
        MAX(simulation_year) AS latest_simulation_year,
        MAX(snapshot_created_at) AS latest_update,
        -- **FIX**: Use COALESCE to handle NULL timestamps
        COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MAX(snapshot_created_at))) / 3600, 0) AS hours_since_update,
        CASE
            WHEN COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MAX(snapshot_created_at))) / 3600, 0) > 24 THEN 'WARN'
            WHEN COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MAX(snapshot_created_at))) / 3600, 0) > 48 THEN 'FAIL'
            ELSE 'PASS'
        END AS freshness_status
    FROM {{ ref('fct_workforce_snapshot') }}

    UNION ALL

    SELECT
        'fct_yearly_events' AS table_name,
        MAX(simulation_year) AS latest_simulation_year,
        MAX(created_at) AS latest_update,
        -- **FIX**: Use COALESCE to handle NULL timestamps
        COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MAX(created_at))) / 3600, 0) AS hours_since_update,
        CASE
            WHEN COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MAX(created_at))) / 3600, 0) > 24 THEN 'WARN'
            WHEN COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MAX(created_at))) / 3600, 0) > 48 THEN 'FAIL'
            ELSE 'PASS'
        END AS freshness_status
    FROM {{ ref('fct_yearly_events') }}
)

-- Final consolidated data quality report
SELECT
    'RECORD_COUNT' AS check_type,
    rc.table_name,
    rc.simulation_year::VARCHAR AS check_dimension,
    rc.employment_status AS check_subcategory,
    -- **FIX**: Ensure metric_value is never NULL
    COALESCE(rc.record_count::FLOAT, 0) AS metric_value,
    COALESCE(rc.unique_employees::FLOAT, 0) AS secondary_metric,
    CASE
        WHEN rc.record_count = 0 THEN 'FAIL'
        WHEN rc.unique_employees = 0 THEN 'FAIL'
        ELSE 'PASS'
    END AS quality_status,
    'Record count and unique employee validation' AS check_description,
    CURRENT_TIMESTAMP AS check_timestamp
FROM record_counts rc

UNION ALL

SELECT
    'COMPLETENESS' AS check_type,
    cc.table_name,
    cc.simulation_year::VARCHAR AS check_dimension,
    cc.field_name AS check_subcategory,
    -- **FIX**: Ensure metric_value is never NULL
    COALESCE(cc.completeness_rate, 0) AS metric_value,
    COALESCE(cc.non_null_records::FLOAT, 0) AS secondary_metric,
    cc.quality_status,
    'Field completeness validation - ' || cc.field_name AS check_description,
    CURRENT_TIMESTAMP AS check_timestamp
FROM completeness_checks cc

UNION ALL

SELECT
    'BUSINESS_RULE' AS check_type,
    brc.table_name,
    brc.simulation_year::VARCHAR AS check_dimension,
    brc.check_name AS check_subcategory,
    -- **FIX**: Ensure metric_value is never NULL
    COALESCE(brc.pass_rate, 0) AS metric_value,
    COALESCE(brc.invalid_records::FLOAT, 0) AS secondary_metric,
    brc.quality_status,
    'Business rule validation - ' || brc.check_name AS check_description,
    CURRENT_TIMESTAMP AS check_timestamp
FROM business_rule_checks brc

UNION ALL

SELECT
    'OUTLIER_DETECTION' AS check_type,
    od.table_name,
    od.simulation_year::VARCHAR AS check_dimension,
    od.outlier_type AS check_subcategory,
    -- **FIX**: Ensure metric_value is never NULL
    COALESCE(od.outlier_rate, 0) AS metric_value,
    COALESCE(od.outlier_count::FLOAT, 0) AS secondary_metric,
    od.quality_status,
    'Outlier detection - ' || od.outlier_type AS check_description,
    CURRENT_TIMESTAMP AS check_timestamp
FROM outlier_detection od

UNION ALL

SELECT
    'YOY_CONSISTENCY' AS check_type,
    'fct_workforce_snapshot' AS table_name,
    yoy.simulation_year::VARCHAR AS check_dimension,
    yoy.check_name AS check_subcategory,
    -- **FIX**: Ensure metric_value is never NULL
    COALESCE(yoy.yoy_change_percent, 0) AS metric_value,
    COALESCE(yoy.current_year_count::FLOAT, 0) AS secondary_metric,
    yoy.quality_status,
    'Year-over-year consistency check' AS check_description,
    CURRENT_TIMESTAMP AS check_timestamp
FROM yoy_consistency yoy

UNION ALL

SELECT
    'FRESHNESS' AS check_type,
    fc.table_name,
    fc.latest_simulation_year::VARCHAR AS check_dimension,
    'data_freshness' AS check_subcategory,
    -- **FIX**: Ensure metric_value is never NULL
    COALESCE(fc.hours_since_update, 0) AS metric_value,
    -- **FIX**: Provide default value instead of NULL for secondary_metric
    0.0 AS secondary_metric,
    fc.freshness_status AS quality_status,
    'Data freshness validation' AS check_description,
    CURRENT_TIMESTAMP AS check_timestamp
FROM freshness_checks fc

ORDER BY check_type, table_name, check_dimension, check_subcategory
