# Orchestrator MVP - Claude Development Guide

A modular, interactive tool for debugging dbt models and running comprehensive workforce simulations with systematic checklist enforcement for PlanWise Navigator.

## Overview

The orchestrator_mvp is a streamlined Python framework that provides:

- **Single-Year Mode**: Step-by-step debugging of dbt models with validation
- **Multi-Year Mode**: Complete workforce simulation (2025-2029) with year-over-year analysis
- **Checklist Enforcement**: Systematic step validation to prevent common errors
- **Resume Capability**: Continue from any completed checkpoint
- **Performance Monitoring**: Runtime tracking and optimization

## Architecture

```
orchestrator_mvp/
├── core/                       # Core infrastructure
│   ├── config.py              # Configuration and path management
│   ├── database_manager.py    # DuckDB operations and table management
│   ├── workforce_calculations.py  # Growth calculations and metrics
│   ├── event_emitter.py       # Event generation (hire, termination, merit, promotion)
│   ├── workforce_snapshot.py  # Multi-year workforce snapshot generation
│   ├── multi_year_simulation.py   # Multi-year simulation orchestration
│   ├── simulation_checklist.py    # Step sequencing and validation
│   └── multi_year_orchestrator.py # Checklist-enforced orchestration
├── loaders/                    # Data loading operations
│   └── staging_loader.py      # dbt model execution and staging
├── inspectors/                 # Validation and inspection
│   ├── staging_inspector.py   # Data validation utilities
│   ├── workforce_inspector.py # Workforce metrics and validation
│   └── multi_year_inspector.py    # Multi-year analysis
├── run_mvp.py                 # Main interactive entry point
├── run_single_year.py         # Single-year simulation
└── run_multi_year.py          # Multi-year simulation
```

## Key Design Principles

### 1. **Modular Architecture**
- Each operation type has clear boundaries and responsibilities
- Easy to add new inspectors, loaders, or core utilities
- Components can be imported and used independently

### 2. **Multi-Year Capable**
- Supports both single-year debugging and multi-year simulation
- Year-aware components understand simulation years and transitions
- Handles workforce transitions between simulation years

### 3. **Checklist Enforcement**
- **7-step workflow validation** for each simulation year
- **Step sequence errors** with clear guidance on missing prerequisites
- **Resume capability** from any completed checkpoint

### 4. **Performance Optimized**
- DuckDB for fast analytical queries
- Vectorized operations where possible
- Minimal data copying between operations

## Usage Patterns

### Interactive Development
```bash
# Single-year debugging with checklist
python orchestrator_mvp/run_mvp.py

# Multi-year simulation with validation
python orchestrator_mvp/run_mvp.py --multi-year

# Non-interactive batch mode
python orchestrator_mvp/run_mvp.py --multi-year --no-breaks
```

### Programmatic Usage
```python
from orchestrator_mvp.core import (
    MultiYearSimulationOrchestrator,
    clear_database,
    get_connection
)
from orchestrator_mvp.loaders import run_dbt_model
from orchestrator_mvp.inspectors import inspect_workforce_snapshot

# Run components individually
clear_database()
run_dbt_model("stg_census_data")
inspect_workforce_snapshot(2025)

# Full multi-year simulation
orchestrator = MultiYearSimulationOrchestrator(2025, 2029, config)
results = orchestrator.run_simulation()
```

## Event Generation Pipeline

The event_emitter.py module generates 5 types of workforce events:

1. **Experienced Terminations** (sequence: 1)
2. **New Hires** (sequence: 2)
3. **New Hire Terminations** (sequence: 3)
4. **Merit Raises** (sequence: 4)
5. **Promotions** (sequence: 5)

All events are stored in `fct_yearly_events` with complete audit trails.

## Multi-Year Workflow

Each simulation year follows a **7-step checklist-enforced process**:

1. **Year Transition Validation** - Ensures proper data handoff
2. **Workforce Baseline Preparation** - Loads active workforce
3. **Workforce Requirements Calculation** - Determines hires/terminations needed
4. **Event Generation Pipeline** - Creates all 5 event types
5. **Workforce Snapshot Generation** - Applies events to create year-end state
6. **Validation & Metrics** - Validates results and calculates metrics
7. **Year Completion** - Records success and prepares for next year

## Configuration

Multi-year simulations read from `config/test_config.yaml`:

```yaml
simulation:
  start_year: 2025
  end_year: 2029
  random_seed: 42
  target_growth_rate: 0.03

workforce:
  total_termination_rate: 0.12
  new_hire_termination_rate: 0.25

compensation:
  cola_rate: 0.025
  merit_budget: 0.04
```

## Integration with Eligibility Engine

For E022 Eligibility Engine integration:

1. **Create dbt model**: `int_eligibility_determination.sql`
2. **Add to loaders**: Run eligibility model after baseline workforce
3. **Filter events**: Use eligibility results to filter promotion/merit events
4. **Add inspector**: Validate eligibility determinations

```python
# Example integration in event_emitter.py
def generate_promotion_events_with_eligibility(simulation_year: int):
    # Load eligibility results
    eligibility_filter = """
        employee_id IN (
            SELECT employee_id FROM int_eligibility_determination
            WHERE simulation_year = ? AND is_eligible = true
        )
    """

    # Apply filter in workforce query
    query = f"""
        SELECT * FROM int_baseline_workforce
        WHERE employment_status = 'active' AND {eligibility_filter}
    """
    # Continue with existing promotion logic...
```

## Performance Targets

- **Single-year simulation**: <2 minutes total runtime
- **Multi-year simulation (5 years)**: <10 minutes total runtime
- **Database operations**: <30 seconds for 100K employees
- **Event generation**: 1000+ events/second creation rate

## Development Guidelines

### Adding New Event Types
1. Add event schema to existing event_emitter.py patterns
2. Follow sequence numbers (6+ for new events)
3. Include audit trail fields (created_at, scenario_id, etc.)
4. Add validation in inspectors/

### Adding New Inspectors
1. Create in `inspectors/` folder
2. Follow naming pattern: `{domain}_inspector.py`
3. Include data quality checks and business rule validation
4. Return structured validation results

### Database Operations
- Always use `get_connection()` from database_manager.py
- Close connections in finally blocks
- Use parameterized queries to prevent SQL injection
- Prefer bulk operations over row-by-row processing

## Testing Strategy

- **Unit tests**: Individual functions with mock data
- **Integration tests**: Full workflow with sample datasets
- **Performance tests**: 100K employee benchmarks
- **Data quality tests**: Edge cases and validation scenarios

## Migration to Full Dagster

The modular structure enables easy migration:
- `core.database_manager.clear_database()` → Dagster op
- `loaders.staging_loader.run_dbt_model()` → `@dbt_assets`
- `inspectors.*.py` functions → `@asset_check`
- Interactive prompts → Dagster job dependencies

## Troubleshooting

### Common Issues
1. **ModuleNotFoundError**: Activate virtual environment (`source venv/bin/activate`)
2. **Database locks**: Close IDE database connections
3. **Step sequence errors**: Use `--validate-only` to check prerequisites
4. **Performance issues**: Check for row-by-row operations vs. vectorized

### Debug Mode
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable detailed logging for database operations
from orchestrator_mvp.core.database_manager import get_connection
conn = get_connection(debug=True)
```

## Future Enhancements

- **Parallel processing**: Multi-core event generation
- **Incremental updates**: Only process changed employees
- **Advanced caching**: Memoization of expensive calculations
- **Real-time monitoring**: Dashboard for simulation progress
- **A/B testing**: Scenario comparison capabilities

---

**Best Practices**:
- Always run from project root directory
- Use checklist validation for production simulations
- Monitor performance with built-in timing
- Validate data quality at each step
- Keep event sequences consistent across years
