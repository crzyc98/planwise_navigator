{% macro classify_service_hours(hours_column) %}
CASE
    WHEN {{ hours_column }} >= 1000 THEN 'year_of_service'
    ELSE 'no_credit'
END
{% endmacro %}
