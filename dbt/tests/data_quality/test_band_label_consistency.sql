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
    AND ws.age_band NOT IN (
      SELECT band_label
      FROM {{ ref('config_age_bands') }}
    )
),

tenure_band_mismatches AS (
  SELECT DISTINCT
    'tenure_band' AS band_type,
    ws.tenure_band AS band_value
  FROM {{ ref('fct_workforce_snapshot') }} ws
  WHERE ws.tenure_band IS NOT NULL
    AND ws.tenure_band NOT IN (
      SELECT band_label
      FROM {{ ref('config_tenure_bands') }}
    )
)

SELECT * FROM age_band_mismatches
UNION ALL
SELECT * FROM tenure_band_mismatches
