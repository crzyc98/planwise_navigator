{# Issue #984: the below-default share is the TOTAL share of self-directed
   enrollees below the AE default, apart from deliberate downward match snaps.
   With AE enabled and a positive resolved share, floor non-choosers at the AE
   default after the demographic grid and spread, before applying the magnet.
   Below-default choosers bypass the magnet. A zero share or disabled AE adds
   no floor. Preserve each channel's magnet draw; callers apply the voluntary
   clamp. YoY opts
   out of the upward magnet, which it never had. All new draws follow the run's
   deferral_behavior seed; channel deduplication cannot change a person's draw. #}

{% macro below_default_share(auto_default, tiers=none) %}
  {%- set tiers = tiers if tiers is not none else var('below_default_share_tiers', [
    {'max_auto_enroll_default_rate': 0.03, 'share': 0.10}, {'max_auto_enroll_default_rate': none, 'share': 0.15}
  ]) -%}
CASE
  {%- for tier in tiers %}
    {%- if tier.max_auto_enroll_default_rate is not none %}
  WHEN {{ auto_default }} <= {{ tier.max_auto_enroll_default_rate }} THEN {{ tier.share }}
    {%- else %}
  WHEN TRUE THEN {{ tier.share }}
    {%- endif %}
  {%- endfor %}
END
{% endmacro %}

{% macro enrollment_behavior_draw(employee_id, simulation_year, salt) -%}
((ABS(PLANALIGN_HASH({{ employee_id }} || '{{ salt }}' ||
  CAST({{ simulation_year }} AS VARCHAR) || '-' ||
  CAST({{ subsystem_seed('deferral_behavior') }} AS VARCHAR))) % 1000000) / 1000000.0)
{%- endmacro %}

{% macro below_default_rate(auto_default, step_random, steps=none) %}
  {%- set steps = steps if steps is not none else var('below_default_steps', [
    {'pp': 1, 'weight': 0.50}, {'pp': 2, 'weight': 0.30}, {'pp': 3, 'weight': 0.20}
  ]) -%}
  {%- set ns = namespace(cumulative=0.0) -%}
GREATEST(0.01, {{ auto_default }} - 0.01 * CASE
  {%- for step in steps %}
    {%- set ns.cumulative = ns.cumulative + step.weight %}
  WHEN {{ step_random }} < {{ ns.cumulative }} THEN {{ step.pp }}
  {%- endfor %}
  ELSE {{ steps[-1].pp }}
END)
{% endmacro %}

{% macro below_default_effective_share(auto_default, age, income, tiers=none) -%}
  {%- set defaults = {
    'age': [{'min': 0, 'multiplier': 1.4}, {'min': 30, 'multiplier': 1.1}, {'min': 40, 'multiplier': 0.9}, {'min': 50, 'multiplier': 0.75}, {'min': 60, 'multiplier': 0.65}],
    'income': [{'min': 0, 'multiplier': 1.6}, {'min': 40000, 'multiplier': 1.2}, {'min': 60000, 'multiplier': 1.0}, {'min': 100000, 'multiplier': 0.7}, {'min': 150000, 'multiplier': 0.5}]
  } -%}
LEAST(1.0, ({{ below_default_share(auto_default, tiers) }})
{%- for dimension, value in [('age', age), ('income', income)] %}
  * ({{ deferral_change_multiplier(value,
    var('below_default_multipliers_' ~ dimension, defaults[dimension])) }})
{%- endfor %}
)
{%- endmacro %}

{% macro self_directed_enrollment_rate(selected_rate, ceiling, magnet_random,
                                      employee_id, simulation_year, upward_enabled=true,
                                      auto_default=none, age='NULL', income='NULL') %}
  {%- set ae_enabled = var('auto_enrollment_enabled', true) -%}
  {%- set auto_default = auto_default if auto_default is not none else var('auto_enrollment_default_deferral_rate', 0.02) -%}
  {%- set tiers = var('below_default_share_tiers', [{'max_auto_enroll_default_rate': 0.03, 'share': 0.10}, {'max_auto_enroll_default_rate': none, 'share': 0.15}]) -%}
  {%- set active = ae_enabled and tiers | selectattr('share', 'gt', 0) | list | length > 0 -%}
  {%- set share = '(' ~ below_default_share(auto_default, tiers) ~ ')' -%}
  {%- set downward = ae_enabled and var('enrollment_match_magnet_downward_enabled', true) -%}
  {%- set magnet_rate = '(CASE WHEN ' ~ share ~ ' > 0 THEN GREATEST(' ~ auto_default ~ ', ' ~ selected_rate ~ ') ELSE ' ~ selected_rate ~ ' END)' if active else selected_rate -%}
  {%- if active %}
CASE
  WHEN {{ enrollment_behavior_draw(employee_id, simulation_year, '-below-default-') }} < {{ below_default_effective_share(auto_default, age, income, tiers) }}
  THEN {{ below_default_rate(auto_default,
    enrollment_behavior_draw(employee_id, simulation_year, '-below-default-step-')) }}
  ELSE
  {%- endif %}
  {%- if upward_enabled or downward %}
  {{ match_magnet_snap(magnet_rate, ceiling, magnet_random,
    var('enrollment_match_magnet_enabled', true), var('enrollment_match_magnet_probability', 0.45),
    downward_enabled=downward, auto_default=auto_default, upward_enabled=upward_enabled) }}
  {%- else %}
  {{ magnet_rate }}
  {%- endif %}
  {%- if active %}
END
  {%- endif %}
{% endmacro %}
