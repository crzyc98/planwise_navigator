{{ config(
    materialized='incremental',
    unique_key=['event_id'],
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'type': 'btree'},
        {'columns': ['event_id'], 'type': 'btree', 'unique': true}
    ],
    tags=['match_engine', 'events', 'critical']
) }}

/*
  Employer Match Event Generation Model - Story S025-02

  Generates EMPLOYER_MATCH events from match calculations for integration
  with the event sourcing architecture. Each match calculation becomes an
  immutable event with full context and payload information.

  Features:
  - Incremental loading for multi-year simulations
  - Complete event payload with formula details
  - Integration with existing event sourcing architecture
  - Performance optimized for batch event generation
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH match_calculations AS (
    SELECT * FROM {{ ref('int_employee_match_calculations') }}
    {% if is_incremental() %}
    WHERE simulation_year > (SELECT COALESCE(MAX(simulation_year), 0) FROM {{ this }})
    {% endif %}
),

match_events AS (
    SELECT
        -- Generate unique event ID using employee_id, year, and a hash component
        MD5(CONCAT(
            employee_id::VARCHAR,
            '-MATCH-',
            simulation_year::VARCHAR,
            '-',
            CURRENT_TIMESTAMP::VARCHAR
        )) AS event_id,
        employee_id,
        'EMPLOYER_MATCH' AS event_type,
        simulation_year,
        -- Set effective date to end of plan year for annual match calculation
        MAKE_DATE(simulation_year, 12, 31) AS effective_date,
        employer_match_amount AS amount,
        -- Build comprehensive event payload
        TO_JSON({
            'event_type': 'EMPLOYER_MATCH',
            'formula_id': formula_id,
            'formula_name': formula_name,
            'formula_type': formula_type,
            'deferral_rate': deferral_rate,
            'eligible_compensation': eligible_compensation,
            'annual_deferrals': annual_deferrals,
            'employer_match_amount': employer_match_amount,
            'uncapped_match_amount': uncapped_match_amount,
            'match_cap_applied': match_cap_applied,
            'effective_match_rate': effective_match_rate,
            'match_percentage_of_comp': match_percentage_of_comp,
            'plan_year': simulation_year,
            'calculation_method': 'annual_aggregate',
            'created_by': 'match_engine_v1',
            'scenario_id': scenario_id,
            'parameter_scenario_id': parameter_scenario_id
        }) AS event_payload,
        CURRENT_TIMESTAMP AS created_at,
        'match_engine' AS source_system,
        scenario_id,
        parameter_scenario_id,
        -- Additional fields for compatibility with event architecture
        NULL AS employee_ssn,  -- Will be joined if needed
        NULL AS event_details,  -- Summary included in payload
        employer_match_amount AS compensation_amount,
        NULL AS previous_compensation,
        NULL::DECIMAL(5,4) AS employee_deferral_rate,  -- In payload
        NULL::DECIMAL(5,4) AS prev_employee_deferral_rate,
        NULL AS employee_age,  -- Can be joined if needed
        NULL AS employee_tenure,
        NULL AS level_id,
        NULL AS age_band,
        NULL AS tenure_band,
        NULL AS event_probability,
        'employer_match' AS event_category
    FROM match_calculations
    WHERE employer_match_amount > 0  -- Only create events for actual matches
)

SELECT
    event_id,
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category,
    amount,
    event_payload,
    created_at,
    source_system,
    scenario_id,
    parameter_scenario_id
FROM match_events
ORDER BY employee_id, simulation_year
