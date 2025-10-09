-- E077: Test that helper model successfully reads previous year's workforce
-- This test verifies there's no data loss between years

{% set simulation_year = var('simulation_year', 2025) %}
{% set start_year = var('start_year', 2025) %}

{% if simulation_year > start_year %}

WITH previous_year_snapshot_count AS (
    SELECT COUNT(*) as snapshot_count
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year - 1 }}
      AND employment_status = 'active'
),

helper_model_count AS (
    SELECT COUNT(*) as helper_count
    FROM {{ ref('int_active_employees_prev_year_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
),

validation AS (
    SELECT
        snapshot_count,
        helper_count,
        ABS(snapshot_count - helper_count) as diff,
        CASE
            WHEN helper_count = 0 THEN 'CRITICAL: Helper model has no data!'
            WHEN snapshot_count = 0 THEN 'WARNING: Snapshot has no data'
            WHEN ABS(snapshot_count - helper_count) > 0 THEN
                'ERROR: Data loss detected - ' ||
                ABS(snapshot_count - helper_count) || ' employees lost'
            ELSE 'PASS'
        END as validation_status
    FROM previous_year_snapshot_count
    CROSS JOIN helper_model_count
)

-- Test fails if there's any data loss
SELECT *
FROM validation
WHERE validation_status != 'PASS'

{% else %}

-- For Year 1, skip this test
SELECT 1 as dummy WHERE 1 = 0

{% endif %}
