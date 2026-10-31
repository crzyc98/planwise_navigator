{% macro distributed_hire_date(sequence_column, simulation_year) %}
  {# Midpoints of equal calendar-year intervals, shuffled independently of level.
     Call over exactly one year's hire cohort, with one row per sequence number. #}
  CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL (
    FLOOR(
      (ROW_NUMBER() OVER (
        ORDER BY PLANALIGN_HASH(CONCAT(
          CAST({{ sequence_column }} AS VARCHAR), '_hiredate_',
          CAST({{ simulation_year }} AS VARCHAR), '_seed_', '{{ subsystem_seed('hiring') }}'
        )), {{ sequence_column }}
      ) - 0.5)
      * DATEDIFF('day', MAKE_DATE({{ simulation_year }}, 1, 1), MAKE_DATE({{ simulation_year }} + 1, 1, 1))
      / COUNT(*) OVER ()
    )
  ) DAY
{% endmacro %}
