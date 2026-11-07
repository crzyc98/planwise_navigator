{#- Level for a pay amount on the shared scale. Each level starts at its minimum,
    so there are no gaps, and pay below level 1 or above the top still gets a level. -#}
{% macro pay_scale_level(pay) -%}
  CASE
    {%- for item in var('job_level_compensation') | sort(attribute='level', reverse=true) %}
    {%- if not loop.last %}
    WHEN {{ pay }} >= {{ item.min_compensation }} THEN {{ item.level }}
    {%- else %}
    ELSE {{ item.level }}
    {%- endif %}
    {%- endfor %}
  END
{%- endmacro %}
