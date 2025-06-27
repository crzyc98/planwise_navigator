{%- macro realistic_timing_calculation(employee_id_column, simulation_year) -%}
(
  WITH month_selection AS (
    SELECT
      {{ employee_id_column }} as emp_id,
      ABS(HASH({{ employee_id_column }} || '_' || {{ simulation_year }} || '_month')) % 10000 / 10000.0 as month_selector
  ),
  cumulative_distribution AS (
    SELECT
      month,
      percentage,
      SUM(percentage) OVER (ORDER BY month) as cumulative_percent
    FROM {{ ref('config_raise_timing_distribution') }}
    WHERE industry_profile = '{{ var("raise_timing_profile", "general_corporate") }}'
  ),
  selected_months AS (
    SELECT
      ms.emp_id,
      -- Use cumulative lookup to select month based on hash value
      (SELECT MIN(cd.month)
       FROM cumulative_distribution cd
       WHERE ms.month_selector <= cd.cumulative_percent) as selected_month
    FROM month_selection ms
  ),
  day_selection AS (
    SELECT
      sm.emp_id,
      sm.selected_month,
      -- Generate day within selected month using separate hash
      (ABS(HASH(sm.emp_id || '_' || {{ simulation_year }} || '_day_' || sm.selected_month)) %
       -- Get number of days in the selected month
       EXTRACT(DAY FROM (
         DATE_TRUNC('month', CAST({{ simulation_year }} || '-' || LPAD(sm.selected_month::VARCHAR, 2, '0') || '-01' AS DATE)) +
         INTERVAL 1 MONTH - INTERVAL 1 DAY
       ))) + 1 as selected_day
    FROM selected_months sm
  )
  SELECT
    CAST({{ simulation_year }} || '-' ||
         LPAD(ds.selected_month::VARCHAR, 2, '0') || '-' ||
         LPAD(ds.selected_day::VARCHAR, 2, '0') AS DATE)
  FROM day_selection ds
  WHERE ds.emp_id = {{ employee_id_column }}
  LIMIT 1
)
{%- endmacro -%}
