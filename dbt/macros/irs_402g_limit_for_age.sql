{% macro irs_402g_limit_for_age(age_expression, limits_alias) -%}
  CASE
    WHEN {{ age_expression }} BETWEEN {{ limits_alias }}.super_catch_up_age_min
      AND {{ limits_alias }}.super_catch_up_age_max
      THEN {{ limits_alias }}.super_catch_up_limit
    WHEN {{ age_expression }} >= {{ limits_alias }}.catch_up_age_threshold
      THEN {{ limits_alias }}.catch_up_limit
    ELSE {{ limits_alias }}.base_limit
  END
{%- endmacro %}
