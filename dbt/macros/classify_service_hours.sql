{% macro classify_service_hours(hours_column, threshold=1000) %}
CASE
    WHEN {{ hours_column }} >= {{ threshold }} THEN 'year_of_service'
    ELSE 'no_credit'
END
{% endmacro %}
