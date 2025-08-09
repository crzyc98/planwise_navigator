{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'type': 'btree', 'unique': true},
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id'], 'type': 'btree'},
        {'columns': ['has_escalations'], 'type': 'btree'}
    ]
) }}

/*
  TEMPORARILY DISABLED: Temporal State Accumulator for Deferral Rate Escalation Tracking

  Epic E035: Automatic Annual Deferral Rate Escalation

  This model has been disabled to resolve circular dependency issues:
  fct_yearly_events -> int_deferral_rate_escalation_events -> int_deferral_escalation_state_accumulator

  TODO: Fix circular dependency and re-enable Epic E035 escalation functionality
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- TEMPORARILY DISABLED: Return empty result set to break circular dependencies
SELECT
    CAST(NULL AS VARCHAR) as employee_id,
    CAST(NULL AS INTEGER) as simulation_year,
    CAST(NULL AS DECIMAL(5,4)) as current_deferral_rate,
    CAST(NULL AS INTEGER) as escalations_received,
    CAST(NULL AS DATE) as last_escalation_date,
    CAST(NULL AS BOOLEAN) as has_escalations,
    CAST(NULL AS VARCHAR) as escalation_source,
    CAST(NULL AS INTEGER) as escalation_events_this_year,
    CAST(NULL AS BOOLEAN) as had_escalation_this_year,
    CAST(NULL AS VARCHAR) as latest_escalation_details,
    CAST(NULL AS DECIMAL(5,4)) as original_deferral_rate,
    CAST(NULL AS DECIMAL(5,4)) as escalation_rate_change_pct,
    CAST(NULL AS DECIMAL(5,4)) as total_escalation_amount,
    CAST(NULL AS INTEGER) as years_since_first_escalation,
    CAST(NULL AS INTEGER) as days_since_last_escalation,
    CAST(NULL AS TIMESTAMP) as created_at,
    CAST(NULL AS VARCHAR) as scenario_id,
    CAST(NULL AS VARCHAR) as data_quality_flag

WHERE FALSE  -- Always return empty result set

{% if is_incremental() %}
    -- For incremental runs, only process current simulation year
    AND simulation_year = {{ simulation_year }}
{% endif %}
