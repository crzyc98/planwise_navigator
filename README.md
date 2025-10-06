# PlanWise Navigator

**An enterprise-grade, on-premises workforce simulation platform with immutable event sourcing, built on DuckDB, dbt, Dagster, and Streamlit.**

## Overview

PlanWise Navigator represents a paradigm shift from rigid spreadsheets to a dynamic, fully transparent simulation engine—essentially a workforce "time machine" that captures every employee lifecycle event with UUID-stamped precision and enables instant scenario replay.

This enterprise-grade platform replaces legacy Pandas-based pipelines with an immutable event-sourced architecture optimized for analytical workloads, audit trails, and regulatory compliance.

### Key Features

- **Immutable Event Sourcing**: Every workforce event permanently recorded with UUID and timestamp
- **Enhanced Multi-year Simulation**: True multi-year workforce transitions with data persistence
- **Data Persistence Architecture**: Table-based materialization prevents data loss across years
- **Selective Data Management**: Preserve existing data or selectively clear specific years
- **Modular Architecture**: Single-responsibility engines for compensation, termination, hiring, and promotions
- **Interactive Analytics**: Sub-2-second dashboard queries for scenario analysis
- **Audit Trail Transparency**: Complete workforce history reconstruction from event logs
- **Scenario Time Machine**: Instantly replay and compare multiple simulation scenarios
- **Enhanced Validation**: Comprehensive data quality checks and fallback mechanisms
- **Enterprise Security**: Zero cloud dependencies, comprehensive audit logging
- **Reproducible Results**: Random seed control for identical simulation outcomes
- **Scalable Performance**: Handle 100K+ employee records with minimal memory footprint

### Navigator Orchestrator (S038)

This repo includes a lightweight orchestrator package under `navigator_orchestrator/` to standardize configuration, dbt execution, registry management, and data validation:

- `config`: Typed loader and `to_dbt_vars` mapping
- `utils`: DB connection manager, execution mutex, timers
- `dbt_runner`: Streaming dbt execution with retry/backoff
- `registries`: Enrollment and deferral escalation registries
- `validation`: Rule-based validation with built-in checks

See `navigator_orchestrator/README.md` for usage, and the stories under `docs/stories/` (S038-01…S038-04) for details.

## Technology Stack

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| **Storage** | DuckDB | 1.0.0 | Immutable event store; in-process OLAP engine |
| **Transformation** | dbt-core | 1.8.8 | SQL-based data modeling and testing |
| **Adapter** | dbt-duckdb | 1.8.1 | Stable DuckDB integration |
| **Orchestration** | navigator_orchestrator | Custom | Multi-year pipeline orchestration with checkpoints |
| **CLI Interface** | planwise (Rich + Typer) | 1.0.0 | Beautiful terminal interface with progress tracking |
| **Dashboard** | Streamlit | 1.39.0 | Interactive analytics interface |
| **Configuration** | Pydantic | 2.7.4 | Type-safe parameter management |
| **Python** | CPython | 3.11.x | Long-term support version |

## Architecture

### Event-Sourced Data Flow
```
Raw Census Data → Staging Models → Event Generation → Immutable Event Store → Snapshots → Dashboard
                     (stg_*)         (Modular Engines)   (fct_yearly_events)   (point-in-time)
```

### Data Flow
1. **Staging Layer**: Clean and validate raw employee master data
2. **Event Generation**: Modular engines create immutable workforce events (UUID-stamped)
3. **Event Store**: Permanent, tamper-proof audit trail in `fct_yearly_events`
4. **Snapshot Layer**: Point-in-time workforce states reconstructed from events
5. **Dashboard Layer**: Interactive scenario analysis with time-machine capabilities

### Modular Engine Architecture
- **Compensation Engine**: COLA, merit, and promotion-based salary adjustments
- **Termination Engine**: Hazard-based turnover modeling with age/tenure factors
- **Hiring Engine**: Growth-driven recruitment with realistic demographic sampling
- **Promotion Engine**: Band-aware advancement with configurable probabilities

## Directory Structure

```
planwise_navigator/
├── navigator_orchestrator/           # Production orchestration engine
│   ├── pipeline.py                   # PipelineOrchestrator main class
│   ├── config.py                     # SimulationConfig management
│   ├── dbt_runner.py                 # DbtRunner with streaming output
│   ├── registries.py                 # State management across years
│   ├── validation.py                 # Data quality validation
│   └── reports.py                    # Multi-year reporting
├── planwise_cli/                     # CLI interface (Rich + Typer)
│   └── main.py                       # planwise command entry point
├── dbt/                              # dbt project
│   ├── models/                       # SQL transformation models
│   │   ├── staging/                  # Raw data cleaning (stg_*)
│   │   ├── intermediate/             # Business logic (int_*)
│   │   │   ├── events/               # Event generation models
│   │   │   └── accumulators/         # State accumulators
│   │   └── marts/                    # Final outputs (fct_*, dim_*)
│   ├── seeds/                        # Configuration data (CSV)
│   ├── macros/                       # Reusable SQL functions
│   └── simulation.duckdb             # DuckDB database (standardized location)
├── streamlit_dashboard/              # Interactive dashboard
│   ├── main.py                       # Main dashboard
│   └── pages/                        # Dashboard pages
│       └── 1_Compensation_Tuning.py  # Compensation tuning interface
├── config/                           # Configuration management
│   ├── simulation_config.yaml        # Simulation parameters
│   ├── schema.py                     # Legacy event schema (Pydantic v1)
│   └── events.py                     # Unified event model (Pydantic v2)
├── scripts/                          # Utility scripts
├── tests/                            # Comprehensive testing
└── data/                             # Raw input files (git-ignored)
```

## Getting Started

### Prerequisites

- **Python 3.11+** (CPython 3.11.x recommended)
- **uv** package manager (optional but recommended for 10× faster installs)
- Access to raw employee census data
- On-premises deployment environment

### Installation

#### Recommended: Using uv (10× faster)

**uv** is a blazing-fast Python package installer built in Rust. Installation takes ~40 seconds instead of 5+ minutes.

1. **Install uv**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Add to PATH if needed
export PATH="$HOME/.local/bin:$PATH"
```

2. **Clone and setup environment**:
```bash
git clone <repository-url> planwise_navigator
cd planwise_navigator

# Create virtual environment with uv
uv venv .venv --python python3.11
source .venv/bin/activate

# Install all dependencies (~40 seconds for 263 packages)
uv pip install -r requirements.txt -r requirements-dev.txt
```

3. **Install dbt dependencies**:
```bash
cd dbt
dbt deps
cd ..
```

#### Alternative: Using Make (recommended for development)

```bash
# One command to set up everything
make install

# Or for full development setup including dbt deps and seeds
make dev-setup
```

#### Legacy: Using pip

If uv is not available, use traditional pip:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
```

#### Post-Installation Configuration

4. **Configure dbt profile** at `~/.dbt/profiles.yml`:
```yaml
planwise_navigator:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: /absolute/path/to/planwise_navigator/dbt/simulation.duckdb
      threads: 1  # Single-threaded for work laptop stability
```

5. **Configure simulation parameters** in `config/simulation_config.yaml`:
```yaml
start_year: 2025
end_year: 2029
target_growth_rate: 0.03
total_termination_rate: 0.12
new_hire_termination_rate: 0.25
random_seed: 42

multi_year:
  optimization:
    level: "medium"        # For work laptops
    max_workers: 1         # Single-threaded
    batch_size: 500
```

6. **Verify installation**:
```bash
# Test Python imports
python -c "import duckdb, dbt, streamlit, pydantic, rich, typer; print('✅ Installation successful!')"

# Check dbt
cd dbt && dbt debug

# Test planwise CLI
planwise health
```

### Running the Platform

#### Option 1: Using planwise CLI (Recommended)

The **planwise** CLI provides a beautiful, user-friendly interface with progress bars and enhanced feedback.

```bash
# Quick system health check
planwise health

# Run multi-year simulation with progress tracking
planwise simulate 2025-2027 --verbose

# Resume from checkpoint after interruption
planwise simulate 2025-2027 --resume

# Preview execution plan (dry run)
planwise simulate 2025-2026 --dry-run

# Run batch scenarios with Excel export
planwise batch --scenarios baseline high_growth
planwise batch --export-format excel --clean

# Validate configuration
planwise validate

# Manage checkpoints
planwise checkpoints list
planwise checkpoints status
planwise checkpoints cleanup --keep 3
```

#### Option 2: Using Python API directly

For programmatic access or advanced control:

```bash
# Single-year simulation
python -m navigator_orchestrator run --years 2025 --threads 1 --verbose

# Multi-year simulation (work laptop optimized)
python -m navigator_orchestrator run --years 2025 2026 2027 --threads 1 --optimization medium

# Batch scenario processing
python -m navigator_orchestrator batch --scenarios baseline high_growth cost_control
python -m navigator_orchestrator batch --clean --export-format excel
```

#### Option 3: Using dbt directly (Development)

For testing specific models or debugging:

```bash
cd dbt

# Build foundation models for a specific year
dbt run --select tag:foundation --vars '{simulation_year: 2025}' --threads 1

# Generate events for a specific year
dbt run --select tag:EVENT_GENERATION --vars '{simulation_year: 2025}' --threads 1

# Build complete pipeline for a year
dbt build --vars '{simulation_year: 2025}' --threads 1
```

#### Launch Interactive Dashboards

```bash
# Main dashboard (port 8501)
streamlit run streamlit_dashboard/main.py

# Compensation tuning interface (port 8502)
streamlit run streamlit_dashboard/pages/1_Compensation_Tuning.py --server.port 8502

# Or use Make shortcuts
make run-dashboard
make run-compensation-tuning
```

### Development Workflow

#### Pre-Commit Validation
**Always run the CI script before committing changes:**
```bash
# Run comprehensive validation suite
./scripts/run_ci_tests.sh

# Expected output:
# ✅ Python import validation passed
# ✅ Ruff linting (critical errors only) passed
# ✅ dbt compilation passed
# ✅ dbt fast tests passed
# ✅ All CI tests passed! 🎉
```

The CI script performs:
- **Python validation**: Import checks and critical error linting
- **dbt compilation**: Ensures all models compile successfully
- **Fast tests**: Runs dbt tests (excluding slow/long-running ones)
- **Critical model validation**: Tests core business models
- **Configuration validation**: Checks YAML configuration files

**Performance**: Completes in under 2 minutes for optimal developer productivity.

#### dbt Development
```bash
cd dbt

# Run all models for a year
dbt run --vars '{simulation_year: 2025}' --threads 1

# Run specific layer
dbt run --select staging --threads 1
dbt run --select tag:foundation --vars '{simulation_year: 2025}' --threads 1

# Run tests
dbt test --threads 1
dbt test --select tag:data_quality

# Generate and serve documentation
dbt docs generate
dbt docs serve
```

#### Orchestrator Development
```bash
# Test single-year execution
python -m navigator_orchestrator run --years 2025 --threads 1 --verbose

# Test multi-year execution with checkpoints
python -m navigator_orchestrator run --years 2025 2026 --threads 1 --optimization medium

# Validate configuration
python -c "
from navigator_orchestrator.config import load_simulation_config
config = load_simulation_config('config/simulation_config.yaml')
print('✅ Configuration valid!')
"

# Test batch processing
python -m navigator_orchestrator batch --scenarios baseline --verbose
```

## Key Components

### Event Sourcing Engine
- **Immutable Events**: UUID-stamped workforce transitions (HIRE, TERMINATION, PROMOTION, RAISE)
- **Audit Trail**: Complete historical record for regulatory compliance and auditing
- **Snapshot Reconstruction**: Any point-in-time workforce state rebuilt from event log
- **Reproducible Scenarios**: Identical results with same random seed for validation

### Modular Simulation Architecture
- **Compensation Engine**: Multi-tier salary adjustments (COLA, merit, promotion-based)
- **Termination Engine**: Sophisticated hazard modeling with age/tenure/level factors
- **Hiring Engine**: Growth-driven recruitment with realistic demographic sampling
- **Promotion Engine**: Band-aware advancement with configurable transition matrices

### Data Models
- **Staging**: `stg_census_data` - Clean employee master data with schema validation
- **Events**: `fct_yearly_events` - Immutable event store with UUID and timestamp
- **Snapshots**: `fct_workforce_snapshot` - Point-in-time reconstructed workforce states
- **Analytics**: Derived metrics and trend analysis for strategic planning

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
- **Schema Tests**: Data type and constraint validation (90% coverage target)
- **Custom Tests**: Business rule validation
- **Relationship Tests**: Referential integrity checks
- **Data Quality Tags**: Models tagged with `tag:data_quality`

### Navigator Orchestrator Validation
- **Built-in Validation**: Automatic data quality checks during pipeline execution
- **Rule-based Validation**: Configurable validation rules with thresholds
- **Row Count Validation**: Detect unexpected data loss or duplication
- **Distribution Validation**: Statistical tests for data drift detection
- **Event Consistency**: Verify event sequences and state transitions

### Python Testing (pytest)
- **Unit Tests**: Individual component testing (95% line coverage target)
- **Integration Tests**: End-to-end simulation validation
- **Performance Tests**: Runtime and resource usage benchmarks
- **Validation Framework**: Golden dataset testing for regression detection

## Deployment

### Local Development
- Single-machine deployment with file-based DuckDB
- planwise CLI for interactive simulation execution
- Streamlit dashboard for immediate feedback and compensation tuning
- Checkpoint-based resumability for long-running simulations

### Production Deployment
- **On-premises Linux server** deployment (no cloud dependencies)
- **Persistent DuckDB database** with automated backup procedures
- **Process monitoring**: systemd services or supervisor for automated restarts
- **CLI-based automation**: Cron jobs or scheduled tasks using planwise CLI
- **Batch processing**: Multi-scenario execution with Excel export for reporting
- **Access control**: File-system permissions and audit logging
- **Resource optimization**: Single-threaded execution for stability on work laptops

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
- **Code Quality**: Type hints, comprehensive testing, docstrings
- **SQL Style**: 2-space indentation, uppercase keywords, CTEs for readability
- **Python Style**: PEP 8, keep functions under 40 lines, explicit exceptions
- **Configuration**: Pydantic v2 models for type-safe parameter validation
- **Event Sourcing**: Immutable events with UUID and timestamp, discriminated unions
- **State Management**: Use state accumulators, avoid circular dependencies

### Testing Requirements
- **dbt Models**: 90% test coverage with schema and custom tests
- **Python Code**: 95% line coverage with pytest
- **Integration Tests**: End-to-end simulation validation

## Troubleshooting

### Common Issues

#### DuckDB Connection Management
```python
# ✅ CORRECT: Use get_database_path helper
from navigator_orchestrator.config import get_database_path
import duckdb

conn = duckdb.connect(str(get_database_path()))
try:
    result = conn.execute("SELECT * FROM fct_yearly_events").df()
    # Process result
finally:
    conn.close()

# Or use context manager (if available)
with duckdb.connect(str(get_database_path())) as conn:
    result = conn.execute(query).df()
```

#### Multi-Year State Management
```python
# ✅ CORRECT: Use state accumulators for cross-year data
# Year N reads Year N-1 accumulator + Year N events
# Example: int_enrollment_state_accumulator, int_deferral_rate_state_accumulator

# ❌ WRONG: Don't create circular dependencies
# int_* models should NEVER read from fct_* models
```

#### Configuration Validation
```python
# Use Pydantic for type safety
class SimulationConfig(BaseModel):
    start_year: int = Field(..., ge=2020, le=2050)
    target_growth_rate: float = Field(0.03, ge=-0.5, le=0.5)
```

#### Version Compatibility Issues
```bash
# CRITICAL: Use only proven stable versions
# DuckDB 1.0.0, dbt-core 1.8.8, dbt-duckdb 1.8.1
# Streamlit 1.39.0, Pydantic 2.7.4
# Rich 13.0.0+, Typer 0.9.0+
# All versions locked in requirements.txt and pyproject.toml
```

#### CI Script Issues
```bash
# If CI script fails, common fixes:
# 1. Install development tools
pip install -r requirements-dev.txt

# 2. Fix Python linting errors
ruff check orchestrator/ streamlit_dashboard/
# Fix imports and syntax issues

# 3. Fix dbt compilation errors
cd dbt && dbt compile
# Check model syntax and dependencies

# 4. dbt test failures
dbt test --exclude tag:slow
# Review test failures and fix data issues

# 5. Missing virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Getting Help
- Run `planwise health` for system diagnostics
- Run `planwise status --detailed` for full system status
- Check `dbt debug` for database connection issues
- Validate configuration: `planwise validate`
- Review orchestrator logs in terminal output with `--verbose` flag
- Check checkpoint status: `planwise checkpoints status`
- **CI Issues**: Run `./scripts/run_ci_tests.sh` for detailed error messages
- **Database Issues**: Verify database path with `python -c "from navigator_orchestrator.config import get_database_path; print(get_database_path())"`

## Further Reading

- [dbt Documentation](https://docs.getdbt.com/)
- [DuckDB Documentation](https://duckdb.org/docs/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [Rich Documentation](https://rich.readthedocs.io/)
- [Typer Documentation](https://typer.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

---

**PlanWise Navigator** - Modern workforce simulation for strategic planning.
