# MVP Orchestrator for PlanWise Navigator

A modular, interactive tool for debugging dbt models by running them individually and inspecting results at each step.

## Overview

This MVP orchestrator provides a streamlined workflow for:
- Clearing the DuckDB database to start fresh
- Running dbt models one at a time with full visibility
- Inspecting and validating model outputs with detailed reports
- Debugging data quality issues step by step

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
│   └── database_manager.py    # Database operations and table management
├── loaders/                    # Data loading operations
│   ├── __init__.py            # Loader module exports
│   └── staging_loader.py      # dbt model execution and staging operations
└── inspectors/                 # Validation and inspection
    ├── __init__.py            # Inspector module exports
    └── staging_inspector.py   # Data validation and inspection utilities
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

5. **Run int_baseline_workforce** (Press Enter when prompted):
   - Executes `dbt run --select int_baseline_workforce`
   - Builds baseline workforce from census data

6. **Completion**: Displays success message with next steps

### Using Individual Modules

You can also import and use individual components:

```python
# Use database operations
from orchestrator_mvp.core import clear_database, list_tables, get_connection

# Use data loading
from orchestrator_mvp.loaders import run_dbt_model, run_staging_models

# Use inspection utilities
from orchestrator_mvp.inspectors import inspect_stg_census_data

# Run specific operations
clear_database()
run_dbt_model("stg_census_data")
inspect_stg_census_data()
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

📋 Press Enter to run int_baseline_workforce model...
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

For more information, see the main project documentation in `/docs/`.
