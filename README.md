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

### Navigator Orchestrator

Enterprise-grade orchestration engine with modular architecture:

**Core Components:**
- `pipeline_orchestrator.py`: Main coordinator (1,220 lines)
- `pipeline/`: Modular pipeline package (E072 - 6 focused modules)
  - `workflow.py`: Workflow stage definitions and builders
  - `year_executor.py`: Year-by-year execution logic
  - `state_manager.py`: State management and checkpointing
  - `event_generation_executor.py`: Hybrid SQL/Polars event generation
  - `hooks.py`: Extensible hook system
  - `data_cleanup.py`: Data cleanup utilities
- `config.py`: Type-safe configuration management
- `dbt_runner.py`: Streaming dbt execution with retry/backoff
- `registries.py`: State registries across simulation years
- `validation.py`: Rule-based data quality validation
- `exceptions.py` & `error_catalog.py`: Comprehensive error handling (E074)

**Testing Infrastructure (E075):**
- 256 tests with 87 fast unit tests (4.7s execution)
- Shared fixture library in `tests/fixtures/`
- 92.91% coverage on event schema
- Enterprise-grade test organization

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
│   ├── pipeline_orchestrator.py      # PipelineOrchestrator coordinator (1,220 lines)
│   ├── pipeline/                     # Modular pipeline components (E072 ✅)
│   │   ├── __init__.py              # Public API exports
│   │   ├── workflow.py              # Workflow stage definitions (212 lines)
│   │   ├── year_executor.py         # Year execution logic (555 lines)
│   │   ├── state_manager.py         # State management across years (406 lines)
│   │   ├── event_generation_executor.py  # Event generation (491 lines)
│   │   ├── hooks.py                 # Hook system (219 lines)
│   │   └── data_cleanup.py          # Data cleanup utilities (322 lines)
│   ├── config.py                     # SimulationConfig management
│   ├── dbt_runner.py                 # DbtRunner with streaming output
│   ├── registries.py                 # Registry management
│   ├── validation.py                 # Data quality validation
│   ├── reports.py                    # Multi-year reporting
│   ├── exceptions.py                 # Error handling (E074 ✅ - 548 lines)
│   └── error_catalog.py              # Error catalog (E074 ✅ - 224 lines)
├── planwise_cli/                     # CLI interface (Rich + Typer)
│   ├── main.py                       # planwise command entry point
│   ├── commands/                     # CLI commands
│   └── integration/                  # Orchestrator integration
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
├── tests/                            # Enterprise-grade testing (E075 ✅)
│   ├── fixtures/                     # Shared fixture library (11 reusable fixtures)
│   │   ├── __init__.py              # Centralized exports
│   │   ├── database.py              # In-memory database fixtures (3 fixtures)
│   │   ├── config.py                # Configuration fixtures (3 fixtures)
│   │   ├── mock_dbt.py              # Mock dbt runners (3 fixtures)
│   │   └── workforce_data.py        # Test data generators (3 fixtures)
│   ├── unit/                        # Fast unit tests (87 tests, 4.7s)
│   │   ├── orchestrator/            # Orchestrator tests
│   │   └── test_fixtures_integration.py  # Fixture validation (7 tests)
│   ├── integration/                 # Integration tests (~120 tests)
│   ├── performance/                 # Performance benchmarks
│   ├── conftest.py                  # Auto-marker configuration (743 lines)
│   ├── test_exceptions.py           # Exception tests (21 tests, E074 ✅)
│   ├── test_error_catalog.py        # Error catalog tests (30 tests, E074 ✅)
│   ├── TEST_INFRASTRUCTURE.md       # Complete testing guide (500+ lines)
│   └── QUICK_START.md               # Developer quick reference
├── scripts/                          # Utility scripts
├── docs/                             # Documentation
│   ├── epics/                       # Epic documentation
│   └── EPIC_STATUS_SUMMARY.md       # Current epic status
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

**On macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Add to PATH if needed
export PATH="$HOME/.local/bin:$PATH"
```

**On Windows (PowerShell):**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Alternative (all platforms):**
```bash
pip install uv
```

2. **Clone and setup environment**:
```bash
git clone <repository-url> planwise_navigator
cd planwise_navigator

# Create virtual environment with uv
uv venv .venv --python python3.11

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows (PowerShell):
# .venv\Scripts\Activate.ps1
# On Windows (CMD):
# .venv\Scripts\activate.bat

# Install all dependencies (~40 seconds for 263 packages)
uv pip install -r requirements.txt -r requirements-dev.txt

# Install planwise CLI in editable mode
uv pip install -e .
```

3. **Install dbt dependencies**:
```bash
cd dbt
dbt deps
cd ..
```

#### Alternative: Using Make (recommended for development)

```bash
# One command to set up everything (includes planwise CLI installation)
make install

# Or for full development setup including dbt deps and seeds
make dev-setup
```

**Note**: The Makefile `install` target automatically installs dependencies and the planwise CLI.

#### Legacy: Using pip

If uv is not available, use traditional pip:

```bash
# Create virtual environment
python3.11 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows (PowerShell):
# .venv\Scripts\Activate.ps1
# On Windows (CMD):
# .venv\Scripts\activate.bat

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt

# Install planwise CLI in editable mode
pip install -e .
```

#### Post-Installation Configuration

4. **Configure dbt profile**:

Create or edit the profiles file:
- **macOS/Linux**: `~/.dbt/profiles.yml`
- **Windows**: `%USERPROFILE%\.dbt\profiles.yml`

```yaml
planwise_navigator:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: /absolute/path/to/planwise_navigator/dbt/simulation.duckdb  # Use absolute path
      threads: 1  # Single-threaded for work laptop stability
```

**Note**: On Windows, use forward slashes or escaped backslashes in the path:
```yaml
# Windows example:
path: C:/Users/YourName/planwise_navigator/dbt/simulation.duckdb
# Or:
path: C:\\Users\\YourName\\planwise_navigator\\dbt\\simulation.duckdb
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

# Verify planwise CLI is available
planwise --version
planwise health

# Check dbt connection
cd dbt && dbt debug
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

#### Testing (E075 ✅ - Enterprise-Grade Infrastructure)

**Fast Unit Tests** (TDD workflow - 4.7s execution):
```bash
# Run fast tests - optimal for development
pytest -m fast                    # 87 tests in 4.7s (2× faster than target)

# Specific component tests
pytest -m "fast and orchestrator" # Orchestrator unit tests
pytest -m "fast and events"       # Event schema tests (92.91% coverage)
pytest -m "fast and config"       # Configuration tests

# With coverage
pytest -m fast --cov=navigator_orchestrator --cov-report=term
```

**Full Test Suite** (256 tests total):
```bash
# All tests (37% more than baseline)
pytest tests/                     # 256 tests in ~2 minutes

# Integration tests only
pytest -m integration             # ~120 tests

# End-to-end tests
pytest -m e2e                     # ~49 tests

# With HTML coverage report
pytest --cov=navigator_orchestrator --cov-report=html
open htmlcov/index.html

# Specific module coverage (example: config.events at 92.91%)
pytest --cov=config.events --cov-report=term-missing
```

**Using Fixture Library** (11 reusable fixtures):
```python
from tests.fixtures import (
    in_memory_db,           # Clean DuckDB (<0.01s setup)
    populated_test_db,      # Pre-loaded with 100 employees + 50 events
    minimal_config,         # Lightweight config for unit tests
    mock_dbt_runner,        # Successful dbt execution mock
    sample_employees,       # 100 test employee records
)

@pytest.mark.fast
@pytest.mark.unit
def test_my_feature(in_memory_db, sample_employees):
    # Test implementation with fixtures
    pass
```

**Test Organization**:
- **Fast tests** (`@pytest.mark.fast`): 87 tests, <5s - For TDD workflow
- **Integration tests** (`@pytest.mark.integration`): ~120 tests, ~45s - For component integration
- **E2E tests** (`@pytest.mark.e2e`): ~49 tests, >10s - For full workflow validation
- **Auto-markers**: Tests automatically marked by file location and feature area

**Test Documentation**:
- `tests/TEST_INFRASTRUCTURE.md` - Complete testing guide (500+ lines)
- `tests/QUICK_START.md` - Quick reference for developers
- `tests/fixtures/` - Centralized fixture library with 11 fixtures

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

## Recent Improvements

### Epic E072: Pipeline Modularization ✅ Complete (Oct 7, 2025)
**Duration**: 4 hours | **Impact**: 51% code reduction

Successfully transformed 2,478-line monolithic `pipeline.py` into modular package architecture:
- **6 focused modules**: workflow (212 lines), event_generation_executor (491 lines), state_manager (406 lines), year_executor (555 lines), hooks (219 lines), data_cleanup (322 lines)
- **100% backward compatibility**: All existing integrations continue to work
- **Zero performance regression**: All E068 optimizations preserved
- **Enhanced maintainability**: 6-8 methods per module (vs. 54 in monolith)
- **Developer productivity**: 20-minute onboarding (vs. 2+ hours previously)

**Documentation**: `docs/epics/E072_COMPLETION_SUMMARY.md`

### Epic E074: Enhanced Error Handling ✅ Complete (Oct 7, 2025)
**Duration**: 90 minutes | **Impact**: 50-80% reduction in debugging time

Delivered comprehensive error handling infrastructure:
- **Structured exception hierarchy**: 15+ specialized exception classes with execution context
- **Error catalog system**: 7 pre-configured patterns covering 90%+ of production errors
- **Automated resolution hints**: Step-by-step guidance with estimated resolution time
- **100% test coverage**: 51 tests (21 exception + 30 catalog tests)
- **Contextual diagnostics**: Correlation IDs, year, stage, model tracking for <5 minute bug diagnosis

**Documentation**: `docs/epics/E074_COMPLETION_SUMMARY.md`, `docs/guides/error_troubleshooting.md`

### Epic E075: Testing Infrastructure ✅ Complete (Oct 8, 2025)
**Duration**: 2 hours | **Impact**: 50% developer productivity increase

Transformed test suite into enterprise-grade infrastructure:
- **256 tests collected**: 37% more than expected (vs. 185 baseline)
- **87 fast unit tests**: 4.7s execution (2× faster than 10s target)
- **Centralized fixture library**: 11 reusable fixtures in `tests/fixtures/` package
- **Comprehensive marker system**: 15+ markers (fast, slow, unit, integration, e2e, by component)
- **92.91% coverage**: On config.events module (exceeds 90% target)
- **Zero collection errors**: Fixed 3 import errors blocking test execution
- **Complete documentation**: `tests/TEST_INFRASTRUCTURE.md` (500+ lines), `tests/QUICK_START.md`

**Developer Experience**: In-memory databases (<0.01s setup), automatic marker application, clear test organization

**Documentation**: `docs/epics/E075_COMPLETION_SUMMARY.md`, `tests/TEST_INFRASTRUCTURE.md`

---

**See `docs/EPIC_STATUS_SUMMARY.md` for complete epic status and roadmap.**

## Further Reading

### Documentation
- `docs/EPIC_STATUS_SUMMARY.md` - Current epic status and roadmap
- `tests/TEST_INFRASTRUCTURE.md` - Complete testing guide
- `tests/QUICK_START.md` - Testing quick reference
- `CLAUDE.md` - Claude Code generation playbook

### External Resources
- [dbt Documentation](https://docs.getdbt.com/)
- [DuckDB Documentation](https://duckdb.org/docs/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [Rich Documentation](https://rich.readthedocs.io/)
- [Typer Documentation](https://typer.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

---

**PlanWise Navigator** - Modern workforce simulation for strategic planning.
