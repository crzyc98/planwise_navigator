"""
Multi-year simulation orchestrator with systematic checklist enforcement.

This module provides the MultiYearSimulationOrchestrator class that wraps the existing
multi-year simulation functionality with systematic checklist validation, ensuring
proper step sequencing and preventing users from executing steps out of order.
"""

from __future__ import annotations
import logging
from typing import Dict, Any, Optional, List
import time
from datetime import datetime

from .simulation_checklist import SimulationChecklist, StepSequenceError, SimulationStep
from .multi_year_simulation import (
    validate_year_transition,
    get_baseline_workforce_count,
    get_previous_year_workforce_count
)
from .workforce_calculations import (
    calculate_workforce_requirements_from_config,
    validate_workforce_calculation_inputs
)
from .event_emitter import generate_and_store_all_events
from .workforce_snapshot import generate_workforce_snapshot
from .database_manager import get_connection

logger = logging.getLogger(__name__)


class MultiYearSimulationOrchestrator:
    """
    Orchestrates multi-year workforce simulations with systematic checklist enforcement.

    This class ensures that the 7-step workflow is executed in proper sequence for each
    simulation year, preventing users from skipping steps or executing them out of order.
    Provides resume capability and comprehensive error handling with clear guidance.
    """

    def __init__(
        self,
        start_year: int,
        end_year: int,
        config: Dict[str, Any],
        force_clear: bool = False,
        preserve_data: bool = True
    ):
        """
        Initialize orchestrator with simulation parameters.

        Args:
            start_year: First year of simulation (e.g., 2025)
            end_year: Last year of simulation (e.g., 2029)
            config: Configuration dictionary containing simulation parameters
            force_clear: If True, clear all simulation data before starting
            preserve_data: If True, preserve existing multi-year data (default)
        """
        self.start_year = start_year
        self.end_year = end_year
        self.config = config
        self.years = list(range(start_year, end_year + 1))
        self.force_clear = force_clear
        self.preserve_data = preserve_data

        # Initialize checklist for step tracking
        self.checklist = SimulationChecklist(start_year, end_year)

        # Simulation results tracking
        self.results = {
            'start_year': start_year,
            'end_year': end_year,
            'years_completed': [],
            'years_failed': [],
            'total_runtime_seconds': 0,
            'year_runtimes': {},
            'step_details': {}
        }

        logger.info(
            f"Initialized MultiYearSimulationOrchestrator for years {start_year}-{end_year}"
        )
        logger.info(f"Data management: force_clear={force_clear}, preserve_data={preserve_data}")

        # Validate configuration
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        """Validate simulation configuration parameters."""
        required_params = ['target_growth_rate']
        missing_params = [param for param in required_params if param not in self.config]

        if missing_params:
            raise ValueError(f"Missing required configuration parameters: {missing_params}")

        # Extract workforce configuration
        workforce_config = self.config.get('workforce', {})
        if 'total_termination_rate' not in workforce_config:
            workforce_config['total_termination_rate'] = 0.12  # Default 12%
        if 'new_hire_termination_rate' not in workforce_config:
            workforce_config['new_hire_termination_rate'] = 0.25  # Default 25%

        self.config['workforce'] = workforce_config

        # Extract and validate eligibility configuration
        eligibility_config = self.config.get('eligibility', {})
        if 'waiting_period_days' not in eligibility_config:
            eligibility_config['waiting_period_days'] = 365  # Default 1 year

        # Validate waiting period is reasonable (0-1095 days, i.e., 0-3 years)
        waiting_period = eligibility_config['waiting_period_days']
        if not isinstance(waiting_period, int) or waiting_period < 0 or waiting_period > 1095:
            raise ValueError(f"Invalid waiting_period_days: {waiting_period}. Must be integer between 0-1095 days.")

        self.config['eligibility'] = eligibility_config

        logger.info("Configuration validated successfully")
        logger.info(f"Eligibility waiting period: {waiting_period} days")

    def run_simulation(
        self,
        skip_breaks: bool = False,
        resume_from: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute complete multi-year simulation with checklist enforcement.

        Args:
            skip_breaks: If True, skip user interaction prompts between years
            resume_from: Optional year to resume from (must have valid checkpoint)

        Returns:
            Dictionary containing simulation results and metadata

        Raises:
            StepSequenceError: If attempting to skip required steps
            ValueError: If configuration or data validation fails
        """
        logger.info(f"🚀 Starting multi-year simulation: {self.start_year}-{self.end_year}")
        start_time = time.time()

        try:
            # Handle resume logic
            if resume_from is not None:
                if resume_from not in self.years:
                    raise ValueError(f"Resume year {resume_from} not in simulation range")
                logger.info(f"🔄 Resuming simulation from year {resume_from}")
                start_year = resume_from
            else:
                start_year = self.start_year
                # Execute pre-simulation setup only if not preserving data or force clearing
                if not self.preserve_data or self.force_clear:
                    self._execute_pre_simulation_setup()
                else:
                    logger.info("🔄 Preserving existing simulation data - skipping data clearing")
                    self._validate_seed_data()  # Still validate required data is available

            # Execute simulation for each year
            for current_year in range(start_year, self.end_year + 1):
                year_start_time = time.time()
                logger.info(f"\n🗓️  SIMULATING YEAR {current_year}")
                logger.info("=" * 50)

                try:
                    # Initialize year in checklist
                    self.checklist.begin_year(current_year)

                    # Execute 7-step workflow for this year
                    self._execute_year_workflow(current_year)

                    # Record successful completion
                    year_runtime = time.time() - year_start_time
                    self.results['years_completed'].append(current_year)
                    self.results['year_runtimes'][current_year] = year_runtime

                    logger.info(f"✅ Year {current_year} completed in {year_runtime:.1f}s")

                    # Interactive break between years (unless skipped or last year)
                    if not skip_breaks and current_year < self.end_year:
                        input(f"📋 Press Enter to continue to year {current_year + 1}...")

                except Exception as e:
                    logger.error(f"❌ Year {current_year} simulation failed: {str(e)}")
                    self.results['years_failed'].append(current_year)
                    raise

            # Calculate total runtime and finalize results
            self.results['total_runtime_seconds'] = time.time() - start_time

            logger.info(f"\n🎉 Multi-year simulation completed successfully!")
            logger.info(f"Years simulated: {self.start_year}-{self.end_year}")
            logger.info(f"Total runtime: {self.results['total_runtime_seconds']:.1f}s")

            return self.results

        except Exception as e:
            self.results['total_runtime_seconds'] = time.time() - start_time
            logger.error(f"💥 Multi-year simulation failed: {str(e)}")
            raise

    def _execute_pre_simulation_setup(self) -> None:
        """Execute pre-simulation setup step with checklist validation."""
        logger.info("🔧 Executing pre-simulation setup")

        try:
            # Validate step readiness (should always pass for pre-simulation)
            self.checklist.assert_step_ready("pre_simulation")

            # Execute pre-simulation tasks
            self._clear_previous_simulation_data()
            self._validate_seed_data()
            self._prepare_baseline_workforce()

            # Mark step as complete
            self.checklist.mark_step_complete("pre_simulation")
            logger.info("✅ Pre-simulation setup completed")

        except Exception as e:
            logger.error(f"❌ Pre-simulation setup failed: {str(e)}")
            raise

    def _execute_year_workflow(self, year: int) -> None:
        """
        Execute the complete 7-step workflow for a simulation year.

        Args:
            year: Simulation year to execute
        """
        self.results['step_details'][year] = {}

        # Step 1: Year Transition Validation (skip for first year)
        if year > self.start_year:
            self._execute_year_transition(year)
        else:
            # For first year, mark year transition as complete (no transition needed)
            self.checklist.mark_step_complete("year_transition", year)

        # Step 2: Workforce Baseline Preparation
        self._execute_workforce_baseline(year)

        # Step 3: Workforce Requirements Calculation
        self._execute_workforce_requirements(year)

        # Step 4: Event Generation Pipeline
        self._execute_event_generation(year)

        # Step 5: Workforce Snapshot Generation
        self._execute_workforce_snapshot(year)

        # Step 6: Validation & Metrics
        self._execute_validation_metrics(year)

        # Mark year completion
        self.checklist.mark_step_complete("validation_metrics", year)

    def _execute_year_transition(self, year: int) -> None:
        """Execute year transition validation step with circular dependency checks."""
        step_start_time = time.time()
        logger.info(f"📋 Step 1: Year Transition Validation ({year-1} → {year})")

        try:
            # Validate step readiness
            self.checklist.assert_step_ready("year_transition", year)

            # For subsequent years, validate previous year's workforce snapshot exists
            if year > self.start_year:
                self._validate_previous_year_snapshot(year - 1)
                logger.info(f"✅ Previous year ({year-1}) workforce snapshot validated")

            # Execute year transition validation
            if not validate_year_transition(year - 1, year):
                raise ValueError(f"Year transition validation failed for {year}")

            # Mark step complete
            step_time = time.time() - step_start_time
            self.checklist.mark_step_complete("year_transition", year)
            self.results['step_details'][year]['year_transition'] = step_time

            logger.info(f"✅ Year transition validation completed ({step_time:.2f}s)")

        except StepSequenceError as e:
            logger.error(f"❌ Step sequence error in year transition: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"❌ Year transition validation failed: {str(e)}")
            logger.error(f"💡 Ensure year {year-1} completed successfully before running year {year}")
            raise

    def _execute_workforce_baseline(self, year: int) -> None:
        """Execute workforce baseline preparation step with dependency validation."""
        step_start_time = time.time()
        logger.info(f"📋 Step 2: Workforce Baseline Preparation")

        try:
            # Validate step readiness
            self.checklist.assert_step_ready("workforce_baseline", year)

            # For subsequent years, validate helper model can be built
            if year > self.start_year:
                self._validate_helper_model_readiness(year)
                logger.info(f"✅ Circular dependency helper model validated for year {year}")

            # Determine and validate workforce count
            if year == self.start_year:
                logger.info(f"📊 Year {year}: Using baseline workforce")
                workforce_count = get_baseline_workforce_count()
            else:
                logger.info(f"📊 Year {year}: Using previous year workforce via helper model")
                workforce_count = get_previous_year_workforce_count(year)

            logger.info(f"Starting workforce for {year}: {workforce_count:,} employees")

            # Store workforce count for next steps
            self.results['step_details'][year]['workforce_count'] = workforce_count

            # Mark step complete
            step_time = time.time() - step_start_time
            self.checklist.mark_step_complete("workforce_baseline", year)
            self.results['step_details'][year]['workforce_baseline'] = step_time

            logger.info(f"✅ Workforce baseline preparation completed ({step_time:.2f}s)")

        except StepSequenceError as e:
            logger.error(f"❌ Step sequence error in workforce baseline: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"❌ Workforce baseline preparation failed: {str(e)}")
            logger.error(f"💡 Check that previous year data exists and is accessible")
            raise

    def _execute_workforce_requirements(self, year: int) -> None:
        """Execute workforce requirements calculation step."""
        step_start_time = time.time()
        logger.info(f"📋 Step 3: Workforce Requirements Calculation")

        try:
            # Validate step readiness
            self.checklist.assert_step_ready("workforce_requirements", year)

            # Get workforce count from previous step
            workforce_count = self.results['step_details'][year]['workforce_count']

            # Validate calculation inputs
            validation = validate_workforce_calculation_inputs(
                workforce_count,
                self.config.get('target_growth_rate', 0.03),
                self.config.get('workforce', {}).get('total_termination_rate', 0.12),
                self.config.get('workforce', {}).get('new_hire_termination_rate', 0.25)
            )

            if not validation['valid']:
                raise ValueError(f"Invalid workforce calculation inputs: {validation['errors']}")

            if validation['warnings']:
                for warning in validation['warnings']:
                    logger.warning(f"⚠️  {warning}")

            # Calculate workforce requirements
            calc_result = calculate_workforce_requirements_from_config(
                workforce_count,
                {
                    'target_growth_rate': self.config.get('target_growth_rate', 0.03),
                    'total_termination_rate': self.config.get('workforce', {}).get('total_termination_rate', 0.12),
                    'new_hire_termination_rate': self.config.get('workforce', {}).get('new_hire_termination_rate', 0.25)
                }
            )

            logger.info(f"📈 Growth calculation: +{calc_result['total_hires_needed']:,} hires, "
                       f"-{calc_result['experienced_terminations']:,} terminations")

            # Store calculation result for next steps
            self.results['step_details'][year]['calc_result'] = calc_result

            # Mark step complete
            step_time = time.time() - step_start_time
            self.checklist.mark_step_complete("workforce_requirements", year)
            self.results['step_details'][year]['workforce_requirements'] = step_time

            logger.info(f"✅ Workforce requirements calculation completed ({step_time:.2f}s)")

        except StepSequenceError as e:
            logger.error(f"❌ Step sequence error in workforce requirements: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"❌ Workforce requirements calculation failed: {str(e)}")
            raise

    def _execute_event_generation(self, year: int) -> None:
        """Execute event generation pipeline step."""
        step_start_time = time.time()
        logger.info(f"📋 Step 4: Event Generation Pipeline")

        try:
            # Validate step readiness
            self.checklist.assert_step_ready("event_generation", year)

            # Get calculation result from previous step
            calc_result = self.results['step_details'][year]['calc_result']

            # Generate random seed for this year
            random_seed = self.config.get('random_seed', 42) + (year - self.start_year)
            logger.info(f"🎲 Generating events for year {year} with seed {random_seed}")

            # Generate and store all events
            generate_and_store_all_events(
                calc_result=calc_result,
                simulation_year=year,
                random_seed=random_seed,
                config=self.config
            )

            # Mark step complete
            step_time = time.time() - step_start_time
            self.checklist.mark_step_complete("event_generation", year)
            self.results['step_details'][year]['event_generation'] = step_time

            logger.info(f"✅ Event generation pipeline completed ({step_time:.2f}s)")

        except StepSequenceError as e:
            logger.error(f"❌ Step sequence error in event generation: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"❌ Event generation pipeline failed: {str(e)}")
            raise

    def _execute_workforce_snapshot(self, year: int) -> None:
        """Execute workforce snapshot generation step."""
        step_start_time = time.time()
        logger.info(f"📋 Step 5: Workforce Snapshot Generation")

        try:
            # Validate step readiness
            self.checklist.assert_step_ready("workforce_snapshot", year)

            # Generate workforce snapshot
            logger.info(f"📸 Generating workforce snapshot for year {year}")
            generate_workforce_snapshot(simulation_year=year)

            # Mark step complete
            step_time = time.time() - step_start_time
            self.checklist.mark_step_complete("workforce_snapshot", year)
            self.results['step_details'][year]['workforce_snapshot'] = step_time

            logger.info(f"✅ Workforce snapshot generation completed ({step_time:.2f}s)")

        except StepSequenceError as e:
            logger.error(f"❌ Step sequence error in workforce snapshot: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"❌ Workforce snapshot generation failed: {str(e)}")
            raise

    def _execute_validation_metrics(self, year: int) -> None:
        """Execute validation and metrics step."""
        step_start_time = time.time()
        logger.info(f"📋 Step 6: Validation & Metrics")

        try:
            # Validate step readiness
            self.checklist.assert_step_ready("validation_metrics", year)

            # Execute validation checks
            validation_results = self._validate_year_results(year)

            # Store validation results
            self.results['step_details'][year]['validation_results'] = validation_results

            # Log validation summary
            logger.info(f"📊 Validation results for year {year}:")
            logger.info(f"   • Workforce continuity: {'✅' if validation_results['workforce_continuity'] else '❌'}")
            logger.info(f"   • Data quality: {'✅' if validation_results['data_quality'] else '❌'}")
            logger.info(f"   • Growth metrics: {'✅' if validation_results['growth_metrics'] else '❌'}")

            # Mark step complete
            step_time = time.time() - step_start_time
            self.checklist.mark_step_complete("validation_metrics", year)
            self.results['step_details'][year]['validation_metrics'] = step_time

            logger.info(f"✅ Validation & metrics completed ({step_time:.2f}s)")

        except StepSequenceError as e:
            logger.error(f"❌ Step sequence error in validation: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"❌ Validation & metrics failed: {str(e)}")
            raise

    def _validate_year_results(self, year: int) -> Dict[str, bool]:
        """
        Validate simulation results for a year.

        Args:
            year: Year to validate

        Returns:
            Dictionary with validation results
        """
        validation_results = {
            'workforce_continuity': False,
            'data_quality': False,
            'growth_metrics': False,
            'helper_model_ready': False
        }

        try:
            conn = get_connection()
            try:
                # Check workforce snapshot exists and has reasonable data
                snapshot_query = """
                    SELECT COUNT(*) as total_employees,
                           SUM(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) as active_employees
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                """

                result = conn.execute(snapshot_query, [year]).fetchone()

                if result and result[0] > 0 and result[1] > 0:
                    validation_results['workforce_continuity'] = True
                    total_employees, active_employees = result
                    logger.info(f"   Snapshot: {total_employees:,} total, {active_employees:,} active employees")

                # Check events exist
                events_query = """
                    SELECT COUNT(*) as event_count,
                           COUNT(CASE WHEN data_quality_flag = 'VALID' THEN 1 END) as valid_events
                    FROM fct_yearly_events
                    WHERE simulation_year = ?
                """

                events_result = conn.execute(events_query, [year]).fetchone()

                if events_result and events_result[0] > 0:
                    event_count, valid_events = events_result
                    validation_results['data_quality'] = valid_events == event_count
                    logger.info(f"   Events: {event_count:,} total, {valid_events:,} valid")

                # Check growth metrics are reasonable
                if year > self.start_year:
                    growth_valid = self._validate_growth_metrics(year, conn)
                    validation_results['growth_metrics'] = growth_valid
                else:
                    validation_results['growth_metrics'] = True  # First year baseline

                # Validate helper model readiness for subsequent years
                if year > self.start_year:
                    try:
                        # Check that helper model data source exists
                        helper_check = """
                            SELECT COUNT(*) FROM fct_workforce_snapshot
                            WHERE simulation_year = ? AND employment_status = 'active'
                        """
                        helper_result = conn.execute(helper_check, [year - 1]).fetchone()
                        validation_results['helper_model_ready'] = (helper_result and helper_result[0] > 0)

                        if validation_results['helper_model_ready']:
                            logger.info(f"   Helper model: Ready ({helper_result[0]:,} employees from year {year-1})")
                        else:
                            logger.warning(f"   Helper model: Not ready - missing previous year data")
                    except Exception as e:
                        logger.warning(f"   Helper model validation error: {str(e)}")
                        validation_results['helper_model_ready'] = False
                else:
                    validation_results['helper_model_ready'] = True  # Not needed for first year

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"❌ Validation error for year {year}: {str(e)}")
            # Keep all validation results as False

        return validation_results

    def _validate_growth_metrics(self, year: int, conn) -> bool:
        """Validate growth metrics between years."""
        try:
            # Compare workforce counts between years
            comparison_query = """
                WITH year_counts AS (
                    SELECT
                        simulation_year,
                        COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_count
                    FROM fct_workforce_snapshot
                    WHERE simulation_year IN (?, ?)
                    GROUP BY simulation_year
                )
                SELECT
                    current_year.active_count as current_active,
                    prev_year.active_count as prev_active,
                    CAST(current_year.active_count AS FLOAT) / prev_year.active_count - 1 as growth_rate
                FROM year_counts current_year
                JOIN year_counts prev_year ON prev_year.simulation_year = current_year.simulation_year - 1
                WHERE current_year.simulation_year = ?
            """

            result = conn.execute(comparison_query, [year - 1, year, year]).fetchone()

            if result:
                current_active, prev_active, actual_growth = result
                target_growth = self.config.get('target_growth_rate', 0.03)

                # Allow 20% variance from target
                growth_variance = abs(actual_growth - target_growth)
                growth_valid = growth_variance <= target_growth * 0.2

                logger.info(f"   Growth: {actual_growth:.2%} actual vs {target_growth:.2%} target")

                return growth_valid

        except Exception as e:
            logger.error(f"❌ Growth validation error: {str(e)}")

        return False

    def _clear_previous_simulation_data(self) -> None:
        """Clear simulation data based on configured clearing strategy."""
        if not self.force_clear:
            logger.info("🔄 Data clearing skipped - force_clear=False")
            return

        logger.info("🧹 Clearing previous simulation data")

        try:
            conn = get_connection()
            try:
                if self.force_clear:
                    # Clear only the specific simulation year range
                    conn.execute(
                        "DELETE FROM fct_yearly_events WHERE simulation_year BETWEEN ? AND ?",
                        [self.start_year, self.end_year]
                    )
                    conn.execute(
                        "DELETE FROM fct_workforce_snapshot WHERE simulation_year BETWEEN ? AND ?",
                        [self.start_year, self.end_year]
                    )
                    logger.info(f"✅ Simulation data cleared for years {self.start_year}-{self.end_year}")

            finally:
                conn.close()

        except Exception as e:
            logger.warning(f"⚠️  Error clearing previous data: {str(e)}")

    def _validate_seed_data(self) -> None:
        """Validate that required seed data is available."""
        logger.info("🔍 Validating seed data availability")

        required_tables = [
            'stg_config_job_levels',
            'comp_levers',
            'config_cola_by_year'
        ]

        try:
            conn = get_connection()
            try:
                for table in required_tables:
                    result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                    if not result or result[0] == 0:
                        raise ValueError(f"Required seed table '{table}' is empty or missing")

                logger.info("✅ Seed data validation passed")

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"❌ Seed data validation failed: {str(e)}")
            raise

    def _prepare_baseline_workforce(self) -> None:
        """Prepare baseline workforce for simulation."""
        logger.info("👥 Preparing baseline workforce")

        try:
            # Ensure baseline workforce exists
            baseline_count = get_baseline_workforce_count()
            logger.info(f"✅ Baseline workforce prepared: {baseline_count:,} employees")

        except Exception as e:
            logger.error(f"❌ Baseline workforce preparation failed: {str(e)}")
            raise

    def get_progress_summary(self) -> str:
        """Get human-readable progress summary."""
        return self.checklist.get_progress_summary()

    def can_resume_from(self, year: int, step: str) -> bool:
        """Check if simulation can resume from a specific point."""
        return self.checklist.can_resume_from(year, step)

    def rollback_year(self, year: int) -> None:
        """
        Rollback a specific year's progress for recovery scenarios.
        Only clears data for the specific year to preserve multi-year continuity.

        Args:
            year: Year to rollback
        """
        logger.info(f"🔄 Rolling back year {year} (selective clearing)")

        try:
            # Clear year data from checklist
            self.checklist.reset_year(year)

            # Clear only this specific year's data from database
            conn = get_connection()
            try:
                events_deleted = conn.execute(
                    "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year]
                ).rowcount
                snapshot_deleted = conn.execute(
                    "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?", [year]
                ).rowcount

                logger.info(f"   Cleared: {events_deleted} events, {snapshot_deleted} snapshots")
            finally:
                conn.close()

            # Remove from results if present
            if year in self.results['years_completed']:
                self.results['years_completed'].remove(year)
            if year in self.results['step_details']:
                del self.results['step_details'][year]

            logger.info(f"✅ Year {year} rollback completed - other years preserved")

        except Exception as e:
            logger.error(f"❌ Year {year} rollback failed: {str(e)}")
            raise

    def clear_specific_years(self, years: List[int]) -> None:
        """
        Clear data for specific years only, preserving other simulation data.

        Args:
            years: List of years to clear
        """
        logger.info(f"🧹 Clearing data for specific years: {years}")

        try:
            conn = get_connection()
            try:
                for year in years:
                    events_deleted = conn.execute(
                        "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year]
                    ).rowcount
                    snapshot_deleted = conn.execute(
                        "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?", [year]
                    ).rowcount

                    logger.info(f"   Year {year}: {events_deleted} events, {snapshot_deleted} snapshots cleared")

            finally:
                conn.close()

            logger.info("✅ Selective year clearing completed")

        except Exception as e:
            logger.error(f"❌ Selective year clearing failed: {str(e)}")
            raise

    def _validate_previous_year_snapshot(self, previous_year: int) -> None:
        """
        Validate that the previous year's workforce snapshot exists and has valid data.
        This prevents circular dependency issues by ensuring sequential execution.

        Args:
            previous_year: The previous year to validate

        Raises:
            ValueError: If previous year data is missing or invalid
        """
        try:
            conn = get_connection()
            try:
                # Check if previous year workforce snapshot exists
                snapshot_query = """
                    SELECT COUNT(*) as total_employees,
                           COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                """

                result = conn.execute(snapshot_query, [previous_year]).fetchone()

                if not result or result[0] == 0:
                    raise ValueError(
                        f"No workforce snapshot found for year {previous_year}. "
                        f"You must complete year {previous_year} before running the current year. "
                        f"Multi-year simulations must be run sequentially."
                    )

                total_employees, active_employees = result

                if active_employees == 0:
                    raise ValueError(
                        f"Year {previous_year} workforce snapshot has no active employees. "
                        f"This indicates a data quality issue - please review year {previous_year} results."
                    )

                logger.info(f"✅ Previous year validation: {total_employees:,} total, {active_employees:,} active employees")

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"❌ Previous year snapshot validation failed: {str(e)}")
            raise

    def _validate_helper_model_readiness(self, year: int) -> None:
        """
        Validate that the circular dependency helper model can be built successfully.
        This ensures the int_active_employees_prev_year_snapshot model has access to required data.

        Args:
            year: Current simulation year

        Raises:
            ValueError: If helper model cannot be built
        """
        previous_year = year - 1

        try:
            conn = get_connection()
            try:
                # Simulate the helper model's main query to ensure it will work
                test_query = """
                    SELECT COUNT(*) as available_employees
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ? AND employment_status = 'active'
                """

                result = conn.execute(test_query, [previous_year]).fetchone()

                if not result or result[0] == 0:
                    raise ValueError(
                        f"Helper model validation failed: No active employees found in year {previous_year} snapshot. "
                        f"The circular dependency helper model (int_active_employees_prev_year_snapshot) "
                        f"requires valid active employee data from the previous year. "
                        f"Please ensure year {previous_year} completed successfully."
                    )

                available_employees = result[0]
                logger.info(f"✅ Helper model validation: {available_employees:,} employees available from year {previous_year}")

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"❌ Helper model readiness validation failed: {str(e)}")
            raise

    def _validate_sequential_dependencies(self, year: int) -> bool:
        """
        Comprehensive validation of sequential year dependencies.

        Args:
            year: Year to validate dependencies for

        Returns:
            bool: True if all dependencies are satisfied

        Raises:
            ValueError: If dependencies are not satisfied
        """
        if year == self.start_year:
            logger.info(f"✅ First year ({year}): No sequential dependencies to validate")
            return True

        logger.info(f"🔍 Validating sequential dependencies for year {year}")

        try:
            # Check that all previous years have completed
            conn = get_connection()
            try:
                for check_year in range(self.start_year, year):
                    # Validate workforce snapshot exists
                    snapshot_check = """
                        SELECT COUNT(*) FROM fct_workforce_snapshot
                        WHERE simulation_year = ? AND employment_status = 'active'
                    """

                    result = conn.execute(snapshot_check, [check_year]).fetchone()

                    if not result or result[0] == 0:
                        raise ValueError(
                            f"Year {check_year} is incomplete - no active workforce snapshot found. "
                            f"Cannot proceed with year {year}. "
                            f"Multi-year simulations must be completed sequentially. "
                            f"Please complete year {check_year} first."
                        )

                    logger.info(f"   Year {check_year}: ✅ Valid ({result[0]:,} active employees)")

            finally:
                conn.close()

            logger.info(f"✅ All sequential dependencies satisfied for year {year}")
            return True

        except Exception as e:
            logger.error(f"❌ Sequential dependency validation failed: {str(e)}")
            raise
