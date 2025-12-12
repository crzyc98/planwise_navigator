-- Test: Verify tenure bands have no gaps (continuous coverage)
-- A gap exists if the max_value of band N does not equal the min_value of band N+1
-- Uses [min, max) interval convention

WITH ordered_bands AS (
    SELECT
        band_id,
        band_label,
        min_value,
        max_value,
        display_order,
        LEAD(min_value) OVER (ORDER BY display_order) AS next_min_value
    FROM {{ ref('stg_config_tenure_bands') }}
),

gaps AS (
    SELECT
        band_label AS current_band,
        max_value AS current_max,
        next_min_value AS next_min
    FROM ordered_bands
    WHERE next_min_value IS NOT NULL  -- Exclude the last band
      AND max_value != next_min_value  -- Gap detected when max != next min
)

-- Test passes when this query returns 0 rows (no gaps)
SELECT * FROM gaps
