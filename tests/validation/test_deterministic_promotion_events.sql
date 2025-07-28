-- Test to verify that promotion events are deterministic
-- Same simulation_year and random seed should produce identical results
-- This test validates that removing anti-duplication logic is safe

WITH promotion_run_1 AS (
    -- First "run" of promotion events (this would be the actual table)
    SELECT
        employee_id,
        simulation_year,
        effective_date,
        from_level,
        to_level,
        random_value,
        promotion_rate
    FROM {{ ref('int_promotion_events') }}
    WHERE simulation_year = {{ var('simulation_year', 2025) }}
),

-- Simulate what a second run would produce by replicating the same logic
-- This would fail if the logic is non-deterministic
promotion_run_2 AS (
    SELECT
        w.employee_id,
        {{ var('simulation_year', 2025) }} AS simulation_year,
        (CAST('{{ var('simulation_year', 2025) }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(w.employee_id)) % 365)) DAY) AS effective_date,
        w.level_id AS from_level,
        w.level_id + 1 AS to_level,
        (ABS(HASH(w.employee_id)) % 1000) / 1000.0 AS random_value,
        h.promotion_rate
    FROM {{ ref('int_employee_compensation_by_year') }} w
    JOIN {{ ref('int_hazard_promotion') }} h
        ON w.level_id = h.level_id
        AND CASE
            WHEN w.current_age < 25 THEN '< 25'
            WHEN w.current_age < 35 THEN '25-34'
            WHEN w.current_age < 45 THEN '35-44'
            WHEN w.current_age < 55 THEN '45-54'
            WHEN w.current_age < 65 THEN '55-64'
            ELSE '65+'
        END = h.age_band
        AND CASE
            WHEN w.current_tenure < 2 THEN '< 2'
            WHEN w.current_tenure < 5 THEN '2-4'
            WHEN w.current_tenure < 10 THEN '5-9'
            WHEN w.current_tenure < 20 THEN '10-19'
            ELSE '20+'
        END = h.tenure_band
        AND h.year = {{ var('simulation_year', 2025) }}
    WHERE w.simulation_year = {{ var('simulation_year', 2025) }}
        AND w.employment_status = 'active'
        AND w.current_tenure >= 1
        AND w.level_id < 5
        AND w.current_age < 65
        AND (ABS(HASH(w.employee_id)) % 1000) / 1000.0 < h.promotion_rate
),

-- Find discrepancies between the two "runs"
discrepancies AS (
    -- Employees in run 1 but not run 2
    SELECT
        r1.employee_id,
        'missing_in_run_2' AS discrepancy_type,
        r1.random_value,
        r1.promotion_rate,
        r1.random_value < r1.promotion_rate AS should_be_promoted
    FROM promotion_run_1 r1
    LEFT JOIN promotion_run_2 r2 ON r1.employee_id = r2.employee_id
    WHERE r2.employee_id IS NULL

    UNION ALL

    -- Employees in run 2 but not run 1
    SELECT
        r2.employee_id,
        'missing_in_run_1' AS discrepancy_type,
        r2.random_value,
        r2.promotion_rate,
        r2.random_value < r2.promotion_rate AS should_be_promoted
    FROM promotion_run_2 r2
    LEFT JOIN promotion_run_1 r1 ON r2.employee_id = r1.employee_id
    WHERE r1.employee_id IS NULL

    UNION ALL

    -- Employees with different attributes
    SELECT
        r1.employee_id,
        'attribute_mismatch' AS discrepancy_type,
        r1.random_value,
        r1.promotion_rate,
        r1.random_value < r1.promotion_rate AS should_be_promoted
    FROM promotion_run_1 r1
    JOIN promotion_run_2 r2 ON r1.employee_id = r2.employee_id
    WHERE r1.from_level != r2.from_level
        OR r1.to_level != r2.to_level
        OR ABS(r1.random_value - r2.random_value) > 0.001
        OR ABS(r1.promotion_rate - r2.promotion_rate) > 0.001
)

-- Return any discrepancies (test passes if no rows returned)
SELECT
    employee_id,
    discrepancy_type,
    random_value,
    promotion_rate,
    should_be_promoted,
    'Promotion event generation is not deterministic for employee ' || employee_id ||
    '. Discrepancy type: ' || discrepancy_type AS error_message
FROM discrepancies
