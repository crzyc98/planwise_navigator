{%- macro legacy_timing_calculation(employee_id_column, simulation_year) -%}
  -- Legacy 50/50 split for backward compatibility (matches current int_merit_events.sql logic)
  CASE
    WHEN (LENGTH({{ employee_id_column }}) % 2) = 0
    THEN CAST({{ simulation_year }} || '-01-01' AS DATE)
    ELSE CAST({{ simulation_year }} || '-07-01' AS DATE)
  END
{%- endmacro -%}
