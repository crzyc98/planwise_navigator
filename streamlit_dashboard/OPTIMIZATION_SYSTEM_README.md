# PlanWise Navigator Unified Optimization Results Storage System

A comprehensive, production-ready optimization results management system for PlanWise Navigator that unifies storage, retrieval, and analysis of optimization results from both advanced optimization and compensation tuning interfaces.

## 🎯 Overview

This system provides:
- **Unified Storage**: Single source of truth for all optimization results
- **DuckDB Integration**: Seamless integration with existing simulation database
- **Version Control**: Complete audit trail and versioning of optimization runs
- **Export Capabilities**: Multiple export formats (JSON, CSV, Excel, Parquet, Pickle)
- **Caching System**: Performance-optimized caching for frequent operations
- **Analytics Dashboard**: Comprehensive visualization and comparison tools
- **Legacy Compatibility**: Drop-in replacement for existing functions

## 📁 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PlanWise Navigator                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Advanced        │  │ Compensation    │  │ Optimization    │  │
│  │ Optimization    │  │ Tuning          │  │ Dashboard       │  │
│  │ (SciPy)         │  │ (Manual)        │  │ (Analytics)     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│           │                    │                    │           │
│           └────────────────────┼────────────────────┘           │
│                                │                                │
│  ┌─────────────────────────────▼─────────────────────────────┐  │
│  │              Optimization Results Manager                 │  │
│  │  • Save/Load Results    • Session Management             │  │
│  │  • Comparison Tools     • Export Functions               │  │
│  └─────────────────────────────┬─────────────────────────────┘  │
│                                │                                │
│  ┌─────────────────────────────▼─────────────────────────────┐  │
│  │                Optimization Storage                       │  │
│  │  • Metadata Tables      • Results Tables                 │  │
│  │  • Configuration Store  • Simulation Data                │  │
│  └─────────────────────────────┬─────────────────────────────┘  │
│                                │                                │
│  ┌─────────────────────────────▼─────────────────────────────┐  │
│  │          DuckDB + Cache + Integration Layer               │  │
│  │  • DuckDB Tables        • File Cache                     │  │
│  │  • Session Cache        • Legacy Compatibility           │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Setup the System

```bash
cd /Users/nicholasamaral/planwise_navigator/streamlit_dashboard
python setup_optimization_storage.py
```

This will:
- Initialize database tables
- Create cache directories
- Validate system components
- Create sample data for testing

### 2. Launch Interfaces

**Optimization Dashboard** (recommended starting point):
```bash
streamlit run optimization_dashboard.py
```

**Advanced Optimization Interface**:
```bash
streamlit run advanced_optimization.py
```

**Compensation Tuning Interface**:
```bash
streamlit run compensation_tuning.py
```

### 3. Integration with Existing Code

For minimal code changes, add to your existing optimization scripts:

```python
# At the top of your file
from optimization_integration_patch import (
    enhanced_save_optimization_results,
    enhanced_load_optimization_results,
    add_results_viewer_widget
)

# Replace existing load function
results = enhanced_load_optimization_results()

# Add saving after successful optimization
run_id = enhanced_save_optimization_results(
    scenario_id="my_scenario",
    algorithm="SLSQP",
    optimization_config=config,
    results=optimization_results
)

# Add results viewer to sidebar
add_results_viewer_widget()
```

## 📊 Core Components

### 1. Optimization Storage (`optimization_storage.py`)
- **Purpose**: Low-level storage interface with DuckDB
- **Features**: CRUD operations, schema management, export functions
- **Tables**: `optimization_runs`, `optimization_results`, `optimization_configurations`

### 2. Optimization Results Manager (`optimization_results_manager.py`)
- **Purpose**: High-level interface for managing optimization results
- **Features**: Save/load results, comparison tools, session management
- **Integration**: Works with both advanced optimization and compensation tuning

### 3. DuckDB Integration (`optimization_integration.py`)
- **Purpose**: Integration with existing PlanWise Navigator database
- **Features**: Data quality validation, simulation data integration, caching
- **Compatibility**: Works with existing `simulation.duckdb`

### 4. Integration Hooks (`integration_hooks.py`)
- **Purpose**: Bridge between new system and existing interfaces
- **Features**: Drop-in replacements, automatic saving, legacy compatibility
- **Usage**: Minimal code changes required for existing interfaces

### 5. Optimization Dashboard (`optimization_dashboard.py`)
- **Purpose**: Unified interface for viewing and managing all results
- **Features**: Search, filter, compare, export, analytics
- **Tabs**: Overview, Results Browser, Comparison, Export, Analytics

### 6. Integration Patch (`optimization_integration_patch.py`)
- **Purpose**: Easy integration for existing code
- **Features**: Enhanced functions, widgets, session management
- **Usage**: Import and use enhanced versions of existing functions

## 🎛️ Database Schema

### optimization_runs
```sql
CREATE TABLE optimization_runs (
    run_id VARCHAR PRIMARY KEY,
    scenario_id VARCHAR NOT NULL,
    user_id VARCHAR,
    session_id VARCHAR,
    optimization_type VARCHAR NOT NULL,  -- 'advanced_scipy', 'compensation_tuning', etc.
    optimization_engine VARCHAR NOT NULL,  -- 'scipy_slsqp', 'scipy_de', 'manual', etc.
    status VARCHAR NOT NULL,  -- 'running', 'completed', 'failed', 'cancelled'
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    random_seed INTEGER,
    max_evaluations INTEGER,
    timeout_minutes INTEGER,
    use_synthetic_mode BOOLEAN,
    runtime_seconds DOUBLE,
    function_evaluations INTEGER,
    converged BOOLEAN,
    convergence_message VARCHAR,
    description VARCHAR,
    tags VARCHAR,  -- JSON array
    business_justification VARCHAR,
    configuration_hash VARCHAR
);
```

### optimization_results
```sql
CREATE TABLE optimization_results (
    run_id VARCHAR PRIMARY KEY,
    objective_value DOUBLE,
    objective_breakdown JSON,
    optimal_parameters JSON NOT NULL,
    parameter_history JSON,
    objective_history JSON,
    constraint_violations JSON,
    parameter_warnings JSON,
    risk_level VARCHAR,
    risk_assessment JSON,
    estimated_cost_impact JSON,
    estimated_employee_impact JSON,
    projected_outcomes JSON,
    sensitivity_analysis JSON,
    parameter_correlations JSON
);
```

### optimization_configurations
```sql
CREATE TABLE optimization_configurations (
    configuration_hash VARCHAR PRIMARY KEY,
    objectives JSON NOT NULL,
    constraints JSON,
    initial_parameters JSON NOT NULL,
    parameter_bounds JSON,
    algorithm_config JSON,
    created_at TIMESTAMP NOT NULL
);
```

## 🔧 Usage Examples

### Advanced Optimization Integration

```python
from optimization_results_manager import get_optimization_results_manager

# Save advanced optimization results
results_manager = get_optimization_results_manager()

run_id = results_manager.save_advanced_optimization_results(
    scenario_id="quarterly_optimization_2024Q4",
    algorithm="SLSQP",
    initial_parameters={
        "merit_rate_level_1": 0.045,
        "merit_rate_level_2": 0.040,
        "cola_rate": 0.025
    },
    optimal_parameters={
        "merit_rate_level_1": 0.042,
        "merit_rate_level_2": 0.038,
        "cola_rate": 0.023
    },
    objective_weights={"cost": 0.4, "equity": 0.3, "targets": 0.3},
    objective_value=0.234567,
    converged=True,
    function_evaluations=87,
    runtime_seconds=45.2,
    use_synthetic=False
)

print(f"Saved optimization: {run_id}")
```

### Compensation Tuning Integration

```python
# Save compensation tuning results
run_id = results_manager.save_compensation_tuning_results(
    scenario_id="merit_adjustment_2025",
    parameters={
        "merit_rate_level_1": 0.045,
        "merit_rate_level_2": 0.040,
        "cola_rate": 0.025
    },
    simulation_results={
        "workforce_summary": {
            2025: {"total_headcount": 1200, "total_compensation": 120000000},
            2026: {"total_headcount": 1250, "total_compensation": 127500000}
        }
    },
    apply_mode="All Years",
    target_years=[2025, 2026, 2027, 2028, 2029],
    random_seed=42
)
```

### Loading and Comparison

```python
# Load recent results
recent_runs = results_manager.get_recent_results(10)

# Load specific result
run = results_manager.load_results(run_id)

# Compare multiple results
comparison = results_manager.compare_results([run_id1, run_id2, run_id3])

# Export results
export_path = results_manager.export_results(
    run_id=run_id,
    format=ExportFormat.EXCEL,
    output_path="/path/to/export.xlsx"
)
```

### Search and Filter

```python
# Search by scenario pattern
results = results_manager.search_results(
    query="quarterly_optimization",
    optimization_type=OptimizationType.ADVANCED_SCIPY,
    status=OptimizationStatus.COMPLETED
)

# Get parameter history for analysis
history = CompensationTuningIntegration.get_parameter_history("merit_adjustment")
```

## 📈 Analytics and Reporting

### Dashboard Features

1. **Overview Tab**:
   - Total runs, completion rates, recent activity
   - Timeline charts, type distribution, status analysis
   - System health monitoring

2. **Results Browser Tab**:
   - Search and filter results
   - Multi-select actions (view, compare, export, delete)
   - Detailed run information

3. **Comparison Tab**:
   - Parameter comparison charts
   - Objective value analysis
   - Risk level distribution
   - Statistical variance analysis

4. **Export & Archive Tab**:
   - Bulk export operations
   - Export history tracking
   - Multiple format support

5. **Analytics Tab**:
   - Performance analytics (runtime, convergence)
   - Objective value trends
   - Simulation data integration
   - Year-over-year growth analysis

### Programmatic Analytics

```python
from optimization_integration import get_duckdb_integration

# Get simulation summary
db_integration = get_duckdb_integration()
summary = db_integration.get_simulation_summary(2025)

# Multi-year analysis
multi_year = db_integration.get_multi_year_summary(2025, 2029)

# Data quality validation
quality_metrics = db_integration.validate_simulation_data_quality(run_id)
```

## 🔄 Caching Strategy

### Session Cache
- **Purpose**: Immediate access to recent results within Streamlit session
- **Storage**: `st.session_state`
- **Lifecycle**: Per-session, cleared on page refresh

### File Cache
- **Purpose**: Persistent caching across sessions
- **Storage**: `/tmp/planwise_optimization_cache/`
- **Lifecycle**: 24-hour TTL, LRU eviction

### Function Cache
- **Purpose**: Expensive computation caching
- **Storage**: Streamlit `@st.cache_data` and custom decorators
- **Lifecycle**: Configurable TTL (5-60 minutes)

```python
from optimization_integration import cached_function

@cached_function(ttl_minutes=30)
def expensive_analysis(parameters):
    # Heavy computation
    return results

# Cache management
cache = get_optimization_cache()
cache.clear_cache("session")  # Clear session cache
cache.clear_cache("file")     # Clear file cache
cache_stats = cache.get_cache_stats()
```

## 🔒 Data Security and Validation

### Parameter Validation
- **Bounds Checking**: All parameters validated against schema bounds
- **Type Validation**: Pydantic models ensure type safety
- **Business Rules**: Risk assessment for parameter combinations

### Data Integrity
- **Immutable Records**: Optimization results are immutable once saved
- **Audit Trail**: Complete history of all optimization runs
- **Checksums**: Configuration hashing for deduplication

### Risk Assessment
```python
# Automatic risk assessment
risk_assessment = {
    'level': 'MEDIUM',  # LOW, MEDIUM, HIGH
    'factors': ['High merit rates detected'],
    'warning_count': 2,
    'assessment_date': '2024-07-04T10:30:00',
    'parameters_within_bounds': True
}
```

## 📥 Export Formats

### Supported Formats

1. **JSON**: Complete data with metadata
2. **CSV**: Tabular data (multiple files)
3. **Excel**: Multi-sheet workbook with formatting
4. **Parquet**: Columnar format for analytics
5. **Pickle**: Python object serialization

### Export Examples

```python
# Single run export
export_path = results_manager.export_results(
    run_id=run_id,
    format=ExportFormat.EXCEL,
    output_path="/exports/optimization_results.xlsx"
)

# Bulk export
storage = get_optimization_storage()
for run_id in run_ids:
    storage.export_optimization_run(
        run_id=run_id,
        format=ExportFormat.JSON,
        include_simulation_data=True
    )
```

## 🔧 Troubleshooting

### Common Issues

1. **Database Connection Errors**:
   ```python
   # Verify database path
   validation = validate_optimization_environment()
   print(validation['database_accessible'])
   ```

2. **Cache Issues**:
   ```python
   # Clear and rebuild cache
   cache = get_optimization_cache()
   cache.clear_cache()
   ```

3. **Import Errors**:
   ```python
   # Check system path
   import sys
   sys.path.insert(0, '/Users/nicholasamaral/planwise_navigator/streamlit_dashboard')
   ```

4. **Memory Issues**:
   ```python
   # Monitor cache size
   cache_stats = cache.get_cache_stats()
   if cache_stats['file_cache_size_mb'] > 500:  # 500MB limit
       cache.clear_cache('file')
   ```

### System Health Check

```python
from optimization_integration import validate_optimization_environment

# Run complete system validation
validation = validate_optimization_environment()

if validation['database_accessible']:
    print("✅ Database OK")
else:
    print("❌ Database issues")

# Check individual components
print(f"Tables: {'✅' if validation['tables_exist'] else '❌'}")
print(f"Cache: {'✅' if validation['cache_operational'] else '❌'}")
print(f"Storage: {'✅' if validation['storage_initialized'] else '❌'}")
```

## 🚀 Performance Optimization

### Best Practices

1. **Use Session Cache**: Access recent results from session state
2. **Batch Operations**: Export multiple runs in single operation
3. **Lazy Loading**: Load full results only when needed
4. **Index Usage**: Database queries use optimized indexes
5. **Cache Warming**: Pre-load frequently accessed data

### Performance Monitoring

```python
# Monitor query performance
import time

start_time = time.time()
results = results_manager.search_results(query="optimization")
query_time = time.time() - start_time

print(f"Query took {query_time:.2f} seconds")

# Monitor cache hit rates
cache_stats = cache.get_cache_stats()
print(f"Cache directory: {cache_stats['cache_directory']}")
print(f"Cache size: {cache_stats['file_cache_size_mb']:.2f} MB")
```

## 🔄 Migration and Upgrades

### Legacy Data Migration

```python
from integration_hooks import LegacyCompatibility

# Import legacy pickle files
imported_runs = LegacyCompatibility.import_legacy_results("/path/to/legacy.pkl")
print(f"Imported {len(imported_runs)} legacy runs")

# Convert legacy format
legacy_data = {...}  # Old format
new_run = LegacyCompatibility.convert_legacy_format(legacy_data)
storage.save_run_with_session_cache(new_run)
```

### System Upgrades

1. **Backup Database**: Copy `simulation.duckdb` before upgrades
2. **Clear Cache**: Remove cache files during major upgrades
3. **Validate System**: Run validation after upgrades
4. **Test Integration**: Verify existing interfaces still work

## 📝 Development Guide

### Adding New Optimization Types

1. **Extend Enums**:
   ```python
   class OptimizationType(str, Enum):
       ADVANCED_SCIPY = "advanced_scipy"
       COMPENSATION_TUNING = "compensation_tuning"
       YOUR_NEW_TYPE = "your_new_type"  # Add here
   ```

2. **Update Results Manager**:
   ```python
   def save_your_optimization_results(self, ...):
       # Implementation
   ```

3. **Add Integration Hooks**:
   ```python
   class YourOptimizationIntegration:
       @staticmethod
       def save_results(...):
           # Implementation
   ```

### Adding New Export Formats

1. **Extend Export Format Enum**
2. **Update Export Function in Storage**
3. **Add Format-Specific Logic**

### Custom Analytics

```python
# Add custom analytics to dashboard
def create_custom_analytics():
    st.subheader("Custom Analytics")

    # Your custom analysis
    results = get_recent_results(50)
    # Process and visualize
```

## 📚 API Reference

### Key Classes

- `OptimizationStorageManager`: High-level storage interface
- `OptimizationResultsManager`: Results management and analysis
- `DuckDBIntegration`: Database integration layer
- `OptimizationCache`: Caching system
- `OptimizationRun`: Complete optimization record

### Key Functions

- `get_optimization_results_manager()`: Get singleton results manager
- `get_optimization_storage()`: Get singleton storage manager
- `validate_optimization_environment()`: System health check
- `enhanced_save_optimization_results()`: Save with new system
- `enhanced_load_optimization_results()`: Load with new system

## 🤝 Contributing

### Development Setup

1. **Clone Repository**
2. **Setup Environment**: `python -m venv venv && source venv/bin/activate`
3. **Install Dependencies**: `pip install -r requirements.txt`
4. **Run Setup**: `python setup_optimization_storage.py`
5. **Test System**: `python -m pytest tests/`

### Code Standards

- **Type Hints**: Required for all functions
- **Docstrings**: Google-style docstrings
- **Error Handling**: Explicit exception handling
- **Logging**: Use structured logging
- **Testing**: Unit tests for all functions

## 📧 Support

For issues, questions, or contributions:

1. **Check System Health**: Run `validate_optimization_environment()`
2. **Review Logs**: Check application logs for errors
3. **Test Components**: Verify individual components work
4. **Clear Cache**: Try clearing cache if issues persist

---

**PlanWise Navigator Optimization Storage System v1.0.0**
*Built for enterprise-grade optimization result management*
