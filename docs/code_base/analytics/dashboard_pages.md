# Dashboard Pages - Interactive Visualization Components

## Purpose

The dashboard pages in `streamlit_app/pages/` provide specialized interactive interfaces for different aspects of workforce analytics, enabling users to explore simulation results, perform scenario analysis, and generate insights through intuitive visualizations and controls.

## Architecture

The multi-page dashboard implements a modular design with:
- **Specialized Pages**: Each page focuses on specific analytical use cases
- **Shared Components**: Reusable UI elements and data loading utilities
- **Session State Management**: Consistent state across page navigation
- **Real-time Data Integration**: Live connection to simulation results

## Key Dashboard Pages

### 1. 01_Growth_Overview.py - Workforce Growth Analytics

**Purpose**: Primary dashboard for monitoring overall workforce growth trends, target achievement, and high-level KPIs.

```python
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from utils.data_loader import DataLoader
from components.filters import create_year_filter, create_scenario_selector

def main():
    st.set_page_config(
        page_title="Growth Overview - PlanWise Navigator",
        page_icon="📈",
        layout="wide"
    )
    
    st.title("📈 Workforce Growth Overview")
    st.markdown("Monitor workforce growth trends and target achievement")
    
    # Initialize data loader
    data_loader = DataLoader()
    
    # Sidebar filters
    with st.sidebar:
        st.header("Filters")
        
        # Year range selector
        years = create_year_filter(data_loader.get_available_years())
        
        # Scenario selector
        scenarios = create_scenario_selector(data_loader.get_scenarios())
        
        # Refresh data button
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
    
    # Load workforce summary data
    @st.cache_data(ttl=300)
    def load_growth_data(year_range, scenario_list):
        return data_loader.get_workforce_summary(
            start_year=year_range[0],
            end_year=year_range[1],
            scenarios=scenario_list
        )
    
    df_summary = load_growth_data(years, scenarios)
    
    if df_summary.empty:
        st.warning("No data available for selected filters")
        return
    
    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    current_year_data = df_summary[df_summary['simulation_year'] == years[1]]
    
    with col1:
        if not current_year_data.empty:
            current_headcount = current_year_data['active_headcount'].iloc[0]
            prev_headcount = df_summary[df_summary['simulation_year'] == years[1]-1]['active_headcount'].iloc[0] if len(df_summary) > 1 else None
            delta = current_headcount - prev_headcount if prev_headcount else 0
            
            st.metric(
                label="Current Workforce",
                value=f"{current_headcount:,}",
                delta=f"{delta:+,}" if delta != 0 else None
            )
    
    with col2:
        if not current_year_data.empty:
            growth_rate = current_year_data['growth_rate_percent'].iloc[0]
            target_rate = 3.0  # From config
            
            st.metric(
                label="Growth Rate",
                value=f"{growth_rate:.1f}%",
                delta=f"{growth_rate - target_rate:+.1f}% vs target"
            )
    
    with col3:
        if not current_year_data.empty:
            turnover_rate = current_year_data['turnover_rate_percent'].iloc[0]
            target_turnover = 12.0  # From config
            
            st.metric(
                label="Turnover Rate",
                value=f"{turnover_rate:.1f}%",
                delta=f"{turnover_rate - target_turnover:+.1f}% vs target"
            )
    
    with col4:
        if not current_year_data.empty:
            total_comp = current_year_data['total_compensation'].iloc[0]
            comp_change = current_year_data['compensation_change'].iloc[0]
            
            st.metric(
                label="Total Compensation",
                value=f"${total_comp/1e6:.1f}M",
                delta=f"${comp_change/1e6:+.1f}M"
            )
    
    # Main visualization area
    tab1, tab2, tab3 = st.tabs(["📊 Growth Trends", "🎯 Target Analysis", "💰 Financial Impact"])
    
    with tab1:
        # Workforce growth over time
        fig_growth = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Workforce Headcount', 'Growth Rate %', 'Event Volumes', 'Turnover Analysis'),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": True}, {"secondary_y": False}]]
        )
        
        # Headcount trend
        fig_growth.add_trace(
            go.Scatter(
                x=df_summary['simulation_year'],
                y=df_summary['active_headcount'],
                mode='lines+markers',
                name='Active Headcount',
                line=dict(color='#1f77b4', width=3)
            ),
            row=1, col=1
        )
        
        # Growth rate
        fig_growth.add_trace(
            go.Scatter(
                x=df_summary['simulation_year'],
                y=df_summary['growth_rate_percent'],
                mode='lines+markers',
                name='Actual Growth %',
                line=dict(color='#ff7f0e', width=3)
            ),
            row=1, col=2
        )
        
        # Target line
        fig_growth.add_hline(
            y=3.0, line_dash="dash", line_color="red",
            annotation_text="Target (3%)",
            row=1, col=2
        )
        
        fig_growth.update_layout(
            height=600,
            showlegend=True,
            title_text="Workforce Growth Analysis"
        )
        
        st.plotly_chart(fig_growth, use_container_width=True)
    
    with tab2:
        # Target vs actual analysis
        st.subheader("Target Achievement Analysis")
        
        target_comparison = df_summary.copy()
        target_comparison['growth_target'] = 3.0
        target_comparison['turnover_target'] = 12.0
        target_comparison['growth_variance'] = target_comparison['growth_rate_percent'] - target_comparison['growth_target']
        target_comparison['turnover_variance'] = target_comparison['turnover_rate_percent'] - target_comparison['turnover_target']
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig_growth_target = px.bar(
                target_comparison,
                x='simulation_year',
                y=['growth_rate_percent', 'growth_target'],
                title='Growth Rate: Actual vs Target',
                barmode='group',
                color_discrete_map={
                    'growth_rate_percent': '#2E86C1',
                    'growth_target': '#E74C3C'
                }
            )
            st.plotly_chart(fig_growth_target, use_container_width=True)
        
        with col2:
            fig_turnover_target = px.bar(
                target_comparison,
                x='simulation_year',
                y=['turnover_rate_percent', 'turnover_target'],
                title='Turnover Rate: Actual vs Target',
                barmode='group',
                color_discrete_map={
                    'turnover_rate_percent': '#8E44AD',
                    'turnover_target': '#E74C3C'
                }
            )
            st.plotly_chart(fig_turnover_target, use_container_width=True)
    
    with tab3:
        # Financial impact analysis
        st.subheader("Financial Impact Analysis")
        
        fig_financial = make_subplots(
            rows=1, cols=2,
            subplot_titles=('Total Compensation Over Time', 'Annual Compensation Changes')
        )
        
        fig_financial.add_trace(
            go.Scatter(
                x=df_summary['simulation_year'],
                y=df_summary['total_compensation'] / 1e6,
                mode='lines+markers',
                name='Total Compensation ($M)',
                line=dict(color='#28B463', width=3)
            ),
            row=1, col=1
        )
        
        fig_financial.add_trace(
            go.Bar(
                x=df_summary['simulation_year'],
                y=df_summary['compensation_change'] / 1e6,
                name='Annual Change ($M)',
                marker_color='#F39C12'
            ),
            row=1, col=2
        )
        
        fig_financial.update_layout(
            height=400,
            showlegend=True
        )
        
        st.plotly_chart(fig_financial, use_container_width=True)
        
        # Financial metrics table
        financial_metrics = df_summary[['simulation_year', 'total_compensation', 'cost_per_employee', 'cost_per_hire']].copy()
        financial_metrics['total_compensation'] = (financial_metrics['total_compensation'] / 1e6).round(1)
        financial_metrics.columns = ['Year', 'Total Comp ($M)', 'Cost/Employee ($)', 'Cost/Hire ($)']
        
        st.subheader("Financial Metrics Summary")
        st.dataframe(financial_metrics, use_container_width=True)

if __name__ == "__main__":
    main()
```

### 2. 02_Workforce_Composition.py - Demographic Analysis

**Purpose**: Detailed workforce composition analysis including demographics, level distribution, and organizational structure.

**Key Features**:
- Level distribution over time
- Age and tenure demographics
- Diversity and inclusion metrics
- Department/division breakdowns
- Interactive drill-down capabilities

### 3. 04_Scenario_Planning.py - What-If Analysis

**Purpose**: Interactive scenario modeling and comparison tools for strategic workforce planning.

```python
def create_scenario_comparison():
    """Create scenario comparison interface"""
    st.header("🎯 Scenario Planning & Analysis")
    
    # Scenario configuration interface
    with st.expander("📋 Configure New Scenario", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            scenario_name = st.text_input("Scenario Name", value="Custom Scenario 1")
            growth_rate = st.slider("Target Growth Rate (%)", -5.0, 15.0, 3.0, 0.1)
            termination_rate = st.slider("Termination Rate (%)", 5.0, 25.0, 12.0, 0.5)
        
        with col2:
            promotion_rate = st.slider("Promotion Rate (%)", 5.0, 25.0, 15.0, 0.5)
            merit_budget = st.slider("Merit Budget (% of payroll)", 1.0, 8.0, 4.0, 0.1)
            years_to_simulate = st.selectbox("Years to Simulate", [1, 3, 5, 10], index=2)
        
        if st.button("🚀 Run Scenario"):
            # Trigger scenario execution
            run_custom_scenario(scenario_name, {
                'growth_rate': growth_rate,
                'termination_rate': termination_rate,
                'promotion_rate': promotion_rate,
                'merit_budget': merit_budget,
                'years': years_to_simulate
            })
    
    # Scenario comparison
    saved_scenarios = load_saved_scenarios()
    
    if len(saved_scenarios) >= 2:
        st.subheader("📊 Compare Scenarios")
        
        selected_scenarios = st.multiselect(
            "Select scenarios to compare",
            options=saved_scenarios['scenario_name'].tolist(),
            default=saved_scenarios['scenario_name'].tolist()[:2]
        )
        
        if len(selected_scenarios) >= 2:
            comparison_data = load_scenario_comparison(selected_scenarios)
            create_comparison_charts(comparison_data)
```

### 4. Additional Dashboard Pages

**Financial Impact Analysis**:
- Multi-year cost projections
- Budget variance analysis
- ROI calculations for workforce initiatives
- Compensation trend analysis

**Cohort Analysis**:
- Employee journey tracking
- Retention analysis by hire cohort
- Career progression patterns
- Performance correlation analysis

## Shared Components & Utilities

### Filter Components
```python
# components/filters.py
def create_year_filter(available_years):
    """Create standardized year range filter"""
    min_year, max_year = min(available_years), max(available_years)
    return st.slider(
        "Year Range",
        min_value=min_year,
        max_value=max_year,
        value=(min_year, max_year),
        step=1
    )

def create_level_filter():
    """Create job level filter"""
    return st.multiselect(
        "Job Levels",
        options=[1, 2, 3, 4, 5],
        default=[1, 2, 3, 4, 5],
        format_func=lambda x: f"Level {x}"
    )
```

### Chart Components
```python
# components/charts.py
def create_workforce_trend_chart(data, metric_column, title):
    """Standardized workforce trend visualization"""
    fig = px.line(
        data,
        x='simulation_year',
        y=metric_column,
        title=title,
        markers=True,
        line_shape='linear'
    )
    
    fig.update_layout(
        height=400,
        hovermode='x unified',
        showlegend=True
    )
    
    return fig

def create_composition_pie_chart(data, values_col, names_col, title):
    """Standardized composition pie chart"""
    fig = px.pie(
        data,
        values=values_col,
        names=names_col,
        title=title,
        hole=0.3
    )
    
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig
```

## Data Loading & Caching

### Data Loader Class
```python
# utils/data_loader.py
class DataLoader:
    def __init__(self, db_path="simulation.duckdb"):
        self.db_path = db_path
    
    @st.cache_data(ttl=300)
    def get_workforce_summary(self, start_year=None, end_year=None, scenarios=None):
        """Load workforce summary data with caching"""
        query = """
        SELECT * FROM mart_workforce_summary
        WHERE 1=1
        """
        
        params = []
        if start_year:
            query += " AND simulation_year >= ?"
            params.append(start_year)
        
        if end_year:
            query += " AND simulation_year <= ?"
            params.append(end_year)
        
        return self._execute_query(query, params)
    
    def _execute_query(self, query, params=None):
        """Execute database query with connection management"""
        import duckdb
        
        try:
            with duckdb.connect(self.db_path) as conn:
                if params:
                    return conn.execute(query, params).fetchdf()
                else:
                    return conn.execute(query).fetchdf()
        except Exception as e:
            st.error(f"Database error: {str(e)}")
            return pd.DataFrame()
```

## Performance Optimization

### Caching Strategy
```python
# Implement multi-level caching
@st.cache_data(ttl=600, max_entries=50)
def load_large_dataset(filters):
    """Cache expensive data operations"""
    return data_loader.get_detailed_data(filters)

# Use session state for user preferences
if 'user_filters' not in st.session_state:
    st.session_state.user_filters = {
        'default_years': (2025, 2029),
        'preferred_view': 'summary'
    }
```

### Query Optimization
- Use indexed columns for filtering
- Implement pagination for large datasets
- Pre-aggregate common metrics
- Use connection pooling for multiple queries

## User Experience Features

### Interactive Elements
- Dynamic filtering with real-time updates
- Drill-down capabilities from summary to detail
- Exportable charts and data tables
- Bookmark and save functionality for scenarios

### Responsive Design
- Mobile-friendly layouts
- Collapsible sections for smaller screens
- Optimized chart rendering for different devices
- Progressive data loading for large datasets

## Dependencies

### External Libraries
- `streamlit` - Web application framework
- `plotly` - Interactive visualizations
- `pandas` - Data manipulation
- `duckdb` - Database connectivity

### Internal Dependencies
- `utils/data_loader.py` - Data access layer
- `components/` - Reusable UI components
- Database models and mart tables
- Configuration management system

## Related Files

### Supporting Components
- `utils/scenario_runner.py` - Scenario execution engine
- `utils/visualization_helpers.py` - Chart utilities
- `components/metrics.py` - KPI calculation helpers

### Configuration
- `config/dashboard_config.yaml` - Dashboard settings
- Page-specific configuration files
- User preference management

## Implementation Notes

### Best Practices
1. **Consistent UI Patterns**: Use standardized components across pages
2. **Performance Monitoring**: Track page load times and user interactions
3. **Error Handling**: Graceful degradation when data is unavailable
4. **Accessibility**: Follow web accessibility guidelines

### Common Issues
- **Data Refresh**: Ensure cache invalidation when simulation data updates
- **Memory Management**: Handle large datasets efficiently
- **Browser Compatibility**: Test across different browsers and devices

### Testing Strategy
- Unit tests for data loading functions
- Integration tests for component interactions
- User acceptance testing for critical workflows
- Performance testing with realistic data volumes