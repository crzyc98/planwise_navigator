{#
    assign_tenure_band - Generate CASE expression for tenure band assignment

    Usage:
        {{ assign_tenure_band('current_tenure') }} AS tenure_band

    The macro reads band definitions from config_tenure_bands seed and generates
    a CASE expression using [min, max) interval convention:
    - Lower bound is INCLUSIVE
    - Upper bound is EXCLUSIVE
    - Example: tenure of exactly 2 years falls into "2-4" band (not "< 2")

    Note: New hires always have tenure < 2, so they fall into the first band.

    Returns: SQL CASE expression that evaluates to band_label
#}

{% macro assign_tenure_band(column_name) %}
    {%- set band_query -%}
        SELECT band_label, min_value, max_value
        FROM {{ ref('config_tenure_bands') }}
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
        WHEN {{ column_name }} < 2 THEN '< 2'
        WHEN {{ column_name }} < 5 THEN '2-4'
        WHEN {{ column_name }} < 10 THEN '5-9'
        WHEN {{ column_name }} < 20 THEN '10-19'
        ELSE '20+'
    END
    {%- endif -%}
{% endmacro %}
