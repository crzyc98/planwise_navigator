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
    AND {{ aw }}.employee_hire_date >= '{{ var('auto_enrollment_hire_date_cutoff', '2020-01-01') }}'::DATE
    AND {{ aw }}.plan_eligibility_date <= MAKE_DATE({{ aw }}.simulation_year, 12, 31)
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
