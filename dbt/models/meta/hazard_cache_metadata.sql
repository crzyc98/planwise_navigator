{{ config(
  materialized='table',
  tags=['CACHE_METADATA']
) }}

-- Hazard cache metadata tracking table
-- Tracks parameter fingerprints, build timestamps, and validation checksums
-- for all hazard cache dimension tables

WITH cache_validation AS (
  -- Validate that all hazard cache tables exist and have data
  SELECT
    'dim_promotion_hazards' AS cache_name,
    (SELECT COUNT(*) FROM {{ ref('dim_promotion_hazards') }}) AS row_count,
    (SELECT COUNT(DISTINCT level_id || tenure_band || age_band)
     FROM {{ ref('dim_promotion_hazards') }}) AS unique_combinations

  UNION ALL

  SELECT
    'dim_termination_hazards' AS cache_name,
    (SELECT COUNT(*) FROM {{ ref('dim_termination_hazards') }}) AS row_count,
    (SELECT COUNT(DISTINCT level_id || tenure_band || age_band)
     FROM {{ ref('dim_termination_hazards') }}) AS unique_combinations

  UNION ALL

  SELECT
    'dim_merit_hazards' AS cache_name,
    (SELECT COUNT(*) FROM {{ ref('dim_merit_hazards') }}) AS row_count,
    (SELECT COUNT(DISTINCT level_id || department || performance_tier)
     FROM {{ ref('dim_merit_hazards') }}) AS unique_combinations

  UNION ALL

  SELECT
    'dim_enrollment_hazards' AS cache_name,
    (SELECT COUNT(*) FROM {{ ref('dim_enrollment_hazards') }}) AS row_count,
    (SELECT COUNT(DISTINCT level_id || tenure_band || age_segment || income_segment)
     FROM {{ ref('dim_enrollment_hazards') }}) AS unique_combinations
),

cache_checksums AS (
  -- Generate checksums for data validation
  SELECT
    'dim_promotion_hazards' AS cache_name,
    (SELECT MD5(STRING_AGG(promotion_probability::TEXT, '' ORDER BY level_id, tenure_band, age_band))
     FROM {{ ref('dim_promotion_hazards') }}) AS data_checksum

  UNION ALL

  SELECT
    'dim_termination_hazards' AS cache_name,
    (SELECT MD5(STRING_AGG(termination_probability::TEXT, '' ORDER BY level_id, tenure_band, age_band))
     FROM {{ ref('dim_termination_hazards') }}) AS data_checksum

  UNION ALL

  SELECT
    'dim_merit_hazards' AS cache_name,
    (SELECT MD5(STRING_AGG(merit_probability::TEXT, '' ORDER BY level_id, department, performance_tier))
     FROM {{ ref('dim_merit_hazards') }}) AS data_checksum

  UNION ALL

  SELECT
    'dim_enrollment_hazards' AS cache_name,
    (SELECT MD5(STRING_AGG(enrollment_probability::TEXT, '' ORDER BY level_id, tenure_band, age_segment, income_segment))
     FROM {{ ref('dim_enrollment_hazards') }}) AS data_checksum
),

cache_build_times AS (
  -- Get build timestamps from each cache table
  SELECT
    'dim_promotion_hazards' AS cache_name,
    (SELECT MAX(cache_built_at) FROM {{ ref('dim_promotion_hazards') }}) AS built_at

  UNION ALL

  SELECT
    'dim_termination_hazards' AS cache_name,
    (SELECT MAX(cache_built_at) FROM {{ ref('dim_termination_hazards') }}) AS built_at

  UNION ALL

  SELECT
    'dim_merit_hazards' AS cache_name,
    (SELECT MAX(cache_built_at) FROM {{ ref('dim_merit_hazards') }}) AS built_at

  UNION ALL

  SELECT
    'dim_enrollment_hazards' AS cache_name,
    (SELECT MAX(cache_built_at) FROM {{ ref('dim_enrollment_hazards') }}) AS built_at
),

consolidated_metadata AS (
  SELECT
    cv.cache_name,
    '{{ var("hazard_params_hash", "default") }}' AS params_hash,
    cbt.built_at,
    cv.row_count,
    cv.unique_combinations,
    cc.data_checksum,

    -- Quality checks
    CASE
      WHEN cv.row_count = 0 THEN 'EMPTY'
      WHEN cv.row_count < cv.unique_combinations THEN 'DUPLICATE_KEYS'
      WHEN cbt.built_at < CURRENT_TIMESTAMP - INTERVAL '24 hours' THEN 'STALE'
      ELSE 'CURRENT'
    END AS cache_status,

    -- Mark as current (all caches built in this run are current)
    TRUE AS is_current,

    -- Performance metrics
    cv.row_count * 8 AS estimated_memory_bytes,  -- Rough estimate

    -- Validation flags
    cv.row_count > 0 AS has_data,
    cv.unique_combinations = cv.row_count AS has_unique_keys,
    cbt.built_at IS NOT NULL AS has_valid_build_time

  FROM cache_validation cv
  JOIN cache_checksums cc ON cv.cache_name = cc.cache_name
  JOIN cache_build_times cbt ON cv.cache_name = cbt.cache_name
)

SELECT
  cache_name,
  params_hash,
  built_at,
  row_count,
  unique_combinations,
  data_checksum,
  cache_status,
  is_current,
  estimated_memory_bytes,
  has_data,
  has_unique_keys,
  has_valid_build_time,

  -- Summary metrics
  CASE
    WHEN has_data AND has_unique_keys AND has_valid_build_time
      AND cache_status = 'CURRENT'
    THEN 'HEALTHY'
    WHEN has_data AND cache_status != 'EMPTY'
    THEN 'WARNING'
    ELSE 'ERROR'
  END AS overall_health,

  -- Recommendations
  CASE
    WHEN cache_status = 'EMPTY' THEN 'Cache is empty - check dependencies and rebuild'
    WHEN cache_status = 'DUPLICATE_KEYS' THEN 'Duplicate keys detected - review unique key logic'
    WHEN cache_status = 'STALE' THEN 'Cache is over 24 hours old - consider rebuilding'
    WHEN NOT has_data THEN 'No data found - verify source tables and parameters'
    WHEN NOT has_unique_keys THEN 'Key uniqueness violation - check for duplicate combinations'
    WHEN NOT has_valid_build_time THEN 'Missing build timestamp - verify cache_built_at field'
    ELSE 'Cache is healthy and current'
  END AS recommendation,

  CURRENT_TIMESTAMP AS metadata_generated_at

FROM consolidated_metadata
ORDER BY cache_name
