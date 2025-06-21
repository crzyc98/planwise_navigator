# Dashboard.py - Streamlit Dashboard Entry Point

## Purpose

The main Streamlit dashboard entry point provides an interactive web interface for PlanWise Navigator, enabling users to configure simulations, monitor execution, visualize results, and perform scenario analysis.

## Architecture

The dashboard implements a multi-page Streamlit application with:
- **Configuration Interface**: Parameter editing and scenario setup
- **Execution Management**: Simulation run control and monitoring
- **Results Visualization**: Interactive charts and workforce analytics
- **Scenario Comparison**: Side-by-side what-if analysis
- **Export Capabilities**: Data download and reporting features

## Key Components

### Main Application Structure
- **Page Navigation**: Multi-page app with sidebar navigation
- **Session State Management**: Persistent state across page transitions
- **Data Loading**: Efficient data access from DuckDB
- **Caching**: Performance optimization for expensive operations

### Interactive Features
- **Parameter Controls**: Sliders, inputs, and selectors for configuration
- **Real-time Updates**: Automatic refresh when simulations complete
- **Drill-down Capabilities**: Interactive filtering and exploration
- **Export Functions**: CSV downloads and PDF report generation

### Visualization Components
- **Workforce Composition**: Headcount by level, department, demographics
- **Trend Analysis**: Year-over-year changes and projections
- **Event Summaries**: Hiring, promotion, termination volumes
- **Financial Impact**: Compensation costs and budget projections

## Configuration

### Dashboard Settings
```yaml
dashboard:
  title: "PlanWise Navigator - Workforce Analytics"
  theme: "light"
  sidebar_state: "expanded"
  
data:
  refresh_interval: 30  # seconds
  cache_ttl: 300       # seconds
  max_rows: 10000      # display limit
```

### Database Connection
- DuckDB connection parameters
- Query timeout settings
- Connection pooling configuration

## Dependencies

### External Dependencies
- `streamlit` - Web application framework
- `plotly` - Interactive visualizations
- `pandas` - Data manipulation
- `duckdb` - Database connectivity

### Internal Dependencies
- `streamlit_app/utils/data_loader.py` - Data access utilities
- `streamlit_app/utils/scenario_runner.py` - Simulation execution
- `streamlit_app/components/` - Reusable UI components
- `config/dashboard_config.yaml` - Dashboard configuration

## Usage Examples

### Local Development
```bash
# Start dashboard server
streamlit run streamlit_app/Dashboard.py

# Or use convenience script
./scripts/start_dashboard.sh
```

### Production Deployment
```bash
# Deploy with custom configuration
streamlit run Dashboard.py --server.port 8501 --server.address 0.0.0.0
```

### Custom Configuration
```python
# Override default settings
st.set_page_config(
    page_title="PlanWise Navigator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)
```

## Key Features

### 1. Growth Overview Page
- Total workforce projections
- Growth rate analysis
- Target vs. actual comparisons
- Trend visualizations

### 2. Workforce Composition Page
- Demographic breakdowns
- Level distribution analysis
- Department/division views
- Age and tenure profiles

### 3. Scenario Planning Page
- Parameter adjustment interface
- What-if scenario execution
- Side-by-side comparisons
- Sensitivity analysis

### 4. Financial Impact Page
- Compensation cost projections
- Budget impact analysis
- ROI calculations
- Cost per hire metrics

## Common Issues

### Data Loading Performance
**Problem**: Slow dashboard loading with large datasets
**Solution**: Implement data caching and pagination

```python
@st.cache_data(ttl=300)
def load_workforce_data(year_filter=None):
    # Cached data loading with optional filtering
    return data_loader.get_workforce_snapshot(year_filter)
```

### Session State Management
**Problem**: Lost state when navigating between pages
**Solution**: Use st.session_state for persistent data

```python
if 'simulation_config' not in st.session_state:
    st.session_state.simulation_config = load_default_config()
```

### Database Connection Issues
**Problem**: Connection timeouts or locked database
**Solution**: Implement connection pooling and proper error handling

## Related Files

### Core Dashboard Components
- `streamlit_app/pages/01_Growth_Overview.py` - Workforce growth analytics
- `streamlit_app/pages/02_Workforce_Composition.py` - Demographic analysis
- `streamlit_app/pages/04_Scenario_Planning.py` - What-if modeling
- `streamlit_app/utils/data_loader.py` - Data access layer

### Supporting Utilities
- `streamlit_app/components/charts.py` - Visualization components
- `streamlit_app/components/filters.py` - Filter controls
- `streamlit_app/utils/scenario_runner.py` - Simulation execution
- `config/dashboard_config.yaml` - Configuration settings

### Integration Points
- `definitions.py` - Dagster pipeline access
- `config/simulation_config.yaml` - Simulation parameters
- `dbt/models/marts/` - Data source models

## Implementation Notes

### Performance Optimization
1. **Caching Strategy**: Cache expensive data operations and calculations
2. **Lazy Loading**: Load data only when needed
3. **Pagination**: Limit displayed rows for large datasets
4. **Connection Management**: Reuse database connections efficiently

### User Experience
1. **Responsive Design**: Ensure compatibility across devices
2. **Error Handling**: Provide clear error messages and recovery options
3. **Loading States**: Show progress indicators for long operations
4. **Accessibility**: Follow web accessibility guidelines

### Security Considerations
1. **Input Validation**: Sanitize all user inputs
2. **Authentication**: Implement user authentication if required
3. **Data Access Control**: Restrict access to sensitive data
4. **Audit Logging**: Track user actions and data access

### Testing Strategy
- Unit tests for utility functions
- Integration tests for data loading
- UI tests for critical user paths
- Performance tests for large datasets