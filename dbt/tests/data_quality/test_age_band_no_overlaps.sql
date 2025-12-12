-- Test: Verify age bands have no overlaps
-- An overlap exists if any two bands cover the same value range
-- Uses [min, max) interval convention: lower bound inclusive, upper bound exclusive

WITH band_pairs AS (
    SELECT
        a.band_id AS band_a_id,
        a.band_label AS band_a_label,
        a.min_value AS a_min,
        a.max_value AS a_max,
        b.band_id AS band_b_id,
        b.band_label AS band_b_label,
        b.min_value AS b_min,
        b.max_value AS b_max
    FROM {{ ref('stg_config_age_bands') }} a
    CROSS JOIN {{ ref('stg_config_age_bands') }} b
    WHERE a.band_id < b.band_id  -- Only compare each pair once
),

overlapping_bands AS (
    SELECT
        band_a_label,
        band_b_label,
        a_min,
        a_max,
        b_min,
        b_max
    FROM band_pairs
    -- Overlap detection for [min, max) intervals:
    -- Two intervals [a_min, a_max) and [b_min, b_max) overlap if:
    -- a_min < b_max AND b_min < a_max
    WHERE a_min < b_max AND b_min < a_max
)

-- Test passes when this query returns 0 rows (no overlaps)
SELECT * FROM overlapping_bands
