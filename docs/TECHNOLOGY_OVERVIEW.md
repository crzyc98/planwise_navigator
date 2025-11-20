# PlanAlign Studio - Technology Overview

## Executive Summary

**PlanAlign Studio** is an enterprise-grade, on-premises workforce simulation platform that replaces legacy spreadsheet-based planning with an immutable event-sourced architecture. Built on modern analytical technologies (DuckDB, dbt, Python), it provides strategic workforce planning capabilities with complete audit trails, scenario analysis, and regulatory compliance.

## Business Value

### Problem Statement
Traditional workforce planning relies on brittle spreadsheets that lack:
- **Auditability**: No trail of who changed what and when
- **Reproducibility**: Inconsistent results across analysts
- **Scalability**: Performance degrades with 10K+ employees
- **Transparency**: Black-box formulas with hidden assumptions
- **Compliance**: Insufficient audit trails for regulatory requirements

### Solution
PlanAlign Studio delivers a "workforce time machine" that:
- **Records every event**: Complete immutable history of all workforce transitions
- **Enables instant replay**: Reconstruct workforce state at any point in time
- **Supports scenario analysis**: Compare unlimited "what-if" scenarios side-by-side
- **Provides full transparency**: Every decision traceable with UUID-stamped audit trail
- **Ensures compliance**: Regulatory-ready audit logs and validation reports
- **Scales efficiently**: Handle 100K+ employees without performance degradation

### ROI Benefits
- **50-80% reduction** in time to diagnose planning errors
- **2-10x faster** multi-year simulation execution (150s vs. 285-1500s)
- **99.5% uptime** target during business hours
- **<2 second** dashboard query response time (95th percentile)
- **100% reproducibility** with deterministic random seed control

## Technical Architecture

### High-Level Design

```
┌─────────────────┐
│  Raw Census     │
│  Data (CSV)     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│              dbt Staging Layer                      │
│  (Data validation, cleaning, type conversion)       │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│          Event Generation Engines                   │
│  ┌──────────────┐  ┌──────────────┐               │
│  │ Compensation │  │ Termination  │               │
│  │   Engine     │  │   Engine     │               │
│  └──────────────┘  └──────────────┘               │
│  ┌──────────────┐  ┌──────────────┐               │
│  │    Hiring    │  │  Promotion   │               │
│  │    Engine    │  │   Engine     │               │
│  └──────────────┘  └──────────────┘               │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│         Immutable Event Store                       │
│  (UUID-stamped events: HIRE, TERMINATION,          │
│   PROMOTION, RAISE, ENROLLMENT, CONTRIBUTION)       │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│      State Reconstruction & Snapshots               │
│  (Point-in-time workforce states from events)       │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│    Analytics & Reporting Layer                     │
│  (Streamlit dashboards, Excel exports)             │
└─────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Version | Purpose | Why Chosen |
|-------|------------|---------|---------|------------|
| **Storage** | DuckDB | 1.0.0 | In-process OLAP database | Zero administration, column-store performance, ACID compliance |
| **Transformation** | dbt-core | 1.8.8 | SQL modeling framework | Declarative SQL, version control, automatic lineage |
| **Adapter** | dbt-duckdb | 1.8.1 | DuckDB integration | Stable dbt-to-DuckDB bridge |
| **Orchestration** | navigator_orchestrator | Custom | Pipeline execution engine | Multi-year workflows, checkpointing, state management |
| **CLI** | Rich + Typer | 13.x / 0.9.x | Command-line interface | Beautiful terminal UI, progress tracking |
| **Dashboard** | Streamlit | 1.39.0 | Interactive analytics | Rapid prototyping, Python-native, self-service |
| **Configuration** | Pydantic | 2.7.4 | Type-safe config | Runtime validation, IDE autocomplete |
| **Runtime** | Python | 3.11.x | Execution environment | Long-term support, performance improvements |
| **Package Manager** | uv | Latest | Dependency management | 10-100x faster than pip |

### Event Sourcing Architecture

**Core Principle**: Instead of updating employee records in-place, PlanAlign Studio records every workforce transition as an immutable event.

**Event Types**:
- **HIRE**: New employee onboarding
- **TERMINATION**: Employee departures (voluntary, involuntary)
- **PROMOTION**: Level/band changes
- **RAISE**: Salary adjustments (COLA, merit, market)
- **DC_PLAN_ENROLLMENT**: Retirement plan participation
- **DC_PLAN_CONTRIBUTION**: Employee/employer contributions
- **DC_PLAN_VESTING**: Vesting schedule progression
- **HCE_STATUS**: Highly Compensated Employee determination

**Benefits**:
1. **Complete Audit Trail**: Every event has UUID, timestamp, and full context
2. **Time Travel**: Reconstruct workforce at any historical point
3. **Scenario Isolation**: Each scenario has independent event stream
4. **Reproducibility**: Same seed → identical event sequence
5. **Compliance**: Immutable logs satisfy regulatory requirements

### Data Model

```sql
-- Immutable event store
fct_yearly_events (
  event_id UUID PRIMARY KEY,
  employee_id TEXT,
  scenario_id TEXT,
  plan_design_id TEXT,
  simulation_year INT,
  event_type TEXT,
  effective_date DATE,
  event_payload STRUCT,
  created_at TIMESTAMP
)

-- Point-in-time workforce snapshots (reconstructed from events)
fct_workforce_snapshot (
  snapshot_id UUID,
  employee_id TEXT,
  scenario_id TEXT,
  simulation_year INT,
  snapshot_date DATE,
  department TEXT,
  job_level INT,
  annual_compensation DECIMAL,
  tenure_years DECIMAL,
  -- ... 20+ additional attributes
)
```

### Pipeline Orchestration

The **navigator_orchestrator** package executes multi-year simulations through staged workflows:

**Workflow Stages** (sequential execution per year):
1. **INITIALIZATION**: Load seed data and configuration
2. **FOUNDATION**: Build baseline workforce from census
3. **EVENT_GENERATION**: Create hire/termination/promotion events
4. **STATE_ACCUMULATION**: Build temporal state accumulators
5. **VALIDATION**: Run data quality checks
6. **REPORTING**: Generate audit reports and metrics

**Modular Architecture** (E072 refactoring):
- `workflow.py`: Stage definitions and workflow building (212 lines)
- `year_executor.py`: Stage-by-stage execution orchestration (555 lines)
- `state_manager.py`: Checkpoint and state management (406 lines)
- `event_generation_executor.py`: Hybrid SQL/Polars event generation (491 lines)
- `hooks.py`: Extensible callback system (219 lines)
- `data_cleanup.py`: Database cleanup operations (322 lines)

**Result**: 51% code reduction from 2,478-line monolith to 1,220-line coordinator with 6 focused modules.

## System Capabilities

### Multi-Year Simulation
- **Temporal State Tracking**: Year N reads Year N-1 accumulator + Year N events
- **Cross-Year Dependencies**: Promotions, vesting, tenure calculations
- **Checkpoint Recovery**: Resume interrupted simulations from last successful stage
- **Performance Optimized**: 5-year simulation in 150 seconds (2x improvement from E068)

### Batch Scenario Processing
```bash
# Run multiple scenarios with Excel export
planwise batch --scenarios baseline high_growth cost_control --export-format excel
```

**Output Structure**:
```
outputs/batch_YYYYMMDD_HHMMSS/
├── baseline/
│   ├── baseline.duckdb           # Isolated scenario database
│   ├── baseline_export.xlsx      # Excel with 6 sheets:
│   │                             #  - Workforce Snapshot
│   │                             #  - Headcount Metrics
│   │                             #  - Event Summary
│   │                             #  - Scenario Metadata
│   │                             #  - Configuration
│   │                             #  - Git Information
├── high_growth/
│   └── high_growth.duckdb
└── comparison_report.xlsx        # Cross-scenario comparison
```

### Data Quality & Validation
- **106 dbt tests** across 3 layers (staging, intermediate, marts)
- **256 Python tests** with 87 fast unit tests (4.7s execution)
- **Built-in validation**: Automated checks during pipeline execution
- **Error catalog**: Pre-configured patterns for 90%+ of production errors
- **92.91% test coverage** on event schema module

### Interactive Analytics
- **Streamlit Dashboard**: Self-service scenario exploration
- **Compensation Tuning**: Interactive parameter adjustment
- **Sub-2-second queries**: Optimized DuckDB column-store performance
- **Excel Export**: Multi-sheet workbooks with metadata and git provenance

## Deployment Architecture

### Local Development
```bash
# Environment setup with uv (10-100x faster than pip)
uv venv .venv --python python3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# Quick validation
planwise health                   # System readiness check

# Multi-year simulation
planwise simulate 2025-2027       # 3-year forecast

# Batch scenarios
planwise batch --scenarios baseline high_growth
```

### Production Deployment (On-Premises)

**Infrastructure Requirements**:
- **OS**: Linux server (RHEL, Ubuntu, CentOS)
- **CPU**: 4+ cores recommended
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 10GB + (1GB per 50K employees per year)
- **Network**: On-premises only (zero cloud dependencies)

**Deployment Pattern**:
```bash
# System service (systemd)
[Unit]
Description=PlanAlign Studio Scheduler
After=network.target

[Service]
Type=simple
User=planwise
WorkingDirectory=/opt/planwise_navigator
ExecStart=/opt/planwise_navigator/.venv/bin/planwise simulate 2025-2030
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**Automation**:
```cron
# Daily baseline simulation (5am)
0 5 * * * /opt/planwise_navigator/.venv/bin/planwise simulate 2025-2030 --verbose >> /var/log/planwise/daily.log 2>&1

# Weekly batch scenarios (Sunday 2am)
0 2 * * 0 /opt/planwise_navigator/.venv/bin/planwise batch --clean --export-format excel >> /var/log/planwise/batch.log 2>&1
```

### Security & Compliance

**Data Security**:
- **On-premises only**: No cloud data transfer
- **File-system ACLs**: Database access via OS permissions
- **PII controls**: Configurable anonymization rules
- **Encrypted at rest**: Leverage OS-level encryption

**Audit & Compliance**:
- **Immutable event log**: Complete audit trail
- **Git-tracked configuration**: Version control on all parameters
- **Execution logging**: Correlation IDs, timestamps, user tracking
- **Validation records**: Data quality and business rule compliance reports

## Performance Characteristics

### Scalability Metrics
| Metric | Target | Actual (E068) |
|--------|--------|---------------|
| 5-year simulation (10K employees) | <5 minutes | 150 seconds |
| Dashboard query (95th percentile) | <2 seconds | 1.2 seconds |
| Memory usage (100K employees) | <8GB RAM | 6.4GB peak |
| Concurrent dashboard users | 10+ | 15 tested |

### Optimization Results (E068 - Performance Epic)
- **Baseline**: 285 seconds (Pandas-based pipeline)
- **Optimized**: 150 seconds (2x improvement with DuckDB push-down)
- **Polars Mode**: 0.76 seconds (375x improvement - experimental)

**Optimizations Applied**:
1. Predicate push-down to DuckDB (filter early)
2. Incremental materialization with `delete+insert` strategy
3. Single-threaded execution for stability
4. Temporal filtering by `simulation_year` variable
5. State accumulator pattern (avoid cross-year joins)

## Development & Testing

### Testing Infrastructure (E075)
```bash
# Fast unit tests (TDD workflow)
pytest -m fast                    # 87 tests in 4.7s

# Full test suite
pytest                            # 256 tests in ~2 minutes

# With coverage
pytest --cov=navigator_orchestrator --cov-report=html
```

**Fixture Library** (`tests/fixtures/`):
- `in_memory_db`: Clean DuckDB (<0.01s setup)
- `populated_test_db`: Pre-loaded with 100 employees + 50 events
- `minimal_config`: Lightweight config for unit tests
- `mock_dbt_runner`: Successful dbt execution mock
- `sample_employees`: 100 test employee records

### Error Handling (E074)
```python
from navigator_orchestrator.exceptions import (
    NavigatorError,      # Base with execution context
    DbtError,            # dbt command failures
    DatabaseError,       # Database operations
    PipelineError        # Pipeline execution
)

try:
    orchestrator.execute_year(2025)
except DbtError as e:
    print(f"Error: {e.message}")
    print(f"Stage: {e.context.stage}")
    print(f"Resolution: {e.resolution_hint}")  # Automated guidance
```

**Benefits**:
- **50-80% reduction** in debugging time
- **<5 minute** bug diagnosis with correlation IDs
- **90%+ error coverage** with pre-configured catalog patterns

### CI/CD Workflow
```bash
# Pre-commit validation
./scripts/run_ci_tests.sh

# Validates:
# - Python imports and critical linting
# - dbt model compilation
# - dbt fast tests (<1min)
# - Core business model validation
```

## Project Status

### Completed Epics (Production-Ready)
- ✅ **E068**: Performance Optimization - 2x improvement
- ✅ **E069**: Batch Scenario Processing - Excel export with metadata
- ✅ **E072**: Pipeline Modularization - 51% code reduction
- ✅ **E074**: Enhanced Error Handling - Context-rich diagnostics
- ✅ **E075**: Testing Infrastructure - 256 tests, 90%+ coverage
- ✅ **E023**: Enrollment Architecture Fix - Temporal state accumulators
- ✅ **E078**: Cohort Pipeline Integration - Polars event factory

### In Progress
- 🟡 **E021-A**: DC Plan Event Schema Foundation (81% complete)
  - ✅ Core Event Model, Workforce Events, DC Plan Events, Plan Administration
  - ❌ Loan & Investment Events, ERISA Compliance Review (outstanding)

### Technology Debt
- ⚠️ **E079**: Performance Architectural Simplification - BLOCKED
  - 60% regression detected (261s → 419s)
  - Investigation required before proceeding

## System Requirements

### Minimum Requirements
- **Python**: 3.11+ (CPython recommended)
- **OS**: Linux, macOS, Windows (WSL recommended)
- **RAM**: 8GB
- **Storage**: 10GB free space
- **Network**: On-premises only (no cloud dependencies)

### Recommended Setup
- **Python**: 3.11.x (long-term support)
- **OS**: Linux (RHEL 8+, Ubuntu 22.04+)
- **RAM**: 16GB
- **CPU**: 4+ cores
- **Storage**: SSD with 50GB+ free space
- **Database**: Single DuckDB file on local/network filesystem

## Getting Started

### Quick Start (5 Minutes)
```bash
# 1. Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone and setup
git clone <repository-url> planwise_navigator
cd planwise_navigator
uv venv .venv --python python3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# 3. Verify installation
planwise health

# 4. Run first simulation
planwise simulate 2025 --verbose
```

### Resources
- **Documentation**: `docs/` directory
- **Testing Guide**: `tests/TEST_INFRASTRUCTURE.md`
- **Troubleshooting**: `docs/guides/error_troubleshooting.md`
- **Development Guide**: `CLAUDE.md`

## Support & Troubleshooting

### Common Commands
```bash
planwise health                   # Quick diagnostic
planwise status --detailed        # Full system status
planwise validate                 # Configuration validation
planwise checkpoints list         # View recovery points
dbt debug                         # Database connection test
```

### Common Issues
1. **Database locks**: Close IDE database connections before simulation
2. **Virtual environment**: Always activate `.venv` before running commands
3. **Path issues**: Use `get_database_path()` helper for database access
4. **Configuration errors**: Run `planwise validate` to check YAML syntax

## Summary

**PlanAlign Studio** transforms workforce planning from error-prone spreadsheets to an enterprise-grade event-sourced platform with:

- **Complete auditability** through immutable event logs
- **Scenario time-machine** capabilities for instant replay
- **2-375x performance** improvements over legacy pipelines
- **Production-ready** deployment with 256 tests and 90%+ coverage
- **On-premises security** with zero cloud dependencies
- **Regulatory compliance** with comprehensive audit trails

**Technology Foundation**: Modern analytical stack (DuckDB, dbt, Python 3.11) optimized for OLAP workloads, with modular architecture enabling rapid feature development and maintenance.

---

**Document Version**: 1.0
**Last Updated**: November 2025
**Contact**: See `pyproject.toml` for author information
