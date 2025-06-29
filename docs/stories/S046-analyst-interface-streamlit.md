# S046: Analyst Interface (Streamlit)

**Epic:** E012 - Analyst-Driven Compensation Tuning System
**Story Points:** 5 (Medium)
**Status:** Planned
**Assignee:** TBD
**Start Date:** TBD
**Target Date:** TBD

## Business Value

Analysts get an intuitive UI to adjust compensation parameters, visualize outcomes, and manage scenarios without technical knowledge.

**User Story:**
As an analyst, I want an intuitive web interface to adjust compensation parameters and immediately see the impact on costs and workforce metrics, so I can make data-driven decisions without needing technical expertise.

## Technical Approach

Build Streamlit interface connecting to `simulation.duckdb` using existing connection patterns. Expose 5-level job structure with specific compensation ranges for parameter adjustment. Provide real-time feedback using existing marts layer and scenario management using event sourcing architecture.

## Implementation Details

### Existing Components to Extend

**Streamlit Framework:**
- `streamlit_dashboard/` → Extend with compensation tuning interface
- `streamlit_dashboard/main.py` → Add navigation to tuning pages
- Existing dashboard patterns and styling

**Database Integration:**
- `fct_workforce_snapshot.sql` → Add real-time cost calculation views
- `fct_compensation_growth.sql` → Dashboard-optimized aggregations
- Existing DuckDB connection patterns

### New Streamlit Pages

**Main Tuning Interface:**
```python
# streamlit_dashboard/pages/compensation_tuning.py
import streamlit as st
import pandas as pd
import plotly.express as px
from utils.duckdb_connection import get_duckdb_connection

def render_compensation_tuning():
    """
    Main parameter adjustment interface with real-time feedback.
    """
    st.title("🎯 Compensation Parameter Tuning")

    # Scenario selection
    scenario_id = st.selectbox("Select Scenario", get_available_scenarios())

    # Parameter adjustment sliders
    render_parameter_controls(scenario_id)

    # Real-time impact visualization
    render_impact_visualization(scenario_id)

    # Target tracking
    render_target_tracking(scenario_id)
```

**Scenario Management:**
```python
# streamlit_dashboard/pages/scenario_management.py
def render_scenario_management():
    """
    Scenario CRUD operations and comparison interface.
    """
    st.title("📊 Scenario Management")

    # Scenario list and operations
    render_scenario_list()

    # Create/copy scenario
    render_scenario_creation()

    # Scenario comparison
    render_scenario_comparison()
```

**Target Tracking Dashboard:**
```python
# streamlit_dashboard/pages/target_tracking.py
def render_target_tracking():
    """
    Budget vs actual monitoring with visual indicators.
    """
    st.title("🎯 Target Tracking")

    # Target vs actual metrics
    render_target_metrics()

    # Variance analysis
    render_variance_analysis()

    # Historical tracking
    render_historical_performance()
```

**Optimization Results:**
```python
# streamlit_dashboard/pages/optimization_results.py
def render_optimization_results():
    """
    Tuning outcome visualization and parameter recommendations.
    """
    st.title("🔧 Optimization Results")

    # Optimization summary
    render_optimization_summary()

    # Parameter recommendations
    render_parameter_recommendations()

    # Convergence analysis
    render_convergence_analysis()
```

### Parameter Control Interface

**Job Level Parameter Controls:**
```python
def render_parameter_controls(scenario_id: str):
    """
    Render parameter adjustment controls for all job levels.
    """
    st.subheader("Parameter Adjustments")

    # Get current parameters
    current_params = get_scenario_parameters(scenario_id)

    # Job level controls
    for level in range(1, 6):  # Staff (1) to VP (5)
        level_name = get_level_name(level)

        with st.expander(f"{level_name} (Level {level}) Parameters"):
            col1, col2 = st.columns(2)

            with col1:
                merit_rate = st.slider(
                    f"Merit Increase %",
                    min_value=0.0,
                    max_value=0.10,
                    value=current_params[f"merit_rate_l{level}"],
                    step=0.001,
                    format="%.1f%%",
                    key=f"merit_l{level}"
                )

            with col2:
                promotion_rate = st.slider(
                    f"Promotion Rate %",
                    min_value=0.0,
                    max_value=0.20,
                    value=current_params[f"promotion_rate_l{level}"],
                    step=0.001,
                    format="%.1f%%",
                    key=f"promotion_l{level}"
                )

            # Update parameters on change
            if st.button(f"Update {level_name} Parameters"):
                update_scenario_parameters(scenario_id, level, merit_rate, promotion_rate)
                st.success(f"{level_name} parameters updated!")
```

### Real-Time Visualization

**Impact Visualization:**
```python
def render_impact_visualization(scenario_id: str):
    """
    Real-time cost impact visualization.
    """
    st.subheader("Impact Analysis")

    # Get current simulation results
    results = get_simulation_results(scenario_id)

    # Cost impact chart
    fig_cost = px.bar(
        results,
        x='job_level',
        y='total_cost',
        title='Total Compensation Cost by Level',
        labels={'total_cost': 'Total Cost ($)', 'job_level': 'Job Level'}
    )
    st.plotly_chart(fig_cost, use_container_width=True)

    # Growth rate analysis
    fig_growth = px.line(
        results,
        x='fiscal_year',
        y='growth_rate',
        color='job_level',
        title='Compensation Growth Rate by Level'
    )
    st.plotly_chart(fig_growth, use_container_width=True)
```

**Target Tracking:**
```python
def render_target_tracking(scenario_id: str):
    """
    Visual target tracking with status indicators.
    """
    st.subheader("Target Achievement")

    targets = get_scenario_targets(scenario_id)
    actuals = get_scenario_actuals(scenario_id)

    for target in targets:
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            st.write(f"**{target['metric_name']}**")

        with col2:
            st.metric(
                label="Target",
                value=f"{target['target_value']:,.0f}",
                delta=None
            )

        with col3:
            actual_value = actuals.get(target['metric_name'], 0)
            variance = (actual_value - target['target_value']) / target['target_value']

            st.metric(
                label="Actual",
                value=f"{actual_value:,.0f}",
                delta=f"{variance:.1%}",
                delta_color="normal" if abs(variance) < 0.02 else "inverse"
            )
```

### Database Integration

**Real-Time Query Functions:**
```python
def get_simulation_results(scenario_id: str) -> pd.DataFrame:
    """
    Get real-time simulation results for visualization.
    """
    with get_duckdb_connection() as conn:
        query = """
        SELECT
            job_level,
            fiscal_year,
            total_compensation_cost,
            median_salary,
            total_employees,
            growth_rate
        FROM fct_workforce_snapshot
        WHERE scenario_id = ?
        ORDER BY fiscal_year, job_level
        """
        return conn.execute(query, [scenario_id]).df()

def update_scenario_parameters(scenario_id: str, job_level: int, merit_rate: float, promotion_rate: float):
    """
    Update scenario parameters in real-time.
    """
    with get_duckdb_connection() as conn:
        # Update merit rate
        conn.execute("""
            UPDATE comp_levers
            SET parameter_value = ?
            WHERE scenario_id = ?
              AND job_level = ?
              AND parameter_name = 'merit_rate'
        """, [merit_rate, scenario_id, job_level])

        # Update promotion rate
        conn.execute("""
            UPDATE comp_levers
            SET parameter_value = ?
            WHERE scenario_id = ?
              AND job_level = ?
              AND parameter_name = 'promotion_rate'
        """, [promotion_rate, scenario_id, job_level])
```

## Acceptance Criteria

### Functional Requirements
- [ ] Parameter sliders for all 5 job levels with appropriate ranges
- [ ] Real-time cost impact visualization with sub-second response
- [ ] Scenario creation, save, and load functionality
- [ ] Before/after comparison charts using existing metrics
- [ ] Target tracking with visual indicators (green/red status)

### Technical Requirements
- [ ] Integration with existing Streamlit dashboard navigation
- [ ] DuckDB connection using established patterns
- [ ] Performance: Page load time <2 seconds, parameter updates <1 second
- [ ] Responsive design for different screen sizes
- [ ] Error handling and user feedback for invalid inputs

### User Experience Requirements
- [ ] Intuitive interface requiring no technical training
- [ ] Clear visual feedback for parameter changes
- [ ] Contextual help and parameter explanations
- [ ] Scenario comparison capabilities
- [ ] Export functionality for reports and analysis

## Dependencies

**Prerequisite Stories:**
- S044 (Model Integration) - Requires parameter-driven models for real-time updates

**Dependent Stories:**
- S047 (Optimization Engine) - Will add auto-tuning interface
- S048 (Governance) - Will add approval workflow interface

**External Dependencies:**
- Existing Streamlit dashboard framework
- Current DuckDB connection patterns
- Established visualization libraries (Plotly, etc.)

## Testing Strategy

### Unit Tests
```python
def test_parameter_validation():
    """Test parameter range validation"""

def test_scenario_management():
    """Test scenario CRUD operations"""

def test_real_time_calculations():
    """Test real-time calculation accuracy"""
```

### Integration Tests
- End-to-end parameter adjustment workflow
- Real-time visualization accuracy
- Database connection and query performance
- Cross-browser compatibility

### User Acceptance Tests
- Analyst workflow testing
- Usability testing with target users
- Performance testing under load
- Accessibility compliance

## Implementation Steps

1. **Create page structure** and navigation
2. **Implement parameter controls** with validation
3. **Add real-time visualization** components
4. **Create scenario management** functionality
5. **Implement target tracking** dashboard
6. **Add export and reporting** features
7. **Performance optimization** and testing
8. **User documentation** and training materials

## User Experience Design

**Navigation Structure:**
```
Compensation Tuning (Main)
├── Parameter Adjustment
├── Scenario Management
├── Target Tracking
├── Optimization Results
└── Help & Documentation
```

**Color Coding:**
- 🟢 Green: Targets achieved within tolerance
- 🟡 Yellow: Targets within warning range
- 🔴 Red: Targets exceeded tolerance
- 🔵 Blue: Informational metrics

## Success Metrics

**Functional Success:**
- All parameter adjustments reflected in real-time
- 100% accuracy between interface and database
- Scenario isolation prevents cross-contamination

**Performance Success:**
- Page load time <2 seconds
- Parameter update response time <1 second
- Visualization rendering time <500ms

**User Success:**
- Analysts can complete tuning workflow without training
- 90% user satisfaction rating
- Zero critical usability issues

---

**Story Dependencies:** S044 (Model Integration)
**Blocked By:** S044
**Blocking:** None (parallel with S047)
**Related Stories:** S047 (Optimization Engine), S048 (Governance)
