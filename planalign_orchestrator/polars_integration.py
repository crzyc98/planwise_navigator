"""
E077: Polars Engine Integration Module

Orchestrates Polars-based cohort generation before dbt runs.
Provides 375× performance improvement over SQL-based event generation.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional

import polars as pl

from planalign_orchestrator.config import SimulationConfig, get_project_root
from planalign_orchestrator.workforce_planning_engine import (
    WorkforcePlanningEngine,
    WorkforceNeeds,
)

logger = logging.getLogger(__name__)


class PolarsIntegrationManager:
    """
    Manages Polars engine execution and integration with dbt pipeline.

    Workflow:
    1. Load starting workforce from DuckDB
    2. Calculate exact workforce needs via Polars engine
    3. Generate cohorts with deterministic selection
    4. Write Parquet files atomically
    5. Signal dbt to load via int_polars_cohort_loader.sql
    """

    def __init__(
        self,
        config: SimulationConfig,
        output_dir: Optional[Path] = None,
        database_path: Optional[Path] = None
    ):
        self.config = config
        self.output_dir = output_dir or get_project_root() / "outputs" / "polars_cohorts"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Use provided database path or fall back to default
        self.database_path = database_path

        self.engine = WorkforcePlanningEngine(
            random_seed=config.simulation.random_seed
        )

        logger.info(
            f"Initialized Polars integration (random_seed={config.simulation.random_seed}, db={database_path})"
        )

    def execute_year(
        self,
        simulation_year: int,
        scenario_id: str = "default"
    ) -> Dict[str, pl.DataFrame]:
        """
        Execute Polars cohort generation for a single year.

        Returns:
            Dictionary of cohort DataFrames (continuous_active, experienced_terminations,
            new_hires_active, new_hires_terminated)
        """
        logger.info(
            f"Executing Polars cohort generation for {scenario_id} year {simulation_year}"
        )

        # Step 1: Load starting workforce from DuckDB
        starting_workforce = self._load_starting_workforce(simulation_year)

        if starting_workforce.height == 0:
            raise ValueError(
                f"No starting workforce found for year {simulation_year}. "
                "Run baseline workforce creation first."
            )

        logger.info(f"Loaded {starting_workforce.height:,} employees")

        # Step 2: Calculate exact workforce needs
        needs = self._calculate_workforce_needs(starting_workforce.height)

        self._log_workforce_needs(needs)

        # Step 3: Generate cohorts with deterministic selection
        cohorts = self.engine.generate_cohorts(
            starting_workforce,
            needs,
            simulation_year
        )

        # Step 4: Write Parquet files atomically
        output_path = self.engine.write_cohorts_atomically(
            cohorts,
            self.output_dir,
            simulation_year,
            scenario_id
        )

        logger.info(
            f"✓ Polars cohorts written to {output_path} "
            f"(ending workforce: {needs.target_ending_workforce:,})"
        )

        return cohorts

    def _load_starting_workforce(self, simulation_year: int) -> pl.DataFrame:
        """
        Load starting workforce from DuckDB.

        For Year 1: Load from int_baseline_workforce
        For Year N: Load from previous year's fct_workforce_snapshot
        """
        import duckdb
        from planalign_orchestrator.config import get_database_path

        # Use instance database path if provided, otherwise fall back to default
        db_path = self.database_path or get_database_path()
        conn = duckdb.connect(str(db_path))

        try:
            # Determine source table based on year
            start_year = self.config.simulation.start_year or simulation_year

            if simulation_year == start_year:
                # Year 1: Use baseline workforce
                query = """
                    SELECT
                        employee_id,
                        employee_ssn,
                        level_id,
                        current_compensation AS employee_compensation,
                        current_age,
                        current_tenure
                    FROM int_baseline_workforce
                    WHERE simulation_year = ?
                      AND employment_status = 'active'
                """
            else:
                # Year N: Use previous year's snapshot
                query = """
                    SELECT
                        employee_id,
                        employee_ssn,
                        level_id,
                        current_compensation AS employee_compensation,
                        current_age,
                        current_tenure
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                      AND employment_status = 'active'
                """

            # For Year N, read from Year N-1's snapshot
            query_year = start_year if simulation_year == start_year else simulation_year - 1
            df = conn.execute(query, [query_year]).pl()
            return df

        finally:
            conn.close()

    def _calculate_workforce_needs(
        self,
        starting_workforce_count: int
    ) -> WorkforceNeeds:
        """Calculate exact workforce needs using Polars engine."""
        needs = self.engine.calculate_exact_needs(
            starting_workforce=starting_workforce_count,
            growth_rate=Decimal(str(self.config.simulation.target_growth_rate)),
            exp_term_rate=Decimal(str(self.config.workforce.total_termination_rate)),
            nh_term_rate=Decimal(str(self.config.workforce.new_hire_termination_rate))
        )

        # Validate feasibility guards
        if needs.nh_term_rate_check != 'PASS':
            raise ValueError(f"NH term rate feasibility failed: {needs.nh_term_rate_check}")
        if needs.growth_bounds_check != 'PASS':
            raise ValueError(f"Growth bounds check failed: {needs.growth_bounds_check}")

        # Warn on hire ratio issues (non-fatal)
        if needs.hire_ratio_check not in ('PASS', 'N/A'):
            logger.warning(f"Hire ratio check: {needs.hire_ratio_check}")

        return needs

    def _log_workforce_needs(self, needs: WorkforceNeeds) -> None:
        """Log workforce planning summary."""
        logger.info(
            f"Workforce planning (ADR E077-A):\n"
            f"  Starting: {needs.starting_workforce:,}\n"
            f"  Target ending: {needs.target_ending_workforce:,}\n"
            f"  Hires needed: {needs.total_hires_needed:,}\n"
            f"  Exp terminations: {needs.expected_experienced_terminations:,}\n"
            f"  NH terminations: {needs.implied_new_hire_terminations:,}\n"
            f"  Reconciliation error: {needs.reconciliation_error} (EXACT)"
        )


def execute_polars_cohort_generation(
    config: SimulationConfig,
    simulation_year: int,
    scenario_id: str = "default",
    output_dir: Optional[Path] = None,
    database_path: Optional[Path] = None
) -> Dict[str, pl.DataFrame]:
    """
    Convenience function to execute Polars cohort generation.

    Used by PipelineOrchestrator when use_polars_engine=True.

    Example:
        cohorts = execute_polars_cohort_generation(
            config=config,
            simulation_year=2025,
            scenario_id="baseline",
            database_path=Path("/path/to/simulation.duckdb")
        )
    """
    manager = PolarsIntegrationManager(config, output_dir, database_path)
    return manager.execute_year(simulation_year, scenario_id)
