# Scenario Configuration Examples

This directory contains example scenario configurations for PlanWise Navigator batch processing (Epic E069).

## Usage

Run batch scenarios using the navigator CLI:

```bash
# Run all scenarios
python -m navigator_orchestrator batch

# Run specific scenarios
python -m navigator_orchestrator batch --scenarios baseline high_growth

# Clean databases before running for a fresh start
python -m navigator_orchestrator batch --clean

# Specify custom directories
python -m navigator_orchestrator batch --scenarios-dir scenarios/ --output-dir my_analysis/

# Export to CSV instead of Excel
python -m navigator_orchestrator batch --export-format csv

# Combine options for a clean run with specific scenarios
python -m navigator_orchestrator batch --scenarios baseline high_growth --clean --export-format excel
```

## Available Scenarios

### baseline.yaml
- **Purpose**: Standard business-as-usual case for comparison
- **Key Features**: Default parameters from base configuration
- **Use Case**: Baseline for comparison with other scenarios

### high_growth.yaml
- **Purpose**: Models aggressive business expansion
- **Key Features**: 8% growth rate, enhanced compensation, reduced turnover
- **Use Case**: Planning for rapid growth periods or talent wars

### cost_control.yaml
- **Purpose**: Models economic downturn or budget constraints
- **Key Features**: Minimal growth (1%), conservative compensation, higher turnover
- **Use Case**: Planning for economic uncertainty or cost reduction initiatives

### enhanced_benefits.yaml
- **Purpose**: Tests improved retirement benefits for retention
- **Key Features**: Enhanced employer match, core contributions, aggressive auto-enrollment
- **Use Case**: Evaluating the impact of benefit improvements on workforce retention

### auto_enrollment_test.yaml
- **Purpose**: Tests various auto-enrollment configurations
- **Key Features**: Different opt-out rates, proactive enrollment, year-over-year conversion
- **Use Case**: Optimizing auto-enrollment program design

## Configuration Structure

Each scenario file inherits from the base configuration (`config/simulation_config.yaml`) and can override specific parameters:

```yaml
# Basic scenario structure
simulation:
  start_year: 2025
  end_year: 2029
  random_seed: 100  # Unique seed per scenario
  target_growth_rate: 0.03

scenario_id: "scenario_name"
plan_design_id: "plan_identifier"

# Override specific sections as needed
compensation:
  cola_rate: 0.02
  merit_budget: 0.03

workforce:
  total_termination_rate: 0.10
```

## Output Structure

Batch execution creates timestamped output directories:

```
outputs/batch_YYYYMMDD_HHMMSS/
├── baseline/
│   ├── baseline.duckdb           # Isolated scenario database
│   ├── baseline_results.xlsx     # Excel workbook with multiple sheets
│   └── baseline_config.yaml      # Merged configuration for reference
├── high_growth/
│   ├── high_growth.duckdb
│   └── high_growth_results.xlsx
└── batch_summary.json            # Execution summary and results
```

## Excel Export Sheets

Each scenario Excel export includes:

1. **Workforce_Snapshot** - Complete workforce data by year (or split by year if large)
2. **Summary_Metrics** - Key KPIs by simulation year
3. **Events_Summary** - Hire/termination/promotion counts and trends
4. **Metadata** - Scenario configuration, git SHA, random seed, export details

## Best Practices

1. **Unique Seeds**: Use different `random_seed` values for each scenario to ensure statistical independence
2. **Descriptive IDs**: Use meaningful `scenario_id` and `plan_design_id` for tracking and analysis
3. **Focused Changes**: Override only the parameters you want to test, inherit everything else
4. **Documentation**: Add comments in scenario files explaining the business case being modeled
5. **Clean Runs**: Use `--clean` flag to delete existing databases before batch execution, ensuring a fresh start without stale data
