{{ config(materialized='table') }}

-- Enhanced workforce handoff with comprehensive validation and error handling
-- Prioritizes previous year snapshots with robust fallback to baseline
-- Includes data quality tracking and troubleshooting metadata

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set previous_year = simulation_year - 1 %}

-- DEBUG: Log the variable values
{{ log("DEBUG int_workforce_previous_year_v2: simulation_year = " ~ simulation_year, info=true) }}
{{ log("DEBUG int_workforce_previous_year_v2: previous_year = " ~ previous_year, info=true) }}

WITH
data_availability_check AS (
    SELECT
        COUNT(*) as total_previous_year_records,
        COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_previous_year_records,
        AVG(current_compensation) as avg_compensation,
        MIN(current_age) as min_age,
        MAX(current_age) as max_age,
        '{{ previous_year }}' as checked_year
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ previous_year }}
),

-- Calculate time-weighted compensation for previous year carryforward
time_weighted_compensation AS (
    SELECT
        fws.employee_id,
        fws.current_compensation,
        fws.full_year_equivalent_compensation,
        -- Calculate time-weighted compensation based on raise events
        COALESCE(
            (
                WITH raise_events AS (
                    SELECT
                        employee_id,
                        effective_date,
                        previous_compensation,
                        compensation_amount,
                        ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY effective_date) AS raise_sequence
                    FROM {{ ref('fct_yearly_events') }}
                    WHERE simulation_year = {{ previous_year }}
                      AND event_category = 'RAISE'
                      AND employee_id = fws.employee_id
                      AND compensation_amount IS NOT NULL
                      AND compensation_amount > 0
                ),
                salary_periods AS (
                    -- Period 1: Start of year to first raise (or end of year if no raises)
                    SELECT
                        fws.employee_id,
                        CAST('{{ previous_year }}-01-01' AS DATE) AS period_start,
                        COALESCE(
                            (SELECT MIN(effective_date) FROM raise_events WHERE employee_id = fws.employee_id),
                            CAST('{{ previous_year }}-12-31' AS DATE)
                        ) AS period_end,
                        COALESCE(
                            (SELECT previous_compensation FROM raise_events WHERE employee_id = fws.employee_id AND raise_sequence = 1),
                            fws.current_compensation
                        ) AS period_salary

                    UNION ALL

                    -- Additional periods for each raise
                    SELECT
                        re.employee_id,
                        re.effective_date AS period_start,
                        COALESCE(
                            (SELECT MIN(effective_date) FROM raise_events re2
                             WHERE re2.employee_id = re.employee_id
                             AND re2.raise_sequence = re.raise_sequence + 1),
                            CAST('{{ previous_year }}-12-31' AS DATE)
                        ) AS period_end,
                        re.compensation_amount AS period_salary
                    FROM raise_events re
                )
                SELECT
                    SUM(period_salary * (GREATEST(0, EXTRACT(DAY FROM (period_end - period_start)) + 1) / 365.0))
                FROM salary_periods
                WHERE employee_id = fws.employee_id
                  AND period_start <= period_end
            ),
            fws.full_year_equivalent_compensation  -- Fallback to full year equivalent
        ) AS time_weighted_compensation
    FROM {{ ref('fct_workforce_snapshot') }} fws
    WHERE fws.simulation_year = {{ previous_year }}
      AND fws.employment_status = 'active'
),

previous_year_snapshot AS (
    SELECT
        fws.employee_id,
        fws.employee_ssn,
        fws.employee_birth_date,
        fws.employee_hire_date,
        twc.time_weighted_compensation AS employee_gross_compensation,
        fws.current_age + 1 AS current_age,
        fws.current_tenure + 1 AS current_tenure,
        fws.level_id,
        -- Recalculate age band
        CASE
            WHEN (fws.current_age + 1) < 25 THEN '< 25'
            WHEN (fws.current_age + 1) < 35 THEN '25-34'
            WHEN (fws.current_age + 1) < 45 THEN '35-44'
            WHEN (fws.current_age + 1) < 55 THEN '45-54'
            WHEN (fws.current_age + 1) < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        -- Recalculate tenure band
        CASE
            WHEN (fws.current_tenure + 1) < 2 THEN '< 2'
            WHEN (fws.current_tenure + 1) < 5 THEN '2-4'
            WHEN (fws.current_tenure + 1) < 10 THEN '5-9'
            WHEN (fws.current_tenure + 1) < 20 THEN '10-19'
            ELSE '20+'
        END AS tenure_band,
        fws.employment_status,
        fws.termination_date,
        fws.termination_reason,
        {{ simulation_year }} AS simulation_year,
        CURRENT_TIMESTAMP AS snapshot_created_at,
        false AS is_from_census,
        false AS is_cold_start,
        {{ simulation_year - 1 }} AS last_completed_year,
        'previous_year_snapshot' AS data_source
    FROM {{ ref('fct_workforce_snapshot') }} fws
    JOIN time_weighted_compensation twc ON fws.employee_id = twc.employee_id
    WHERE fws.simulation_year = {{ previous_year }}
      AND fws.employment_status = 'active'
),

baseline_fallback AS (
    SELECT
        bf.employee_id,
        bf.employee_ssn,
        bf.employee_birth_date,
        bf.employee_hire_date,
        bf.current_compensation AS employee_gross_compensation,
        bf.current_age,
        bf.current_tenure,
        bf.level_id,
        bf.age_band,
        bf.tenure_band,
        bf.employment_status,
        bf.termination_date,
        bf.termination_reason,
        {{ simulation_year }}::INT AS simulation_year,  -- Force current simulation year as integer
        CURRENT_TIMESTAMP AS snapshot_created_at,
        bf.is_from_census,
        bf.is_cold_start,
        NULL AS last_completed_year,  -- Reset to NULL since we're starting fresh
        'baseline_fallback' AS data_source
    FROM {{ ref('int_baseline_workforce') }} bf
    WHERE bf.employment_status = 'active'
),

-- Enhanced combined data with data quality metadata
-- Explicitly list all columns to ensure correct ordering and avoid conflicts
combined_data AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        age_band,
        tenure_band,
        employment_status,
        termination_date,
        termination_reason,
        simulation_year,
        snapshot_created_at,
        is_from_census,
        is_cold_start,
        last_completed_year,
        data_source,
        -- Data quality flags
        CASE
            WHEN data_source = 'previous_year_snapshot' THEN 'GOOD'
            WHEN data_source = 'baseline_fallback' THEN 'FALLBACK_WARNING'
            ELSE 'UNKNOWN'
        END as data_quality_flag,
        -- Validation metadata
        CASE
            WHEN employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
            WHEN current_age IS NULL OR current_age < 18 OR current_age > 100 THEN 'INVALID_AGE'
            WHEN employee_gross_compensation IS NULL OR employee_gross_compensation < 0 THEN 'INVALID_COMPENSATION'
            WHEN level_id IS NULL THEN 'INVALID_LEVEL'
            ELSE 'VALID'
        END as validation_flag
    FROM previous_year_snapshot
    UNION ALL
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        age_band,
        tenure_band,
        employment_status,
        termination_date,
        termination_reason,
        simulation_year,
        snapshot_created_at,
        is_from_census,
        is_cold_start,
        last_completed_year,
        data_source,
        'FALLBACK_WARNING' as data_quality_flag,
        CASE
            WHEN employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
            WHEN current_age IS NULL OR current_age < 18 OR current_age > 100 THEN 'INVALID_AGE'
            WHEN employee_gross_compensation IS NULL OR employee_gross_compensation < 0 THEN 'INVALID_COMPENSATION'
            WHEN level_id IS NULL THEN 'INVALID_LEVEL'
            ELSE 'VALID'
        END as validation_flag
    FROM baseline_fallback
    WHERE NOT EXISTS (SELECT 1 FROM previous_year_snapshot)
),

-- Enhanced workforce with comprehensive statistics and validation
workforce_with_metadata AS (
    SELECT
        cd.*,
        -- Workforce statistics
        COUNT(*) OVER () AS total_employees,
        SUM(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) OVER () AS active_employees,
        -- Data source statistics
        SUM(CASE WHEN data_source = 'previous_year_snapshot' THEN 1 ELSE 0 END) OVER () AS from_previous_year,
        SUM(CASE WHEN data_source = 'baseline_fallback' THEN 1 ELSE 0 END) OVER () AS from_baseline,
        -- Data quality statistics
        SUM(CASE WHEN data_quality_flag = 'GOOD' THEN 1 ELSE 0 END) OVER () AS good_quality_records,
        SUM(CASE WHEN validation_flag = 'VALID' THEN 1 ELSE 0 END) OVER () AS valid_records,
        -- Availability check results (for troubleshooting)
        (SELECT active_previous_year_records FROM data_availability_check) AS previous_year_available_count,
        (SELECT avg_compensation FROM data_availability_check) AS previous_year_avg_compensation,
        -- Timestamp and metadata
        CURRENT_TIMESTAMP AS processing_timestamp,
        '{{ simulation_year }}' AS target_simulation_year
    FROM combined_data cd
    CROSS JOIN data_availability_check
)

-- Final selection with debug info
SELECT
    *,
    {{ simulation_year }} AS debug_expected_simulation_year,
    '{{ simulation_year }}' AS debug_simulation_year_string
FROM workforce_with_metadata
