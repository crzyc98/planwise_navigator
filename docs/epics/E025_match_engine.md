# Epic E025: Match Engine with Formula Support

## Epic Overview

### Summary
Create a SQL/dbt-first employer match calculation engine supporting tiered formulas and basic match types, with event sourcing integration and DuckDB optimizations for 100K+ employee populations.

### Business Value
- Enables accurate modeling of employer match costs ($5-50M annually)
- Supports optimization of match formulas to maximize participation
- Reduces manual calculations and errors in match processing
- Provides foundation for advanced features (true-up, vesting)

### Success Criteria
- ✅ Core match formulas (simple %, tiered) in pure SQL
- ✅ Processes 100K employees in <10 seconds using DuckDB
- ✅ Integrates with event sourcing architecture
- ✅ Supports formula configuration via dbt variables
- ✅ Generates match events for downstream processing
- ✅ Enables formula comparison and cost analysis

---

## Phase 1: MVP (2 weeks, ~18 points)

### MVP User Stories

### Story E025-01: Core Match Formula Models (6 points)
**As a** plan administrator
**I want** SQL-based match formula calculations
**So that** I can efficiently calculate employer matches

**Acceptance Criteria:**
- Simple percentage match (e.g., 50% of deferrals) in pure SQL
- Tiered match (100% on first 3%, 50% on next 2%) using DuckDB
- Maximum match caps (% of compensation)
- Formula configuration via dbt variables
- Integration with contribution events

### Story E025-02: Match Event Generation (6 points)
**As a** system architect
**I want** match calculations to generate events
**So that** we maintain audit trails

**Acceptance Criteria:**
- Generate EMPLOYER_MATCH events from calculations
- Include formula details in event payload
- Support batch event generation
- Integrate with event sourcing architecture
- Performance: <5 seconds for 10K employees

### Story E025-03: Formula Comparison Analytics (6 points)
**As a** benefits analyst
**I want** to compare different match formulas
**So that** I can optimize cost vs participation

**Acceptance Criteria:**
- Side-by-side formula cost comparison
- Participation impact analysis
- Annual cost projections
- SQL-based analytics models
- Integration with Streamlit dashboard

---

## Phase 2: Post-MVP Features

### Story E025-04: Stretch Match Formulas (8 points)
**As a** benefits designer
**I want** stretch match formulas
**So that** I can incentivize higher savings rates

**Acceptance Criteria:**
- Stretch match calculations (25% on first 12%)
- Multiple tier support (unlimited)
- Dynamic cap calculations
- Performance optimization for complex formulas

### Story E025-05: True-Up Calculations (12 points)
**As a** payroll manager
**I want** annual true-up calculations
**So that** employees receive their full match

**Acceptance Criteria:**
- Annual true-up for employees who max early
- Variable compensation handling
- Termination true-up rules
- True-up event generation
- Integration with year-end processing

### Story E025-06: Vesting Integration (8 points)
**As a** plan administrator
**I want** vesting schedules applied to matches
**So that** we properly track vested amounts

**Acceptance Criteria:**
- Cliff vesting (3-year)
- Graded vesting (2-6 year)
- Service computation
- Forfeiture calculations
- Integration with termination events

### Story E025-07: Safe Harbor Formulas (6 points)
**As a** compliance officer
**I want** safe harbor match formulas
**So that** we meet regulatory requirements

**Acceptance Criteria:**
- Basic safe harbor match
- Enhanced safe harbor match
- Automatic immediate vesting
- Compliance validation
- QACA/QDIA support

### Story E025-08: Match Optimization AI (10 points)
**As a** CFO
**I want** AI-powered match optimization
**So that** I can maximize ROI

**Acceptance Criteria:**
- Machine learning participation models
- Optimal formula recommendations
- Cost/benefit analysis
- A/B testing framework
- Predictive analytics

---

## Technical Specifications (MVP)

### dbt Variable Configuration
```yaml
# dbt_project.yml
vars:
  match_formulas:
    simple_match:
      name: "Simple 50% Match"
      type: "simple"
      match_rate: 0.50
      max_match_percentage: 0.03

    tiered_match:
      name: "Standard Tiered Match"
      type: "tiered"
      tiers:
        - tier: 1
          employee_min: 0.00
          employee_max: 0.03
          match_rate: 1.00
        - tier: 2
          employee_min: 0.03
          employee_max: 0.05
          match_rate: 0.50
      max_match_percentage: 0.04

  # Active formula for simulations
  active_match_formula: "tiered_match"
```

### Core SQL Models (MVP)

#### int_employee_match_calculations.sql
```sql
{{
  config(
    materialized='table',
    indexes=[
      {'columns': ['employee_id', 'simulation_year'], 'unique': true}
    ]
  )
}}

WITH employee_contributions AS (
  SELECT
    employee_id,
    simulation_year,
    SUM(contribution_amount) as annual_deferrals,
    MAX(eligible_compensation) as eligible_compensation,
    -- Calculate effective deferral rate
    CASE
      WHEN MAX(eligible_compensation) > 0
      THEN SUM(contribution_amount) / MAX(eligible_compensation)
      ELSE 0
    END as deferral_rate
  FROM {{ ref('fct_contribution_events') }}
  WHERE contribution_type = 'EMPLOYEE_DEFERRAL'
  GROUP BY employee_id, simulation_year
),

-- Simple match calculation
simple_match AS (
  SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    deferral_rate,
    annual_deferrals,
    -- Simple percentage match
    annual_deferrals * {{ var('match_formulas')['simple_match']['match_rate'] }} as match_amount,
    'simple' as formula_type
  FROM employee_contributions
  WHERE '{{ var("active_match_formula") }}' = 'simple_match'
),

-- Tiered match calculation using DuckDB's powerful window functions
tiered_match AS (
  SELECT
    ec.employee_id,
    ec.simulation_year,
    ec.eligible_compensation,
    ec.deferral_rate,
    ec.annual_deferrals,
    -- Calculate match for each tier
    SUM(
      CASE
        WHEN ec.deferral_rate > tier.employee_min
        THEN LEAST(
          ec.deferral_rate - tier.employee_min,
          tier.employee_max - tier.employee_min
        ) * tier.match_rate * ec.eligible_compensation
        ELSE 0
      END
    ) as match_amount,
    'tiered' as formula_type
  FROM employee_contributions ec
  CROSS JOIN (
    {% for tier in var('match_formulas')['tiered_match']['tiers'] %}
    SELECT
      {{ tier['tier'] }} as tier_number,
      {{ tier['employee_min'] }} as employee_min,
      {{ tier['employee_max'] }} as employee_max,
      {{ tier['match_rate'] }} as match_rate
    {% if not loop.last %}UNION ALL{% endif %}
    {% endfor %}
  ) as tier
  WHERE '{{ var("active_match_formula") }}' = 'tiered_match'
  GROUP BY ec.employee_id, ec.simulation_year, ec.eligible_compensation,
           ec.deferral_rate, ec.annual_deferrals
),

-- Combine all match types
all_matches AS (
  SELECT * FROM simple_match
  UNION ALL
  SELECT * FROM tiered_match
),

-- Apply match caps
final_match AS (
  SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    deferral_rate,
    annual_deferrals,
    formula_type,
    -- Apply maximum match cap
    LEAST(
      match_amount,
      eligible_compensation * {{ var('match_formulas')[var('active_match_formula')]['max_match_percentage'] }}
    ) as employer_match_amount,
    -- Track if cap was applied
    CASE
      WHEN match_amount > eligible_compensation * {{ var('match_formulas')[var('active_match_formula')]['max_match_percentage'] }}
      THEN true
      ELSE false
    END as match_cap_applied
  FROM all_matches
)

SELECT
  employee_id,
  simulation_year,
  eligible_compensation,
  deferral_rate,
  annual_deferrals,
  employer_match_amount,
  formula_type,
  match_cap_applied,
  '{{ var("active_match_formula") }}' as formula_id,
  -- Calculate effective match rate
  CASE
    WHEN annual_deferrals > 0
    THEN employer_match_amount / annual_deferrals
    ELSE 0
  END as effective_match_rate
FROM final_match
```

#### fct_employer_match_events.sql
```sql
{{
  config(
    materialized='incremental',
    unique_key=['event_id'],
    on_schema_change='sync_all_columns'
  )
}}

WITH match_calculations AS (
  SELECT * FROM {{ ref('int_employee_match_calculations') }}
  {% if is_incremental() %}
  WHERE simulation_year > (SELECT MAX(simulation_year) FROM {{ this }})
  {% endif %}
),

match_events AS (
  SELECT
    {{ dbt_utils.generate_surrogate_key(['employee_id', 'simulation_year', 'current_timestamp()']) }} as event_id,
    employee_id,
    'EMPLOYER_MATCH' as event_type,
    simulation_year,
    DATE(simulation_year || '-12-31') as effective_date,
    employer_match_amount as amount,
    -- Event payload
    {
      'formula_id': formula_id,
      'formula_type': formula_type,
      'deferral_rate': deferral_rate,
      'eligible_compensation': eligible_compensation,
      'match_cap_applied': match_cap_applied,
      'effective_match_rate': effective_match_rate
    }::JSON as event_payload,
    CURRENT_TIMESTAMP as created_at
  FROM match_calculations
  WHERE employer_match_amount > 0
)

SELECT * FROM match_events
```

#### int_match_formula_comparison.sql
```sql
{{
  config(
    materialized='table'
  )
}}

-- Calculate costs for each formula type
WITH formula_costs AS (
  {% for formula_key, formula_config in var('match_formulas').items() %}
  SELECT
    '{{ formula_key }}' as formula_id,
    '{{ formula_config["name"] }}' as formula_name,
    COUNT(DISTINCT employee_id) as total_employees,
    COUNT(DISTINCT CASE WHEN employer_match_amount > 0 THEN employee_id END) as participating_employees,
    SUM(employer_match_amount) as total_annual_cost,
    AVG(employer_match_amount) as avg_match_per_employee,
    AVG(CASE WHEN employer_match_amount > 0 THEN employer_match_amount END) as avg_match_per_participant,
    AVG(effective_match_rate) as avg_effective_match_rate,
    COUNT(CASE WHEN match_cap_applied THEN 1 END) as employees_hitting_cap,
    simulation_year
  FROM {{ ref('int_employee_match_calculations') }}
  WHERE formula_id = '{{ formula_key }}'
  GROUP BY simulation_year
  {% if not loop.last %}UNION ALL{% endif %}
  {% endfor %}
)

SELECT
  formula_id,
  formula_name,
  simulation_year,
  total_employees,
  participating_employees,
  participating_employees::FLOAT / NULLIF(total_employees, 0) as participation_rate,
  total_annual_cost,
  total_annual_cost * 5 as projected_5_year_cost,
  avg_match_per_employee,
  avg_match_per_participant,
  avg_effective_match_rate,
  employees_hitting_cap,
  employees_hitting_cap::FLOAT / NULLIF(participating_employees, 0) as pct_hitting_cap
FROM formula_costs
ORDER BY simulation_year, formula_id
```

### Orchestrator Integration (MVP)

#### orchestrator_mvp/assets/match_engine.py
```python
from dagster import asset, AssetExecutionContext
from dagster_dbt import DbtCliResource
import pandas as pd

@asset(
    deps=["contribution_events"],
    group_name="dc_plan"
)
def employer_match_calculations(
    context: AssetExecutionContext,
    dbt: DbtCliResource
) -> None:
    """Calculate employer matches based on contribution events"""

    # Run match calculation models
    dbt_result = dbt.cli(
        ["run", "--select", "int_employee_match_calculations+"],
        context=context
    ).wait()

    if not dbt_result.success:
        raise Exception("Match calculation failed")

    context.log.info(f"Calculated employer matches for simulation")

@asset(
    deps=["employer_match_calculations"],
    group_name="dc_plan"
)
def match_events(
    context: AssetExecutionContext,
    dbt: DbtCliResource,
    duckdb: DuckDBResource
) -> pd.DataFrame:
    """Generate employer match events"""

    # Run event generation model
    dbt_result = dbt.cli(
        ["run", "--select", "fct_employer_match_events"],
        context=context
    ).wait()

    # Query generated events
    with duckdb.get_connection() as conn:
        events_df = conn.execute("""
            SELECT
                event_id,
                employee_id,
                event_type,
                simulation_year,
                amount,
                event_payload
            FROM fct_employer_match_events
            WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_employer_match_events)
        """).df()

    context.log.info(f"Generated {len(events_df)} match events")
    return events_df
```

### Streamlit Dashboard Integration

#### streamlit_dashboard/pages/match_formula_comparison.py
```python
import streamlit as st
import pandas as pd
import plotly.express as px
from utils.database import get_duckdb_connection

st.set_page_config(page_title="Match Formula Comparison", layout="wide")
st.title("Employer Match Formula Comparison")

# Load comparison data
@st.cache_data(ttl=300)
def load_formula_comparison():
    with get_duckdb_connection() as conn:
        return conn.execute("""
            SELECT * FROM int_match_formula_comparison
            ORDER BY simulation_year, formula_id
        """).df()

comparison_df = load_formula_comparison()

# Formula selection
col1, col2 = st.columns(2)
with col1:
    selected_year = st.selectbox(
        "Simulation Year",
        comparison_df['simulation_year'].unique()
    )

# Filter data
year_data = comparison_df[comparison_df['simulation_year'] == selected_year]

# Key metrics
st.subheader("Formula Comparison Metrics")
metrics_cols = st.columns(len(year_data))

for idx, (_, formula) in enumerate(year_data.iterrows()):
    with metrics_cols[idx]:
        st.metric(
            formula['formula_name'],
            f"${formula['total_annual_cost']:,.0f}",
            f"{formula['participation_rate']:.1%} participation"
        )

# Cost comparison chart
fig_cost = px.bar(
    year_data,
    x='formula_name',
    y='total_annual_cost',
    title='Annual Match Cost by Formula',
    labels={'total_annual_cost': 'Annual Cost ($)'}
)
st.plotly_chart(fig_cost, use_container_width=True)

# Participation analysis
col1, col2 = st.columns(2)

with col1:
    fig_participation = px.scatter(
        year_data,
        x='participation_rate',
        y='avg_match_per_participant',
        size='total_annual_cost',
        text='formula_name',
        title='Participation vs Average Match'
    )
    st.plotly_chart(fig_participation)

with col2:
    fig_caps = px.bar(
        year_data,
        x='formula_name',
        y='pct_hitting_cap',
        title='Employees Hitting Match Cap',
        labels={'pct_hitting_cap': '% at Cap'}
    )
    st.plotly_chart(fig_caps)
```

---

## Performance Optimizations

### DuckDB-Specific Optimizations
```sql
-- Create optimized aggregation macro for match calculations
{% macro calculate_tiered_match_optimized() %}
  -- Use DuckDB's LIST comprehension for tier calculations
  SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    deferral_rate,
    -- Vectorized tier calculation using DuckDB arrays
    list_sum(
      list_transform(
        [
          {% for tier in var('match_formulas')['tiered_match']['tiers'] %}
          {
            'min': {{ tier['employee_min'] }},
            'max': {{ tier['employee_max'] }},
            'rate': {{ tier['match_rate'] }}
          }{% if not loop.last %},{% endif %}
          {% endfor %}
        ],
        tier -> GREATEST(0,
          LEAST(deferral_rate - tier.min, tier.max - tier.min)
          * tier.rate * eligible_compensation
        )
      )
    ) as match_amount
  FROM employee_contributions
{% endmacro %}
```

---

## Performance Requirements (MVP)

| Metric | MVP Requirement | Implementation |
|--------|----------------|----------------|
| Match Calculation | <10 seconds for 100K employees | DuckDB columnar processing |
| Event Generation | <5 seconds for 10K employees | Batch INSERT with CTEs |
| Formula Comparison | <2 seconds for 5 formulas | Pre-aggregated materialized tables |
| Dashboard Response | <1 second | Cached queries with TTL |

## Dependencies
- E021-A: DC Plan Event Schema (complete)
- E024: Contribution Calculator (for contribution events)
- DuckDB 1.0.0+ for performance
- dbt-core 1.8.8+ for SQL models
- Dagster for orchestration

## Risks & Mitigations
- **Risk**: Complex formula configurations
- **Mitigation**: Start with simple/tiered only, defer complex formulas
- **Risk**: Performance with large populations
- **Mitigation**: Use DuckDB optimizations and materialized tables

## Estimated Effort
**MVP Phase**: 18 points (2 weeks)
**Post-MVP Phase**: 44 points (3-4 sprints)

---

## Definition of Done (MVP)
- [ ] Simple and tiered match formulas in SQL
- [ ] Match event generation integrated
- [ ] Formula comparison analytics complete
- [ ] Performance targets met (<10s for 100K)
- [ ] Integration with orchestrator_mvp
- [ ] Streamlit dashboard page
- [ ] Unit tests for SQL models
