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
{% if var('deferral_rate_changes_enabled', false) %}CAST({% endif %}
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
{% if var('deferral_rate_changes_enabled', false) %}AS DECIMAL(5,4)){% endif %}
{%- endmacro %}

{% macro deferral_change_category(draw, increase_probability, decrease_probability, has_escalation='FALSE') -%}
CASE
  WHEN {{ draw }} < {{ increase_probability }} THEN 'proactive_increase'
  WHEN {{ draw }} < {{ increase_probability }} + {{ decrease_probability }}
    THEN CASE WHEN {{ has_escalation }} THEN 'aip_response_decrease'
      ELSE 'proactive_decrease' END
  ELSE NULL
END
{%- endmacro %}

{% macro deferral_change_step(draw, direction) -%}
  {%- set defaults = [{'pp': 1, 'weight': 0.15}, {'pp': 2, 'weight': 0.20},
    {'pp': 3, 'weight': 0.15}, {'pp': 5, 'weight': 0.20},
    {'pp': 7, 'weight': 0.15}, {'pp': 10, 'weight': 0.15}]
    if direction == 'increase' else [
    {'pp': 1, 'weight': 0.15}, {'pp': 2, 'weight': 0.25},
    {'pp': 3, 'weight': 0.20}, {'pp': 5, 'weight': 0.20}, {'pp': 8, 'weight': 0.20}] -%}
  {%- set steps = var('deferral_rate_changes_' ~ direction ~ '_steps', defaults) -%}
  {%- set ns = namespace(cumulative=0.0) -%}
CASE
  {%- for step in steps %}
    {%- set ns.cumulative = ns.cumulative + step.weight %}
  WHEN {{ draw }} < {{ ns.cumulative }} THEN {{ step.pp }}
  {%- endfor %}
  ELSE {{ steps[-1].pp }}
END
{%- endmacro %}

{% macro deferral_change_cap(compensation, age, irs_alias='il') -%}
LEAST({{ plan_deferral_cap() }}, {{ var('voluntary_max_deferral_rate', 0.15) }},
  CASE WHEN {{ compensation }} > 0
    THEN FLOOR({{ irs_402g_limit_for_age(age, irs_alias) }}::DECIMAL
      / {{ compensation }} * 10000) / 10000
    ELSE {{ var('voluntary_max_deferral_rate', 0.15) }} END)
{%- endmacro %}

{% macro deferral_change_rate(previous_rate, category, step_pp, cap) -%}
CAST(CASE WHEN {{ category }} = 'proactive_increase'
  THEN GREATEST({{ previous_rate }}, LEAST({{ cap }}, {{ previous_rate }} + {{ step_pp }} / 100.0))
  ELSE LEAST({{ previous_rate }}, GREATEST(0.01, {{ previous_rate }} - {{ step_pp }} / 100.0))
END AS DECIMAL(5,4))
{%- endmacro %}

{% macro deferral_change_date(window_start, window_end, draw) -%}
CASE WHEN {{ window_start }} <= {{ window_end }}
  THEN CAST({{ window_start }} AS DATE) + CAST(FLOOR({{ draw }}
    * (DATEDIFF('day', {{ window_start }}, {{ window_end }}) + 1)) AS INTEGER)
  ELSE NULL::DATE
END
{%- endmacro %}
