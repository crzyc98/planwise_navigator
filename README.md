# PlanWise Navigator

**An enterprise-grade, on-premises workforce simulation platform with immutable event sourcing, built on DuckDB, dbt, Dagster, and Streamlit.**

## Overview

PlanWise Navigator represents a paradigm shift from rigid spreadsheets to a dynamic, fully transparent simulation engine—essentially a workforce "time machine" that captures every employee lifecycle event with UUID-stamped precision and enables instant scenario replay.

This enterprise-grade platform replaces legacy Pandas-based pipelines with an immutable event-sourced architecture optimized for analytical workloads, audit trails, and regulatory compliance.

### Key Features

- **Immutable Event Sourcing**: Every workforce event permanently recorded with UUID and timestamp
- **Multi-year Workforce Simulation**: Model hiring, promotions, raises, and terminations over 1-10 years
- **Modular Architecture**: Single-responsibility engines for compensation, termination, hiring, and promotions
- **Interactive Analytics**: Sub-2-second dashboard queries for scenario analysis
- **Audit Trail Transparency**: Complete workforce history reconstruction from event logs
- **Scenario Time Machine**: Instantly replay and compare multiple simulation scenarios
- **Enterprise Security**: Zero cloud dependencies, comprehensive audit logging
- **Reproducible Results**: Random seed control for identical simulation outcomes
- **Scalable Performance**: Handle 100K+ employee records with minimal memory footprint

## Technology Stack

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| **Storage** | DuckDB | 1.0.0 | In-process OLAP database engine |
| **Transformation** | dbt-core | 1.8.8 | SQL-based data modeling and testing |
| **Adapter** | dbt-duckdb | 1.8.1 | Stable DuckDB integration |
| **Orchestration** | Dagster | 1.8.12 | Asset-based pipeline management |
| **Dashboard** | Streamlit | 1.39.0 | Interactive analytics interface |
| **Configuration** | Pydantic | 2.7.4 | Type-safe parameter management |
| **Python** | CPython | 3.11.x | Long-term support version |

## Architecture

```
Raw Census Data → Staging Models → Intermediate Models → Marts → Dashboard
                     (stg_*)         (int_*)            (fct_*, dim_*)
```

### Data Flow
1. **Staging Layer**: Clean and validate raw employee data
2. **Intermediate Layer**: Generate workforce events (hiring, termination, promotion, raises)
3. **Marts Layer**: Aggregate into final analytical tables
4. **Dashboard Layer**: Interactive visualization and scenario comparison

## Directory Structure

```
planwise_navigator/
├── definitions.py                    # Dagster workspace entry point
├── orchestrator/                     # Dagster pipeline code
│   ├── simulation_pipeline.py       # Main simulation logic
│   ├── assets/                       # Asset definitions
│   ├── jobs/                         # Job workflows
│   └── resources/                    # Shared resources (DuckDBResource)
├── dbt/                              # dbt project
│   ├── models/                       # SQL transformation models
│   │   ├── staging/                  # Raw data cleaning (stg_*)
│   │   ├── intermediate/             # Business logic (int_*)
│   │   └── marts/                    # Final outputs (fct_*, dim_*)
│   ├── seeds/                        # Configuration data (CSV)
│   └── macros/                       # Reusable SQL functions
├── streamlit_dashboard/              # Interactive dashboard
├── config/                           # Configuration management
│   └── simulation_config.yaml       # Simulation parameters
├── scripts/                          # Utility scripts
├── tests/                            # Comprehensive testing
├── data/                             # Raw input files (git-ignored)
├── .dagster/                         # Dagster home directory (git-ignored)
└── simulation.duckdb                 # DuckDB database file (git-ignored)
```

## Getting Started

### Prerequisites

- Python 3.11+
- Access to raw employee census data
- On-premises deployment environment

### Installation

1. **Clone and setup environment**:
```bash
git clone <repository-url> planwise_navigator
cd planwise_navigator
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Configure DAGSTER_HOME** (if not already set):
```bash
export DAGSTER_HOME=~/dagster_home_planwise
# Or run: ./scripts/set_dagster_home.sh
```

3. **Configure dbt profile** at `~/.dbt/profiles.yml`:
```yaml
planwise_navigator:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: /absolute/path/to/planwise_navigator/simulation.duckdb
      threads: 4
```

### Running the Platform

#### 1. Start Dagster Development Server
```bash
dagster dev
# Access at http://localhost:3000
```

#### 2. Configure Simulation Parameters
Edit `config/simulation_config.yaml`:
```yaml
start_year: 2025
end_year: 2029
target_growth_rate: 0.03
total_termination_rate: 0.12
new_hire_termination_rate: 0.25
random_seed: 42
```

#### 3. Run Simulations
```bash
# Single year simulation
dagster asset materialize --select simulation_year_state

# Multi-year simulation
dagster asset materialize --select multi_year_simulation

# Run all dbt models
dagster asset materialize --select dbt_models
```

#### 4. Launch Interactive Dashboard
```bash
streamlit run streamlit_dashboard/main.py
# Access at http://localhost:8501
```

### Development Workflow

#### dbt Development
```bash
cd dbt
dbt run                   # Run all models
dbt run --select staging  # Run specific layer
dbt test                  # Run all tests
dbt docs generate && dbt docs serve  # Documentation
```

#### Asset Development
```bash
# Run specific asset groups
dagster asset materialize --select workforce_simulation
dagster asset materialize --select dashboard_data

# Run data quality checks
dagster asset check --select validate_data_quality
dagster asset check --select validate_simulation_results
```

## Key Components

### Simulation Engine
- **Event Generation**: Probabilistic modeling of workforce transitions
- **Hazard Tables**: Risk models based on age, tenure, and job level
- **Multi-year Processing**: Cumulative simulation with state persistence

### Data Models
- **Staging**: `stg_census_data` - Clean employee master data
- **Intermediate**: Event generation models (`int_*_events`)
- **Marts**: Final outputs (`fct_workforce_snapshot`, `fct_yearly_events`)

### Analytics
- **Interactive Dashboard**: Streamlit-based scenario analysis
- **Comparative Analysis**: Multi-scenario comparison capabilities
- **Export Capabilities**: Data export for external reporting

## Configuration

### Simulation Parameters
Key configuration options in `config/simulation_config.yaml`:

- `start_year`, `end_year`: Simulation time range
- `target_growth_rate`: Annual workforce growth target
- `total_termination_rate`: Overall termination rate
- `new_hire_termination_rate`: First-year termination rate
- `random_seed`: For reproducible results

### Advanced Configuration
- **Hazard Multipliers**: Age and tenure-based risk adjustments
- **Promotion Matrices**: Level-to-level transition probabilities
- **Compensation Models**: Merit raise and promotion increase rules

## Data Quality & Testing

### dbt Tests
- **Schema Tests**: Data type and constraint validation
- **Custom Tests**: Business rule validation
- **Relationship Tests**: Referential integrity checks

### Dagster Asset Checks
- **Data Quality**: Row counts, null checks, distribution validation
- **Simulation Validation**: Growth rate verification, event consistency
- **Performance Monitoring**: Runtime and resource usage tracking

## Deployment

### Local Development
- Single-machine deployment with file-based DuckDB
- Dagster development server for interactive development
- Streamlit dashboard for immediate feedback

### Production Deployment
- On-premises Linux server deployment
- Persistent DuckDB database with backup procedures
- Process monitoring and automated restarts
- Access control and audit logging

## Performance Characteristics

### Scalability
- **Dataset Size**: Handle 100K+ employee records without memory errors
- **Simulation Runtime**: 5-year simulation in < 5 minutes for 10K employees
- **Query Performance**: < 2 seconds response time (95th percentile)
- **Concurrent Users**: Support 10 analysts simultaneously

### Resource Requirements
- **Memory**: < 8GB RAM peak during simulation
- **Storage**: ~1GB per 50,000 employees per simulation year
- **CPU**: Multi-threaded processing with configurable thread counts
- **Uptime**: 99.5% during business hours target

## Security & Compliance

### Data Security
- **On-premises Only**: No cloud data transfer
- **File-system Security**: Database access controls
- **PII Handling**: Configurable data masking and anonymization

### Audit & Compliance
- **Processing Logs**: Complete audit trail of all operations
- **Configuration Versioning**: Git-based parameter change tracking
- **Validation Records**: Data quality and business rule compliance

## Contributing

### Development Standards
- **Code Quality**: Type hints, comprehensive testing, documentation
- **SQL Style**: 2-space indentation, uppercase keywords, CTEs for readability
- **Asset Patterns**: Always return serializable objects from Dagster assets
- **Configuration**: Pydantic models for type-safe parameter validation

### Testing Requirements
- **dbt Models**: 90% test coverage with schema and custom tests
- **Python Code**: 95% line coverage with pytest
- **Integration Tests**: End-to-end simulation validation

## Troubleshooting

### Common Issues

#### DuckDB Serialization (CRITICAL)
```python
# ✅ CORRECT: DuckDB Asset Pattern
@asset
def workforce_data(context: AssetExecutionContext, duckdb: DuckDBResource) -> pd.DataFrame:
    with duckdb.get_connection() as conn:
        # Convert immediately to DataFrame - serializable
        df = conn.execute("SELECT * FROM employees").df()
        return df  # Safe to return

# ❌ WRONG: Never return DuckDB objects
@asset
def broken_asset():
    conn = duckdb.connect("db.duckdb")
    return conn.table("employees")  # DuckDBPyRelation - NOT SERIALIZABLE!
```

#### Connection Management
```python
# Always use context managers
with duckdb_resource.get_connection() as conn:
    result = conn.execute(query).df()
# Connection automatically closed
```

#### Configuration Validation
```python
# Use Pydantic for type safety
class SimulationConfig(BaseModel):
    start_year: int = Field(..., ge=2020, le=2050)
    target_growth_rate: float = Field(0.03, ge=-0.5, le=0.5)
```

#### Version Compatibility Issues
```python
# CRITICAL: Use only proven stable versions
# DuckDB 1.0.0, dbt-core 1.8.8, dbt-duckdb 1.8.1
# Dagster 1.8.12, Streamlit 1.39.0, Pydantic 2.7.4
# Lock all versions in requirements.txt
```

### Getting Help
- Check Dagster logs in the web interface
- Run `dbt debug` for connection issues
- Validate configuration with Pydantic models
- Review asset lineage in Dagster for dependency issues
- Ensure DAGSTER_HOME is set: `launchctl getenv DAGSTER_HOME`

## Further Reading

- [dbt Documentation](https://docs.getdbt.com/)
- [Dagster Documentation](https://docs.dagster.io/)
- [DuckDB Documentation](https://duckdb.org/docs/)
- [Streamlit Documentation](https://docs.streamlit.io/)

---

**PlanWise Navigator** - Modern workforce simulation for strategic planning.
