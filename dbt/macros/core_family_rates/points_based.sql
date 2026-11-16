{# #1222: an optional flat pre-service rate applies until the service minimum. #}
{% macro core_family_rate_points_based() -%}
CASE
  WHEN COALESCE(snap.years_of_service, FLOOR(COALESCE(pop.current_tenure, 0))::INT)
    < pdp.core_points_min_service_years
    THEN pdp.core_points_pre_service_rate
  ELSE core_points.rate
END
{%- endmacro %}
