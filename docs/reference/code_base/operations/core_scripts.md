# Core Scripts - Primary Operational Utilities

## Purpose

The core operational scripts in `scripts/` provide essential utilities for managing Fidelity PlanAlign Engine simulations, data operations, and system maintenance. These scripts serve as the primary interface for running simulations, validating data, and performing administrative tasks.

## Architecture

The scripts implement a modular design with:
- **Simulation Management**: Primary simulation execution and control
- **Data Operations**: Data cleanup, validation, and maintenance
- **Environment Management**: Setup, configuration, and deployment
- **Analysis Tools**: Data exploration and validation utilities

## Key Core Scripts

### 1. run_simulation.py - Primary Simulation Interface

**Purpose**: Main script for executing workforce simulations with configuration management and result validation.

```python
#!/usr/bin/env python3
"""
Fidelity PlanAlign Engine - Simulation Execution Script

Usage:
    python scripts/run_simulation.py --config config/simulation_config.yaml
    python scripts/run_simulation.py --scenario test --years 3
    python scripts/run_simulation.py --quick-test
"""

import argparse
import sys
import os
import yaml
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator.utils.config_loader import ConfigLoader
from orchestrator.utils.simulation_utils import SimulationValidator
from orchestrator.utils.database_utils import DatabaseManager

class SimulationRunner:
    """Main simulation execution controller"""

    def __init__(self, config_path: str = None, verbose: bool = False):
        self.config_path = config_path or "config/simulation_config.yaml"
        self.verbose = verbose
        self.logger = self._setup_logging()

        # Initialize components
        self.config_loader = ConfigLoader()
        self.validator = SimulationValidator()
        self.db_manager = DatabaseManager()

        # Load configuration
        self.config = self._load_configuration()

    def _setup_logging(self) -> logging.Logger:
        """Configure logging for simulation execution"""
        log_level = logging.DEBUG if self.verbose else logging.INFO

        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'logs/simulation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            ]
        )

        return logging.getLogger(__name__)

    def _load_configuration(self) -> Dict[str, Any]:
        """Load and validate simulation configuration"""
        try:
            self.logger.info(f"Loading configuration from {self.config_path}")
            config = self.config_loader.load_config(self.config_path)

            # Validate configuration
            validation_result = self.validator.validate_config(config)
            if not validation_result.is_valid:
                raise ValueError(f"Configuration validation failed: {validation_result.errors}")

            self.logger.info("Configuration loaded and validated successfully")
            return config

        except Exception as e:
            self.logger.error(f"Failed to load configuration: {str(e)}")
            raise

    def run_simulation(self, simulation_type: str = "multi_year") -> Dict[str, Any]:
        """Execute simulation with specified type"""

        try:
            self.logger.info(f"Starting {simulation_type} simulation")
            start_time = datetime.now()

            # Pre-simulation validation
            self._validate_environment()

            # Clean existing data if requested
            if self.config.get('simulation', {}).get('clean_data', False):
                self.logger.info("Cleaning existing simulation data")
                self._clean_simulation_data()

            # Execute simulation via Dagster
            execution_result = self._execute_dagster_job(simulation_type)

            # Post-simulation validation
            validation_result = self._validate_results()

            execution_time = (datetime.now() - start_time).total_seconds()

            # Prepare results summary
            result = {
                'status': 'success' if execution_result['success'] else 'failed',
                'execution_time': execution_time,
                'config_file': self.config_path,
                'simulation_type': simulation_type,
                'validation': validation_result,
                'summary': self._generate_summary(),
                'dagster_result': execution_result
            }

            self.logger.info(f"Simulation completed in {execution_time:.2f} seconds")
            return result

        except Exception as e:
            self.logger.error(f"Simulation failed: {str(e)}")
            return {
                'status': 'error',
                'error': str(e),
                'execution_time': (datetime.now() - start_time).total_seconds()
            }

    def _validate_environment(self) -> None:
        """Validate environment prerequisites"""
        self.logger.info("Validating environment")

        # Check database connectivity
        if not self.db_manager.test_connection():
            raise RuntimeError("Database connection failed")

        # Check required directories
        required_dirs = ['data', 'logs', 'config']
        for dir_name in required_dirs:
            dir_path = project_root / dir_name
            if not dir_path.exists():
                self.logger.warning(f"Creating missing directory: {dir_path}")
                dir_path.mkdir(parents=True, exist_ok=True)

        # Validate data freshness
        data_validation = self.validator.validate_data_freshness()
        if not data_validation.is_valid:
            self.logger.warning(f"Data freshness issues: {data_validation.warnings}")

    def _clean_simulation_data(self) -> None:
        """Clean existing simulation data"""
        self.logger.info("Cleaning simulation data")

        # Implementation would clean simulation-specific tables
        # while preserving baseline and configuration data

        cleanup_tables = [
            'fct_yearly_events',
            'fct_workforce_snapshot',
            'int_hiring_events',
            'int_promotion_events',
            'int_termination_events',
            'int_merit_events'
        ]

        for table in cleanup_tables:
            try:
                self.db_manager.truncate_table(table)
                self.logger.debug(f"Cleaned table: {table}")
            except Exception as e:
                self.logger.warning(f"Could not clean table {table}: {str(e)}")

    def _execute_dagster_job(self, simulation_type: str) -> Dict[str, Any]:
        """Execute Dagster simulation job"""
        import subprocess

        job_name = f"{simulation_type}_simulation"
        cmd = [
            "dagster", "job", "execute",
            "-f", "definitions.py",
            "-j", job_name,
            "-c", self.config_path
        ]

        self.logger.info(f"Executing Dagster job: {job_name}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minute timeout
                cwd=project_root
            )

            if result.returncode == 0:
                self.logger.info("Dagster job completed successfully")
                return {
                    'success': True,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'return_code': result.returncode
                }
            else:
                self.logger.error(f"Dagster job failed with return code {result.returncode}")
                self.logger.error(f"STDERR: {result.stderr}")
                return {
                    'success': False,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'return_code': result.returncode
                }

        except subprocess.TimeoutExpired:
            self.logger.error("Dagster job timed out")
            return {
                'success': False,
                'error': 'Job execution timed out (30 minutes)'
            }

    def _validate_results(self) -> Dict[str, Any]:
        """Validate simulation results"""
        self.logger.info("Validating simulation results")

        validation_results = {
            'data_quality': self.validator.validate_data_quality(),
            'business_rules': self.validator.validate_business_rules(),
            'growth_targets': self.validator.validate_growth_targets(self.config),
            'financial_constraints': self.validator.validate_financial_constraints(self.config)
        }

        # Aggregate validation status
        all_valid = all(result.is_valid for result in validation_results.values())

        return {
            'overall_valid': all_valid,
            'details': validation_results,
            'warnings': [
                warning for result in validation_results.values()
                for warning in result.warnings
            ],
            'errors': [
                error for result in validation_results.values()
                for error in result.errors
            ]
        }

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate simulation results summary"""
        try:
            # Load results from database
            query = """
            SELECT
                simulation_year,
                active_headcount,
                growth_rate_percent,
                turnover_rate_percent,
                total_compensation,
                total_hires,
                total_promotions,
                total_terminations
            FROM mart_workforce_summary
            ORDER BY simulation_year
            """

            results = self.db_manager.execute_query(query)

            if results.empty:
                return {'message': 'No results available'}

            # Calculate summary metrics
            final_year = results.iloc[-1]
            initial_year = results.iloc[0]

            return {
                'years_simulated': len(results),
                'initial_headcount': int(initial_year['active_headcount']),
                'final_headcount': int(final_year['active_headcount']),
                'total_growth': int(final_year['active_headcount'] - initial_year['active_headcount']),
                'avg_growth_rate': float(results['growth_rate_percent'].mean()),
                'avg_turnover_rate': float(results['turnover_rate_percent'].mean()),
                'total_events': {
                    'hires': int(results['total_hires'].sum()),
                    'promotions': int(results['total_promotions'].sum()),
                    'terminations': int(results['total_terminations'].sum())
                },
                'final_compensation': float(final_year['total_compensation'])
            }

        except Exception as e:
            self.logger.error(f"Failed to generate summary: {str(e)}")
            return {'error': str(e)}

def main():
    """Main entry point for simulation script"""
    parser = argparse.ArgumentParser(description='Run Fidelity PlanAlign Engine workforce simulation')

    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config/simulation_config.yaml',
        help='Path to simulation configuration file'
    )

    parser.add_argument(
        '--type', '-t',
        type=str,
        choices=['single_year', 'multi_year'],
        default='multi_year',
        help='Type of simulation to run'
    )

    parser.add_argument(
        '--scenario',
        type=str,
        help='Named scenario configuration to use'
    )

    parser.add_argument(
        '--years',
        type=int,
        help='Number of years to simulate (overrides config)'
    )

    parser.add_argument(
        '--clean',
        action='store_true',
        help='Clean existing simulation data before running'
    )

    parser.add_argument(
        '--quick-test',
        action='store_true',
        help='Run quick test scenario (1 year, small dataset)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    try:
        # Handle special scenarios
        if args.quick_test:
            args.config = 'config/test_config.yaml'
            args.type = 'single_year'
            print("Running quick test scenario...")

        if args.scenario:
            args.config = f'config/{args.scenario}_config.yaml'

        # Initialize and run simulation
        runner = SimulationRunner(
            config_path=args.config,
            verbose=args.verbose
        )

        # Override configuration if specified
        if args.years:
            runner.config['simulation']['end_year'] = runner.config['simulation']['start_year'] + args.years - 1

        if args.clean:
            runner.config['simulation']['clean_data'] = True

        # Execute simulation
        result = runner.run_simulation(args.type)

        # Display results
        if result['status'] == 'success':
            print(f"\n✅ Simulation completed successfully!")
            print(f"   Execution time: {result['execution_time']:.2f} seconds")

            if 'summary' in result:
                summary = result['summary']
                print(f"   Years simulated: {summary.get('years_simulated', 'N/A')}")
                print(f"   Final headcount: {summary.get('final_headcount', 'N/A'):,}")
                print(f"   Total growth: {summary.get('total_growth', 'N/A'):+,}")
                print(f"   Average growth rate: {summary.get('avg_growth_rate', 'N/A'):.1f}%")
        else:
            print(f"\n❌ Simulation failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n⚠️  Simulation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### 2. clean_simulation_data.py - Data Cleanup Utility

**Purpose**: Comprehensive data cleanup and reset functionality for simulation environments.

```python
#!/usr/bin/env python3
"""
Data cleanup utility for Fidelity PlanAlign Engine

Usage:
    python scripts/clean_simulation_data.py --all
    python scripts/clean_simulation_data.py --events-only
    python scripts/clean_simulation_data.py --year 2025
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import List, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator.utils.database_utils import DatabaseManager

class DataCleaner:
    """Comprehensive data cleanup utility"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = self._setup_logging()
        self.db_manager = DatabaseManager()

    def _setup_logging(self) -> logging.Logger:
        log_level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')
        return logging.getLogger(__name__)

    def clean_all_simulation_data(self) -> None:
        """Clean all simulation-generated data"""
        self.logger.info("Cleaning all simulation data")

        tables_to_clean = [
            'fct_yearly_events',
            'fct_workforce_snapshot',
            'int_hiring_events',
            'int_promotion_events',
            'int_termination_events',
            'int_merit_events',
            'int_previous_year_workforce',
            'mart_workforce_summary',
            'mart_cohort_analysis',
            'mart_financial_impact'
        ]

        self._clean_tables(tables_to_clean)

    def clean_events_only(self) -> None:
        """Clean only event tables, preserve workforce snapshots"""
        self.logger.info("Cleaning event data only")

        event_tables = [
            'fct_yearly_events',
            'int_hiring_events',
            'int_promotion_events',
            'int_termination_events',
            'int_merit_events'
        ]

        self._clean_tables(event_tables)

    def clean_specific_year(self, year: int) -> None:
        """Clean data for specific simulation year"""
        self.logger.info(f"Cleaning data for year {year}")

        tables_with_year = [
            'fct_yearly_events',
            'fct_workforce_snapshot',
            'int_hiring_events',
            'int_promotion_events',
            'int_termination_events',
            'int_merit_events'
        ]

        for table in tables_with_year:
            try:
                self.db_manager.execute_query(
                    f"DELETE FROM {table} WHERE simulation_year = ?",
                    [year]
                )
                self.logger.info(f"Cleaned {table} for year {year}")
            except Exception as e:
                self.logger.error(f"Failed to clean {table}: {str(e)}")

    def _clean_tables(self, tables: List[str]) -> None:
        """Clean specified tables"""
        for table in tables:
            try:
                self.db_manager.truncate_table(table)
                self.logger.info(f"Cleaned table: {table}")
            except Exception as e:
                self.logger.warning(f"Could not clean {table}: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Clean Fidelity PlanAlign Engine simulation data')

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true', help='Clean all simulation data')
    group.add_argument('--events-only', action='store_true', help='Clean event data only')
    group.add_argument('--year', type=int, help='Clean data for specific year')

    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')

    args = parser.parse_args()

    cleaner = DataCleaner(verbose=args.verbose)

    try:
        if args.all:
            cleaner.clean_all_simulation_data()
        elif args.events_only:
            cleaner.clean_events_only()
        elif args.year:
            cleaner.clean_specific_year(args.year)

        print("✅ Data cleanup completed successfully")

    except Exception as e:
        print(f"❌ Cleanup failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### 3. validate_workforce_dynamics.py - Comprehensive Validation

**Purpose**: End-to-end validation framework for workforce dynamics and simulation accuracy.

**Key Features**:
- Business rule validation
- Statistical validation of results
- Growth rate verification
- Financial constraint checking
- Data quality assessment

### 4. setup_unified_pipeline.py - Environment Setup

**Purpose**: Validate environment setup and perform migration tasks for unified pipeline deployment.

**Key Features**:
- Environment validation
- Database schema validation
- Configuration validation
- Migration readiness assessment
- Dependency checking

## Supporting Scripts

### Auto-optimization Scripts
- **auto_tune_hazard_tables.py**: Automated parameter optimization
- **simple_drift_optimizer.py**: Parameter drift optimization
- **analyze_termination_patterns.py**: Advanced pattern analysis

### Analysis Tools
- **quick_growth_analysis.py**: Rapid growth scenario analysis
- **analyze_workforce_composition.py**: Demographic analysis tools
- **export_simulation_results.py**: Data export utilities

## Script Configuration

### Common Configuration Pattern
```python
# Standard configuration loading
from orchestrator.utils.config_loader import ConfigLoader

def load_script_config(config_path: str, overrides: Dict[str, Any] = None):
    """Load configuration with script-specific overrides"""
    loader = ConfigLoader()
    config = loader.load_config(config_path)

    if overrides:
        config = loader.apply_overrides(config, overrides)

    return config
```

### Logging Configuration
```python
def setup_script_logging(script_name: str, verbose: bool = False):
    """Standard logging setup for all scripts"""
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                log_dir / f"{script_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            )
        ]
    )

    return logging.getLogger(script_name)
```

## Usage Examples

### Basic Simulation Execution
```bash
# Run standard multi-year simulation
python scripts/run_simulation.py

# Run with custom configuration
python scripts/run_simulation.py --config config/test_config.yaml

# Quick test run
python scripts/run_simulation.py --quick-test

# Clean and run simulation
python scripts/run_simulation.py --clean --verbose
```

### Data Management
```bash
# Clean all simulation data
python scripts/clean_simulation_data.py --all

# Clean specific year
python scripts/clean_simulation_data.py --year 2025

# Validate results
python scripts/validate_workforce_dynamics.py --comprehensive
```

## Dependencies

### External Dependencies
- `subprocess` - For Dagster job execution
- `argparse` - Command-line interface
- `logging` - Comprehensive logging
- `yaml` - Configuration management

### Internal Dependencies
- Database utilities and connection management
- Configuration loading and validation
- Simulation validation framework
- Dagster pipeline definitions

## Related Files

### Core Infrastructure
- `orchestrator/utils/` - Utility libraries
- `config/` - Configuration files
- `definitions.py` - Dagster pipeline definitions

### Environment Scripts
- `scripts/start_dagster.sh` - Development server startup
- `scripts/start_dashboard.sh` - Dashboard deployment
- `scripts/set_dagster_home.sh` - Environment configuration

## Implementation Notes

### Best Practices
1. **Error Handling**: Comprehensive error handling with meaningful messages
2. **Logging**: Consistent logging across all scripts
3. **Configuration**: Flexible configuration management with overrides
4. **Validation**: Thorough validation before and after operations

### Performance Considerations
- Use connection pooling for database operations
- Implement appropriate timeouts for long-running operations
- Provide progress indicators for lengthy processes
- Cache expensive validation operations

### Security Guidelines
- Validate all input parameters
- Use parameterized queries for database operations
- Implement proper access controls for sensitive operations
- Log all administrative actions for audit trails
