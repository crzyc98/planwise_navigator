# PlanWise Navigator - Logic Documentation

*Updated: 2025-06-21*

This document provides comprehensive documentation of the PlanWise Navigator codebase logic, based on the actual file structure and implementation patterns.

## System Architecture Overview

PlanWise Navigator is a workforce simulation platform built on:
- **DuckDB**: Column-store database for analytical queries
- **dbt**: SQL transformations and data modeling
- **Dagster**: Pipeline orchestration and asset management
- **Streamlit**: Interactive dashboard for results visualization

## Complete File Tree Structure

```
planwise_navigator/
├── .gitignore
├── CLAUDE.md
├── README.md
├── definitions.py
├── pyproject.toml
├── requirements.txt
├── simulation.duckdb
│
├── config/
│   ├── multi_year_config.yaml
│   ├── simulation_config.yaml
│   └── test_config.yaml
│
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── analyses/
│   ├── macros/
│   │   ├── get_config_value.sql
│   │   ├── get_current_simulation_year.sql
│   │   ├── get_random_seed.sql
│   │   └── validate_simulation_year.sql
│   ├── models/
│   │   ├── intermediate/
│   │   │   ├── events/
│   │   │   │   ├── int_hiring_events.sql
│   │   │   │   ├── int_merit_events.sql
│   │   │   │   ├── int_new_hire_termination_events.sql
│   │   │   │   ├── int_promotion_events.sql
│   │   │   │   └── int_termination_events.sql
│   │   │   ├── hazards/
│   │   │   │   ├── int_hazard_merit.sql
│   │   │   │   ├── int_hazard_promotion.sql
│   │   │   │   └── int_hazard_termination.sql
│   │   │   ├── int_baseline_workforce.sql
│   │   │   ├── int_previous_year_workforce.sql
│   │   │   └── schema.yml
│   │   ├── marts/
│   │   │   ├── dim_hazard_table.sql
│   │   │   ├── fct_workforce_snapshot.sql
│   │   │   ├── fct_yearly_events.sql
│   │   │   ├── mart_cohort_analysis.sql
│   │   │   ├── mart_financial_impact.sql
│   │   │   ├── mart_workforce_summary.sql
│   │   │   └── schema.yml
│   │   ├── monitoring/
│   │   │   ├── mon_data_quality.sql
│   │   │   └── mon_pipeline_performance.sql
│   │   ├── staging/
│   │   │   └── stg_census_data.sql
│   │   └── test/
│   │       └── test_simulation_data.sql
│   ├── seeds/
│   │   ├── bootstrap_census_data.csv
│   │   ├── config_cola_by_year.csv
│   │   ├── config_job_levels.csv
│   │   ├── config_promotion_hazard_age_multipliers.csv
│   │   ├── config_promotion_hazard_base.csv
│   │   ├── config_promotion_hazard_tenure_multipliers.csv
│   │   ├── config_raises_hazard.csv
│   │   ├── config_termination_hazard_age_multipliers.csv
│   │   ├── config_termination_hazard_base.csv
│   │   └── config_termination_hazard_tenure_multipliers.csv
│   └── tests/
│       ├── epic_11_5_acceptance_criteria.sql
│       └── epic_11_5_new_hire_terminations.sql
│
├── docs/
│   ├── README.md
│   ├── architecture.md
│   ├── events.md
│   ├── migration_guide.md
│   ├── simulation_config.md
│   ├── duckdb_relation_serialization_issue.md
│   └── rebuild/
│       ├── PRD-REBUILD-PLANWISE-NAVIGATOR.md
│       ├── dagster_patterns.md
│       ├── duckdb_dagster_patterns.md
│       ├── file_tree.md
│       ├── logic_documentation.md
│       ├── rebuild_implementation_addendum.md
│       └── technical_implementation_guide.md
│
├── orchestrator/
│   ├── __init__.py
│   ├── assets/
│   │   ├── __init__.py
│   │   ├── census_data.py
│   │   ├── dbt_assets.py
│   │   ├── simulation_state.py
│   │   └── validation.py
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── multi_year_simulation.py
│   │   └── single_year_simulation.py
│   ├── ops/
│   │   ├── __init__.py
│   │   ├── census_ops.py
│   │   ├── simulation_ops.py
│   │   └── validation_ops.py
│   ├── resources/
│   │   ├── __init__.py
│   │   ├── dbt_resource.py
│   │   └── duckdb_resource.py
│   └── utils/
│       ├── __init__.py
│       ├── config_loader.py
│       ├── database_utils.py
│       └── simulation_utils.py
│
├── scripts/
│   ├── __init__.py
│   ├── analysis_tools.py
│   ├── dashboard_launcher.py
│   ├── data_export.py
│   ├── install_venv.sh
│   ├── lint.py
│   ├── migration_helper.py
│   ├── set_dagster_home.sh
│   ├── setup_unified_pipeline.py
│   ├── start_dashboard.sh
│   ├── test_runner.py
│   └── validation_checks.py
│
├── streamlit_dashboard/
│   ├── __init__.py
│   ├── app.py
│   ├── components/
│   │   ├── __init__.py
│   │   ├── charts.py
│   │   ├── data_explorer.py
│   │   ├── filters.py
│   │   └── metrics.py
│   ├── pages/
│   │   ├── __init__.py
│   │   ├── cohort_analysis.py
│   │   ├── financial_impact.py
│   │   ├── scenario_comparison.py
│   │   └── workforce_overview.py
│   └── utils/
│       ├── __init__.py
│       ├── data_loader.py
│       └── visualization_helpers.py
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_assets/
    │   ├── __init__.py
    │   ├── test_census_data.py
    │   ├── test_dbt_assets.py
    │   ├── test_simulation_state.py
    │   └── test_validation.py
    ├── test_jobs/
    │   ├── __init__.py
    │   ├── test_multi_year_simulation.py
    │   └── test_single_year_simulation.py
    ├── test_ops/
    │   ├── __init__.py
    │   ├── test_census_ops.py
    │   ├── test_simulation_ops.py
    │   └── test_validation_ops.py
    ├── test_resources/
    │   ├── __init__.py
    │   ├── test_dbt_resource.py
    │   └── test_duckdb_resource.py
    ├── test_scripts/
    │   ├── __init__.py
    │   ├── test_analysis_tools.py
    │   ├── test_migration_helper.py
    │   └── test_validation_checks.py
    └── test_utils/
        ├── __init__.py
        ├── test_config_loader.py
        ├── test_database_utils.py
        └── test_simulation_utils.py
```

## File Architecture & Logic Flow

### Core Entry Points

#### `definitions.py` - Dagster Workspace Entry
**Purpose**: Main Dagster workspace definition that discovers and configures all assets, jobs, and resources.

**Logic**:
- Imports all asset definitions from `orchestrator/assets/`
- Configures DuckDB and dbt resources
- Defines job compositions for single-year and multi-year simulations
- Sets up sensors and schedules for automation
- Returns unified Definitions object for Dagster workspace

**Critical Requirements**:
- Must not serialize DuckDB objects directly
- All resources must handle connection lifecycle properly
- Asset dependencies must be explicitly defined
- Error handling must convert database errors to Dagster failures

### Configuration Layer (`config/`)

#### Configuration Files
- **`simulation_config.yaml`**: Default simulation parameters and workforce settings
- **`multi_year_config.yaml`**: Multi-year simulation configuration with growth targets
- **`test_config.yaml`**: Testing scenario parameters for validation

**Logic**:
- YAML-based hierarchical configuration structure
- Environment-specific parameter overrides
- Validation rules for parameter ranges and dependencies
- Integration with dbt variables and Dagster job configs

### Data Transformation Layer (`dbt/`)

#### dbt Project Structure
```
dbt/
├── dbt_project.yml          # dbt configuration and variable definitions
├── profiles.yml             # Database connection profiles
├── models/
│   ├── staging/             # Raw data cleaning and standardization
│   ├── intermediate/        # Business logic and event generation
│   └── marts/               # Final analytical outputs
├── seeds/                   # Configuration data and bootstrap datasets
├── macros/                  # Reusable SQL functions
└── tests/                   # Custom dbt tests
```

#### Staging Models (`dbt/models/staging/`)

**`stg_census_data.sql`** - Employee Census Data Staging
**Purpose**: Clean and standardize raw employee census data.

**Logic**:
- Standardize column names and data types
- Filter invalid records (null IDs, invalid levels)
- Calculate derived fields (age_bands, tenure_years)
- Apply business rules (active employees only)
- Add data quality flags for downstream validation

#### Intermediate Models (`dbt/models/intermediate/`)

**Event Generation Models (`events/`)**:

**`int_hiring_events.sql`** - New Hire Event Generation
**Purpose**: Generate new hire events based on growth targets and turnover replacement needs.

**Logic**:
1. Calculate hiring needs based on target growth rate
2. Calculate replacement needs based on termination events
3. Apply hiring constraints (budget, headcount caps)
4. Generate hire events with realistic hire dates
5. Assign salary levels based on job level configurations

**`int_promotion_events.sql`** - Promotion Event Generation
**Purpose**: Generate promotion events using hazard-based probability calculations.

**Logic**:
1. **Eligibility Assessment**: Filter employees eligible for promotion
   - Minimum tenure requirements by level
   - Performance score thresholds
   - Level progression rules
2. **Probability Application**: Apply hazard table probabilities
   - Base promotion rate by current level
   - Age and tenure multipliers
   - Random number generation with controlled seed
3. **Event Creation**: Generate promotion records with new level and salary
4. **Validation**: Ensure promotion rules and budget constraints

**`int_termination_events.sql`** - Termination Event Generation
**Purpose**: Generate termination events based on configurable turnover rates.

**Logic**:
1. **Risk Assessment**: Calculate termination probability by employee segment
   - Base termination rates by level and tenure
   - Higher rates for new hires (first-year turnover)
   - Age and performance adjustments
2. **Event Generation**: Create termination records with realistic effective dates
3. **Replacement Calculation**: Track positions requiring backfill

**`int_merit_events.sql`** - Merit Raise Event Generation
**Purpose**: Generate merit raise events based on performance and budget constraints.

**Logic**:
1. **Eligibility**: Identify employees eligible for merit increases
2. **Budget Allocation**: Distribute merit budget across eligible population
3. **Raise Calculation**: Calculate individual raise amounts based on performance
4. **Timing**: Schedule raises based on review cycles and hire anniversaries

**Hazard Calculation Models (`hazards/`)**:

**`int_hazard_promotion.sql`** - Promotion Probability Tables
**Purpose**: Calculate promotion probabilities by employee characteristics.

**Logic**:
- Base promotion rates from configuration seeds
- Age multipliers (career stage adjustments)
- Tenure multipliers (experience adjustments)
- Level-specific caps and progression rules
- Output: Probability table for event generation

**Workforce Progression Models**:

**`int_baseline_workforce.sql`** - Starting Workforce State
**Purpose**: Establish initial workforce composition for simulation start year.

**Logic**:
- Load census data for simulation baseline year
- Standardize employee records and validate data quality
- Calculate initial workforce metrics (headcount by level, average tenure, etc.)
- Apply any needed corrections or adjustments

**`int_previous_year_workforce.sql`** - Previous Year Workforce State
**Purpose**: Calculate workforce state at end of previous simulation year.

**Logic**:
- Start with baseline workforce or previous year's end state
- Apply all events from previous years cumulatively
- Calculate current workforce composition
- Track changes and validate against business rules

#### Mart Models (`dbt/models/marts/`)

**`fct_workforce_snapshot.sql`** - Annual Workforce Snapshots
**Purpose**: Create point-in-time workforce composition for each simulation year.

**Logic**:
1. **State Calculation**: Calculate workforce state by applying all events through target year
2. **Aggregation**: Group by key dimensions (level, department, age_band, tenure_band)
3. **Metrics**: Calculate headcount, compensation totals, averages
4. **Validation**: Ensure workforce counts and financial totals are reasonable

**`fct_yearly_events.sql`** - Event Summary Tables
**Purpose**: Aggregate all events by year and type for analysis.

**Logic**:
- Union all event types (hires, promotions, terminations, merit raises)
- Standardize event schema across types
- Calculate event volumes and financial impacts
- Enable year-over-year trend analysis

**Analytics Marts**:
- **`mart_cohort_analysis.sql`**: Track employee cohorts over time
- **`mart_financial_impact.sql`**: Calculate financial projections and costs
- **`mart_workforce_summary.sql`**: High-level workforce metrics and KPIs

#### dbt Macros (`dbt/macros/`)

**`get_config_value.sql`** - Configuration Value Retrieval
**Purpose**: Safely retrieve configuration values with defaults and validation.

**`get_random_seed.sql`** - Random Seed Management
**Purpose**: Ensure reproducible random number generation across simulation runs.

**`validate_simulation_year.sql`** - Year Validation
**Purpose**: Validate simulation year parameters and ensure proper sequencing.

### Orchestration Layer (`orchestrator/`)

#### Asset Definitions (`orchestrator/assets/`)

**`dbt_assets.py`** - dbt Model Assets
**Purpose**: Wrap dbt models as Dagster assets with proper dependencies.

**Logic**:
- Auto-generate assets from dbt manifest
- Define asset dependencies based on dbt model refs
- Handle dbt run execution and error handling
- Manage asset materialization and caching

**`simulation_state.py`** - Simulation State Management
**Purpose**: Track and manage simulation execution state.

**Logic**:
- Maintain current simulation year and progress
- Store intermediate results and checkpoints
- Handle simulation restart and recovery
- Coordinate multi-year simulation sequencing

**`census_data.py`** - Census Data Assets
**Purpose**: Manage employee census data loading and validation.

**`validation.py`** - Data Quality Assets
**Purpose**: Comprehensive data quality checks and validation.

#### Job Definitions (`orchestrator/jobs/`)

**`single_year_simulation.py`** - Single Year Simulation Job
**Purpose**: Execute complete single-year simulation workflow.

**Job Flow**:
1. Load and validate configuration
2. Prepare baseline workforce data
3. Generate hazard tables
4. Execute event generation models
5. Create workforce snapshots
6. Run validation checks

**`multi_year_simulation.py`** - Multi-Year Simulation Job
**Purpose**: Execute multi-year simulation with year-over-year progression.

**Job Flow**:
1. Initialize multi-year configuration
2. For each simulation year:
   - Run single-year simulation logic
   - Update workforce state
   - Validate year-end results
3. Generate cumulative analytics
4. Create final summary reports

#### Operations (`orchestrator/ops/`)

**`simulation_ops.py`** - Core Simulation Operations
**Purpose**: Individual operations for simulation logic components.

**Key Operations**:
- `prepare_year_snapshot`: Prepare workforce state for year processing
- `run_year_simulation`: Execute single year simulation logic
- `validate_growth_rates`: Validate simulation results against targets

**`census_ops.py`** - Census Data Operations
**Purpose**: Operations for census data loading and processing.

**`validation_ops.py`** - Validation Operations
**Purpose**: Data quality and business rule validation operations.

#### Resources (`orchestrator/resources/`)

**`duckdb_resource.py`** - DuckDB Connection Resource
**Purpose**: Manage DuckDB database connections with proper lifecycle.

**Logic**:
- Connection pooling and reuse
- Transaction management
- Error handling and cleanup
- Connection parameter configuration

**`dbt_resource.py`** - dbt CLI Resource
**Purpose**: Manage dbt CLI execution within Dagster context.

**Logic**:
- dbt command execution with proper context
- Environment variable management
- Log capture and integration
- Error handling and result processing

### Analytics Dashboard (`streamlit_dashboard/`)

#### Main Application (`streamlit_dashboard/app.py`)
**Purpose**: Multi-page Streamlit application for interactive simulation management.

**Application Structure**:
- **Configuration**: Parameter editing and scenario setup
- **Execution**: Simulation run management and monitoring
- **Results**: Visualization of workforce projections
- **Comparison**: Side-by-side scenario analysis
- **Export**: Data download and reporting capabilities

#### Dashboard Components (`streamlit_dashboard/components/`)

**`charts.py`** - Visualization Components
**Purpose**: Reusable chart components for workforce analytics.

**Chart Types**:
- Workforce composition over time
- Event volume trends
- Financial impact projections
- Cohort progression analysis

**`data_explorer.py`** - Interactive Data Exploration
**Purpose**: Allow users to explore simulation results interactively.

**`filters.py`** - Filter and Control Components
**Purpose**: Parameter controls and data filtering interfaces.

#### Dashboard Pages (`streamlit_dashboard/pages/`)

**`workforce_overview.py`** - Workforce Analytics Dashboard
**Purpose**: High-level workforce metrics and trends visualization.

**`scenario_comparison.py`** - Scenario Comparison Tools
**Purpose**: Compare multiple simulation scenarios side-by-side.

**`cohort_analysis.py`** - Cohort Progression Analysis
**Purpose**: Track employee cohorts through career progression.

**`financial_impact.py`** - Financial Impact Analysis
**Purpose**: Analyze financial implications of workforce changes.

### Utility Scripts (`scripts/`)

**`setup_unified_pipeline.py`** - Pipeline Setup and Migration
**Purpose**: Validate environment and migrate from legacy systems.

**`dashboard_launcher.py`** - Dashboard Startup Automation
**Purpose**: Launch Streamlit dashboard with proper configuration.

**`analysis_tools.py`** - Data Analysis Utilities
**Purpose**: Ad-hoc analysis and data exploration tools.

**`validation_checks.py`** - Data Quality Checks
**Purpose**: Comprehensive data validation and quality assessment.

### Testing Infrastructure (`tests/`)

#### Test Organization
```
tests/
├── test_assets/          # Dagster asset tests
├── test_jobs/            # Job execution tests
├── test_ops/             # Individual operation tests
├── test_resources/       # Resource configuration tests
├── test_scripts/         # Utility script tests
└── test_utils/           # Utility function tests
```

**`conftest.py`** - Test Configuration
**Purpose**: Pytest fixtures and test database setup.

**Key Fixtures**:
- Test database with clean data
- Mock configuration objects
- Sample workforce data
- Expected result datasets

## Implementation Guidelines

### Development Order
1. **Foundation**: Basic Dagster workspace and DuckDB connection
2. **Configuration**: YAML configuration management and validation
3. **Data Layer**: dbt staging models and data cleaning
4. **Business Logic**: Event generation and hazard calculation models
5. **Orchestration**: Dagster assets and job definitions
6. **Analytics**: Mart models and summary tables
7. **Interface**: Streamlit dashboard and visualization
8. **Testing**: Comprehensive test suite and validation

### Critical Success Factors

**Database Management**:
- Never serialize DuckDB connection objects
- Always use context managers for connections
- Convert query results to DataFrames or dictionaries
- Handle connection errors gracefully

**Configuration Management**:
- Use Pydantic models for type safety
- Validate all configuration parameters
- Support environment-specific overrides
- Document all configuration options

**Error Handling**:
- Convert database errors to Dagster failures
- Provide meaningful error messages
- Implement proper cleanup on failures
- Log errors with sufficient context

**Testing Strategy**:
- Mock all external dependencies
- Use isolated test databases
- Test both success and failure scenarios
- Validate business logic thoroughly

### Common Patterns

**Asset Pattern**:
```python
@asset
def my_asset(context, config):
    # Load configuration
    # Execute business logic
    # Return serializable result
    pass
```

**Database Pattern**:
```python
with duckdb_resource.get_connection() as conn:
    # Execute SQL
    result = conn.execute(query).fetchdf()
    # Process results
    return result.to_dict('records')
```

**Configuration Pattern**:
```python
config = SimulationConfig.parse_obj(yaml_data)
config.validate()  # Raises ValidationError if invalid
```

This architecture provides a robust, scalable foundation for workforce simulation with clear separation of concerns and comprehensive testing capabilities.