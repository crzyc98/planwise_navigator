-- Cross-model band label consistency test
-- Validates that all age_band and tenure_band values in fct_workforce_snapshot
-- exist in the corresponding seed configuration tables.
-- Test passes when zero rows are returned (no mismatches).

WITH age_band_mismatches AS (
  SELECT DISTINCT
    'age_band' AS band_type,
    ws.age_band AS band_value
  FROM {{ ref('fct_workforce_snapshot') }} ws
  WHERE ws.age_band IS NOT NULL
    AND NOT EXISTS (
      SELECT 1
      FROM {{ ref('config_age_bands') }} cab
      WHERE cab.band_label = ws.age_band
    )
),

tenure_band_mismatches AS (
  SELECT DISTINCT
    'tenure_band' AS band_type,
    ws.tenure_band AS band_value
  FROM {{ ref('fct_workforce_snapshot') }} ws
  WHERE ws.tenure_band IS NOT NULL
    AND NOT EXISTS (
      SELECT 1
      FROM {{ ref('config_tenure_bands') }} ctb
      WHERE ctb.band_label = ws.tenure_band
    )
)

SELECT * FROM age_band_mismatches
UNION ALL
SELECT * FROM tenure_band_mismatches
