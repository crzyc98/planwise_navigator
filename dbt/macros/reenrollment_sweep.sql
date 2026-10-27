{# Keep candidacy's cutoff identical to the emitted sweep election date. #}
{% macro reenrollment_sweep_date(aw) -%}
CASE WHEN EXTRACT(YEAR FROM {{ aw }}.employee_hire_date) < {{ aw }}.simulation_year
  THEN CAST(GREATEST(MAKE_DATE({{ aw }}.simulation_year, 1, 15), {{ aw }}.plan_eligibility_date) AS TIMESTAMP)
  ELSE CAST({{ aw }}.plan_eligibility_date + {{ aw }}.auto_enrollment_window_days * INTERVAL '1 day' AS TIMESTAMP)
END
{%- endmacro %}

{# Shared schedule for candidate selection and the post-opt-out invariant. #}
{% macro is_reenrollment_sweep_year(year, enabled, interval, first_year) %}
  ({{ enabled }}
    AND {{ year }} >= COALESCE({{ first_year }}, {{ var('start_year', 2025) }} + {{ interval }})
    AND ({{ year }} - COALESCE({{ first_year }}, {{ var('start_year', 2025) }} + {{ interval }})) % {{ interval }} = 0)
{% endmacro %}

{% macro is_reenrollment_sweep_candidate(aw, pe) %}
  ({{ var('auto_enrollment_enabled', true) }}
    AND {{ is_reenrollment_sweep_year(aw ~ '.simulation_year', aw ~ '.reenrollment_sweep_enabled', aw ~ '.reenrollment_sweep_interval_years', aw ~ '.reenrollment_sweep_first_year') }}
    AND {{ aw }}.employment_status = 'active'
    AND NOT {{ aw }}.is_plan_ineligible_override
    AND {{ aw }}.is_plan_eligible
    AND {{ aw }}.plan_eligibility_date <= MAKE_DATE({{ aw }}.simulation_year, 12, 31)
    AND {{ aw }}.reenrollment_sweep_include_non_contributors
    AND COALESCE({{ pe }}.sweep_deferral_rate, 0) = 0
    AND ({{ pe }}.latest_opt_out_date IS NULL
      OR {{ pe }}.latest_opt_out_date < ({{ reenrollment_sweep_date(aw) }})))
{% endmacro %}

{% macro is_ordinary_auto_enrollment_candidate(aw, pe) %}
  ({{ aw }}.employment_status = 'active'
    AND NOT COALESCE({{ pe }}.was_enrolled_previously, false)
    AND NOT COALESCE({{ pe }}.ever_opted_out, false)
    AND NOT {{ aw }}.is_plan_ineligible_override
    AND {{ aw }}.is_plan_eligible
    AND {{ is_eligible_for_auto_enrollment_scope(aw ~ '.employee_hire_date', aw ~ '.simulation_year', aw ~ '.auto_enrollment_scope') }})
{% endmacro %}

{% macro reenrollment_contributor_group(aw, rate) -%}
({{ rate }} > 0 AND (
  ({{ aw }}.reenrollment_sweep_include_below_default
    AND {{ rate }} < {{ aw }}.auto_enrollment_default_deferral_rate)
  OR ({{ aw }}.reenrollment_sweep_include_below_aip_cap
    AND {{ rate }} < {{ aw }}.deferral_escalation_cap)))
{%- endmacro %}

{% macro reenrollment_contributor_rate(aw, rate) -%}
CASE WHEN {{ aw }}.reenrollment_sweep_method = 'into_aip' THEN {{ rate }}
  ELSE GREATEST({{ rate }}, {{ aw }}.auto_enrollment_default_deferral_rate) END
{%- endmacro %}

{# Accepted sweeps elect membership; a later voluntary exit still takes priority.
   Membership is carried in state, so historical elections cannot undo an exit. #}
{% macro reenrollment_aip_member(events, employee, year, scenario, historical=false) -%}
EXISTS (
  SELECT 1 FROM {{ events }} sweep
  WHERE sweep.employee_id = {{ employee }} AND sweep.scenario_id = {{ scenario }}
    AND sweep.simulation_year {{ '<=' if historical else '=' }} {{ year }}
    AND ((sweep.event_category = 'reenrollment_sweep'
      AND {{ var('deferral_escalation_enabled', true) }})
      OR sweep.event_details LIKE 'Re-enrollment sweep - %method=into_aip%')
)
{%- endmacro %}

{# Temporal source: prior accepted sweeps lift the ordinary hire cutoff. #}
{% macro prior_reenrollment_aip_member(employee) -%}
{% if var('simulation_year') | int > var('start_year', 2025) | int %}
{{ reenrollment_aip_member(target.schema ~ '.fct_yearly_events', employee,
  var('simulation_year') | int - 1, "'" ~ var('scenario_id', 'default') ~ "'", historical=true) }}
{% else %}FALSE{% endif %}
{%- endmacro %}
