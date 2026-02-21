{{ config(
  materialized='ephemeral',
  tags=['EVENT_GENERATION', 'E058_MATCH_RESPONSE']
) }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', 2025) %}
{% set prev_year = (simulation_year | int) - 1 %}

{# E058: Match-responsive deferral adjustment configuration #}
{% set mr_enabled = var('deferral_match_response_enabled', false) %}
{% set upward_participation = var('deferral_match_response_upward_participation_rate', 0.40) %}
{% set upward_maximize = var('deferral_match_response_upward_maximize_rate', 0.60) %}
{% set upward_partial_factor = var('deferral_match_response_upward_partial_factor', 0.50) %}
{% set downward_enabled = var('deferral_match_response_downward_enabled', true) %}
{% set downward_participation = var('deferral_match_response_downward_participation_rate', 0.15) %}
{% set downward_reduce_max = var('deferral_match_response_downward_reduce_to_max_rate', 0.70) %}
{% set downward_partial_factor = var('deferral_match_response_downward_partial_factor', 0.50) %}

{# Existing deferral config for caps #}
{% set esc_cap = var('deferral_escalation_cap', 0.10) %}
{% set irs_402g_limit = var('irs_402g_limit', 23500) %}

{# Match configuration #}
{% set employer_match_status = var('employer_match_status', 'deferral_based') %}
{# Pre-computed match-maximizing rate from Python export (avoids Jinja scoping issues) #}
{% set precomputed_match_max = var('deferral_match_response_match_max_rate', none) %}
{% set match_tiers = var('match_tiers', [
    {'employee_min': 0.00, 'employee_max': 0.03, 'match_rate': 1.00},
    {'employee_min': 0.03, 'employee_max': 0.05, 'match_rate': 0.50}
]) %}
{% set employer_match_graded_schedule = var('employer_match_graded_schedule', []) %}
{% set tenure_match_tiers = var('tenure_match_tiers', []) %}
{% set points_match_tiers = var('points_match_tiers', []) %}

/*
  E058: Match-Responsive Deferral Adjustment Events

  Generates events when employees adjust deferrals in response to the
  match formula gap. Fires in the first simulation year only (D5 in plan.md).

  Selection uses deterministic HASH-based random (D4 in plan.md) with
  a unique salt '-match-response-' to ensure independent selection
  from enrollment optimization and escalation.
*/

{% if mr_enabled and (simulation_year | int) == (start_year | int) %}

-- Calculate match-maximizing rate based on match mode
WITH match_maximizing_rate AS (
  {% if employer_match_status == 'deferral_based' %}
  -- Deferral-based: use pre-computed match max rate from Python config export
  -- (avoids Jinja2 scoping bug where set inside for loop doesn't update outer scope)
  {% if precomputed_match_max is not none %}
  SELECT {{ precomputed_match_max }}::DECIMAL(5,4) AS match_max_rate
  {% else %}
  -- Fallback: compute from match_tiers using Jinja namespace (scoping fix)
  SELECT
    {% set ns = namespace(max_employee_max=0.0) %}
    {% for tier in match_tiers %}
      {% if tier.employee_max is not none and tier.employee_max > ns.max_employee_max %}
        {% set ns.max_employee_max = tier.employee_max %}
      {% endif %}
    {% endfor %}
    {{ ns.max_employee_max }}::DECIMAL(5,4) AS match_max_rate
  {% endif %}
  {% elif employer_match_status == 'graded_by_service' %}
  -- Service-based: per-employee rate based on years of service
  -- Handled in eligible_employees CTE below (requires employee data)
  SELECT 0.06::DECIMAL(5,4) AS match_max_rate  -- placeholder, overridden per-employee
  {% elif employer_match_status == 'tenure_based' %}
  SELECT 0.06::DECIMAL(5,4) AS match_max_rate  -- placeholder, overridden per-employee
  {% elif employer_match_status == 'points_based' %}
  SELECT 0.06::DECIMAL(5,4) AS match_max_rate  -- placeholder, overridden per-employee
  {% else %}
  SELECT 0.06::DECIMAL(5,4) AS match_max_rate
  {% endif %}
),

-- Get initial enrollment rates for Year 1 (same pattern as escalation model)
initial_enrollment_rates AS (
    SELECT
        employee_id,
        employee_deferral_rate AS initial_deferral_rate,
        effective_date AS enrollment_date,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date
        ) AS rn
    FROM {{ ref('int_enrollment_events') }}
    WHERE LOWER(event_type) = 'enrollment'
        AND employee_id IS NOT NULL
        AND employee_deferral_rate IS NOT NULL
        AND simulation_year <= {{ simulation_year }}

    UNION ALL

    -- Include synthetic baseline enrollments for pre-enrolled census employees
    SELECT
        employee_id,
        employee_deferral_rate AS initial_deferral_rate,
        effective_date AS enrollment_date,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date
        ) AS rn
    FROM {{ ref('int_synthetic_baseline_enrollment_events') }}
    WHERE employee_id IS NOT NULL
        AND employee_deferral_rate > 0
),

{% if (simulation_year | int) != (start_year | int) %}
-- Year 2+: Read current rates from previous year's state accumulator
-- Direct table reference to avoid circular dependency (R7 in research.md)
previous_year_rates AS (
    SELECT
        employee_id,
        current_deferral_rate,
        employee_enrollment_date
    FROM {{ target.schema }}.int_deferral_rate_state_accumulator_v2
    WHERE simulation_year = {{ prev_year }}
      AND employee_id IS NOT NULL
),
{% endif %}

-- Eligible employees: active, enrolled, not new hires in current year
eligible_employees AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.employment_status,
        w.is_enrolled_flag,
        {% if (simulation_year | int) == (start_year | int) %}
        -- Year 1: Use enrollment events for current rate
        COALESCE(ier.initial_deferral_rate, 0.0)::DECIMAL(5,4) AS current_deferral_rate,
        {% else %}
        -- Year 2+: Use prior year accumulator
        COALESCE(pyr.current_deferral_rate, ier.initial_deferral_rate, 0.0)::DECIMAL(5,4) AS current_deferral_rate,
        {% endif %}

        -- Match-maximizing rate (per-employee for non-deferral-based modes)
        {% if employer_match_status == 'deferral_based' %}
        (SELECT match_max_rate FROM match_maximizing_rate)::DECIMAL(5,4) AS match_max_rate,
        {% elif employer_match_status == 'graded_by_service' %}
        ({{ get_tiered_match_max_deferral('FLOOR(w.current_tenure)', employer_match_graded_schedule, 0.06) }})::DECIMAL(5,4) AS match_max_rate,
        {% elif employer_match_status == 'tenure_based' %}
        ({{ get_tiered_match_max_deferral('FLOOR(w.current_tenure)', tenure_match_tiers, 0.06) }})::DECIMAL(5,4) AS match_max_rate,
        {% elif employer_match_status == 'points_based' %}
        {# Points = FLOOR(age) + FLOOR(tenure) #}
        ({{ get_tiered_match_max_deferral('FLOOR(w.current_age) + FLOOR(w.current_tenure)', points_match_tiers, 0.06) }})::DECIMAL(5,4) AS match_max_rate,
        {% else %}
        0.06::DECIMAL(5,4) AS match_max_rate,
        {% endif %}

        -- Deterministic hash for upward selection
        (ABS(HASH(w.employee_id || '-match-response-' || CAST({{ simulation_year }} AS VARCHAR))) % 1000) / 1000.0 AS hash_value_up,
        -- Deterministic hash for downward selection (different salt)
        (ABS(HASH(w.employee_id || '-match-response-down-' || CAST({{ simulation_year }} AS VARCHAR))) % 1000) / 1000.0 AS hash_value_down

    FROM {{ ref('int_employee_compensation_by_year') }} w
    LEFT JOIN initial_enrollment_rates ier
        ON w.employee_id = ier.employee_id AND ier.rn = 1
    {% if (simulation_year | int) != (start_year | int) %}
    LEFT JOIN previous_year_rates pyr
        ON w.employee_id = pyr.employee_id
    {% endif %}
    WHERE w.simulation_year = {{ simulation_year }}
        AND w.employment_status = 'active'
        AND w.employee_id IS NOT NULL
        -- Must be enrolled
        AND COALESCE(w.is_enrolled_flag, false) = true
        -- Exclude new hires in current simulation year (FR-012)
        AND NOT (w.employee_id LIKE 'NH_{{ simulation_year }}_%')
),

-- Upward response candidates: current rate below match-maximizing rate
upward_response_candidates AS (
    SELECT
        e.*,
        'upward' AS response_direction,
        CASE
            -- Maximizers: jump to match-maximizing rate
            WHEN e.hash_value_up < {{ upward_participation }} * {{ upward_maximize }}
            THEN e.match_max_rate
            -- Partial responders: close a fraction of the gap
            ELSE ROUND(
                (e.current_deferral_rate + {{ upward_partial_factor }} * (e.match_max_rate - e.current_deferral_rate))
                / 0.005
            ) * 0.005  -- Round to nearest 0.5% increment
        END AS raw_new_rate
    FROM eligible_employees e
    WHERE e.current_deferral_rate < e.match_max_rate
      AND e.hash_value_up < {{ upward_participation }}
),

-- Apply caps to upward rates
upward_events AS (
    SELECT
        employee_id,
        employee_ssn,
        'deferral_match_response'::VARCHAR AS event_type,
        {{ simulation_year }} AS simulation_year,
        DATE '{{ simulation_year }}-01-01' AS effective_date,
        -- Cap at escalation cap and IRS 402(g) rate-equivalent
        LEAST(
            raw_new_rate,
            {{ esc_cap }},
            CASE WHEN employee_compensation > 0
                 THEN ({{ irs_402g_limit }}::DECIMAL / employee_compensation)
                 ELSE {{ esc_cap }}
            END
        )::DECIMAL(5,4) AS employee_deferral_rate,
        current_deferral_rate AS prev_employee_deferral_rate,
        response_direction,
        match_max_rate,
        employee_compensation AS compensation_amount,
        employee_compensation AS previous_compensation,
        current_age AS employee_age,
        current_tenure AS employee_tenure,
        level_id,
        hash_value_up AS event_probability
    FROM upward_response_candidates
),

{% if downward_enabled %}
-- Downward response candidates: current rate above match-maximizing rate
downward_response_candidates AS (
    SELECT
        e.*,
        'downward' AS response_direction,
        CASE
            -- Reducers: drop to match-maximizing rate
            WHEN e.hash_value_down < {{ downward_participation }} * {{ downward_reduce_max }}
            THEN e.match_max_rate
            -- Partial reducers: close a fraction of the gap downward
            ELSE ROUND(
                (e.current_deferral_rate - {{ downward_partial_factor }} * (e.current_deferral_rate - e.match_max_rate))
                / 0.005
            ) * 0.005  -- Round to nearest 0.5% increment
        END AS raw_new_rate
    FROM eligible_employees e
    WHERE e.current_deferral_rate > e.match_max_rate
      AND e.hash_value_down < {{ downward_participation }}
),

-- Apply floor to downward rates
downward_events AS (
    SELECT
        employee_id,
        employee_ssn,
        'deferral_match_response'::VARCHAR AS event_type,
        {{ simulation_year }} AS simulation_year,
        DATE '{{ simulation_year }}-01-01' AS effective_date,
        -- Floor at 0.0 (no negative deferral rates)
        GREATEST(raw_new_rate, 0.0)::DECIMAL(5,4) AS employee_deferral_rate,
        current_deferral_rate AS prev_employee_deferral_rate,
        response_direction,
        match_max_rate,
        employee_compensation AS compensation_amount,
        employee_compensation AS previous_compensation,
        current_age AS employee_age,
        current_tenure AS employee_tenure,
        level_id,
        hash_value_down AS event_probability
    FROM downward_response_candidates
),
{% endif %}

-- Combine upward and downward events
combined_events AS (
    SELECT * FROM upward_events
    -- Only include events where the rate actually changed
    WHERE employee_deferral_rate != prev_employee_deferral_rate

    {% if downward_enabled %}
    UNION ALL

    SELECT * FROM downward_events
    WHERE employee_deferral_rate != prev_employee_deferral_rate
    {% endif %}
)

-- Final output matching fct_yearly_events schema
SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    'Match response: ' || ROUND(prev_employee_deferral_rate * 100, 1) || '% → '
        || ROUND(employee_deferral_rate * 100, 1) || '% ('
        || response_direction || ', target ' || ROUND(match_max_rate * 100, 1) || '%)'
        AS event_details,
    compensation_amount,
    previous_compensation,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    (employee_deferral_rate - prev_employee_deferral_rate)::DECIMAL(5,4) AS escalation_rate,
    employee_age,
    employee_tenure,
    level_id,
    -- Age and tenure bands for analysis
    CASE
        WHEN employee_age < 25 THEN '< 25'
        WHEN employee_age < 35 THEN '25-34'
        WHEN employee_age < 45 THEN '35-44'
        WHEN employee_age < 55 THEN '45-54'
        WHEN employee_age < 65 THEN '55-64'
        ELSE '65+'
    END AS age_band,
    CASE
        WHEN employee_tenure < 2 THEN '< 2'
        WHEN employee_tenure < 5 THEN '2-4'
        WHEN employee_tenure < 10 THEN '5-9'
        WHEN employee_tenure < 20 THEN '10-19'
        ELSE '20+'
    END AS tenure_band,
    event_probability,
    'match_response'::VARCHAR AS event_category
FROM combined_events

{% else %}
-- Feature disabled or not first year: return empty result set with correct schema
SELECT
    CAST(NULL AS VARCHAR)           AS employee_id,
    CAST(NULL AS VARCHAR)           AS employee_ssn,
    CAST('deferral_match_response' AS VARCHAR) AS event_type,
    CAST(NULL AS INTEGER)           AS simulation_year,
    CAST(NULL AS DATE)              AS effective_date,
    CAST(NULL AS VARCHAR)           AS event_details,
    CAST(NULL AS DECIMAL(15,2))     AS compensation_amount,
    CAST(NULL AS DECIMAL(15,2))     AS previous_compensation,
    CAST(NULL AS DECIMAL(5,4))      AS employee_deferral_rate,
    CAST(NULL AS DECIMAL(5,4))      AS prev_employee_deferral_rate,
    CAST(NULL AS DECIMAL(5,4))      AS escalation_rate,
    CAST(NULL AS SMALLINT)          AS employee_age,
    CAST(NULL AS DECIMAL(10,2))     AS employee_tenure,
    CAST(NULL AS SMALLINT)          AS level_id,
    CAST(NULL AS VARCHAR)           AS age_band,
    CAST(NULL AS VARCHAR)           AS tenure_band,
    CAST(NULL AS DECIMAL(5,4))      AS event_probability,
    'match_response'::VARCHAR       AS event_category
WHERE FALSE
{% endif %}
