{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['employee_id', 'simulation_year'],
    on_schema_change='ignore',
    pre_hook=[
      "{% set rel = adapter.get_relation(database=this.database, schema=this.schema, identifier=this.identifier) %}{% if rel is not none %}DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}{% else %}SELECT 1{% endif %}"
    ]
) }}

/*
  Temporal State Accumulator for Deferral Rate Escalation Tracking

  Epic E035: Automatic Annual Deferral Rate Escalation

  This model tracks the cumulative state of deferral rate escalations across simulation years.
  It accumulates escalation history and current state for each employee.

  FIXED: Circular dependency resolved by depending only on:
  - int_deferral_rate_escalation_events (the fixed version)
  - int_employee_compensation_by_year for baseline data
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

WITH current_workforce AS (
    -- Get all active employees for the current year with deferral rate from state accumulator
    SELECT
        comp.employee_id,
        comp.employee_ssn,
        -- Use current deferral rate from state accumulator, fallback to 0.03 (3%) baseline if not found
        COALESCE(dra.current_deferral_rate, 0.03) as baseline_deferral_rate,
        {{ simulation_year }} as simulation_year
    FROM {{ ref('int_employee_compensation_by_year') }} comp
    LEFT JOIN {{ ref('int_deferral_rate_state_accumulator_v2') }} dra
        ON comp.employee_id = dra.employee_id
        AND comp.simulation_year = dra.simulation_year
    WHERE comp.simulation_year = {{ simulation_year }}
        AND comp.employment_status = 'active'
),

-- Epic E078: Mode-aware query - uses fct_yearly_events in Polars mode, int_deferral_rate_escalation_events in SQL mode
escalation_events_history AS (
    -- Get all escalation events up to and including current year
    {% if var('event_generation_mode', 'sql') == 'polars' %}
    -- Polars mode: Read from fct_yearly_events
    SELECT
        employee_id,
        simulation_year,
        effective_date,
        prev_employee_deferral_rate as previous_deferral_rate,
        employee_deferral_rate as new_deferral_rate,
        CAST(NULL AS DECIMAL(5,4)) as escalation_rate,
        CAST(NULL AS INTEGER) as new_escalation_count,
        event_details
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year <= {{ simulation_year }}
      AND event_type IN ('enrollment_change', 'deferral_escalation')
    {% else %}
    -- SQL mode: Use intermediate event model
    SELECT
        employee_id,
        simulation_year,
        effective_date,
        previous_deferral_rate,
        new_deferral_rate,
        escalation_rate,
        new_escalation_count,
        event_details
    FROM {{ ref('int_deferral_rate_escalation_events') }}
    WHERE simulation_year <= {{ simulation_year }}
    {% endif %}
),

employee_escalation_summary AS (
    -- Summarize escalation history per employee
    SELECT
        employee_id,
        COUNT(*) as total_escalations,
        MAX(effective_date) as last_escalation_date,
        SUM(escalation_rate) as total_escalation_amount,
        MAX(new_deferral_rate) as latest_deferral_rate,
        MIN(effective_date) as first_escalation_date,
        -- Get current year escalation if exists
        MAX(CASE WHEN simulation_year = {{ simulation_year }} THEN 1 ELSE 0 END) as had_escalation_this_year,
        MAX(CASE WHEN simulation_year = {{ simulation_year }} THEN event_details END) as latest_escalation_details
    FROM escalation_events_history
    GROUP BY employee_id
),

final_state AS (
    SELECT
        w.employee_id,
        w.simulation_year,

        -- Current deferral rate (baseline + all escalations)
        COALESCE(e.latest_deferral_rate, w.baseline_deferral_rate, 0.00) as current_deferral_rate,

        -- Escalation tracking
        COALESCE(e.total_escalations, 0) as escalations_received,
        e.last_escalation_date,
        (COALESCE(e.total_escalations, 0) > 0) as has_escalations,
        'int_deferral_rate_escalation_events' as escalation_source,

        -- Current year activity
        CASE WHEN e.had_escalation_this_year = 1 THEN 1 ELSE 0 END as escalation_events_this_year,
        COALESCE(e.had_escalation_this_year = 1, false) as had_escalation_this_year,
        e.latest_escalation_details,

        -- Rate analysis
        w.baseline_deferral_rate as original_deferral_rate,
        CASE
            WHEN w.baseline_deferral_rate > 0
            THEN ((COALESCE(e.latest_deferral_rate, w.baseline_deferral_rate) - w.baseline_deferral_rate) / w.baseline_deferral_rate)
            ELSE NULL
        END as escalation_rate_change_pct,
        COALESCE(e.total_escalation_amount, 0.00) as total_escalation_amount,

        -- Time-based metrics
        CASE
            WHEN e.first_escalation_date IS NOT NULL
            THEN DATE_DIFF('year', e.first_escalation_date, CAST('{{ simulation_year }}-12-31' AS DATE))
            ELSE NULL
        END as years_since_first_escalation,
        CASE
            WHEN e.last_escalation_date IS NOT NULL
            THEN DATE_DIFF('day', e.last_escalation_date, CAST('{{ simulation_year }}-12-31' AS DATE))
            ELSE NULL
        END as days_since_last_escalation,

        -- Metadata
        CURRENT_TIMESTAMP as created_at,
        'default' as scenario_id,
        'VALID' as data_quality_flag

    FROM current_workforce w
    LEFT JOIN employee_escalation_summary e ON w.employee_id = e.employee_id
)

SELECT * FROM final_state

{% if is_incremental() %}
    -- For incremental runs, only process current simulation year
    WHERE simulation_year = {{ simulation_year }}
{% endif %}
