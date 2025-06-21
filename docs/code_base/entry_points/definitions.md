# definitions.py - Dagster Workspace Entry Point

## Purpose

The `definitions.py` file serves as the main entry point for the Dagster workspace in PlanWise Navigator. It discovers, configures, and exposes all assets, jobs, resources, and schedules that comprise the workforce simulation platform.

## Architecture

This file acts as the central registry that:
- Imports and consolidates all Dagster assets from the orchestrator package
- Configures shared resources (DuckDB connections, dbt CLI)
- Defines job compositions for single-year and multi-year simulations
- Sets up sensors and schedules for automated execution
- Returns a unified `Definitions` object for the Dagster workspace

## Key Components

### Asset Discovery
- **dbt Assets**: Auto-generated from dbt manifest
- **Simulation State Assets**: Workforce progression tracking
- **Validation Assets**: Data quality and business rule checks
- **Census Data Assets**: Employee data management

### Resource Configuration
- **DuckDB Resource**: Database connection management
- **dbt CLI Resource**: dbt command execution
- **Configuration Resources**: YAML parameter loading

### Job Definitions
- **Single Year Simulation**: Complete workflow for one simulation year
- **Multi-Year Simulation**: Sequential multi-year progression
- **Data Validation Jobs**: Quality assurance workflows

## Configuration

### Required Environment Variables
```bash
DAGSTER_HOME=~/dagster_home_planwise
```

### Resource Settings
- Database connection parameters
- dbt project and profiles paths
- Configuration file locations

## Dependencies

### External Dependencies
- `dagster` - Core orchestration framework
- `dagster_dbt` - dbt integration package
- `duckdb` - Database engine
- `pydantic` - Configuration validation

### Internal Dependencies
- `orchestrator/assets/` - All asset definitions
- `orchestrator/jobs/` - Job compositions
- `orchestrator/resources/` - Resource configurations
- `config/` - YAML configuration files

## Usage Examples

### Local Development
```bash
# Start Dagster development server
dagster dev

# Execute specific job
dagster job execute -f definitions.py -j single_year_simulation

# Materialize individual assets
dagster asset materialize --select simulation_year_state
```

### Configuration Override
```bash
# Run with custom configuration
dagster job execute -f definitions.py -j multi_year_simulation -c config/test_config.yaml
```

## Common Issues

### DuckDB Serialization Error
**Problem**: DuckDB connection objects cannot be serialized by Dagster
**Solution**: Use connection factories and context managers, never return raw connection objects

### Asset Dependency Resolution
**Problem**: Assets not found or circular dependencies
**Solution**: Check import statements and ensure proper asset decorators

### Environment Variable Issues
**Problem**: DAGSTER_HOME not set correctly
**Solution**: Run `./scripts/set_dagster_home.sh` to configure system-wide environment

## Related Files

### Direct Dependencies
- `orchestrator/assets/__init__.py` - Asset imports
- `orchestrator/jobs/__init__.py` - Job definitions
- `orchestrator/resources/__init__.py` - Resource configurations

### Configuration Files
- `config/simulation_config.yaml` - Default parameters
- `dbt/dbt_project.yml` - dbt configuration
- `dbt/profiles.yml` - Database profiles

### Setup Scripts
- `scripts/setup_unified_pipeline.py` - Environment validation
- `scripts/set_dagster_home.sh` - Environment configuration

## Implementation Notes

### Critical Requirements
1. Never serialize DuckDB objects directly
2. All resources must handle connection lifecycle properly
3. Asset dependencies must be explicitly defined
4. Error handling must convert database errors to Dagster failures

### Performance Considerations
- Use lazy loading for large asset collections
- Implement proper connection pooling
- Cache expensive resource initialization

### Testing Strategy
- Mock all external resources in tests
- Validate asset dependency graphs
- Test job execution with sample data
- Verify error handling scenarios
