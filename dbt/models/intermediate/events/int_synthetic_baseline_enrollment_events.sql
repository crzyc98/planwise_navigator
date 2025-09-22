{{ config(
  materialized='ephemeral',
  tags=['EVENT_GENERATION', 'E068A_EPHEMERAL']
) }}

/*
Epic E049: Census Deferral Rate Integration - Synthetic Baseline Event Generation
Story S049-02: Generate enrollment events for all pre-enrolled census participants

Purpose: Transform census data into synthetic enrollment events to maintain full
         event-sourcing while preserving actual participant deferral rates.

Key Features:
- Preserves exact census rates (1.3% → 0.013, not default 6%)
- Generates proper event metadata for audit trail
- Normalizes rates to [0,1] with IRS cap enforcement
- Only processes employees enrolled at census date
*/

{% set start_year = var('start_year', 2025) %}
{% set start_date = start_year ~ '-01-01' %}

WITH census_enrolled AS (
    SELECT
        employee_id,
        employee_deferral_rate,
        employee_enrollment_date,
        current_age,
        current_tenure,
        level_id,
        current_compensation,
        {{ start_year }} as simulation_year
    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ start_year }}
      AND employee_enrollment_date IS NOT NULL
      AND employee_enrollment_date < '{{ start_date }}'::DATE
      AND employee_deferral_rate > 0
      AND is_enrolled_at_census = true
),

-- Generate synthetic enrollment events with proper rate normalization
synthetic_events AS (
    SELECT
        employee_id,
        'enrollment' as event_type,
        {{ start_year }} as simulation_year,
        -- Use census enrollment date as effective date for historical accuracy
        employee_enrollment_date as effective_date,

        -- Preserve exact census rate with proper clamping and normalization
        {{ normalize_deferral_rate('employee_deferral_rate') }} as employee_deferral_rate,

        -- Generate sequence number (all synthetic events are sequence 0)
        0 as event_sequence,

        -- Event details showing actual rate with source attribution
        CONCAT(
            'Census baseline enrollment - ',
            CAST(ROUND(employee_deferral_rate * 100, 1) AS VARCHAR),
            '% deferral rate (synthetic)'
        ) as event_details,

        -- Event metadata
        'synthetic_baseline_generator' as event_source,
        'int_synthetic_baseline_enrollment_events' as model_source,
        CURRENT_TIMESTAMP as created_at,

        -- Additional context for debugging
        current_age,
        current_tenure,
        level_id,
        current_compensation

    FROM census_enrolled
),

-- Add data quality flags and validation
final_events AS (
    SELECT
        employee_id,
        event_type,
        simulation_year,
        effective_date,
        employee_deferral_rate,
        event_sequence,
        event_details,
        event_source,
        model_source,
        created_at,
        current_age,
        current_tenure,
        level_id,
        current_compensation,

        -- Data quality flags
        CASE
            WHEN employee_deferral_rate = {{ census_fallback_rate() }}
            THEN 'fallback_rate_applied'
            WHEN employee_deferral_rate = {{ plan_deferral_cap() }}
            THEN 'capped_at_irs_limit'
            ELSE 'census_rate_preserved'
        END as data_quality_flag,

        -- Validation flags
        employee_deferral_rate > 0 as has_valid_rate,
        effective_date < '{{ start_date }}'::DATE as is_pre_simulation_enrollment

    FROM synthetic_events
)

SELECT
    employee_id,
    event_type,
    simulation_year,
    effective_date,
    employee_deferral_rate,
    event_sequence,
    event_details,
    event_source,
    model_source,
    created_at,
    data_quality_flag,
    has_valid_rate,
    is_pre_simulation_enrollment,
    -- Additional context preserved for downstream models
    current_age,
    current_tenure,
    level_id,
    current_compensation

FROM final_events
WHERE has_valid_rate = true
  AND is_pre_simulation_enrollment = true
ORDER BY employee_id, effective_date
