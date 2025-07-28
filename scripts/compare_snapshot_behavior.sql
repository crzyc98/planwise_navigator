-- Workforce Snapshot Architecture Behavior Comparison SQL Scripts
-- Compare original vs refactored implementation behavior

-- =====================================================
-- Employee Count Validation
-- =====================================================

-- Total employee counts by year and status
WITH employee_counts AS (
    SELECT
        simulation_year,
        employment_status,
        COUNT(*) as employee_count,
        COUNT(DISTINCT employee_id) as unique_employees
    FROM fct_workforce_snapshot
    WHERE simulation_year BETWEEN 2024 AND 2027
    GROUP BY simulation_year, employment_status
)
SELECT
    simulation_year,
    employment_status,
    employee_count,
    unique_employees,
    employee_count - LAG(employee_count) OVER (PARTITION BY employment_status ORDER BY simulation_year) as yoy_change
FROM employee_counts
ORDER BY simulation_year, employment_status;

-- Active vs terminated distribution validation
SELECT
    simulation_year,
    SUM(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) as active_count,
    SUM(CASE WHEN employment_status = 'terminated' THEN 1 ELSE 0 END) as terminated_count,
    ROUND(100.0 * SUM(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) / COUNT(*), 2) as active_pct
FROM fct_workforce_snapshot
WHERE simulation_year BETWEEN 2024 AND 2027
GROUP BY simulation_year
ORDER BY simulation_year;

-- =====================================================
-- Compensation Validation
-- =====================================================

-- Compensation statistics by year and level
SELECT
    simulation_year,
    level_id,
    COUNT(*) as employee_count,
    ROUND(AVG(current_compensation), 2) as avg_compensation,
    ROUND(MIN(current_compensation), 2) as min_compensation,
    ROUND(MAX(current_compensation), 2) as max_compensation,
    ROUND(STDDEV(current_compensation), 2) as stddev_compensation,
    ROUND(SUM(current_compensation), 2) as total_compensation
FROM fct_workforce_snapshot
WHERE employment_status = 'active'
    AND simulation_year BETWEEN 2024 AND 2027
GROUP BY simulation_year, level_id
ORDER BY simulation_year, level_id;

-- Compensation distribution by age band
SELECT
    simulation_year,
    age_band,
    COUNT(*) as employee_count,
    ROUND(AVG(current_compensation), 2) as avg_compensation,
    ROUND(AVG(prorated_annual_compensation), 2) as avg_prorated,
    ROUND(AVG(full_year_equivalent_compensation), 2) as avg_full_year
FROM fct_workforce_snapshot
WHERE employment_status = 'active'
    AND simulation_year BETWEEN 2024 AND 2027
GROUP BY simulation_year, age_band
ORDER BY simulation_year, age_band;

-- Validate compensation calculations consistency
SELECT
    simulation_year,
    COUNT(*) as total_records,
    SUM(CASE
        WHEN current_compensation < 0 THEN 1
        ELSE 0
    END) as negative_comp_count,
    SUM(CASE
        WHEN prorated_annual_compensation > full_year_equivalent_compensation THEN 1
        ELSE 0
    END) as invalid_proration_count,
    SUM(CASE
        WHEN employment_status = 'active' AND current_compensation = 0 THEN 1
        ELSE 0
    END) as zero_comp_active_count
FROM fct_workforce_snapshot
WHERE simulation_year BETWEEN 2024 AND 2027
GROUP BY simulation_year
ORDER BY simulation_year;

-- =====================================================
-- Event Application Validation
-- =====================================================

-- Promotion event validation
WITH promotion_analysis AS (
    SELECT
        e.simulation_year,
        e.event_type,
        COUNT(*) as event_count,
        AVG(CAST(JSON_EXTRACT_STRING(e.event_data, '$.new_level_id') AS INTEGER) -
            CAST(JSON_EXTRACT_STRING(e.event_data, '$.previous_level_id') AS INTEGER)) as avg_level_jump
    FROM fct_yearly_events e
    WHERE e.event_type = 'promotion'
        AND e.simulation_year BETWEEN 2024 AND 2027
    GROUP BY e.simulation_year, e.event_type
)
SELECT * FROM promotion_analysis
ORDER BY simulation_year;

-- Termination reason distribution
SELECT
    simulation_year,
    JSON_EXTRACT_STRING(event_data, '$.termination_reason') as termination_reason,
    COUNT(*) as termination_count
FROM fct_yearly_events
WHERE event_type = 'termination'
    AND simulation_year BETWEEN 2024 AND 2027
GROUP BY simulation_year, JSON_EXTRACT_STRING(event_data, '$.termination_reason')
ORDER BY simulation_year, termination_reason;

-- Merit increase validation
SELECT
    simulation_year,
    COUNT(*) as merit_count,
    ROUND(AVG(CAST(JSON_EXTRACT_STRING(event_data, '$.compensation_change') AS DOUBLE)), 2) as avg_merit_increase,
    ROUND(MIN(CAST(JSON_EXTRACT_STRING(event_data, '$.compensation_change') AS DOUBLE)), 2) as min_merit_increase,
    ROUND(MAX(CAST(JSON_EXTRACT_STRING(event_data, '$.compensation_change') AS DOUBLE)), 2) as max_merit_increase
FROM fct_yearly_events
WHERE event_type = 'merit_increase'
    AND simulation_year BETWEEN 2024 AND 2027
GROUP BY simulation_year
ORDER BY simulation_year;

-- Hiring validation
SELECT
    simulation_year,
    COUNT(*) as hire_count,
    COUNT(DISTINCT JSON_EXTRACT_STRING(event_data, '$.level_id')) as unique_levels_hired,
    ROUND(AVG(CAST(JSON_EXTRACT_STRING(event_data, '$.starting_compensation') AS DOUBLE)), 2) as avg_starting_comp
FROM fct_yearly_events
WHERE event_type = 'hire'
    AND simulation_year BETWEEN 2024 AND 2027
GROUP BY simulation_year
ORDER BY simulation_year;

-- =====================================================
-- Temporal Validation
-- =====================================================

-- Age and tenure calculations
SELECT
    simulation_year,
    AVG(age) as avg_age,
    MIN(age) as min_age,
    MAX(age) as max_age,
    AVG(years_of_service) as avg_tenure,
    MIN(years_of_service) as min_tenure,
    MAX(years_of_service) as max_tenure
FROM fct_workforce_snapshot
WHERE employment_status = 'active'
    AND simulation_year BETWEEN 2024 AND 2027
GROUP BY simulation_year
ORDER BY simulation_year;

-- Validate age progression
WITH age_progression AS (
    SELECT
        employee_id,
        simulation_year,
        age,
        LAG(age) OVER (PARTITION BY employee_id ORDER BY simulation_year) as prev_age,
        age - LAG(age) OVER (PARTITION BY employee_id ORDER BY simulation_year) as age_diff
    FROM fct_workforce_snapshot
    WHERE employment_status = 'active'
)
SELECT
    simulation_year,
    COUNT(*) as total_comparisons,
    SUM(CASE WHEN age_diff = 1 THEN 1 ELSE 0 END) as correct_progressions,
    SUM(CASE WHEN age_diff != 1 AND age_diff IS NOT NULL THEN 1 ELSE 0 END) as incorrect_progressions
FROM age_progression
WHERE prev_age IS NOT NULL
GROUP BY simulation_year
ORDER BY simulation_year;

-- =====================================================
-- Data Quality Validation
-- =====================================================

-- Comprehensive data quality checks
SELECT
    'null_employee_ids' as check_name,
    simulation_year,
    COUNT(*) as issue_count
FROM fct_workforce_snapshot
WHERE employee_id IS NULL
GROUP BY simulation_year

UNION ALL

SELECT
    'negative_compensation' as check_name,
    simulation_year,
    COUNT(*) as issue_count
FROM fct_workforce_snapshot
WHERE current_compensation < 0
GROUP BY simulation_year

UNION ALL

SELECT
    'invalid_age' as check_name,
    simulation_year,
    COUNT(*) as issue_count
FROM fct_workforce_snapshot
WHERE age < 18 OR age > 100
GROUP BY simulation_year

UNION ALL

SELECT
    'invalid_tenure' as check_name,
    simulation_year,
    COUNT(*) as issue_count
FROM fct_workforce_snapshot
WHERE years_of_service < 0 OR years_of_service > age - 18
GROUP BY simulation_year

UNION ALL

SELECT
    'missing_level_id' as check_name,
    simulation_year,
    COUNT(*) as issue_count
FROM fct_workforce_snapshot
WHERE employment_status = 'active' AND level_id IS NULL
GROUP BY simulation_year

ORDER BY check_name, simulation_year;

-- Referential integrity check with job levels
SELECT
    ws.simulation_year,
    COUNT(*) as total_employees,
    SUM(CASE WHEN jl.level_id IS NULL THEN 1 ELSE 0 END) as missing_level_refs
FROM fct_workforce_snapshot ws
LEFT JOIN stg_job_levels jl ON ws.level_id = jl.level_id
WHERE ws.employment_status = 'active'
GROUP BY ws.simulation_year
ORDER BY ws.simulation_year;

-- Band calculation validation
SELECT
    simulation_year,
    age_band,
    COUNT(*) as count,
    MIN(age) as min_age_in_band,
    MAX(age) as max_age_in_band,
    CASE
        WHEN age_band = '<25' AND MAX(age) >= 25 THEN 'ERROR'
        WHEN age_band = '25-34' AND (MIN(age) < 25 OR MAX(age) >= 35) THEN 'ERROR'
        WHEN age_band = '35-44' AND (MIN(age) < 35 OR MAX(age) >= 45) THEN 'ERROR'
        WHEN age_band = '45-54' AND (MIN(age) < 45 OR MAX(age) >= 55) THEN 'ERROR'
        WHEN age_band = '55+' AND MIN(age) < 55 THEN 'ERROR'
        ELSE 'OK'
    END as band_validation
FROM fct_workforce_snapshot
WHERE employment_status = 'active'
    AND simulation_year BETWEEN 2024 AND 2027
GROUP BY simulation_year, age_band
ORDER BY simulation_year, age_band;

-- =====================================================
-- Row-Level Comparison (for detecting differences)
-- =====================================================

-- This query would compare two versions if both existed
-- For now, it validates internal consistency
WITH employee_metrics AS (
    SELECT
        employee_id,
        simulation_year,
        employment_status,
        current_compensation,
        level_id,
        age,
        years_of_service,
        -- Create a hash of key fields for comparison
        MD5(CONCAT(
            COALESCE(CAST(current_compensation AS VARCHAR), 'NULL'),
            COALESCE(CAST(level_id AS VARCHAR), 'NULL'),
            COALESCE(CAST(age AS VARCHAR), 'NULL'),
            COALESCE(CAST(years_of_service AS VARCHAR), 'NULL')
        )) as row_hash
    FROM fct_workforce_snapshot
    WHERE simulation_year = 2025
)
SELECT
    COUNT(*) as total_rows,
    COUNT(DISTINCT employee_id) as unique_employees,
    COUNT(DISTINCT row_hash) as unique_row_patterns
FROM employee_metrics;

-- Summary validation query
WITH validation_summary AS (
    SELECT
        simulation_year,
        COUNT(*) as total_records,
        COUNT(DISTINCT employee_id) as unique_employees,
        SUM(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) as active_count,
        SUM(CASE WHEN employment_status = 'terminated' THEN 1 ELSE 0 END) as terminated_count,
        ROUND(AVG(CASE WHEN employment_status = 'active' THEN current_compensation END), 2) as avg_active_comp,
        COUNT(DISTINCT level_id) as unique_levels,
        COUNT(DISTINCT age_band) as unique_age_bands,
        COUNT(DISTINCT tenure_band) as unique_tenure_bands
    FROM fct_workforce_snapshot
    WHERE simulation_year BETWEEN 2024 AND 2027
    GROUP BY simulation_year
)
SELECT * FROM validation_summary
ORDER BY simulation_year;
