# simulation_pipeline.py - Core Simulation Orchestration

## Purpose

The `orchestrator/simulation_pipeline.py` file contains the heart of the Fidelity PlanAlign Engine system - the unified workforce simulation pipeline that orchestrates multi-year workforce modeling using Dagster and dbt integration.

## Architecture

This pipeline implements a sophisticated workforce simulation engine with:
- **Multi-year progression**: Sequential year-over-year workforce evolution
- **Event-driven modeling**: Probabilistic generation of hiring, promotion, termination, and merit events
- **Cumulative calculations**: Proper handling of year-over-year workforce state changes
- **Comprehensive validation**: Data quality checks and business rule enforcement

## Key Components

### Pipeline Orchestration
- **Year Progression Logic**: Manages sequential simulation years
- **Asset Coordination**: Orchestrates dbt model execution and dependency management
- **State Management**: Tracks simulation progress and intermediate results
- **Error Recovery**: Handles failures and provides restart capabilities

### Business Logic Integration
- **Configuration Management**: Loads and validates simulation parameters
- **Hazard Table Application**: Applies probability models for event generation
- **Growth Rate Validation**: Ensures simulation results meet target parameters
- **Financial Calculations**: Computes compensation impacts and budget constraints

### Data Pipeline Management
- **dbt Model Execution**: Coordinates SQL model runs through Dagster
- **Database Operations**: Manages DuckDB transactions and data persistence
- **Incremental Processing**: Handles only changed data between simulation runs
- **Quality Assurance**: Implements comprehensive data validation checks

## Configuration

### Simulation Parameters
```yaml
simulation:
  start_year: 2025
  end_year: 2029
  random_seed: 42

workforce:
  target_growth_rate: 0.03
  total_termination_rate: 0.12
  new_hire_termination_rate: 0.25
```

### Pipeline Settings
- dbt project configuration
- Database connection parameters
- Asset materialization strategies
- Validation thresholds

## Dependencies

### Core Dependencies
- **Dagster**: Pipeline orchestration and asset management
- **dbt**: SQL model execution and data transformation
- **DuckDB**: High-performance analytical database
- **Pydantic**: Configuration validation and type safety

### Data Dependencies
- **Census Data**: Employee baseline information
- **Configuration Seeds**: Hazard tables and parameter settings
- **Previous Year State**: For multi-year progression

### Model Dependencies
- **Staging Models**: Data standardization and cleaning
- **Intermediate Models**: Event generation and hazard calculations
- **Mart Models**: Final analytical outputs

## Usage Examples

### Single Year Simulation
```python
# Execute single year simulation
dagster job execute -f definitions.py -j single_year_simulation -c config/test_config.yaml
```

### Multi-Year Simulation
```python
# Run complete multi-year simulation
dagster job execute -f definitions.py -j multi_year_simulation -c config/multi_year_config.yaml
```

### Asset-Level Execution
```python
# Execute specific simulation components
dagster asset materialize --select simulation_year_state
dagster asset materialize --select dbt_simulation_models
```

## Common Issues

### Cumulative Growth Calculation Errors
**Problem**: Incorrect year-over-year growth showing flat numbers
**Solution**: Calculate cumulative events from all previous years, not just current year

```python
# WRONG: Calculate from baseline each year
current_active = baseline_count + current_year_hires - current_year_terminations

# CORRECT: Calculate cumulative from all events up to current year
cumulative_events = conn.execute("""
    SELECT
        SUM(CASE WHEN event_type = 'hire' THEN 1 ELSE 0 END) as total_hires,
        SUM(CASE WHEN event_type = 'termination' THEN 1 ELSE 0 END) as total_terminations
    FROM fct_yearly_events
    WHERE simulation_year <= ?
""", [year]).fetchone()
current_active = baseline_count + total_hires - total_terminations
```

### Dagster Context Issues
**Problem**: AssetExecutionContext vs OpExecutionContext errors
**Solution**: Use OpExecutionContext for ops within jobs, AssetExecutionContext for standalone assets

### DbtCliInvocation Result Handling
**Problem**: `.success` attribute doesn't exist on DbtCliInvocation
**Solution**: Use `.wait()` method and check `process.returncode`

```python
invocation = dbt.cli(["run", "--select", model], context=context).wait()
if invocation.process is None or invocation.process.returncode != 0:
    # Handle error
```

## Related Files

### Core Pipeline Components
- `orchestrator/assets/simulation_state.py` - State management
- `orchestrator/ops/simulation_ops.py` - Individual operations
- `orchestrator/jobs/single_year_simulation.py` - Single year job
- `orchestrator/jobs/multi_year_simulation.py` - Multi-year job

### Business Logic Models
- `dbt/models/intermediate/events/` - Event generation models
- `dbt/models/intermediate/hazards/` - Probability calculations
- `dbt/models/marts/fct_workforce_snapshot.sql` - Workforce state
- `dbt/models/marts/fct_yearly_events.sql` - Event aggregation

### Configuration and Validation
- `config/simulation_config.yaml` - Primary configuration
- `orchestrator/resources/dbt_resource.py` - dbt integration
- `orchestrator/resources/duckdb_resource.py` - Database management

## Implementation Notes

### Critical Success Factors
1. **Proper State Management**: Ensure simulation state persists correctly between years
2. **Cumulative Logic**: Always calculate from baseline + all events to date
3. **Error Handling**: Convert database errors to Dagster failures with meaningful messages
4. **Resource Management**: Properly handle database connections and cleanup

### Performance Optimization
- Use incremental dbt models where appropriate
- Implement proper indexing on key columns
- Leverage DuckDB's columnar storage for analytics
- Cache intermediate results for recovery scenarios

### Testing Strategy
- Unit tests for individual operations
- Integration tests for complete pipeline execution
- Validation tests with known data scenarios
- Performance tests with realistic data volumes
