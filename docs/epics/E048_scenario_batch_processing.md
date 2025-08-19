# Epic E048: Scenario Batch Processing System

**Epic Points**: 16
**Priority**: MEDIUM
**Duration**: 2 Sprints
**Status**: 🔴 Not Started
**Last Updated**: August 18, 202511

## Epic Story

**As a** workforce planning analyst
**I want** to run multiple simulation scenarios in batch and compare results
**So that** I can efficiently analyze different plan designs and policy changes

## Business Context

Currently, PlanWise Navigator requires manual execution of individual scenarios, copying databases, and manual comparison of results. This creates significant friction for scenario analysis, plan design optimization, and policy impact assessment.

This epic enables analysts to define multiple scenario configurations and execute them automatically, with isolated databases and structured comparison outputs for decision-making.

## Current Limitations

- **Manual scenario execution**: Each scenario requires manual CLI invocation
- **Database collision**: Multiple scenarios overwrite the same `simulation.duckdb`
- **No comparison tools**: Manual analysis required to compare scenario results
- **Export limitations**: Only JSON/CSV exports available, no Excel output
- **No batch orchestration**: No way to queue and execute multiple scenarios

## Epic Acceptance Criteria

### Batch Execution
- [x] **Sequential scenario processing** with isolated database instances
- [x] **Configuration override system** for scenario variations
- [x] **Progress tracking** with status updates for each scenario
- [x] **Error isolation** continuing batch execution when individual scenarios fail

### Database Isolation
- [x] **Separate databases** per scenario to prevent data collision
- [x] **Automated cleanup** of scenario databases after export
- [x] **Database verification** ensuring clean state for each scenario
- [x] **Backup integration** leveraging existing backup system

### Export & Comparison
- [x] **Structured outputs** with consistent naming and metadata
- [x] **Excel export capability** for analyst-friendly format
- [x] **Comparison reports** highlighting key differences between scenarios
- [x] **Summary dashboards** with scenario performance metrics

### CLI Integration
- [x] **Batch subcommand** extending existing navigator_orchestrator CLI
- [x] **Scenario discovery** automatically finding scenario configurations
- [x] **Output management** organizing results by timestamp and scenario
- [x] **Resume capability** restarting failed batch runs

## Story Breakdown

| Story | Title | Points | Owner | Status | Dependencies |
|-------|-------|--------|-------|--------|--------------|
| **S048-01** | Database Isolation & Scenario Runner | 6 | Platform | ❌ Not Started | E043 (Backup System) |
| **S048-02** | CLI Batch Integration | 4 | Platform | ❌ Not Started | S048-01 |
| **S048-03** | Excel Export & Comparison Reports | 4 | Platform | ❌ Not Started | S048-01 |
| **S048-04** | Documentation & Examples | 2 | Platform | ❌ Not Started | S048-01,02,03 |

**Completed**: 0 points (0%) | **Remaining**: 16 points (100%)

## Technical Implementation

### Database Isolation Strategy
```python
# navigator_orchestrator/batch_runner.py
from pathlib import Path
from typing import Dict, List, Optional
import shutil
from .config import load_simulation_config, SimulationConfig
from .pipeline import PipelineOrchestrator
from .utils import DatabaseConnectionManager

class ScenarioBatchRunner:
    def __init__(self, scenarios_dir: Path, outputs_dir: Path):
        self.scenarios_dir = Path(scenarios_dir)
        self.outputs_dir = Path(outputs_dir)
        self.batch_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.batch_output_dir = self.outputs_dir / f"batch_{self.batch_timestamp}"

    def run_batch(self, scenario_names: Optional[List[str]] = None) -> Dict[str, any]:
        """Execute batch of scenarios with isolated databases"""

        # Discover scenarios
        scenarios = self._discover_scenarios(scenario_names)
        results = {}

        print(f"🎯 Starting batch execution: {len(scenarios)} scenarios")

        for i, (name, config_path) in enumerate(scenarios.items(), 1):
            print(f"\n[{i}/{len(scenarios)}] Processing scenario: {name}")

            try:
                result = self._run_isolated_scenario(name, config_path)
                results[name] = result
                print(f"✅ Scenario {name} completed successfully")

            except Exception as e:
                print(f"❌ Scenario {name} failed: {e}")
                results[name] = {"status": "failed", "error": str(e)}

        # Generate comparison report
        self._generate_comparison_report(results)

        return results

    def _run_isolated_scenario(self, scenario_name: str, config_path: Path) -> Dict[str, any]:
        """Run single scenario with isolated database"""

        # Create scenario output directory
        scenario_dir = self.batch_output_dir / scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)

        # Create isolated database
        scenario_db = scenario_dir / f"{scenario_name}.duckdb"

        # Load scenario configuration
        config = load_simulation_config(config_path)

        # Setup isolated orchestrator
        db_manager = DatabaseConnectionManager(scenario_db)
        # ... rest of orchestrator setup

        # Execute simulation
        orchestrator = PipelineOrchestrator(config, db_manager, ...)
        summary = orchestrator.execute_multi_year_simulation()

        # Export scenario results
        self._export_scenario_results(scenario_name, scenario_dir, db_manager)

        return {
            "status": "completed",
            "summary": summary,
            "database_path": str(scenario_db),
            "exports_dir": str(scenario_dir)
        }
```

### Configuration Override System
```python
def load_scenario_config(self, scenario_path: Path) -> SimulationConfig:
    """Load scenario config with simple override support"""

    # Load the scenario file
    with open(scenario_path, 'r') as f:
        scenario_data = yaml.safe_load(f)

    # Check if it references a base config
    if 'base_config' in scenario_data:
        base_path = self.scenarios_dir / scenario_data['base_config']
        base_config = load_simulation_config(base_path)

        # Apply simple overrides (not deep merge - keep it simple)
        config_dict = base_config.model_dump()

        # Override top-level sections
        for key, value in scenario_data.items():
            if key not in ['scenario', 'base_config']:
                config_dict[key] = value

        # Create new config from merged data
        return SimulationConfig.model_validate(config_dict)
    else:
        # Direct config file
        return load_simulation_config(scenario_path)
```

### Excel Export Integration
```python
# navigator_orchestrator/excel_exporter.py
import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

class ExcelExporter:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager

    def export_scenario_data(self, scenario_name: str, output_dir: Path):
        """Export key tables to Excel with proper formatting"""

        excel_path = output_dir / f"{scenario_name}_results.xlsx"

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:

            # Export workforce snapshots
            df_workforce = pd.read_sql(
                "SELECT * FROM fct_workforce_snapshot ORDER BY simulation_year, employee_id",
                self.db.get_connection()
            )
            df_workforce.to_excel(writer, sheet_name='Workforce_Snapshot', index=False)

            # Export yearly events summary
            df_events_summary = pd.read_sql("""
                SELECT
                    simulation_year,
                    event_type,
                    COUNT(*) as event_count,
                    AVG(CASE WHEN event_type = 'RAISE' THEN new_compensation END) as avg_new_compensation
                FROM fct_yearly_events
                GROUP BY simulation_year, event_type
                ORDER BY simulation_year, event_type
            """, self.db.get_connection())
            df_events_summary.to_excel(writer, sheet_name='Events_Summary', index=False)

            # Export key metrics
            df_metrics = self._calculate_key_metrics()
            df_metrics.to_excel(writer, sheet_name='Key_Metrics', index=False)

            # Format worksheets
            self._format_worksheets(writer)

    def _calculate_key_metrics(self) -> pd.DataFrame:
        """Calculate scenario summary metrics"""
        metrics = pd.read_sql("""
            SELECT
                simulation_year,
                COUNT(DISTINCT employee_id) as total_employees,
                COUNT(DISTINCT CASE WHEN enrollment_status = 'enrolled' THEN employee_id END) as enrolled_employees,
                AVG(total_compensation) as avg_compensation,
                SUM(CASE WHEN enrollment_status = 'enrolled' THEN annual_contribution_amount ELSE 0 END) as total_contributions
            FROM fct_workforce_snapshot ws
            LEFT JOIN int_employee_contributions ec
                ON ws.employee_id = ec.employee_id AND ws.simulation_year = ec.simulation_year
            GROUP BY simulation_year
            ORDER BY simulation_year
        """, self.db.get_connection())

        # Calculate participation rate
        metrics['participation_rate'] = metrics['enrolled_employees'] / metrics['total_employees']

        return metrics
```

### CLI Integration
```python
# navigator_orchestrator/cli.py - Add batch subcommand
def cmd_batch(args: argparse.Namespace) -> int:
    """Execute batch scenario processing"""

    scenarios_dir = Path(args.scenarios_dir or "batch_scenarios")
    outputs_dir = Path(args.output_dir or "batch_outputs")

    if not scenarios_dir.exists():
        print(f"❌ Scenarios directory not found: {scenarios_dir}")
        return 1

    # Run batch processing
    batch_runner = ScenarioBatchRunner(scenarios_dir, outputs_dir)

    scenario_names = args.scenarios.split(',') if args.scenarios else None
    results = batch_runner.run_batch(scenario_names)

    # Print summary
    successful = sum(1 for r in results.values() if r.get('status') == 'completed')
    failed = len(results) - successful

    print(f"\n🎯 Batch execution complete:")
    print(f"  ✅ Successful: {successful}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📁 Results: {batch_runner.batch_output_dir}")

    return 0 if failed == 0 else 1

# Add to argument parser
batch_parser = subparsers.add_parser('batch', help='Run multiple scenarios in batch')
batch_parser.add_argument('--scenarios-dir', help='Directory containing scenario configs')
batch_parser.add_argument('--output-dir', help='Directory for batch outputs')
batch_parser.add_argument('--scenarios', help='Comma-separated list of specific scenarios to run')
batch_parser.add_argument('--with-comparison', action='store_true', help='Generate comparison report')
batch_parser.set_defaults(func=cmd_batch)
```

## Directory Structure

### Input Structure
```
batch_scenarios/
├── simulation_baseline.yaml
├── simulation_s1_aip_new_hires.yaml
├── simulation_s2_aip_all.yaml
└── simulation_s3_enhanced_match.yaml
```

### Output Structure
```
batch_outputs/
└── batch_20250818_143022/
    ├── baseline/
    │   ├── baseline.duckdb
    │   ├── baseline_results.xlsx
    │   └── exports/
    ├── s1_aip_new_hires/
    │   ├── s1_aip_new_hires.duckdb
    │   ├── s1_aip_new_hires_results.xlsx
    │   └── exports/
    ├── s2_aip_all/
    │   └── ...
    └── comparison_report.xlsx
```

## Sample Scenario Configurations

### simulation_baseline.yaml
```yaml
# Baseline scenario - current plan design
scenario:
  name: "baseline"
  description: "Current plan design with voluntary enrollment only"

simulation:
  start_year: 2025
  end_year: 2029
  random_seed: 42
  target_growth_rate: 0.03

enrollment:
  auto_enrollment:
    enabled: false
  voluntary_enrollment:
    enabled: true
    annual_enrollment_probability: 0.60

employer_match:
  active_formula: 'simple_match'
```

### simulation_s1_aip_new_hires.yaml
```yaml
# Auto-enroll new hires only
base_config: "simulation_baseline.yaml"

scenario:
  name: "s1_aip_new_hires"
  description: "Auto-enrollment for new hires hired after 2025-01-01"

enrollment:
  auto_enrollment:
    enabled: true
    scope: "new_hires_only"
    hire_date_cutoff: "2025-01-01"
    default_deferral_rate: 0.06
    window_days: 45
  voluntary_enrollment:
    enabled: true
    annual_enrollment_probability: 0.60  # Keep existing voluntary for current employees
```

### simulation_s2_aip_all.yaml
```yaml
# Auto-enroll all eligible employees
base_config: "simulation_baseline.yaml"

scenario:
  name: "s2_aip_all"
  description: "Auto-enrollment for all eligible employees"

enrollment:
  auto_enrollment:
    enabled: true
    scope: "all_eligible_employees"
    default_deferral_rate: 0.06
    window_days: 45
  voluntary_enrollment:
    enabled: false  # Replaced by auto-enrollment
```

## Success Metrics

### Processing Efficiency
- **Batch execution time**: Complete 4-scenario batch in <30 minutes
- **Database isolation**: Zero cross-scenario data contamination
- **Error recovery**: Continue processing remaining scenarios after individual failures
- **Resource management**: Automated cleanup of temporary databases

### Output Quality
- **Export completeness**: All key tables exported to Excel with proper formatting
- **Comparison accuracy**: Scenario differences accurately captured and highlighted
- **Metadata preservation**: Scenario configuration and run details included in outputs
- **Analyst usability**: Excel outputs ready for analysis without additional processing

### Operational Value
- **Scenario throughput**: Enable analysis of 10+ scenarios per day
- **Decision support**: Clear comparison reports highlighting policy trade-offs
- **Reproducibility**: Identical results for same scenario configurations
- **Documentation**: Complete audit trail of scenario assumptions and results

## CLI Usage Examples

```bash
# Run all scenarios in batch_scenarios/
python -m navigator_orchestrator.cli batch

# Run specific scenarios
python -m navigator_orchestrator.cli batch --scenarios baseline,s1_aip_new_hires,s2_aip_all

# Custom directories
python -m navigator_orchestrator.cli batch --scenarios-dir my_scenarios --output-dir my_results

# With comparison report
python -m navigator_orchestrator.cli batch --with-comparison
```

## Integration with Production Hardening

This epic builds on the production hardening epics:

- **E043**: Uses backup system for database safety during batch processing
- **E044**: Leverages logging framework for batch execution tracking
- **E045**: Ensures data integrity across multiple scenario databases
- **E046**: Integrates with checkpoint system for scenario resume capability

## Definition of Done

- [x] **Batch runner implementation** executing multiple scenarios with database isolation
- [x] **CLI integration** with batch subcommand in navigator_orchestrator
- [x] **Excel export capability** producing analyst-friendly formatted outputs
- [x] **Comparison reporting** highlighting key differences between scenarios
- [x] **Error handling** continuing batch execution despite individual scenario failures
- [x] **Documentation** with example scenarios and usage instructions
- [x] **Testing** validating batch processing with sample scenario configurations

## Related Epics

- **E043**: Production Data Safety & Backup System (provides database safety)
- **E044**: Production Observability & Logging Framework (logs batch execution)
- **E047**: Production Testing & Validation Framework (validates batch outputs)

---

**Implementation Note**: This epic focuses on practical scenario analysis capabilities that work with the existing navigator_orchestrator architecture, enabling efficient plan design comparison and policy impact analysis.
