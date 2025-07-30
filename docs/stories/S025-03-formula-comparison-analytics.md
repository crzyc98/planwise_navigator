# Story S025-03: Formula Comparison Analytics

**Epic**: E025 - Match Engine with Formula Support
**Story Points**: 6
**Priority**: High
**Sprint**: TBD
**Owner**: Platform Team
**Status**: 📋 **PLANNED**

## Story

**As a** benefits analyst
**I want** to compare different match formulas
**So that** I can optimize cost vs participation and make data-driven plan design decisions

## Business Context

This story delivers analytical capabilities that allow benefits professionals to evaluate the financial and participation impact of different employer match formulas. It builds comprehensive comparison models that analyze cost, participation rates, and effectiveness metrics across multiple formula configurations. This enables evidence-based decision making for plan design optimization and cost management.

## Acceptance Criteria

### Comparative Analytics Requirements
- [ ] **Side-by-side formula cost comparison** showing annual and projected costs
- [ ] **Participation impact analysis** measuring engagement by formula type
- [ ] **Annual cost projections** with 5-year forecasting
- [ ] **SQL-based analytics models** for efficient computation
- [ ] **Integration with Streamlit dashboard** for interactive analysis

### Key Metrics & Analysis
- [ ] **Total annual match cost** by formula configuration
- [ ] **Participation rates** and employee engagement metrics
- [ ] **Average match per employee** and per participant calculations
- [ ] **Match cap impact analysis** showing optimization opportunities
- [ ] **Cost-per-participant** efficiency ratios

### Dashboard Integration
- [ ] **Interactive formula selection** for comparison scenarios
- [ ] **Visual cost comparison** with charts and metrics
- [ ] **Participation vs cost analysis** with scatter plots
- [ ] **Match cap utilization** reporting

## Technical Specifications

### Core Comparison Analytics Model

```sql
-- dbt/models/intermediate/int_match_formula_comparison.sql
{{
  config(
    materialized='table'
  )
}}

-- Calculate costs for each formula type by running simulations
WITH formula_scenarios AS (
  {% for formula_key, formula_config in var('match_formulas').items() %}
  SELECT
    '{{ formula_key }}' as formula_id,
    '{{ formula_config["name"] }}' as formula_name,
    '{{ formula_config["type"] }}' as formula_type,
    {{ formula_config["max_match_percentage"] }} as max_match_percentage,
    -- Calculate match amounts for this specific formula
    {{ calculate_match_for_formula(formula_key) }} as match_calculations
  {% if not loop.last %}UNION ALL{% endif %}
  {% endfor %}
),

-- Aggregate results by formula
formula_costs AS (
  SELECT
    fs.formula_id,
    fs.formula_name,
    fs.formula_type,
    fs.max_match_percentage,
    COUNT(DISTINCT mc.employee_id) as total_employees,
    COUNT(DISTINCT CASE WHEN mc.employer_match_amount > 0 THEN mc.employee_id END) as participating_employees,
    SUM(mc.employer_match_amount) as total_annual_cost,
    AVG(mc.employer_match_amount) as avg_match_per_employee,
    AVG(CASE WHEN mc.employer_match_amount > 0 THEN mc.employer_match_amount END) as avg_match_per_participant,
    AVG(mc.effective_match_rate) as avg_effective_match_rate,
    COUNT(CASE WHEN mc.match_cap_applied THEN 1 END) as employees_hitting_cap,
    SUM(mc.eligible_compensation) as total_eligible_compensation,
    mc.simulation_year
  FROM formula_scenarios fs
  CROSS JOIN {{ ref('int_employee_match_calculations') }} mc
  WHERE mc.formula_id = fs.formula_id
  GROUP BY fs.formula_id, fs.formula_name, fs.formula_type,
           fs.max_match_percentage, mc.simulation_year
),

-- Calculate derived metrics
enhanced_metrics AS (
  SELECT
    *,
    participating_employees::FLOAT / NULLIF(total_employees, 0) as participation_rate,
    total_annual_cost * 5 as projected_5_year_cost,
    total_annual_cost / NULLIF(participating_employees, 0) as cost_per_participant,
    total_annual_cost / NULLIF(total_eligible_compensation, 0) as cost_as_pct_of_payroll,
    employees_hitting_cap::FLOAT / NULLIF(participating_employees, 0) as pct_hitting_cap,
    -- ROI metrics
    participating_employees::FLOAT / NULLIF(total_annual_cost, 0) * 1000 as participation_per_1k_cost
  FROM formula_costs
)

SELECT
  formula_id,
  formula_name,
  formula_type,
  max_match_percentage,
  simulation_year,
  total_employees,
  participating_employees,
  participation_rate,
  total_annual_cost,
  projected_5_year_cost,
  avg_match_per_employee,
  avg_match_per_participant,
  cost_per_participant,
  cost_as_pct_of_payroll,
  avg_effective_match_rate,
  employees_hitting_cap,
  pct_hitting_cap,
  participation_per_1k_cost,
  -- Ranking metrics for optimization
  RANK() OVER (PARTITION BY simulation_year ORDER BY participation_rate DESC) as participation_rank,
  RANK() OVER (PARTITION BY simulation_year ORDER BY total_annual_cost ASC) as cost_rank,
  RANK() OVER (PARTITION BY simulation_year ORDER BY participation_per_1k_cost DESC) as efficiency_rank
FROM enhanced_metrics
ORDER BY simulation_year, formula_id
```

### Multi-Formula Calculation Macro

```sql
-- dbt/macros/calculate_match_for_formula.sql
{% macro calculate_match_for_formula(formula_key) %}

  {% set formula_config = var('match_formulas')[formula_key] %}

  {% if formula_config['type'] == 'simple' %}
    -- Simple match calculation
    (
      SELECT
        employee_id,
        simulation_year,
        eligible_compensation,
        deferral_rate,
        annual_deferrals,
        annual_deferrals * {{ formula_config['match_rate'] }} as employer_match_amount,
        CASE
          WHEN annual_deferrals * {{ formula_config['match_rate'] }} >
               eligible_compensation * {{ formula_config['max_match_percentage'] }}
          THEN true ELSE false
        END as match_cap_applied,
        LEAST(
          annual_deferrals * {{ formula_config['match_rate'] }},
          eligible_compensation * {{ formula_config['max_match_percentage'] }}
        ) as final_match_amount,
        '{{ formula_key }}' as formula_id
      FROM {{ ref('int_contribution_summary') }}
    )

  {% elif formula_config['type'] == 'tiered' %}
    -- Tiered match calculation
    (
      SELECT
        cs.employee_id,
        cs.simulation_year,
        cs.eligible_compensation,
        cs.deferral_rate,
        cs.annual_deferrals,
        SUM(
          CASE
            WHEN cs.deferral_rate > tier.employee_min
            THEN LEAST(
              cs.deferral_rate - tier.employee_min,
              tier.employee_max - tier.employee_min
            ) * tier.match_rate * cs.eligible_compensation
            ELSE 0
          END
        ) as employer_match_amount,
        CASE
          WHEN SUM(
            CASE
              WHEN cs.deferral_rate > tier.employee_min
              THEN LEAST(
                cs.deferral_rate - tier.employee_min,
                tier.employee_max - tier.employee_min
              ) * tier.match_rate * cs.eligible_compensation
              ELSE 0
            END
          ) > cs.eligible_compensation * {{ formula_config['max_match_percentage'] }}
          THEN true ELSE false
        END as match_cap_applied,
        LEAST(
          SUM(
            CASE
              WHEN cs.deferral_rate > tier.employee_min
              THEN LEAST(
                cs.deferral_rate - tier.employee_min,
                tier.employee_max - tier.employee_min
              ) * tier.match_rate * cs.eligible_compensation
              ELSE 0
            END
          ),
          cs.eligible_compensation * {{ formula_config['max_match_percentage'] }}
        ) as final_match_amount,
        '{{ formula_key }}' as formula_id
      FROM {{ ref('int_contribution_summary') }} cs
      CROSS JOIN (
        {% for tier in formula_config['tiers'] %}
        SELECT
          {{ tier['tier'] }} as tier_number,
          {{ tier['employee_min'] }} as employee_min,
          {{ tier['employee_max'] }} as employee_max,
          {{ tier['match_rate'] }} as match_rate
        {% if not loop.last %}UNION ALL{% endif %}
        {% endfor %}
      ) as tier
      GROUP BY cs.employee_id, cs.simulation_year, cs.eligible_compensation,
               cs.deferral_rate, cs.annual_deferrals
    )
  {% endif %}

{% endmacro %}
```

### Streamlit Dashboard Integration

```python
# streamlit_dashboard/pages/match_formula_comparison.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.database import get_duckdb_connection

st.set_page_config(page_title="Match Formula Comparison", layout="wide")
st.title("🎯 Employer Match Formula Comparison & Optimization")

# Load comparison data
@st.cache_data(ttl=300)
def load_formula_comparison():
    with get_duckdb_connection() as conn:
        return conn.execute("""
            SELECT * FROM int_match_formula_comparison
            ORDER BY simulation_year, formula_id
        """).df()

@st.cache_data(ttl=300)
def load_detailed_breakdown():
    with get_duckdb_connection() as conn:
        return conn.execute("""
            SELECT
                formula_id,
                formula_name,
                simulation_year,
                SUM(CASE WHEN deferral_rate = 0 THEN 1 ELSE 0 END) as non_participants,
                SUM(CASE WHEN deferral_rate BETWEEN 0.01 AND 0.03 THEN 1 ELSE 0 END) as low_deferrals,
                SUM(CASE WHEN deferral_rate BETWEEN 0.031 AND 0.06 THEN 1 ELSE 0 END) as medium_deferrals,
                SUM(CASE WHEN deferral_rate > 0.06 THEN 1 ELSE 0 END) as high_deferrals
            FROM int_employee_match_calculations
            GROUP BY formula_id, formula_name, simulation_year
        """).df()

comparison_df = load_formula_comparison()
breakdown_df = load_detailed_breakdown()

# Sidebar controls
st.sidebar.header("Analysis Controls")
selected_year = st.sidebar.selectbox(
    "Simulation Year",
    comparison_df['simulation_year'].unique(),
    index=len(comparison_df['simulation_year'].unique()) - 1
)

selected_formulas = st.sidebar.multiselect(
    "Formulas to Compare",
    comparison_df['formula_name'].unique(),
    default=comparison_df['formula_name'].unique()[:3]
)

# Filter data
year_data = comparison_df[comparison_df['simulation_year'] == selected_year]
filtered_data = year_data[year_data['formula_name'].isin(selected_formulas)]

# Executive Summary Metrics
st.header("📊 Executive Summary")
metrics_cols = st.columns(len(filtered_data))

for idx, (_, formula) in enumerate(filtered_data.iterrows()):
    with metrics_cols[idx]:
        st.metric(
            formula['formula_name'],
            f"${formula['total_annual_cost']:,.0f}",
            f"{formula['participation_rate']:.1%} participation"
        )
        st.caption(f"Cost per participant: ${formula['cost_per_participant']:,.0f}")

# Main Analysis Section
col1, col2 = st.columns(2)

with col1:
    st.subheader("💰 Annual Cost Analysis")

    # Cost comparison chart
    fig_cost = px.bar(
        filtered_data,
        x='formula_name',
        y='total_annual_cost',
        title='Annual Match Cost by Formula',
        labels={'total_annual_cost': 'Annual Cost ($)', 'formula_name': 'Formula'},
        color='formula_name'
    )
    fig_cost.update_layout(showlegend=False)
    st.plotly_chart(fig_cost, use_container_width=True)

    # 5-year projection
    fig_projection = px.bar(
        filtered_data,
        x='formula_name',
        y='projected_5_year_cost',
        title='5-Year Cost Projection',
        labels={'projected_5_year_cost': '5-Year Cost ($)', 'formula_name': 'Formula'},
        color='formula_name'
    )
    fig_projection.update_layout(showlegend=False)
    st.plotly_chart(fig_projection, use_container_width=True)

with col2:
    st.subheader("📈 Participation & Efficiency")

    # Participation vs cost efficiency
    fig_efficiency = px.scatter(
        filtered_data,
        x='participation_rate',
        y='cost_per_participant',
        size='total_annual_cost',
        text='formula_name',
        title='Participation Rate vs Cost Efficiency',
        labels={
            'participation_rate': 'Participation Rate',
            'cost_per_participant': 'Cost per Participant ($)'
        }
    )
    fig_efficiency.update_traces(textposition="top center")
    st.plotly_chart(fig_efficiency, use_container_width=True)

    # Match cap utilization
    fig_caps = px.bar(
        filtered_data,
        x='formula_name',
        y='pct_hitting_cap',
        title='Employees Hitting Match Cap',
        labels={'pct_hitting_cap': '% at Cap', 'formula_name': 'Formula'},
        color='pct_hitting_cap',
        color_continuous_scale='Reds'
    )
    st.plotly_chart(fig_caps, use_container_width=True)

# Detailed Comparison Table
st.header("📋 Detailed Formula Comparison")

comparison_metrics = filtered_data[[
    'formula_name', 'participation_rate', 'total_annual_cost',
    'avg_match_per_participant', 'cost_per_participant',
    'cost_as_pct_of_payroll', 'pct_hitting_cap'
]].copy()

# Format columns for display
comparison_metrics['participation_rate'] = comparison_metrics['participation_rate'].apply(lambda x: f"{x:.1%}")
comparison_metrics['total_annual_cost'] = comparison_metrics['total_annual_cost'].apply(lambda x: f"${x:,.0f}")
comparison_metrics['avg_match_per_participant'] = comparison_metrics['avg_match_per_participant'].apply(lambda x: f"${x:,.0f}")
comparison_metrics['cost_per_participant'] = comparison_metrics['cost_per_participant'].apply(lambda x: f"${x:,.0f}")
comparison_metrics['cost_as_pct_of_payroll'] = comparison_metrics['cost_as_pct_of_payroll'].apply(lambda x: f"{x:.2%}")
comparison_metrics['pct_hitting_cap'] = comparison_metrics['pct_hitting_cap'].apply(lambda x: f"{x:.1%}")

st.dataframe(
    comparison_metrics,
    column_config={
        'formula_name': 'Formula',
        'participation_rate': 'Participation',
        'total_annual_cost': 'Annual Cost',
        'avg_match_per_participant': 'Avg Match/Participant',
        'cost_per_participant': 'Cost/Participant',
        'cost_as_pct_of_payroll': '% of Payroll',
        'pct_hitting_cap': '% at Cap'
    },
    use_container_width=True
)

# Optimization Recommendations
st.header("🎯 Optimization Recommendations")

# Find best performing formulas
best_participation = filtered_data.loc[filtered_data['participation_rate'].idxmax()]
lowest_cost = filtered_data.loc[filtered_data['total_annual_cost'].idxmin()]
best_efficiency = filtered_data.loc[filtered_data['participation_per_1k_cost'].idxmax()]

rec_col1, rec_col2, rec_col3 = st.columns(3)

with rec_col1:
    st.success(f"**Highest Participation**\n\n{best_participation['formula_name']}\n\n{best_participation['participation_rate']:.1%} participation rate")

with rec_col2:
    st.info(f"**Lowest Cost**\n\n{lowest_cost['formula_name']}\n\n${lowest_cost['total_annual_cost']:,.0f} annual cost")

with rec_col3:
    st.warning(f"**Best Efficiency**\n\n{best_efficiency['formula_name']}\n\n{best_efficiency['participation_per_1k_cost']:.1f} participants per $1K cost")

# Download data option
st.header("📥 Export Analysis")
csv_data = filtered_data.to_csv(index=False)
st.download_button(
    label="Download Comparison Data (CSV)",
    data=csv_data,
    file_name=f"match_formula_comparison_{selected_year}.csv",
    mime="text/csv"
)
```

## Test Scenarios

### dbt Tests for Comparison Analytics
```yaml
# dbt/models/intermediate/schema.yml
models:
  - name: int_match_formula_comparison
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - formula_id
            - simulation_year
    columns:
      - name: participation_rate
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1
              inclusive: true
      - name: total_annual_cost
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              inclusive: true
```

### Test Cases
1. **Multi-Formula Comparison**:
   - Input: 3 different match formulas configured
   - Expected: Side-by-side cost and participation analysis
   - Validation: All metrics calculated correctly

2. **Cost Projection Accuracy**:
   - Verify 5-year projections are 5x annual cost
   - Check cost-per-participant calculations
   - Validate percentage-of-payroll metrics

3. **Participation Analysis**:
   - Compare participation rates across formulas
   - Verify match cap impact calculations
   - Check efficiency ratio computations

4. **Dashboard Responsiveness**:
   - Load comparison data in <2 seconds
   - Interactive filtering works correctly
   - Charts update properly with selections

5. **Edge Case Handling**:
   - Zero-cost formulas display correctly
   - 100% participation scenarios handled
   - Missing data gracefully managed

## Implementation Tasks

### Phase 1: Core Analytics Model
- [ ] **Create comparison analytics model** with multi-formula support
- [ ] **Implement derived metrics** (participation rate, cost efficiency)
- [ ] **Add ranking and optimization** logic for recommendations
- [ ] **Create reusable macros** for formula calculations

### Phase 2: Dashboard Development
- [ ] **Build Streamlit comparison page** with interactive controls
- [ ] **Implement key metrics display** with executive summary
- [ ] **Add comparative visualizations** (charts, scatter plots)
- [ ] **Create optimization recommendations** engine

### Phase 3: Advanced Features
- [ ] **Add 5-year cost projections** with trend analysis
- [ ] **Implement participation breakdowns** by deferral levels
- [ ] **Create match cap optimization** analysis
- [ ] **Add data export capabilities** for external analysis

## Dependencies

### Technical Dependencies
- **S025-01**: Core Match Formula Models (provides calculation foundation)
- **S025-02**: Match Event Generation (provides event data)
- **Streamlit dashboard infrastructure**
- **dbt macro system** for reusable calculations

### Story Dependencies
- **S025-01**: Core Match Formula Models (must be completed)
- **S025-02**: Match Event Generation (must be completed)

## Success Metrics

### Functionality
- [ ] **Comparison completeness**: All configured formulas analyzed
- [ ] **Metric accuracy**: All calculations validated against manual checks
- [ ] **Dashboard usability**: Intuitive interface with clear insights
- [ ] **Optimization recommendations**: Actionable insights for plan design

### Performance
- [ ] **Analytics speed**: <2 seconds for comparison model execution
- [ ] **Dashboard response**: <1 second for interactive updates
- [ ] **Data processing**: Handles multiple formulas efficiently

## Definition of Done

- [ ] **Formula comparison model** implemented with comprehensive metrics
- [ ] **Streamlit dashboard page** complete with interactive analysis
- [ ] **Optimization recommendations** engine providing actionable insights
- [ ] **Performance targets met**: <2 seconds for analytics computation
- [ ] **All comparison scenarios** tested and validated
- [ ] **Export capabilities** working for external analysis
- [ ] **Documentation complete** with dashboard usage guide
- [ ] **Integration testing** with full pipeline validation

## Notes

This story completes the MVP match engine by providing the analytical tools needed for plan optimization. The comparison framework supports both current plan evaluation and future scenario planning, enabling data-driven benefits design decisions.
