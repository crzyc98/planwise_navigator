# Data Utilities - Data Access and Processing Layer

## Purpose

The data utilities in `streamlit_app/utils/` provide the foundational data access layer for the PlanWise Navigator dashboard, handling database connections, query execution, data transformation, and caching for optimal performance and user experience.

## Architecture

The data utilities implement a clean separation of concerns with:
- **Data Access Layer**: Database connection management and query execution
- **Transformation Layer**: Data processing and business logic application
- **Caching Layer**: Performance optimization and data freshness management
- **Validation Layer**: Data quality checks and error handling

## Key Utility Components

### 1. data_loader.py - Primary Data Access Interface

**Purpose**: Centralized data loading with caching, error handling, and performance optimization.

```python
import streamlit as st
import pandas as pd
import duckdb
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging
from functools import wraps

class DataLoader:
    """Central data loading utility for PlanWise Navigator dashboard"""
    
    def __init__(self, db_path: str = "simulation.duckdb"):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self._connection_pool = {}
    
    def get_connection(self):
        """Get database connection with connection pooling"""
        try:
            # Use thread-local connection for Streamlit
            thread_id = st.get_option("server.runOnSave")
            
            if thread_id not in self._connection_pool:
                self._connection_pool[thread_id] = duckdb.connect(self.db_path)
            
            return self._connection_pool[thread_id]
        except Exception as e:
            self.logger.error(f"Database connection error: {str(e)}")
            raise
    
    @st.cache_data(ttl=300, max_entries=100, show_spinner=False)
    def get_workforce_summary(_self, start_year: Optional[int] = None, 
                            end_year: Optional[int] = None,
                            scenarios: Optional[List[str]] = None) -> pd.DataFrame:
        """Load workforce summary data with filtering and caching"""
        
        query = """
        SELECT 
            simulation_year,
            active_headcount,
            growth_rate_percent,
            turnover_rate_percent,
            total_compensation,
            avg_compensation,
            total_hires,
            total_promotions,
            total_terminations,
            total_merit_raises,
            cost_per_employee,
            cost_per_hire,
            compensation_change,
            voluntary_turnover_percent
        FROM mart_workforce_summary
        WHERE 1=1
        """
        
        params = []
        
        if start_year:
            query += " AND simulation_year >= ?"
            params.append(start_year)
            
        if end_year:
            query += " AND simulation_year <= ?"
            params.append(end_year)
            
        if scenarios:
            placeholders = ','.join(['?' for _ in scenarios])
            query += f" AND scenario_name IN ({placeholders})"
            params.extend(scenarios)
        
        query += " ORDER BY simulation_year"
        
        return _self._execute_query(query, params)
    
    @st.cache_data(ttl=600, max_entries=50)
    def get_workforce_composition(_self, year: int, 
                                 group_by: str = 'level_id') -> pd.DataFrame:
        """Get workforce composition breakdown by specified dimension"""
        
        valid_group_by = ['level_id', 'age_band', 'tenure_band', 'department']
        if group_by not in valid_group_by:
            raise ValueError(f"group_by must be one of {valid_group_by}")
        
        query = f"""
        SELECT 
            {group_by},
            COUNT(*) as headcount,
            AVG(current_compensation) as avg_compensation,
            AVG(current_age) as avg_age,
            AVG(current_tenure) / 12.0 as avg_tenure_years,
            COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage
        FROM fct_workforce_snapshot
        WHERE simulation_year = ? 
          AND employment_status = 'active'
        GROUP BY {group_by}
        ORDER BY {group_by}
        """
        
        return _self._execute_query(query, [year])
    
    @st.cache_data(ttl=300, max_entries=25)
    def get_event_summary(_self, start_year: int, end_year: int) -> pd.DataFrame:
        """Get event summary data for specified year range"""
        
        query = """
        SELECT 
            simulation_year,
            event_type,
            event_subtype,
            COUNT(*) as event_count,
            AVG(financial_impact) as avg_financial_impact,
            SUM(financial_impact) as total_financial_impact,
            MIN(event_date) as first_event_date,
            MAX(event_date) as last_event_date
        FROM fct_yearly_events
        WHERE simulation_year BETWEEN ? AND ?
        GROUP BY simulation_year, event_type, event_subtype
        ORDER BY simulation_year, event_type, event_subtype
        """
        
        return _self._execute_query(query, [start_year, end_year])
    
    @st.cache_data(ttl=900, max_entries=20)
    def get_cohort_analysis(_self, hire_year: int, follow_years: int = 5) -> pd.DataFrame:
        """Analyze employee cohort progression over time"""
        
        query = """
        WITH hire_cohort AS (
            SELECT DISTINCT employee_id
            FROM fct_yearly_events
            WHERE event_type = 'hire' 
              AND simulation_year = ?
        ),
        
        cohort_progression AS (
            SELECT 
                w.simulation_year,
                w.simulation_year - ? as years_since_hire,
                COUNT(w.employee_id) as active_count,
                AVG(w.current_compensation) as avg_compensation,
                AVG(w.level_id) as avg_level,
                COUNT(CASE WHEN e.event_type = 'promotion' THEN 1 END) as promotions,
                COUNT(CASE WHEN e.event_type = 'termination' THEN 1 END) as terminations
            FROM hire_cohort hc
            JOIN fct_workforce_snapshot w ON hc.employee_id = w.employee_id
            LEFT JOIN fct_yearly_events e ON w.employee_id = e.employee_id 
                                        AND w.simulation_year = e.simulation_year
            WHERE w.simulation_year BETWEEN ? AND ?
              AND w.employment_status = 'active'
            GROUP BY w.simulation_year
        )
        
        SELECT 
            simulation_year,
            years_since_hire,
            active_count,
            avg_compensation,
            avg_level,
            promotions,
            terminations,
            -- Retention rate calculation
            active_count * 100.0 / FIRST_VALUE(active_count) OVER (ORDER BY simulation_year) as retention_rate
        FROM cohort_progression
        ORDER BY simulation_year
        """
        
        end_year = hire_year + follow_years
        return _self._execute_query(query, [hire_year, hire_year, hire_year, end_year])
    
    def get_available_years(self) -> List[int]:
        """Get list of available simulation years"""
        query = "SELECT DISTINCT simulation_year FROM mart_workforce_summary ORDER BY simulation_year"
        result = self._execute_query(query)
        return result['simulation_year'].tolist()
    
    def get_scenarios(self) -> List[str]:
        """Get list of available scenarios"""
        query = "SELECT DISTINCT scenario_name FROM mart_workforce_summary WHERE scenario_name IS NOT NULL ORDER BY scenario_name"
        result = self._execute_query(query)
        return result['scenario_name'].tolist() if not result.empty else ['default']
    
    def _execute_query(self, query: str, params: Optional[List] = None) -> pd.DataFrame:
        """Execute database query with error handling and logging"""
        try:
            conn = self.get_connection()
            
            start_time = datetime.now()
            
            if params:
                result = conn.execute(query, params).fetchdf()
            else:
                result = conn.execute(query).fetchdf()
            
            execution_time = (datetime.now() - start_time).total_seconds()
            self.logger.info(f"Query executed in {execution_time:.2f}s, returned {len(result)} rows")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Query execution error: {str(e)}")
            self.logger.error(f"Query: {query}")
            self.logger.error(f"Params: {params}")
            
            # Return empty DataFrame with error in Streamlit
            st.error(f"Database error: {str(e)}")
            return pd.DataFrame()
    
    def validate_data_freshness(self) -> Dict[str, Any]:
        """Check data freshness and quality"""
        try:
            query = """
            SELECT 
                MAX(simulation_year) as latest_year,
                COUNT(DISTINCT simulation_year) as year_count,
                MAX(recorded_at) as last_updated,
                COUNT(*) as total_records
            FROM mart_workforce_summary
            """
            
            result = self._execute_query(query)
            
            if not result.empty:
                row = result.iloc[0]
                return {
                    'latest_year': int(row['latest_year']),
                    'year_count': int(row['year_count']),
                    'last_updated': row['last_updated'],
                    'total_records': int(row['total_records']),
                    'is_fresh': (datetime.now() - pd.to_datetime(row['last_updated'])).days < 1
                }
            else:
                return {'is_fresh': False, 'error': 'No data available'}
                
        except Exception as e:
            return {'is_fresh': False, 'error': str(e)}
```

### 2. scenario_runner.py - Simulation Execution Engine

**Purpose**: Execute custom scenarios and manage simulation runs from the dashboard interface.

```python
import streamlit as st
import yaml
import subprocess
import tempfile
import os
from typing import Dict, Any, Optional
import pandas as pd
from datetime import datetime

class ScenarioRunner:
    """Execute custom simulation scenarios from dashboard"""
    
    def __init__(self, config_template_path: str = "config/simulation_config.yaml"):
        self.config_template_path = config_template_path
        self.temp_dir = tempfile.mkdtemp(prefix="planwise_scenarios_")
    
    def create_scenario_config(self, scenario_params: Dict[str, Any]) -> str:
        """Create temporary configuration file for scenario"""
        
        # Load base configuration
        with open(self.config_template_path, 'r') as f:
            base_config = yaml.safe_load(f)
        
        # Update with scenario parameters
        if 'growth_rate' in scenario_params:
            base_config['workforce']['target_growth_rate'] = scenario_params['growth_rate'] / 100.0
        
        if 'termination_rate' in scenario_params:
            base_config['workforce']['total_termination_rate'] = scenario_params['termination_rate'] / 100.0
        
        if 'promotion_rate' in scenario_params:
            base_config['promotion']['base_rate'] = scenario_params['promotion_rate'] / 100.0
        
        if 'merit_budget' in scenario_params:
            base_config['compensation']['merit_budget'] = scenario_params['merit_budget'] / 100.0
        
        if 'years' in scenario_params:
            base_config['simulation']['end_year'] = base_config['simulation']['start_year'] + scenario_params['years'] - 1
        
        # Add scenario metadata
        base_config['scenario'] = {
            'name': scenario_params.get('name', 'Custom Scenario'),
            'created_at': datetime.now().isoformat(),
            'parameters': scenario_params
        }
        
        # Save to temporary file
        scenario_file = os.path.join(self.temp_dir, f"scenario_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml")
        
        with open(scenario_file, 'w') as f:
            yaml.dump(base_config, f, default_flow_style=False)
        
        return scenario_file
    
    @st.cache_data(ttl=60, show_spinner=True)
    def run_scenario(_self, scenario_params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute simulation scenario and return results"""
        
        try:
            # Create scenario configuration
            config_file = _self.create_scenario_config(scenario_params)
            
            # Execute simulation via Dagster CLI
            cmd = [
                "dagster", "job", "execute",
                "-f", "definitions.py",
                "-j", "multi_year_simulation",
                "-c", config_file
            ]
            
            with st.spinner(f"Running scenario: {scenario_params.get('name', 'Custom Scenario')}..."):
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
            
            if result.returncode == 0:
                # Load results
                data_loader = DataLoader()
                summary = data_loader.get_workforce_summary()
                
                return {
                    'status': 'success',
                    'message': 'Scenario executed successfully',
                    'data': summary,
                    'execution_time': 'N/A',  # Could parse from output
                    'config_file': config_file
                }
            else:
                return {
                    'status': 'error',
                    'message': f"Execution failed: {result.stderr}",
                    'stdout': result.stdout,
                    'stderr': result.stderr
                }
                
        except subprocess.TimeoutExpired:
            return {
                'status': 'timeout',
                'message': 'Scenario execution timed out (>5 minutes)'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Unexpected error: {str(e)}"
            }
    
    def save_scenario_results(self, scenario_name: str, results: pd.DataFrame, 
                            parameters: Dict[str, Any]) -> bool:
        """Save scenario results for later comparison"""
        try:
            # Implementation would save to database or file system
            # For now, use session state
            if 'saved_scenarios' not in st.session_state:
                st.session_state.saved_scenarios = {}
            
            st.session_state.saved_scenarios[scenario_name] = {
                'results': results,
                'parameters': parameters,
                'created_at': datetime.now(),
                'id': len(st.session_state.saved_scenarios) + 1
            }
            
            return True
            
        except Exception as e:
            st.error(f"Failed to save scenario: {str(e)}")
            return False
    
    def load_saved_scenarios(self) -> pd.DataFrame:
        """Load previously saved scenarios"""
        if 'saved_scenarios' not in st.session_state:
            return pd.DataFrame()
        
        scenarios = []
        for name, data in st.session_state.saved_scenarios.items():
            scenarios.append({
                'scenario_name': name,
                'id': data['id'],
                'created_at': data['created_at'],
                'parameters': data['parameters']
            })
        
        return pd.DataFrame(scenarios)
```

### 3. visualization_helpers.py - Chart Utilities

**Purpose**: Reusable visualization components and chart generation utilities.

```python
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import streamlit as st
from typing import List, Dict, Optional, Tuple

# Color schemes for consistent branding
PLANWISE_COLORS = {
    'primary': '#1f77b4',
    'secondary': '#ff7f0e', 
    'success': '#2ca02c',
    'warning': '#ff7f0e',
    'danger': '#d62728',
    'info': '#17a2b8',
    'light': '#f8f9fa',
    'dark': '#343a40'
}

EVENT_COLORS = {
    'hire': '#2ca02c',
    'promotion': '#ff7f0e',
    'termination': '#d62728',
    'merit_raise': '#9467bd'
}

def create_workforce_trend_chart(data: pd.DataFrame, 
                               x_col: str = 'simulation_year',
                               y_col: str = 'active_headcount',
                               title: str = 'Workforce Trend',
                               show_target: bool = False,
                               target_value: Optional[float] = None) -> go.Figure:
    """Create standardized workforce trend line chart"""
    
    fig = px.line(
        data,
        x=x_col,
        y=y_col,
        title=title,
        markers=True,
        line_shape='linear',
        color_discrete_sequence=[PLANWISE_COLORS['primary']]
    )
    
    # Add target line if specified
    if show_target and target_value is not None:
        fig.add_hline(
            y=target_value,
            line_dash="dash",
            line_color=PLANWISE_COLORS['danger'],
            annotation_text=f"Target ({target_value})"
        )
    
    # Styling
    fig.update_layout(
        height=400,
        hovermode='x unified',
        showlegend=True,
        plot_bgcolor='white',
        font=dict(size=12)
    )
    
    fig.update_traces(
        mode='lines+markers',
        hovertemplate='%{y:,.0f}<extra></extra>',
        line=dict(width=3),
        marker=dict(size=8)
    )
    
    return fig

def create_composition_chart(data: pd.DataFrame,
                           category_col: str,
                           value_col: str,
                           chart_type: str = 'pie',
                           title: str = 'Composition') -> go.Figure:
    """Create composition visualization (pie or bar chart)"""
    
    if chart_type == 'pie':
        fig = px.pie(
            data,
            values=value_col,
            names=category_col,
            title=title,
            hole=0.4,  # Donut chart
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        
        fig.update_traces(
            textposition='inside',
            textinfo='percent+label',
            hovertemplate='%{label}: %{value:,.0f} (%{percent})<extra></extra>'
        )
        
    else:  # bar chart
        fig = px.bar(
            data,
            x=category_col,
            y=value_col,
            title=title,
            color=category_col,
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        
        fig.update_traces(
            hovertemplate='%{x}: %{y:,.0f}<extra></extra>'
        )
    
    fig.update_layout(
        height=400,
        showlegend=True,
        plot_bgcolor='white'
    )
    
    return fig

def create_event_volume_chart(data: pd.DataFrame) -> go.Figure:
    """Create stacked bar chart for event volumes"""
    
    # Pivot data for stacked bar chart
    pivot_data = data.pivot(
        index='simulation_year',
        columns='event_type',
        values='event_count'
    ).fillna(0)
    
    fig = go.Figure()
    
    for event_type in pivot_data.columns:
        fig.add_trace(go.Bar(
            name=event_type.title(),
            x=pivot_data.index,
            y=pivot_data[event_type],
            marker_color=EVENT_COLORS.get(event_type, PLANWISE_COLORS['primary']),
            hovertemplate=f'{event_type.title()}: %{{y:,.0f}}<extra></extra>'
        ))
    
    fig.update_layout(
        title='Event Volumes by Year',
        barmode='stack',
        height=400,
        xaxis_title='Year',
        yaxis_title='Event Count',
        plot_bgcolor='white',
        hovermode='x unified'
    )
    
    return fig

def create_financial_waterfall(data: pd.DataFrame,
                              categories: List[str],
                              values: List[float],
                              title: str = 'Financial Impact') -> go.Figure:
    """Create waterfall chart for financial analysis"""
    
    fig = go.Figure(go.Waterfall(
        name="Financial Impact",
        orientation="v",
        measure=["relative"] * (len(categories) - 1) + ["total"],
        x=categories,
        textposition="outside",
        text=[f"${v/1e6:.1f}M" for v in values],
        y=values,
        connector={"line": {"color": "rgb(63, 63, 63)"}},
        increasing={"marker": {"color": PLANWISE_COLORS['success']}},
        decreasing={"marker": {"color": PLANWISE_COLORS['danger']}},
        totals={"marker": {"color": PLANWISE_COLORS['info']}}
    ))
    
    fig.update_layout(
        title=title,
        height=400,
        showlegend=False,
        plot_bgcolor='white'
    )
    
    return fig

def create_comparison_chart(data: pd.DataFrame,
                          scenarios: List[str],
                          metric: str,
                          title: str) -> go.Figure:
    """Create scenario comparison chart"""
    
    fig = go.Figure()
    
    colors = px.colors.qualitative.Set1[:len(scenarios)]
    
    for i, scenario in enumerate(scenarios):
        scenario_data = data[data['scenario_name'] == scenario]
        
        fig.add_trace(go.Scatter(
            x=scenario_data['simulation_year'],
            y=scenario_data[metric],
            mode='lines+markers',
            name=scenario,
            line=dict(color=colors[i], width=3),
            marker=dict(size=8),
            hovertemplate=f'{scenario}: %{{y:,.2f}}<extra></extra>'
        ))
    
    fig.update_layout(
        title=title,
        height=400,
        hovermode='x unified',
        plot_bgcolor='white',
        xaxis_title='Year',
        yaxis_title=metric.replace('_', ' ').title()
    )
    
    return fig

def apply_planwise_theme(fig: go.Figure) -> go.Figure:
    """Apply consistent PlanWise theme to any plotly figure"""
    
    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(
            family="Arial, sans-serif",
            size=12,
            color="#2c3e50"
        ),
        title=dict(
            font=dict(size=16, color="#2c3e50"),
            x=0.5,
            xanchor='center'
        ),
        legend=dict(
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="rgba(0,0,0,0.2)",
            borderwidth=1
        ),
        margin=dict(l=50, r=50, t=60, b=50)
    )
    
    # Update axes styling
    fig.update_xaxes(
        gridcolor='lightgray',
        gridwidth=1,
        zeroline=False,
        linecolor='lightgray'
    )
    
    fig.update_yaxes(
        gridcolor='lightgray', 
        gridwidth=1,
        zeroline=False,
        linecolor='lightgray'
    )
    
    return fig
```

## Performance Optimization

### Caching Strategy
- **Data Loading**: Cache expensive database queries with appropriate TTL
- **Chart Generation**: Cache complex visualizations
- **User Preferences**: Store in session state for persistence

### Connection Management
- Connection pooling for database efficiency
- Graceful connection handling and cleanup
- Error recovery and retry logic

## Dependencies

### External Libraries
- `pandas` - Data manipulation and analysis
- `duckdb` - Database connectivity
- `plotly` - Interactive visualizations
- `streamlit` - Caching and UI components

### Internal Dependencies
- Database models and mart tables
- Configuration management system
- Scenario execution infrastructure

## Related Files

### Core Components
- Dashboard pages that consume these utilities
- Database connection configuration
- Chart and visualization components

### Configuration
- Database connection settings
- Caching configuration
- Performance tuning parameters

## Implementation Notes

### Best Practices
1. **Error Handling**: Always handle database and network errors gracefully
2. **Performance**: Use appropriate caching for expensive operations
3. **Data Validation**: Validate data before processing and visualization
4. **User Feedback**: Provide clear feedback for long-running operations

### Common Issues
- **Cache Invalidation**: Ensure data freshness when simulation results update
- **Memory Usage**: Handle large datasets efficiently with pagination
- **Connection Management**: Proper cleanup of database connections

### Testing Strategy
- Unit tests for data loading functions
- Integration tests for database queries
- Performance tests for large datasets
- Error handling tests for edge cases