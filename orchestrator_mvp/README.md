# MVP Orchestrator for PlanWise Navigator

A modular, interactive tool for debugging dbt models and running comprehensive workforce simulations with **systematic checklist enforcement**. Supports both single-year debugging and multi-year workforce simulation with year-over-year analysis, ensuring proper step sequencing and preventing common errors.

## Overview

This MVP orchestrator provides a streamlined workflow for:

- **Single-Year Mode with Checklist**: Debugging dbt models step-by-step with systematic validation
  - Clearing the DuckDB database to start fresh
  - Running dbt models one at a time with detailed inspection
  - **Checklist enforcement** ensures proper step sequencing
  - Validating model outputs and debugging data quality issues
  - Generating workforce snapshots by applying simulation events
  - Analyzing workforce metrics and validating growth targets

- **Multi-Year Mode with Checklist**: Comprehensive workforce simulation with step sequence enforcement
  - Running complete multi-year simulations (e.g., 2025-2029)
  - **7-step workflow validation** for each simulation year
  - **Resume capability** from any completed checkpoint
  - **Step sequence errors** with clear guidance on missing prerequisites
  - Year-over-year workforce transitions with proper data handoff
  - Cumulative growth validation against targets
  - Multi-year event consistency analysis
  - Workforce aging and demographic trend analysis

## Architecture

The orchestrator is organized into modular components:

```
orchestrator_mvp/
├── __init__.py                 # Main package with convenient imports
├── run_mvp.py                  # Main interactive entry point (single-year + multi-year)
├── README.md                   # This documentation
├── core/                       # Core infrastructure
│   ├── __init__.py            # Core module exports
│   ├── config.py              # Configuration and path management
│   ├── database_manager.py    # Database operations and table management
│   ├── workforce_calculations.py  # Year-aware workforce growth calculations
│   ├── event_emitter.py       # Multi-year compatible event generation
│   ├── workforce_snapshot.py  # Multi-year workforce snapshot generation
│   ├── multi_year_simulation.py   # Multi-year simulation orchestration
│   ├── simulation_checklist.py    # Step sequencing and validation system
│   └── multi_year_orchestrator.py # Checklist-enforced orchestration
├── loaders/                    # Data loading operations
│   ├── __init__.py            # Loader module exports
│   └── staging_loader.py      # dbt model execution and staging operations
└── inspectors/                 # Validation and inspection
    ├── __init__.py            # Inspector module exports
    ├── staging_inspector.py   # Data validation and inspection utilities
    ├── workforce_inspector.py # Workforce snapshot validation and metrics
    └── multi_year_inspector.py    # Multi-year analysis and validation
```

### Benefits of This Structure

- **Modular**: Each operation type is in its own subfolder with clear boundaries
- **Extensible**: Easy to add new inspectors, loaders, or core utilities
- **Multi-Year Capable**: Supports both single-year debugging and multi-year simulation
- **Year-Aware**: All components understand simulation years and transitions
- **Reusable**: Modules can be imported and used independently
- **Maintainable**: Clear separation of concerns between single-year and multi-year logic
- **Testable**: Each module can be tested individually with mock data
- **Scalable**: Handles small debugging runs to large multi-year simulations
- **Dagster-ready**: Functions can easily be converted to Dagster assets later
- **Step-Safe**: **Checklist enforcement prevents common errors** and ensures proper sequencing
- **Resumable**: **Resume capability** allows recovery from interruptions
- **Auditable**: **Complete step-by-step audit trail** for compliance and debugging

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

### Single-Year Simulation with Checklist Enforcement

For debugging dbt models and single-year workforce simulation with step validation:

1. **Navigate to project root**:
   ```bash
   cd /Users/nicholasamaral/planwise_navigator
   ```

2. **Activate virtual environment**:
   ```bash
   source venv/bin/activate
   ```

3. **Run the checklist-enforced orchestrator**:
   ```bash
   # Interactive mode with checklist validation (default)
   python orchestrator_mvp/run_mvp.py

   # Non-interactive mode with checklist validation
   python orchestrator_mvp/run_mvp.py --no-breaks
   python orchestrator_mvp/run_mvp.py -n

   # Override checklist validation for specific step (emergency only)
   python orchestrator_mvp/run_mvp.py --force-step workforce_snapshot
   ```

### Multi-Year Simulation with Checklist Enforcement

For comprehensive multi-year workforce simulation with systematic step validation:

```bash
# Interactive checklist-enforced multi-year simulation
python orchestrator_mvp/run_mvp.py --multi-year
python orchestrator_mvp/run_mvp.py -m

# Non-interactive checklist-enforced multi-year simulation
python orchestrator_mvp/run_mvp.py --multi-year --no-breaks
python orchestrator_mvp/run_mvp.py -m -n

# Resume multi-year simulation from a specific year
python orchestrator_mvp/run_mvp.py --multi-year --resume-from 2027

# Validate prerequisites without running simulation
python orchestrator_mvp/run_mvp.py --multi-year --validate-only

# Emergency override for specific step (use with caution)
python orchestrator_mvp/run_mvp.py --multi-year --force-step event_generation
```

#### Multi-Year Configuration

Multi-year simulations read settings from `config/test_config.yaml`:

```yaml
simulation:
  start_year: 2025    # First simulation year
  end_year: 2029      # Last simulation year
  random_seed: 42     # For reproducible results
  target_growth_rate: 0.03  # 3% annual growth

workforce:
  total_termination_rate: 0.12      # 12% termination rate
  new_hire_termination_rate: 0.25   # 25% new hire turnover

compensation:
  cola_rate: 0.025    # 2.5% cost of living adjustment
  merit_budget: 0.04  # 4% merit increase budget
```

### Single-Year Mode Workflow with Checklist Enforcement

The orchestrator guides you through these steps with systematic validation in single-year mode:

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

### Multi-Year Mode Workflow with Checklist Enforcement

Multi-year simulations follow this systematic, validated workflow with a **7-step process** for each simulation year:

1. **Setup Phase**: Same initial steps as single-year (clear database, load census data, etc.)

2. **Configuration Loading**: Reads multi-year settings from `config/test_config.yaml`

3. **Checklist-Enforced Year-by-Year Simulation**: For each year (e.g., 2025-2029), the **7-step process** with validation:
   - **Step 1 - Year Transition Validation**: Ensures proper data handoff from previous year (with prerequisite checking)
   - **Step 2 - Workforce Baseline Preparation**: Uses previous year's active employees or baseline for year 1 (validates prerequisites)
   - **Step 3 - Workforce Requirements Calculation**: Calculates terminations and hires needed (validates baseline completion)
   - **Step 4 - Event Generation Pipeline**: Creates all 5 event types and stores in fct_yearly_events (validates requirements completion)
   - **Step 5 - Workforce Snapshot Generation**: Runs fct_workforce_snapshot model (validates event generation completion)
   - **Step 6 - Validation & Metrics**: Validates results and calculates metrics (validates snapshot completion)
   - **Step 7 - Year Completion**: Records success and prepares for next year

4. **Multi-Year Analysis**:
   - **Year-over-Year Comparison**: Workforce growth, compensation trends, event patterns
   - **Growth Validation**: Actual vs. target CAGR with deviation analysis
   - **Event Consistency**: Validates realistic event patterns across years
   - **Demographic Analysis**: Tracks workforce aging and tenure progression

### Using Individual Modules

You can import and use components individually:

```python
# Single-year functionality with checklist enforcement
from orchestrator_mvp.core import (
    clear_database, list_tables, get_connection,
    SimulationChecklist, MultiYearSimulationOrchestrator, StepSequenceError
)
from orchestrator_mvp.loaders import run_dbt_model, run_staging_models
from orchestrator_mvp.inspectors import inspect_stg_census_data
from orchestrator_mvp import generate_workforce_snapshot, inspect_workforce_snapshot

# Multi-year simulation with checklist enforcement
from orchestrator_mvp import (
    run_multi_year_simulation,
    MultiYearSimulationOrchestrator,
    compare_year_over_year_metrics,
    validate_cumulative_growth,
    display_multi_year_summary
)

# Example: Run single-year components
clear_database()
run_dbt_model("stg_census_data")
inspect_stg_census_data()

# Example: Run checklist-enforced multi-year simulation programmatically
config = {
    'target_growth_rate': 0.03,
    'workforce': {
        'total_termination_rate': 0.12,
        'new_hire_termination_rate': 0.25
    },
    'random_seed': 42
}

# Use checklist-enforced orchestrator
orchestrator = MultiYearSimulationOrchestrator(2025, 2029, config)

# Check progress before starting
print(orchestrator.get_progress_summary())

# Run with resume capability
results = orchestrator.run_simulation(skip_breaks=True)

# Analyze results
compare_year_over_year_metrics(2025, 2029)
validate_cumulative_growth(2025, 2029, 0.03)
display_multi_year_summary(2025, 2029)

# Example: Handle step sequence errors
try:
    checklist = SimulationChecklist(2025, 2025)
    checklist.assert_step_ready('workforce_snapshot', 2025)
except StepSequenceError as e:
    print(f"Step sequence error: {e}")
    # Error provides clear guidance on missing prerequisites
```

### Expected Console Output

```
============================================================
🚀 PLANWISE NAVIGATOR - MVP ORCHESTRATOR
============================================================

This tool will help you debug dbt models by running them
individually and inspecting the results at each step.
Single-year mode includes checklist validation for key steps.

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
✅ CHECKLIST-ENFORCED MVP ORCHESTRATOR COMPLETED SUCCESSFULLY!
============================================================

Checklist-enforced single-year simulation completed:
  • All steps validated in proper sequence
  • Workforce snapshot generated and validated
  • Complete audit trail of step completion

You can now:
  1. Run additional models with run_dbt_model()
  2. Create new inspector functions for other tables
  3. Query the database directly with DuckDB
  4. Analyze workforce snapshots with inspect_workforce_snapshot()

📋 Single-Year Checklist Status:
Simulation Progress Summary:
========================================
✓ Pre-simulation setup
✓ Year 2025
  ✓ Year Transition
  ✓ Workforce Baseline
  ✓ Workforce Requirements
  ✓ Event Generation
  ✓ Workforce Snapshot
  ✓ Validation Metrics

Happy debugging! 🎉
```

### Multi-Year Simulation Output with Checklist Enforcement

Checklist-enforced multi-year mode produces enhanced output with step validation and comprehensive analysis:

```
============================================================
🚀 PLANWISE NAVIGATOR - MVP ORCHESTRATOR
============================================================

🗓️ MULTI-YEAR SIMULATION MODE WITH CHECKLIST ENFORCEMENT
This tool will run a complete multi-year workforce simulation
using the configuration parameters from test_config.yaml
Each step will be validated to ensure proper sequencing.

🗓️ Multi-year simulation configured for 2025-2029

📋 Press Enter to run multi-year simulation (2025-2029)...

🚀 Starting multi-year simulation: 2025-2029

📋 Initial Progress Status:
Simulation Progress Summary:
========================================
○ Pre-simulation setup
○ Year 2025
○ Year 2026
○ Year 2027
○ Year 2028
○ Year 2029

🗓️  SIMULATING YEAR 2025
==================================================
📋 Step 1: Year Transition Validation (skip for first year)
📋 Step 2: Workforce Baseline Preparation
📊 Year 2025: Using baseline workforce
Starting workforce for 2025: 4,500 employees
📋 Step 3: Workforce Requirements Calculation
📈 Growth calculation: +621 hires, -360 terminations
📋 Step 4: Event Generation Pipeline
🎲 Generating events for year 2025 with seed 42
📋 Step 5: Workforce Snapshot Generation
📸 Generating workforce snapshot for year 2025
📋 Step 6: Validation & Metrics
✅ Year 2025 completed in 12.3s

📋 Press Enter to continue to year 2026...

🗓️  SIMULATING YEAR 2026
==================================================
🔍 Validating year transition: 2025 → 2026
📊 Year 2025 snapshot: 5,121 total, 4,725 active employees
📊 Average age: 42.3, tenure: 8.7 years
✅ Year transition validation passed: 2025 → 2026
📊 Year 2026: Using previous year workforce
Starting workforce for 2026: 4,725 employees
✅ Year 2026 completed in 11.8s

[... continues for years 2027-2029 ...]

✅ Checklist-enforced multi-year simulation completed successfully!
Years simulated: 2025-2029
Total runtime: 58.4s

📋 Final Progress Status:
Simulation Progress Summary:
========================================
✓ Pre-simulation setup
✓ Year 2025
✓ Year 2026
✓ Year 2027
✓ Year 2028
✓ Year 2029

============================================================
📊 MULTI-YEAR ANALYSIS
============================================================

📊 YEAR-OVER-YEAR WORKFORCE COMPARISON
============================================================
Year 2025:
  • Active workforce: 4,725
  • Total compensation: $425,250,000
  • Average compensation: $90,000
  • Total events: 1,017

Year 2026:
  • Active workforce: 4,867
  • Total compensation: $448,130,000
  • Average compensation: $92,070
  • Total events: 1,049

[... continues for all years ...]

📈 SUMMARY:
  • Workforce growth: 4,725 → 5,321
  • Total growth rate: +12.6%
  • Average annual: +3.0%

📈 CUMULATIVE GROWTH VALIDATION
==================================================
Status: ✅ PASS
Target annual growth: 3.0%
Actual CAGR: 3.0%
Workforce: 4,725 → 5,321
Deviation: +0.0%

📋 MULTI-YEAR SIMULATION SUMMARY
============================================================
Simulation range: 2025-2029
Total years: 5

🔍 Key Insights:
  • Overall workforce grew 12.6% over simulation period
  • Average compensation increased 8.4%
  • Event generation remained consistent across years
  • No significant demographic shifts detected

============================================================
✅ CHECKLIST-ENFORCED MULTI-YEAR SIMULATION COMPLETED SUCCESSFULLY!
============================================================

Checklist-enforced multi-year simulation artifacts created:
  • Workforce snapshots for each year
  • Event logs across all simulation years
  • Year-over-year analysis results
  • Growth validation reports
  • Complete step-by-step audit trail

Happy debugging! 🎉
```

## Troubleshooting

### Common Issues

#### Checklist Enforcement Issues

7. **Step sequence errors**: If you see messages like `Cannot execute step 'workforce_snapshot' for year 2025. Missing prerequisites: event_generation`, this means you're trying to run steps out of order:
   ```bash
   # Check what steps are missing
   python orchestrator_mvp/run_mvp.py --multi-year --validate-only

   # Use resume functionality to continue from correct point
   python orchestrator_mvp/run_mvp.py --multi-year --resume-from 2025

   # Emergency override (use with caution)
   python orchestrator_mvp/run_mvp.py --force-step workforce_snapshot
   ```

8. **Cannot resume from checkpoint**: Ensure the previous steps for that year are actually completed in the database:
   ```python
   from orchestrator_mvp.core import get_connection
   conn = get_connection()
   # Check if events exist for the year
   result = conn.execute("SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = 2025").fetchone()
   print(f"Events for 2025: {result[0]}")
   ```

#### Original Issues

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

1. **Adding multi-year inspector functions**: Create custom analysis in `inspectors/multi_year_inspector.py`
   ```python
   def analyze_compensation_equity(start_year: int, end_year: int):
       # Custom analysis for pay equity trends across years
   ```

2. **Custom multi-year simulations**: Use the multi-year simulation framework programmatically
   ```python
   from orchestrator_mvp import run_multi_year_simulation

   # Custom scenario analysis
   scenarios = {
       'conservative': {'target_growth_rate': 0.02},
       'aggressive': {'target_growth_rate': 0.05}
   }

   for scenario_name, config in scenarios.items():
       results = run_multi_year_simulation(2025, 2029, config)
       print(f"{scenario_name}: {results['total_runtime_seconds']:.1f}s")
   ```

3. **Year transition logic**: Customize workforce transitions between years
   ```python
   from orchestrator_mvp.core.multi_year_simulation import validate_year_transition

   # Add custom transition validation
   def custom_year_validation(from_year: int, to_year: int):
       # Custom logic for year transitions
       return validate_year_transition(from_year, to_year)
   ```

4. **Custom event patterns**: Extend event generation for specific scenarios
   ```python
   from orchestrator_mvp.core.event_emitter import generate_and_store_all_events

   # Generate events with custom parameters per year
   for year in range(2025, 2030):
       custom_config = get_year_specific_config(year)
       generate_and_store_all_events(calc_result, year, random_seed)
   ```

5. **Multi-year database queries**: Analyze data across multiple years
   ```python
   from orchestrator_mvp.core import get_connection

   conn = get_connection()
   # Compare workforce across all years
   df = conn.execute("""
       SELECT
           simulation_year,
           COUNT(*) as total_employees,
           AVG(current_compensation) as avg_comp
       FROM fct_workforce_snapshot
       WHERE employment_status = 'active'
       GROUP BY simulation_year
       ORDER BY simulation_year
   """).df()
   ```

## Migration to Dagster

The modular structure makes migration to Dagster straightforward:

- **`core.database_manager.clear_database()`** → Dagster op or asset
- **`loaders.staging_loader.run_dbt_model()`** → `@dbt_assets`
- **`inspectors.staging_inspector.inspect_stg_census_data()`** → `@asset_check`
- **Interactive prompts** → Dagster job with explicit dependencies

### Troubleshooting Multi-Year Simulations

**Common multi-year issues:**

1. **Year transition failures**: Check that previous year's workforce snapshot exists
   ```bash
   # Verify snapshots exist for all years
   python -c "from orchestrator_mvp.core import get_connection;
   conn = get_connection();
   print(conn.execute('SELECT simulation_year, COUNT(*) FROM fct_workforce_snapshot GROUP BY simulation_year').fetchall())"
   ```

2. **Configuration errors**: Validate `config/test_config.yaml` settings
   ```yaml
   # Ensure all required fields are present:
   simulation:
     start_year: 2025  # Must be integer
     end_year: 2029    # Must be >= start_year
     random_seed: 42   # For reproducibility
   ```

3. **Memory issues with large simulations**: Use non-interactive mode for long simulations
   ```bash
   # Run multi-year without prompts for better performance
   python orchestrator_mvp/run_mvp.py -m -n
   ```

4. **Inconsistent event generation**: Check random seed configuration
   ```python
   # Verify reproducible results
   results1 = run_multi_year_simulation(2025, 2027, config)
   results2 = run_multi_year_simulation(2025, 2027, config)
   assert results1['years_completed'] == results2['years_completed']
   ```

## Next Steps

After running the MVP orchestrator, you can:

**Single-Year Mode:**
1. Continue running additional dbt models using the loader functions
2. Add new inspection and validation functions for debugging
3. Modify and test individual dbt models
4. Query the database directly for custom analysis

**Multi-Year Mode:**
1. Analyze multi-year trends with the inspector functions
2. Run scenario analysis with different growth parameters
3. Validate workforce planning assumptions across years
4. Export multi-year data for external reporting
5. Create custom multi-year validation rules

**Integration:**
1. Use the Dagster UI for full pipeline orchestration
2. Explore data with the Streamlit dashboards
3. Integrate with external workforce planning tools
4. Set up automated multi-year simulation schedules

For more information, see the main project documentation in `/docs/`.
