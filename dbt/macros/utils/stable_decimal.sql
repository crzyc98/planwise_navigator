{% macro stable_decimal(expression, width, scale) %}
  {# DuckDB 1.1.3 rounds scaled floating inputs to the nearest even integer.
     1.5.5 changed that conversion. Preserve the old rule explicitly, while
     leaving exact DECIMAL/string inputs on their existing cast path. #}
  CAST(
    CASE
      WHEN typeof({{ expression }}) IN ('FLOAT', 'DOUBLE') THEN
        CAST(
          CASE WHEN typeof({{ expression }}) = 'FLOAT' THEN
            round_even(CAST(CAST({{ expression }} AS DOUBLE) * {{ 10 ** scale }} AS FLOAT), 0)
          ELSE
            round_even(CAST({{ expression }} AS DOUBLE) * {{ 10 ** scale }}, 0)
          END AS DECIMAL({{ width }}, 0)
        ) * CAST('0.{{ '0' * (scale - 1) }}1' AS DECIMAL({{ scale + 1 }}, {{ scale }}))
      ELSE CAST({{ expression }} AS DECIMAL({{ width }}, {{ scale }}))
    END AS DECIMAL({{ width }}, {{ scale }})
  )
{% endmacro %}
