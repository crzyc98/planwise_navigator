{#
    assign_age_band - Generate CASE expression for age band assignment

    Usage:
        {{ assign_age_band('current_age') }} AS age_band

    The macro reads band definitions from config_age_bands seed and generates
    a CASE expression using [min, max) interval convention:
    - Lower bound is INCLUSIVE
    - Upper bound is EXCLUSIVE
    - Example: age 35 falls into "35-44" band (not "25-34")

    Returns: SQL CASE expression that evaluates to band_label
#}

{% macro assign_age_band(column_name) %}
    {%- set band_query -%}
        SELECT band_label, min_value, max_value
        FROM {{ ref('config_age_bands') }}
        ORDER BY min_value
    {%- endset -%}

    {%- set bands = run_query(band_query) -%}

    {%- if bands and bands.rows | length > 0 -%}
    CASE
        {%- for row in bands.rows %}
        {%- if row['max_value'] | int >= 999 %}
        WHEN {{ column_name }} >= {{ row['min_value'] }} THEN '{{ row['band_label'] }}'
        {%- else %}
        WHEN {{ column_name }} >= {{ row['min_value'] }} AND {{ column_name }} < {{ row['max_value'] }} THEN '{{ row['band_label'] }}'
        {%- endif %}
        {%- endfor %}
        ELSE 'Unknown'
    END
    {%- else -%}
    {# Fallback if seed table is not yet loaded #}
    CASE
        WHEN {{ column_name }} < 25 THEN '< 25'
        WHEN {{ column_name }} < 35 THEN '25-34'
        WHEN {{ column_name }} < 45 THEN '35-44'
        WHEN {{ column_name }} < 55 THEN '45-54'
        WHEN {{ column_name }} < 65 THEN '55-64'
        ELSE '65+'
    END
    {%- endif -%}
{% endmacro %}
