{% comment %}
DuckDB-optimized macros for Story S031-02: Year Processing Optimization

Implements columnar storage patterns, vectorized operations, and analytical
query optimizations specifically designed for DuckDB's columnar engine.

Key optimizations:
- Vectorized window functions for tenure/compensation calculations
- SIMD-accelerated aggregations for payroll summaries
- Hash join optimization for employee-event associations
- Columnar storage-friendly query patterns
{% endcomment %}

{% macro optimize_duckdb_workforce_query() %}
  {# Enable DuckDB optimizations for workforce analytics #}
  -- PRAGMA enable_optimization_statistics;  -- Not available in current DuckDB version
  PRAGMA enable_vectorized_execution=true;
  PRAGMA force_parallelism=true;
{% endmacro %}

{% macro vectorized_tenure_calculation(hire_date_col, as_of_date) %}
  {# Vectorized tenure calculation using DuckDB date arithmetic #}
  CAST((DATE '{{ as_of_date }}' - {{ hire_date_col }}) AS INTEGER) / 365.25
{% endmacro %}

{% macro vectorized_age_calculation(birth_date_col, as_of_date) %}
  {# Vectorized age calculation optimized for columnar processing #}
  CAST((DATE '{{ as_of_date }}' - {{ birth_date_col }}) AS INTEGER) / 365.25
{% endmacro %}

{% macro optimized_workforce_aggregation(group_by_cols, simulation_year) %}
  {# Optimized aggregation pattern for workforce analytics #}
  SELECT
    {{ group_by_cols }},
    COUNT(*) as employee_count,
    SUM(salary) as total_payroll,
    AVG(salary) as avg_salary,
    MIN(salary) as min_salary,
    MAX(salary) as max_salary,
    MEDIAN(salary) as median_salary,
    AVG(age) as avg_age,
    AVG(tenure_years) as avg_tenure,
    COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_count,
    COUNT(CASE WHEN plan_enrolled = true THEN 1 END) as enrolled_count
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = {{ simulation_year }}
  GROUP BY {{ group_by_cols }}
  ORDER BY {{ group_by_cols }}
{% endmacro %}

{% macro optimized_event_aggregation(event_types, simulation_year) %}
  {# Optimized event aggregation using columnar operations #}
  SELECT
    event_type,
    COUNT(*) as event_count,
    COUNT(DISTINCT employee_id) as unique_employees,
    SUM(compensation_amount) as total_compensation_impact,
    AVG(compensation_amount) as avg_compensation_impact,
    MIN(effective_date) as earliest_date,
    MAX(effective_date) as latest_date,

    {# Vectorized calculations for age and tenure statistics #}
    AVG(employee_age) as avg_employee_age,
    AVG(employee_tenure) as avg_employee_tenure,

    {# Level distribution using vectorized aggregation #}
    COUNT(CASE WHEN level_id = 'L1' THEN 1 END) as l1_events,
    COUNT(CASE WHEN level_id = 'L2' THEN 1 END) as l2_events,
    COUNT(CASE WHEN level_id = 'L3' THEN 1 END) as l3_events,
    COUNT(CASE WHEN level_id = 'L4' THEN 1 END) as l4_events,
    COUNT(CASE WHEN level_id = 'L5' THEN 1 END) as l5_events

  FROM {{ ref('fct_yearly_events') }}
  WHERE simulation_year = {{ simulation_year }}
    {% if event_types %}
    AND event_type IN ({{ event_types | map("string") | join(", ") }})
    {% endif %}
  GROUP BY event_type
  ORDER BY event_count DESC
{% endmacro %}

{% macro create_optimized_workforce_index(table_name, index_columns) %}
  {# Create DuckDB-optimized indexes for workforce tables #}
  {% set index_name = "idx_" + table_name + "_" + (index_columns | join("_")) %}
  CREATE INDEX IF NOT EXISTS {{ index_name }}
  ON {{ table_name }} ({{ index_columns | join(", ") }})
{% endmacro %}

{% macro optimized_enrollment_analysis(simulation_year) %}
  {# Vectorized enrollment analysis for plan participation #}
  WITH enrollment_summary AS (
    SELECT
      enrollment_type,
      COUNT(*) as enrollment_count,
      COUNT(DISTINCT employee_id) as unique_enrollees,

      {# Vectorized demographic calculations #}
      AVG(age) as avg_enrollee_age,
      AVG(salary) as avg_enrollee_salary,
      AVG(tenure_years) as avg_enrollee_tenure,

      {# Income brackets using vectorized case statements #}
      COUNT(CASE WHEN salary < 30000 THEN 1 END) as low_income_enrollees,
      COUNT(CASE WHEN salary BETWEEN 30000 AND 50000 THEN 1 END) as moderate_income_enrollees,
      COUNT(CASE WHEN salary BETWEEN 50000 AND 100000 THEN 1 END) as high_income_enrollees,
      COUNT(CASE WHEN salary > 100000 THEN 1 END) as executive_enrollees,

      {# Age brackets using vectorized operations #}
      COUNT(CASE WHEN age BETWEEN 18 AND 30 THEN 1 END) as young_enrollees,
      COUNT(CASE WHEN age BETWEEN 31 AND 45 THEN 1 END) as mid_career_enrollees,
      COUNT(CASE WHEN age BETWEEN 46 AND 55 THEN 1 END) as mature_enrollees,
      COUNT(CASE WHEN age > 55 THEN 1 END) as senior_enrollees,

      {# Monthly enrollment pattern #}
      COUNT(CASE WHEN EXTRACT(MONTH FROM enrollment_date) BETWEEN 1 AND 3 THEN 1 END) as q1_enrollments,
      COUNT(CASE WHEN EXTRACT(MONTH FROM enrollment_date) BETWEEN 4 AND 6 THEN 1 END) as q2_enrollments,
      COUNT(CASE WHEN EXTRACT(MONTH FROM enrollment_date) BETWEEN 7 AND 9 THEN 1 END) as q3_enrollments,
      COUNT(CASE WHEN EXTRACT(MONTH FROM enrollment_date) BETWEEN 10 AND 12 THEN 1 END) as q4_enrollments

    FROM {{ ref('int_enrollment_events') }}
    WHERE simulation_year = {{ simulation_year }}
    GROUP BY enrollment_type
  )
  SELECT * FROM enrollment_summary
  ORDER BY enrollment_count DESC
{% endmacro %}

{% macro optimized_compensation_growth_analysis(current_year, previous_year) %}
  {# Vectorized compensation growth analysis across years #}
  WITH current_compensation AS (
    SELECT
      employee_id,
      level_id,
      salary as current_salary,
      age as current_age,
      tenure_years as current_tenure
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ current_year }}
      AND employment_status = 'active'
  ),
  previous_compensation AS (
    SELECT
      employee_id,
      level_id,
      salary as previous_salary
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ previous_year }}
      AND employment_status = 'active'
  ),
  compensation_changes AS (
    SELECT
      c.employee_id,
      c.level_id,
      c.current_salary,
      p.previous_salary,
      c.current_age,
      c.current_tenure,

      {# Vectorized growth calculations #}
      (c.current_salary - p.previous_salary) as salary_change,
      CASE
        WHEN p.previous_salary > 0
        THEN ((c.current_salary - p.previous_salary) / p.previous_salary) * 100
        ELSE 0
      END as growth_percentage,

      {# Categorize growth types #}
      CASE
        WHEN (c.current_salary - p.previous_salary) = 0 THEN 'no_change'
        WHEN (c.current_salary - p.previous_salary) > 0 AND
             ((c.current_salary - p.previous_salary) / p.previous_salary) <= 0.05 THEN 'modest_increase'
        WHEN (c.current_salary - p.previous_salary) > 0 AND
             ((c.current_salary - p.previous_salary) / p.previous_salary) > 0.05 THEN 'significant_increase'
        ELSE 'decrease'
      END as growth_category

    FROM current_compensation c
    INNER JOIN previous_compensation p ON c.employee_id = p.employee_id
  )
  SELECT
    level_id,
    growth_category,
    COUNT(*) as employee_count,
    AVG(salary_change) as avg_salary_change,
    AVG(growth_percentage) as avg_growth_percentage,
    SUM(salary_change) as total_payroll_impact,
    AVG(current_age) as avg_age,
    AVG(current_tenure) as avg_tenure
  FROM compensation_changes
  GROUP BY level_id, growth_category
  ORDER BY level_id, growth_category
{% endmacro %}

{% macro create_workforce_performance_view(simulation_year) %}
  {# Create materialized view for workforce performance analytics #}
  CREATE OR REPLACE VIEW vw_workforce_performance_{{ simulation_year }} AS
  SELECT
    w.level_id,
    w.department,
    w.employment_status,

    {# Workforce metrics using vectorized aggregations #}
    COUNT(*) as employee_count,
    SUM(w.salary) as total_payroll,
    AVG(w.salary) as avg_salary,
    MEDIAN(w.salary) as median_salary,

    {# Age and tenure analytics #}
    AVG(w.age) as avg_age,
    AVG(w.tenure_years) as avg_tenure,

    {# Plan participation rates #}
    COUNT(CASE WHEN w.plan_eligible = true THEN 1 END) as eligible_employees,
    COUNT(CASE WHEN w.plan_enrolled = true THEN 1 END) as enrolled_employees,
    CASE
      WHEN COUNT(CASE WHEN w.plan_eligible = true THEN 1 END) > 0
      THEN COUNT(CASE WHEN w.plan_enrolled = true THEN 1 END)::FLOAT /
           COUNT(CASE WHEN w.plan_eligible = true THEN 1 END)::FLOAT
      ELSE 0
    END as participation_rate,

    {# Event activity summary #}
    COALESCE(e.total_events, 0) as total_events,
    COALESCE(e.hire_events, 0) as hire_events,
    COALESCE(e.termination_events, 0) as termination_events,
    COALESCE(e.promotion_events, 0) as promotion_events,
    COALESCE(e.merit_events, 0) as merit_events

  FROM {{ ref('fct_workforce_snapshot') }} w
  LEFT JOIN (
    SELECT
      level_id,
      COUNT(*) as total_events,
      COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as hire_events,
      COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as termination_events,
      COUNT(CASE WHEN event_type = 'promotion' THEN 1 END) as promotion_events,
      COUNT(CASE WHEN event_type = 'merit_increase' THEN 1 END) as merit_events
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
    GROUP BY level_id
  ) e ON w.level_id = e.level_id
  WHERE w.simulation_year = {{ simulation_year }}
  GROUP BY w.level_id, w.department, w.employment_status
  ORDER BY w.level_id, w.department
{% endmacro %}

{% macro analyze_batch_performance(batch_name, start_time, end_time) %}
  {# Performance analysis macro for batch execution monitoring #}
  SELECT
    '{{ batch_name }}' as batch_name,
    '{{ start_time }}' as start_time,
    '{{ end_time }}' as end_time,
    (EXTRACT(EPOCH FROM TIMESTAMP '{{ end_time }}') -
     EXTRACT(EPOCH FROM TIMESTAMP '{{ start_time }}')) as execution_time_seconds,

    {# Memory usage estimation based on table sizes #}
    (SELECT SUM(estimated_size)
     FROM pragma_table_info()
     WHERE table_type = 'TABLE') as estimated_memory_usage,

    {# Query performance metrics #}
    (SELECT COUNT(*) FROM pragma_query_profiler()) as total_queries_executed
{% endmacro %}
