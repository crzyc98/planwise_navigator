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
    CASE
        WHEN {{ column_name }} < 25 THEN '< 25'
        WHEN {{ column_name }} < 35 THEN '25-34'
        WHEN {{ column_name }} < 45 THEN '35-44'
        WHEN {{ column_name }} < 55 THEN '45-54'
        WHEN {{ column_name }} < 65 THEN '55-64'
        ELSE '65+'
    END
{% endmacro %}
