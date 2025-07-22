# MVP Orchestrator for PlanWise Navigator

A modular, interactive tool for debugging dbt models by running them individually and inspecting results at each step.

## Overview

This MVP orchestrator provides a streamlined workflow for:
- Clearing the DuckDB database to start fresh
- Running dbt models one at a time with full visibility
- Inspecting and validating model outputs with detailed reports
- Debugging data quality issues step by step
- Generating workforce snapshots by applying simulation events
- Analyzing workforce metrics and validating growth targets

## Architecture

The orchestrator is organized into modular components:

```
orchestrator_mvp/
├── __init__.py                 # Main package with convenient imports
├── run_mvp.py                  # Main interactive entry point
├── README.md                   # This documentation
├── core/                       # Core infrastructure
│   ├── __init__.py            # Core module exports
│   ├── config.py              # Configuration and path management
│   ├── database_manager.py    # Database operations and table management
│   ├── workforce_calculations.py  # Workforce growth calculations
│   ├── event_emitter.py       # Event generation and storage
│   └── workforce_snapshot.py  # Workforce snapshot generation
├── loaders/                    # Data loading operations
│   ├── __init__.py            # Loader module exports
│   └── staging_loader.py      # dbt model execution and staging operations
└── inspectors/                 # Validation and inspection
    ├── __init__.py            # Inspector module exports
    ├── staging_inspector.py   # Data validation and inspection utilities
    └── workforce_inspector.py # Workforce snapshot validation and metrics
```

### Benefits of This Structure

- **Modular**: Each operation type is in its own subfolder
- **Extensible**: Easy to add new inspectors, loaders, or core utilities
- **Reusable**: Modules can be imported and used independently
- **Maintainable**: Clear separation of concerns
- **Testable**: Each module can be tested individually
- **Dagster-ready**: Functions can easily be converted to Dagster assets later

## Prerequisites

Before using the orchestrator, ensure you have:

1. **Python Environment**: Activated virtual environment with all dependencies
   ```bash
   source venv/bin/activate
   ```

2. **dbt Setup**: dbt-core and dbt-duckdb installed and configured
   ```bash
   pip install dbt-core==1.8.8 dbt-duckdb==1.8.1
   ```

3. **Data Files**: Census data parquet files in `data/` directory
   - The `stg_census_data` model expects files matching `data/census*.parquet`

4. **DuckDB Database**: The `simulation.duckdb` file will be created automatically

## Usage

### Basic Workflow

1. **Navigate to project root**:
   ```bash
   cd /Users/nicholasamaral/planwise_navigator
   ```

2. **Activate virtual environment**:
   ```bash
   source venv/bin/activate
   ```

3. **Run the orchestrator**:
   ```bash
   python orchestrator_mvp/run_mvp.py
   ```

### Interactive Steps

The orchestrator will guide you through these steps:

1. **Welcome Message**: Displays tool purpose and overview

2. **Clear Database** (Press Enter when prompted):
   - Lists all existing tables in the main schema
   - Drops foreign key constraints to resolve dependencies
   - Drops each table individually with retry logic
   - Confirms database is empty or shows remaining non-dbt tables

3. **Run stg_census_data** (Press Enter when prompted):
   - Executes `dbt run --select stg_census_data`
   - Shows dbt output in real-time
   - Loads census data from parquet files

4. **Inspect Census Data** (Press Enter when prompted):
   - Validates table exists and contains data
   - Checks for NULL employee_ids
   - Displays table schema and column types
   - Shows sample data (first 5 rows) in markdown format
   - Provides comprehensive statistics (unique counts, date ranges, compensation stats)

5. **Load Seed Data** (Press Enter when prompted):
   - Loads configuration tables (job levels, comp levers, COLA, promotion hazards)
   - Creates staging models for configuration data

6. **Run int_baseline_workforce** (Press Enter when prompted):
   - Executes `dbt run --select int_baseline_workforce`
   - Builds baseline workforce from census data

7. **Calculate Workforce Requirements** (Press Enter when prompted):
   - Shows simulation parameters (growth rate, termination rates)
   - Calculates terminations and hires needed
   - Displays calculation formulas used

8. **Generate Simulation Events** (Press Enter when prompted):
   - Creates termination events for existing employees
   - Generates new hire events to meet growth targets
   - Validates all events were created correctly

9. **Generate Workforce Snapshot** (Press Enter when prompted):
   - Runs fct_workforce_snapshot model with simulation year
   - Applies all events chronologically to baseline workforce
   - Creates year-end workforce state

10. **Inspect Workforce Snapshot** (Press Enter when prompted):
    - Validates data quality (checks for missing employees, invalid status)
    - Displays workforce metrics (headcount by status, compensation stats)
    - Shows event application summary (counts by event type)
    - Validates growth target achievement

11. **Completion**: Displays success message with next steps

### Using Individual Modules

You can also import and use individual components:

```python
# Use database operations
from orchestrator_mvp.core import clear_database, list_tables, get_connection

# Use data loading
from orchestrator_mvp.loaders import run_dbt_model, run_staging_models

# Use inspection utilities
from orchestrator_mvp.inspectors import inspect_stg_census_data

# Use workforce snapshot generation
from orchestrator_mvp import generate_workforce_snapshot, inspect_workforce_snapshot

# Run specific operations
clear_database()
run_dbt_model("stg_census_data")
inspect_stg_census_data()

# Generate and inspect workforce snapshot
snapshot_result = generate_workforce_snapshot(simulation_year=2025)
inspect_workforce_snapshot(simulation_year=2025)
```

### Expected Console Output

```
============================================================
🚀 PLANWISE NAVIGATOR - MVP ORCHESTRATOR
============================================================

This tool will help you debug dbt models by running them
individually and inspecting the results at each step.

📋 Press Enter to clear the database...

============================================================
CLEARING DATABASE
============================================================

Found 3 tables to drop:
  - stg_census_data
  - int_baseline_workforce
  - fct_workforce_snapshot

Dropping foreign key constraints...
  ✓ No foreign key constraints found or dropped

Dropping tables...
  ✓ Dropped stg_census_data
  ✓ Dropped int_baseline_workforce
  ✓ Dropped fct_workforce_snapshot

✅ Database completely cleared!

📋 Press Enter to run stg_census_data model...

============================================================
RUNNING DBT MODEL: stg_census_data
============================================================

Executing command: dbt run --select stg_census_data
Working directory: /Users/nicholasamaral/planwise_navigator/dbt
----------------------------------------
[dbt output appears here]

✅ Successfully ran stg_census_data

📋 Press Enter to inspect census data...

============================================================
INSPECTING: stg_census_data
============================================================
✓ Table main.stg_census_data exists
✓ Table contains 5,000 rows
✓ No NULL values in employee_id column

Table has 15 columns:
  - employee_id: VARCHAR
  - employee_ssn: VARCHAR
  - employee_birth_date: DATE
  [... more columns ...]

Sample data (first 5 rows):
[Markdown table with sample data]

Basic Statistics:
  - Unique employees: 5,000
  - Total rows: 5,000
  - Unique SSNs: 5,000
  - Hire date range: 2010-01-01 to 2024-12-31
  - Active employees: 4,750
  - Terminated employees: 250
  - Avg compensation: $85,234.56
  - Compensation range: $35,000.00 to $250,000.00

✅ All validations passed for stg_census_data!

✨ Foundational data looks good!
Now let's build on top of it...

📋 Press Enter to load seed data...
[Seed loading output]

📋 Press Enter to run int_baseline_workforce model...
[dbt model output]

📋 Press Enter to calculate workforce requirements...

============================================================
📊 WORKFORCE CALCULATION RESULTS
============================================================

✅ Baseline workforce loaded: 4,500 active employees

📋 SIMULATION PARAMETERS:
   • Target growth rate: 5.0%
   • Total termination rate: 8.0%
   • New hire termination rate: 15.0%

📊 NEXT YEAR REQUIREMENTS:
   • Starting workforce: 4,500
   • Terminations needed: 360
   • Gross hires needed: 621
   • Expected new hire terminations: 36
   • Net workforce growth: +225

🧮 CALCULATION FORMULAS:
   • experienced_terminations: 4500 * 0.08 = 360
   • net_hires_needed: 225 + 360 = 585
   • total_hires_needed: 585 / (1 - 0.15/2) = 621

✅ Workforce calculation completed successfully!

📋 Press Enter to generate simulation events...
[Event generation output]

📋 Press Enter to generate workforce snapshot...

🔄 Generating workforce snapshot for year 2025...
   Starting workforce: 4,500 employees
   Running fct_workforce_snapshot model...

✅ Workforce snapshot generated successfully!

📋 Press Enter to inspect workforce snapshot...

📊 Inspecting Workforce Snapshot for Year 2025
============================================================

✅ Data Quality: All checks passed

📈 Workforce Metrics
----------------------------------------

Headcount by Status:
   Active         4,725 ( 89.5%)
   Terminated       550 ( 10.5%)

Compensation Statistics (Active Employees):
   Total Payroll:   $425,250,000
   Average Salary:  $90,000
   Median Salary:   $85,000
   Salary Range:    $35,000 - $250,000

Headcount by Band:
   Band 1:   1,200 (avg: $45,000)
   Band 2:   1,500 (avg: $65,000)
   Band 3:   1,200 (avg: $95,000)
   Band 4:     600 (avg: $125,000)
   Band 5:     225 (avg: $175,000)

🔄 Event Application Summary
----------------------------------------

Events Applied:
   termination       396 events affecting 396 employees
   hire              621 events affecting 621 employees
   Total           1,017 events

Workforce Change:
   Baseline:    4,500 employees
   Current:     4,725 employees
   Net Change:  +225 (+5.0%)

🎯 Growth Target Validation
----------------------------------------

Target Growth Rate: 5.0%
Actual Growth Rate: 5.0%

Target Headcount:   4,725
Actual Headcount:   4,725
Variance:           +0 (+0.0%)

✅ Growth target achieved (within 0.5% tolerance)

============================================================
✅ Workforce snapshot inspection complete

============================================================
✅ MVP ORCHESTRATOR COMPLETED SUCCESSFULLY!
============================================================

You can now:
  1. Run additional models with run_dbt_model()
  2. Create new inspector functions for other tables
  3. Query the database directly with DuckDB
  4. Analyze workforce snapshots with inspect_workforce_snapshot()

Happy debugging! 🎉
```

## Troubleshooting

### Common Issues

1. **ModuleNotFoundError**: Ensure virtual environment is activated
   ```bash
   source venv/bin/activate
   ```

2. **Import errors with relative imports**: Run the script from project root:
   ```bash
   python orchestrator_mvp/run_mvp.py  # Correct
   cd orchestrator_mvp && python run_mvp.py  # May cause import issues
   ```

3. **dbt command not found**: Install dbt in the virtual environment
   ```bash
   pip install dbt-core==1.8.8 dbt-duckdb==1.8.1
   ```

4. **Database file not found**: The script will create it automatically if missing

5. **No census data**: Ensure parquet files exist in `data/` directory
   ```bash
   ls data/census*.parquet
   ```

6. **Foreign key constraint errors**: The new database manager handles these automatically with retry logic

### Advanced Usage

You can extend the orchestrator by:

1. **Adding new inspector functions**: Create functions in `inspectors/staging_inspector.py` or new files
   ```python
   def inspect_int_baseline_workforce():
       # Custom validation logic for baseline workforce
   ```

2. **Adding new loader functions**: Create functions in `loaders/staging_loader.py` or new files
   ```python
   def run_intermediate_models():
       # Custom logic to run multiple intermediate models
   ```

3. **Adding new core utilities**: Create functions in `core/database_manager.py` or new files
   ```python
   def backup_database():
       # Logic to backup the current database state
   ```

4. **Custom validation**: Query the database directly
   ```python
   from orchestrator_mvp.core import get_connection
   conn = get_connection()
   df = conn.execute("SELECT * FROM main.stg_census_data").df()
   ```

## Migration to Dagster

The modular structure makes migration to Dagster straightforward:

- **`core.database_manager.clear_database()`** → Dagster op or asset
- **`loaders.staging_loader.run_dbt_model()`** → `@dbt_assets`
- **`inspectors.staging_inspector.inspect_stg_census_data()`** → `@asset_check`
- **Interactive prompts** → Dagster job with explicit dependencies

## Next Steps

After running the MVP orchestrator, you can:

1. Continue running additional dbt models using the loader functions
2. Use the Dagster UI for full pipeline orchestration
3. Explore data with the Streamlit dashboards
4. Modify and test individual dbt models
5. Add new inspection and validation functions
6. Analyze workforce snapshots across multiple years
7. Validate event application and growth target achievement

For more information, see the main project documentation in `/docs/`.
