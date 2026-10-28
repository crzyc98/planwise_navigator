{# A sweep election replaces rate decisions on or before its effective date. #}
{% macro rate_event_survives_sweep(sweep_flag, enrollment_date, event_date) -%}
(NOT COALESCE({{ sweep_flag }}, false) OR {{ event_date }} > {{ enrollment_date }})
{%- endmacro %}

{# Preserve the accumulator's legacy enrollment payload fallback exactly. #}
{% macro enrollment_payload_deferral_rate() -%}
COALESCE(
            employee_deferral_rate,
            CASE
                WHEN REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) IS NOT NULL
                     AND REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) != ''
                THEN CAST(REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) AS DECIMAL(6,4)) / 100.0
                ELSE 0.06
            END
        )
{%- endmacro %}

{# Canonical pre-voluntary rate precedence, shared with the state accumulator.
   Keep the legacy expression (including its types) unchanged when disabled. #}
{% macro rate_before_voluntary_change(opt_out, enrolled, fallback, escalation,
    match_rate, increment, escalation_cap, compensation, age, irs_alias='il') -%}
{# Event payloads are DECIMAL(5,4). Canonicalize only in enabled runs so that
   inherited DOUBLE rates (e.g. 0.06 + 0.01) compare exactly with their payload. #}
{% if var('deferral_rate_changes_enabled', true) %}CAST({% endif %}
CASE
  WHEN {{ opt_out }} THEN 0.00::DECIMAL(5,4)
  WHEN NOT ({{ enrolled }}) THEN 0.00::DECIMAL(5,4)
  WHEN {{ match_rate }} IS NOT NULL AND {{ escalation }} IS NOT NULL
    AND COALESCE({{ compensation }}, 0) > 0
  THEN LEAST(
    {{ match_rate }} + {{ increment }},
    GREATEST({{ match_rate }},
      COALESCE({{ escalation_cap }}, {{ var('deferral_escalation_cap', 0.10) }})),
    FLOOR({{ irs_402g_limit_for_age(age, irs_alias) }}::DECIMAL
      / {{ compensation }} * 10000) / 10000
  )::DECIMAL(5,4)
  ELSE COALESCE({{ escalation }}, {{ match_rate }}, {{ fallback }})
END
{% if var('deferral_rate_changes_enabled', true) %}AS DECIMAL(5,4)){% endif %}
{%- endmacro %}

{# A zero rate alone is not stop provenance. A later opt-out cancels that stop. #}
{% macro has_unreversed_stop(events, employee, scenario, before_year) -%}
EXISTS (
  SELECT 1 FROM {{ events }} stopped
  WHERE stopped.employee_id = {{ employee }} AND stopped.scenario_id = {{ scenario }}
    AND stopped.simulation_year < {{ before_year }}
    AND stopped.event_type = 'deferral_change' AND stopped.event_category = 'stop'
    AND NOT EXISTS (
      SELECT 1 FROM {{ events }} opted_out
      WHERE opted_out.employee_id = stopped.employee_id
        AND opted_out.scenario_id = stopped.scenario_id
        AND opted_out.simulation_year < {{ before_year }}
        AND opted_out.event_type = 'enrollment_change'
        AND COALESCE(opted_out.employee_deferral_rate, 0) = 0
        AND opted_out.effective_date >= stopped.effective_date
    )
)
{%- endmacro %}

{% macro deferral_change_category(draw, increase_probability, decrease_probability, has_escalation='FALSE', stop_probability='0') -%}
CASE
  WHEN {{ draw }} < {{ increase_probability }} THEN 'proactive_increase'
  WHEN {{ draw }} < {{ increase_probability }} + {{ decrease_probability }}
    THEN CASE WHEN {{ has_escalation }} THEN 'aip_response_decrease'
      ELSE 'proactive_decrease' END
  WHEN {{ draw }} < {{ increase_probability }} + {{ decrease_probability }} + {{ stop_probability }}
    THEN 'stop'
  ELSE NULL
END
{%- endmacro %}

{% macro deferral_change_step(draw, direction) -%}
  {%- set defaults = [
    {'pp': 1, 'weight': 0.1}, {'pp': 2, 'weight': 0.1},
    {'pp': 3, 'weight': 0.15}, {'pp': 5, 'weight': 0.2},
    {'pp': 7, 'weight': 0.2}, {'pp': 10, 'weight': 0.25}]
    if direction == 'increase' else [
    {'share': 0.25, 'weight': 0.2}, {'share': 0.5, 'weight': 0.25},
    {'share': 0.75, 'weight': 0.35}, {'share': 0.9, 'weight': 0.2}] -%}
  {%- set field = 'pp' if direction == 'increase' else 'share' -%}
  {%- set suffix = '_steps' if direction == 'increase' else '_shares' -%}
  {%- set steps = var('deferral_rate_changes_' ~ direction ~ suffix, defaults) -%}
  {%- set ns = namespace(cumulative=0.0) -%}
CASE
  {%- for step in steps %}
    {%- set ns.cumulative = ns.cumulative + step.weight %}
  WHEN {{ draw }} < {{ ns.cumulative }} THEN {{ step[field] }}
  {%- endfor %}
  ELSE {{ steps[-1][field] }}
END
{%- endmacro %}

{% macro deferral_change_cap(compensation, age, irs_alias='il') -%}
LEAST({{ plan_deferral_cap() }}, {{ var('voluntary_max_deferral_rate', 0.15) }},
  CASE WHEN {{ compensation }} > 0
    THEN FLOOR({{ irs_402g_limit_for_age(age, irs_alias) }}::DECIMAL
      / {{ compensation }} * 10000) / 10000
    ELSE {{ var('voluntary_max_deferral_rate', 0.15) }} END)
{%- endmacro %}

{% macro deferral_change_rate(previous_rate, category, step_pp, cap, last_nonzero='NULL') -%}
CAST(CASE
  WHEN {{ category }} = 'stop' THEN 0
  WHEN {{ category }} = 'restart' THEN LEAST({{ last_nonzero }}, {{ cap }})
  WHEN {{ category }} = 'proactive_increase'
  THEN GREATEST({{ previous_rate }}, LEAST({{ cap }}, {{ previous_rate }} + {{ step_pp }} / 100.0))
  ELSE GREATEST(0.01, LEAST({{ previous_rate }} - 0.01, ROUND({{ previous_rate }} * (1 - {{ step_pp }}), 2)))
END AS DECIMAL(5,4))
{%- endmacro %}

{% macro deferral_change_date(window_start, window_end, draw) -%}
CASE WHEN {{ window_start }} <= {{ window_end }}
  THEN CAST({{ window_start }} AS DATE) + CAST(FLOOR({{ draw }}
    * (DATEDIFF('day', {{ window_start }}, {{ window_end }}) + 1)) AS INTEGER)
  ELSE NULL::DATE
END
{%- endmacro %}

{# Like YoY conversion, multiply independent demographic CASE lookups.
   Lower bounds are inclusive; NULL/negative inputs use the first band. #}
{% macro deferral_change_multiplier(value, bands) -%}
CASE
  {%- for band in bands | reverse %}
  WHEN {{ value }} >= {{ band.min }} THEN {{ band.multiplier }}::DOUBLE
  {%- endfor %}
  ELSE {{ bands[0].multiplier }}::DOUBLE
END
{%- endmacro %}

{% macro deferral_change_probability_product(base, direction, age, income, tenure) -%}
  {%- set defaults = {
    'increase': {
      'age': [
        {'min': 0, 'multiplier': 0.8}, {'min': 30, 'multiplier': 0.95},
        {'min': 40, 'multiplier': 1.05}, {'min': 50, 'multiplier': 1.25},
        {'min': 60, 'multiplier': 1.3}, {'min': 70, 'multiplier': 0.8}],
      'income': [
        {'min': 0, 'multiplier': 0.5}, {'min': 25000, 'multiplier': 0.65},
        {'min': 50000, 'multiplier': 0.75}, {'min': 60000, 'multiplier': 0.9},
        {'min': 75000, 'multiplier': 1.0}, {'min': 100000, 'multiplier': 1.15},
        {'min': 125000, 'multiplier': 1.2}, {'min': 150000, 'multiplier': 1.35},
        {'min': 200000, 'multiplier': 1.3}, {'min': 250000, 'multiplier': 1.2}],
      'tenure': [
        {'min': 0, 'multiplier': 1.05}, {'min': 2, 'multiplier': 0.9},
        {'min': 5, 'multiplier': 0.95}, {'min': 10, 'multiplier': 1.1},
        {'min': 15, 'multiplier': 1.15}, {'min': 20, 'multiplier': 1.2},
        {'min': 25, 'multiplier': 1.25}, {'min': 30, 'multiplier': 1.15}],
    },
    'decrease': {
      'age': [
        {'min': 0, 'multiplier': 0.95}, {'min': 30, 'multiplier': 1.1},
        {'min': 40, 'multiplier': 1.0}, {'min': 50, 'multiplier': 0.85},
        {'min': 60, 'multiplier': 0.75}, {'min': 70, 'multiplier': 0.5}],
      'income': [
        {'min': 0, 'multiplier': 0.5}, {'min': 25000, 'multiplier': 0.65},
        {'min': 40000, 'multiplier': 0.6}, {'min': 50000, 'multiplier': 0.75},
        {'min': 60000, 'multiplier': 0.85}, {'min': 75000, 'multiplier': 0.95},
        {'min': 100000, 'multiplier': 1.05}, {'min': 125000, 'multiplier': 1.25},
        {'min': 150000, 'multiplier': 1.4}, {'min': 200000, 'multiplier': 1.55},
        {'min': 250000, 'multiplier': 1.25}],
      'tenure': [
        {'min': 0, 'multiplier': 0.9}, {'min': 2, 'multiplier': 0.95},
        {'min': 3, 'multiplier': 1.05}, {'min': 4, 'multiplier': 1.1},
        {'min': 5, 'multiplier': 1.05}, {'min': 15, 'multiplier': 1.0},
        {'min': 20, 'multiplier': 0.9}, {'min': 25, 'multiplier': 0.85},
        {'min': 30, 'multiplier': 0.75}],
    },
  } -%}
({{ base }})
{%- for dimension, value in [('age', age), ('income', income), ('tenure', tenure)] %}
  * ({{ deferral_change_multiplier(value,
    var('deferral_rate_changes_multipliers_' ~ direction ~ '_' ~ dimension,
      defaults[direction][dimension])) }})
{%- endfor %}
{%- endmacro %}

{# Stop retains its mass; the two directional probabilities share the remainder. #}
{% macro deferral_change_rescaled_probability(probability, other, stop) -%}
CASE WHEN {{ probability }} + {{ other }} + {{ stop }} > 1.0
  THEN {{ probability }} / ({{ probability }} + {{ other }}) * (1.0 - {{ stop }})
  ELSE {{ probability }} END
{%- endmacro %}

{% macro deferral_change_rate_multiplier(rate) -%}
{{ deferral_change_multiplier(rate, var('deferral_rate_changes_multipliers_decrease_rate', [
  {'min': 0, 'multiplier': 0.5}, {'min': 0.04, 'multiplier': 0.8},
  {'min': 0.07, 'multiplier': 1.0}, {'min': 0.10, 'multiplier': 1.3},
  {'min': 0.15, 'multiplier': 1.6}])) }}
{%- endmacro %}
