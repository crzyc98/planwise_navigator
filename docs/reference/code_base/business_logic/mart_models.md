# Mart Models - Final Analytical Outputs

## Purpose

The mart models in `dbt/models/marts/` represent the final analytical layer of Fidelity PlanAlign Engine, providing clean, aggregated, and business-ready datasets for reporting, dashboards, and decision-making. These models transform raw events and workforce data into meaningful insights and metrics.

## Architecture

The mart layer implements a dimensional modeling approach with:
- **Fact Tables**: Event-based and snapshot-based metrics
- **Dimension Tables**: Reference data and hierarchies
- **Summary Tables**: Pre-aggregated KPIs and trends
- **Financial Models**: Cost projections and budget analysis

## Key Mart Models

### 1. fct_workforce_snapshot.sql - Workforce State Table

**Purpose**: Point-in-time workforce composition for each simulation year, showing the complete organizational structure after all events have been applied.

```sql
WITH workforce_progression AS (
  -- Start with baseline workforce
  SELECT * FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('baseline_year') }}

  UNION ALL

  -- Apply all events cumulatively through target year
  SELECT
    COALESCE(w.employee_id, e.employee_id) AS employee_id,
    COALESCE(w.employee_ssn, e.employee_ssn) AS employee_ssn,
    {{ var('current_simulation_year') }} AS simulation_year,
    CASE
      WHEN e.event_type = 'termination' THEN 'terminated'
      WHEN e.event_type = 'hire' THEN 'active'
      ELSE COALESCE(w.employment_status, 'active')
    END AS employment_status,
    CASE
      WHEN e.event_type = 'promotion' THEN e.to_level
      ELSE COALESCE(w.level_id, e.level_id)
    END AS level_id,
    -- Calculate current compensation with all adjustments
    CASE
      WHEN e.event_type = 'promotion' THEN e.new_salary
      WHEN e.event_type = 'merit_raise' THEN w.current_compensation + e.merit_increase
      WHEN e.event_type = 'hire' THEN e.starting_salary
      ELSE w.current_compensation * (1 + {{ var('cola_rate', 0.025) }})
    END AS current_compensation
  FROM {{ ref('int_previous_year_workforce') }} w
  FULL OUTER JOIN {{ ref('fct_yearly_events') }} e
    ON w.employee_id = e.employee_id
    AND e.simulation_year <= {{ var('current_simulation_year') }}
)

SELECT
  employee_id,
  employee_ssn,
  simulation_year,
  employment_status,
  level_id,
  current_compensation,
  -- Calculated fields
  EXTRACT(YEAR FROM CURRENT_DATE) - birth_year AS current_age,
  (simulation_year - hire_year) * 12 + hire_month_offset AS current_tenure,
  CASE
    WHEN current_age < 30 THEN '< 30'
    WHEN current_age < 40 THEN '30-39'
    WHEN current_age < 50 THEN '40-49'
    WHEN current_age < 60 THEN '50-59'
    ELSE '60+'
  END AS age_band,
  -- Status categorization
  CASE
    WHEN employment_status = 'active' THEN 'A'
    WHEN employment_status = 'terminated' THEN 'T'
    ELSE 'U'
  END AS detailed_status_code
FROM workforce_progression
WHERE employment_status IN ('active', 'terminated')
```

**Key Features**:
- Complete workforce state at year-end
- Cumulative application of all events
- Calculated demographics and tenure
- Performance-optimized for dashboard queries

### 2. fct_yearly_events.sql - Event Summary Table

**Purpose**: Comprehensive record of all workforce events by year, providing the foundation for trend analysis and event-based reporting.

```sql
WITH unified_events AS (
  -- Hiring events
  SELECT
    employee_id,
    simulation_year,
    'hire' AS event_type,
    NULL AS from_level,
    level_id AS to_level,
    starting_salary AS financial_impact,
    hire_date AS event_date,
    'new_hire' AS event_subtype
  FROM {{ ref('int_hiring_events') }}

  UNION ALL

  -- Promotion events
  SELECT
    employee_id,
    simulation_year,
    'promotion' AS event_type,
    from_level,
    to_level,
    salary_increase AS financial_impact,
    effective_date AS event_date,
    'career_advancement' AS event_subtype
  FROM {{ ref('int_promotion_events') }}

  UNION ALL

  -- Termination events
  SELECT
    employee_id,
    simulation_year,
    'termination' AS event_type,
    current_level AS from_level,
    NULL AS to_level,
    -current_salary AS financial_impact,  -- Negative impact
    termination_date AS event_date,
    termination_reason AS event_subtype
  FROM {{ ref('int_termination_events') }}

  UNION ALL

  -- Merit raise events
  SELECT
    employee_id,
    simulation_year,
    'merit_raise' AS event_type,
    current_level AS from_level,
    current_level AS to_level,  -- Same level
    merit_increase AS financial_impact,
    effective_date AS event_date,
    'performance_adjustment' AS event_subtype
  FROM {{ ref('int_merit_events') }}
)

SELECT
  employee_id,
  simulation_year,
  event_type,
  event_subtype,
  from_level,
  to_level,
  financial_impact,
  event_date,
  -- Event sequencing
  ROW_NUMBER() OVER (
    PARTITION BY employee_id, simulation_year
    ORDER BY event_date,
    CASE event_type
      WHEN 'termination' THEN 1
      WHEN 'hire' THEN 2
      WHEN 'promotion' THEN 3
      WHEN 'merit_raise' THEN 4
    END
  ) AS event_sequence,
  -- Aggregation helpers
  1 AS event_count,
  ABS(financial_impact) AS absolute_financial_impact
FROM unified_events
ORDER BY simulation_year, event_date, employee_id
```

**Key Features**:
- Unified view of all event types
- Proper event sequencing and timing
- Financial impact calculations
- Support for trend and volume analysis

### 3. mart_workforce_summary.sql - Executive Dashboard KPIs

**Purpose**: High-level workforce metrics and key performance indicators for executive reporting and dashboard display.

```sql
WITH workforce_metrics AS (
  SELECT
    simulation_year,
    -- Headcount metrics
    COUNT(*) AS total_headcount,
    COUNT(*) FILTER (WHERE employment_status = 'active') AS active_headcount,
    COUNT(*) FILTER (WHERE employment_status = 'terminated') AS terminated_headcount,

    -- Level distribution
    COUNT(*) FILTER (WHERE level_id = 1) AS level_1_count,
    COUNT(*) FILTER (WHERE level_id = 2) AS level_2_count,
    COUNT(*) FILTER (WHERE level_id = 3) AS level_3_count,
    COUNT(*) FILTER (WHERE level_id = 4) AS level_4_count,
    COUNT(*) FILTER (WHERE level_id = 5) AS level_5_count,

    -- Compensation metrics
    SUM(current_compensation) AS total_compensation,
    AVG(current_compensation) AS avg_compensation,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY current_compensation) AS median_compensation,

    -- Demographics
    AVG(current_age) AS avg_age,
    AVG(current_tenure) / 12.0 AS avg_tenure_years,

    -- Diversity metrics
    COUNT(*) FILTER (WHERE age_band IN ('< 30', '30-39')) AS early_career_count,
    COUNT(*) FILTER (WHERE age_band IN ('40-49', '50-59')) AS mid_career_count,
    COUNT(*) FILTER (WHERE age_band = '60+') AS late_career_count
  FROM {{ ref('fct_workforce_snapshot') }}
  GROUP BY simulation_year
),

event_metrics AS (
  SELECT
    simulation_year,
    -- Event volumes
    COUNT(*) FILTER (WHERE event_type = 'hire') AS total_hires,
    COUNT(*) FILTER (WHERE event_type = 'promotion') AS total_promotions,
    COUNT(*) FILTER (WHERE event_type = 'termination') AS total_terminations,
    COUNT(*) FILTER (WHERE event_type = 'merit_raise') AS total_merit_raises,

    -- Financial impacts
    SUM(financial_impact) FILTER (WHERE event_type = 'hire') AS hiring_cost,
    SUM(financial_impact) FILTER (WHERE event_type = 'promotion') AS promotion_cost,
    SUM(financial_impact) FILTER (WHERE event_type = 'merit_raise') AS merit_cost,
    ABS(SUM(financial_impact) FILTER (WHERE event_type = 'termination')) AS termination_savings,

    -- Rates and ratios
    COUNT(*) FILTER (WHERE event_type = 'termination' AND event_subtype = 'voluntary') AS voluntary_terms,
    COUNT(*) FILTER (WHERE event_type = 'termination' AND event_subtype = 'involuntary') AS involuntary_terms
  FROM {{ ref('fct_yearly_events') }}
  GROUP BY simulation_year
)

SELECT
  w.simulation_year,
  -- Workforce composition
  w.active_headcount,
  w.total_compensation,
  w.avg_compensation,
  w.avg_age,
  w.avg_tenure_years,

  -- Growth metrics
  w.active_headcount - LAG(w.active_headcount) OVER (ORDER BY w.simulation_year) AS headcount_change,
  ROUND(
    (w.active_headcount - LAG(w.active_headcount) OVER (ORDER BY w.simulation_year)) * 100.0 /
    LAG(w.active_headcount) OVER (ORDER BY w.simulation_year), 2
  ) AS growth_rate_percent,

  -- Event summary
  e.total_hires,
  e.total_promotions,
  e.total_terminations,
  e.total_merit_raises,

  -- Turnover analysis
  ROUND(e.total_terminations * 100.0 / w.active_headcount, 2) AS turnover_rate_percent,
  ROUND(e.voluntary_terms * 100.0 / NULLIF(e.total_terminations, 0), 2) AS voluntary_turnover_percent,

  -- Financial analysis
  e.hiring_cost + e.promotion_cost + e.merit_cost AS total_compensation_investment,
  e.termination_savings,
  w.total_compensation - LAG(w.total_compensation) OVER (ORDER BY w.simulation_year) AS compensation_change,

  -- Efficiency metrics
  ROUND(w.total_compensation / w.active_headcount, 0) AS cost_per_employee,
  ROUND(e.hiring_cost / NULLIF(e.total_hires, 0), 0) AS cost_per_hire
FROM workforce_metrics w
LEFT JOIN event_metrics e ON w.simulation_year = e.simulation_year
ORDER BY w.simulation_year
```

### 4. mart_financial_impact.sql - Financial Analysis

**Purpose**: Detailed financial projections and cost analysis for budgeting and strategic planning.

**Key Features**:
- Multi-year compensation cost projections
- Budget variance analysis
- ROI calculations for workforce investments
- Cost-per-hire and retention metrics

### 5. mart_cohort_analysis.sql - Employee Journey Tracking

**Purpose**: Track employee cohorts through their career progression and organizational tenure.

**Key Features**:
- Hire cohort progression analysis
- Retention rates by cohort and time period
- Career advancement patterns
- Compensation growth trajectories

## Data Quality & Validation

Each mart model includes comprehensive data quality checks:

```sql
-- Example validation in schema.yml
- name: fct_workforce_snapshot
  description: "Annual workforce snapshots with complete employee records"
  tests:
    - dbt_utils.accepted_range:
        column_name: current_age
        min_value: 18
        max_value: 75
    - dbt_utils.accepted_range:
        column_name: current_compensation
        min_value: 30000
        max_value: 500000
  columns:
    - name: employee_id
      description: "Unique employee identifier"
      tests:
        - not_null
        - unique
```

## Performance Optimization

### Materialization Strategy
```sql
{{ config(
    materialized='table',
    indexes=[
      {'columns': ['simulation_year'], 'type': 'btree'},
      {'columns': ['employee_id'], 'type': 'btree'},
      {'columns': ['employment_status', 'level_id'], 'type': 'btree'}
    ]
) }}
```

### Query Optimization
- Strategic use of indexes on frequently filtered columns
- Pre-aggregated metrics for dashboard performance
- Partitioning by simulation year for time-series queries
- Efficient JOIN strategies for large datasets

## Usage Examples

### Dashboard Queries
```sql
-- Get current year workforce summary
SELECT * FROM mart_workforce_summary
WHERE simulation_year = 2025;

-- Compare growth across years
SELECT
  simulation_year,
  active_headcount,
  growth_rate_percent,
  turnover_rate_percent
FROM mart_workforce_summary
ORDER BY simulation_year;
```

### Analysis Queries
```sql
-- Analyze promotion patterns
SELECT
  from_level,
  to_level,
  COUNT(*) as promotion_count,
  AVG(financial_impact) as avg_salary_increase
FROM fct_yearly_events
WHERE event_type = 'promotion'
GROUP BY from_level, to_level;
```

## Dependencies

### Source Dependencies
- All intermediate event models
- Baseline and previous year workforce models
- Configuration seeds and parameters

### Downstream Usage
- Streamlit dashboard components
- Executive reporting systems
- Ad-hoc analysis queries
- Export and API endpoints

## Related Files

### Supporting Models
- `dim_hazard_table.sql` - Reference dimension for probabilities
- All intermediate event and workforce models
- Configuration and seed data

### Integration Points
- Dashboard data loading utilities
- Export and reporting scripts
- Validation and monitoring models

## Implementation Notes

### Business Logic
- Ensure consistent calculation methods across all metrics
- Implement proper handling of edge cases (new hires, terminations)
- Maintain referential integrity across fact and dimension tables

### Performance Considerations
- Use appropriate materialization strategies (table vs. view)
- Implement efficient aggregation patterns
- Consider data retention policies for historical data

### Testing Strategy
- Validate key business metrics against known scenarios
- Test edge cases and boundary conditions
- Verify financial calculations and budget constraints
- Ensure data consistency across related models
