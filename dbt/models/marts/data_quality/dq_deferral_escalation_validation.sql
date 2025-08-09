{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['validation_type'], 'type': 'btree'},
        {'columns': ['validation_status'], 'type': 'btree'},
        {'columns': ['severity'], 'type': 'btree'}
    ]
) }}

/*
  TEMPORARILY DISABLED: Data Quality Validation for Deferral Rate Escalation

  Epic E035: Automatic Annual Deferral Rate Escalation

  This model has been disabled to resolve circular dependency issues.

  TODO: Fix circular dependency and re-enable Epic E035 data quality validation
*/

{% set simulation_year = var('simulation_year', 2025) %}

-- TEMPORARILY DISABLED: Return empty result set to break circular dependencies
SELECT
    CAST(NULL AS VARCHAR) as employee_id,
    CAST(NULL AS INTEGER) as simulation_year,
    CAST(NULL AS VARCHAR) as validation_type,
    CAST(NULL AS VARCHAR) as validation_status,
    CAST(NULL AS VARCHAR) as severity,
    CAST(NULL AS VARCHAR) as validation_message,
    CAST(NULL AS VARCHAR) as validation_details,
    CAST(NULL AS TIMESTAMP) as created_at

WHERE FALSE  -- Always return empty result set
