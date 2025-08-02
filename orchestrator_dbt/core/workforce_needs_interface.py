"""
Workforce needs model interface for orchestrator_dbt.

Provides access to dbt workforce needs models (int_workforce_needs and
int_workforce_needs_by_level) to drive event generation quantities in
the multi-year simulation pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from contextlib import contextmanager

from .config import OrchestrationConfig
from .database_manager import DatabaseManager
from .dbt_executor import DbtExecutor


logger = logging.getLogger(__name__)


@dataclass
class WorkforceRequirements:
    """Workforce requirements data from int_workforce_needs model."""

    # Identifiers
    workforce_needs_id: str
    scenario_id: str
    simulation_year: int

    # Current workforce state
    starting_workforce_count: int
    starting_experienced_count: int
    starting_new_hire_count: int
    avg_current_compensation: float
    total_current_compensation: float

    # Growth targets
    target_growth_rate: float
    target_net_growth: int
    target_ending_workforce: int

    # Termination forecasts
    experienced_termination_rate: float
    expected_experienced_terminations: int
    new_hire_termination_rate: float
    expected_new_hire_terminations: int
    total_expected_terminations: int

    # Hiring requirements
    total_hires_needed: int

    # Financial impact
    avg_new_hire_compensation: float
    total_new_hire_compensation_cost: float
    expected_termination_compensation_cost: float
    net_compensation_change_forecast: float

    # Validation
    calculated_net_change: int
    growth_variance: int
    balance_status: str

    # Calculated rates
    hiring_rate: float
    total_turnover_rate: float
    actual_growth_rate: float


@dataclass
class LevelWorkforceRequirements:
    """Level-specific workforce requirements from int_workforce_needs_by_level model."""

    # Identifiers
    workforce_needs_id: str
    scenario_id: str
    simulation_year: int
    level_id: int

    # Current state
    current_headcount: int
    experienced_headcount: int
    new_hire_headcount: int
    avg_compensation: float
    median_compensation: float
    total_compensation: float

    # Terminations
    expected_terminations: int
    termination_compensation_cost: float

    # Hiring
    hiring_distribution: float
    hires_needed: int
    expected_new_hire_terminations: int

    # Net workforce change
    net_headcount_change: int
    projected_ending_headcount: int

    # Compensation planning
    new_hire_avg_compensation: float
    total_new_hire_compensation: float
    merit_increase_cost: float
    cola_cost: float
    expected_promotions: float
    promotion_cost: float

    # Additional costs
    recruiting_costs: float
    training_costs: float
    severance_costs: float
    additional_termination_costs: float

    # Total costs
    total_hiring_costs: float
    total_termination_costs: float
    total_compensation_change_costs: float

    # Financial impact
    net_compensation_change: float
    total_budget_impact: float

    # Rates
    level_hiring_rate: float
    level_termination_rate: float
    level_growth_rate: float


class DbtWorkforceNeedsInterface:
    """
    Interface to dbt workforce needs models for event generation.

    Provides methods to query int_workforce_needs and int_workforce_needs_by_level
    models and convert results to structured data for event generation.
    """

    def __init__(
        self,
        config: OrchestrationConfig,
        database_manager: DatabaseManager,
        dbt_executor: DbtExecutor
    ):
        """
        Initialize workforce needs interface.

        Args:
            config: Orchestration configuration
            database_manager: Database connection manager
            dbt_executor: dbt command executor
        """
        self.config = config
        self.database_manager = database_manager
        self.dbt_executor = dbt_executor
        self._cache: Dict[str, Any] = {}

    def execute_workforce_needs_models(
        self,
        simulation_year: int,
        scenario_id: str = "default"
    ) -> bool:
        """
        Execute dbt workforce needs models for the given year and scenario.

        Args:
            simulation_year: Year to calculate workforce needs for
            scenario_id: Scenario identifier

        Returns:
            True if execution successful, False otherwise
        """
        logger.info(f"Executing workforce needs models for year {simulation_year}, scenario {scenario_id}")

        # Prepare dbt variables
        dbt_vars = {
            "simulation_year": simulation_year,
            "scenario_id": scenario_id
        }

        try:
            # Execute int_workforce_needs model
            result1 = self.dbt_executor.run_model("int_workforce_needs", vars_dict=dbt_vars)
            if not result1.success:
                logger.error(f"Failed to execute int_workforce_needs: {result1.stderr}")
                return False

            # Execute int_workforce_needs_by_level model
            result2 = self.dbt_executor.run_model("int_workforce_needs_by_level", vars_dict=dbt_vars)
            if not result2.success:
                logger.error(f"Failed to execute int_workforce_needs_by_level: {result2.stderr}")
                return False

            logger.info("✅ Workforce needs models executed successfully")

            # Clear cache for this year/scenario combination
            cache_key = f"{simulation_year}_{scenario_id}"
            if cache_key in self._cache:
                del self._cache[cache_key]

            return True

        except Exception as e:
            logger.error(f"💥 Error executing workforce needs models: {e}")
            return False

    def get_workforce_requirements(
        self,
        simulation_year: int,
        scenario_id: str = "default"
    ) -> Optional[WorkforceRequirements]:
        """
        Get workforce requirements from int_workforce_needs model.

        Args:
            simulation_year: Year to get requirements for
            scenario_id: Scenario identifier

        Returns:
            WorkforceRequirements object or None if not found
        """
        cache_key = f"{simulation_year}_{scenario_id}_requirements"

        # Check cache first
        if cache_key in self._cache:
            logger.debug(f"Retrieved workforce requirements from cache for {simulation_year}")
            return self._cache[cache_key]

        try:
            with self.database_manager.get_connection() as conn:
                query = """
                SELECT
                    workforce_needs_id,
                    scenario_id,
                    simulation_year,
                    starting_workforce_count,
                    starting_experienced_count,
                    starting_new_hire_count,
                    avg_current_compensation,
                    total_current_compensation,
                    target_growth_rate,
                    target_net_growth,
                    target_ending_workforce,
                    experienced_termination_rate,
                    expected_experienced_terminations,
                    new_hire_termination_rate,
                    expected_new_hire_terminations,
                    total_expected_terminations,
                    total_hires_needed,
                    avg_new_hire_compensation,
                    total_new_hire_compensation_cost,
                    expected_termination_compensation_cost,
                    net_compensation_change_forecast,
                    calculated_net_change,
                    growth_variance,
                    balance_status,
                    hiring_rate,
                    total_turnover_rate,
                    actual_growth_rate
                FROM int_workforce_needs
                WHERE simulation_year = ? AND scenario_id = ?
                """

                result = conn.execute(query, [simulation_year, scenario_id]).fetchone()

                if not result:
                    logger.warning(f"No workforce requirements found for year {simulation_year}, scenario {scenario_id}")
                    return None

                # Convert to WorkforceRequirements object
                requirements = WorkforceRequirements(
                    workforce_needs_id=result[0],
                    scenario_id=result[1],
                    simulation_year=result[2],
                    starting_workforce_count=result[3],
                    starting_experienced_count=result[4],
                    starting_new_hire_count=result[5],
                    avg_current_compensation=result[6],
                    total_current_compensation=result[7],
                    target_growth_rate=result[8],
                    target_net_growth=result[9],
                    target_ending_workforce=result[10],
                    experienced_termination_rate=result[11],
                    expected_experienced_terminations=result[12],
                    new_hire_termination_rate=result[13],
                    expected_new_hire_terminations=result[14],
                    total_expected_terminations=result[15],
                    total_hires_needed=result[16],
                    avg_new_hire_compensation=result[17],
                    total_new_hire_compensation_cost=result[18],
                    expected_termination_compensation_cost=result[19],
                    net_compensation_change_forecast=result[20],
                    calculated_net_change=result[21],
                    growth_variance=result[22],
                    balance_status=result[23],
                    hiring_rate=result[24],
                    total_turnover_rate=result[25],
                    actual_growth_rate=result[26]
                )

                # Cache the result
                self._cache[cache_key] = requirements

                logger.info(f"✅ Retrieved workforce requirements for year {simulation_year}: {requirements.total_hires_needed} hires needed")
                return requirements

        except Exception as e:
            logger.error(f"💥 Error retrieving workforce requirements: {e}")
            return None

    def get_level_breakdown(
        self,
        simulation_year: int,
        scenario_id: str = "default"
    ) -> List[LevelWorkforceRequirements]:
        """
        Get level-specific workforce requirements from int_workforce_needs_by_level model.

        Args:
            simulation_year: Year to get requirements for
            scenario_id: Scenario identifier

        Returns:
            List of LevelWorkforceRequirements objects
        """
        cache_key = f"{simulation_year}_{scenario_id}_level_breakdown"

        # Check cache first
        if cache_key in self._cache:
            logger.debug(f"Retrieved level breakdown from cache for {simulation_year}")
            return self._cache[cache_key]

        try:
            with self.database_manager.get_connection() as conn:
                query = """
                SELECT
                    workforce_needs_id,
                    scenario_id,
                    simulation_year,
                    level_id,
                    current_headcount,
                    experienced_headcount,
                    new_hire_headcount,
                    avg_compensation,
                    median_compensation,
                    total_compensation,
                    expected_terminations,
                    termination_compensation_cost,
                    hiring_distribution,
                    hires_needed,
                    expected_new_hire_terminations,
                    net_headcount_change,
                    projected_ending_headcount,
                    new_hire_avg_compensation,
                    total_new_hire_compensation,
                    merit_increase_cost,
                    cola_cost,
                    expected_promotions,
                    promotion_cost,
                    recruiting_costs,
                    training_costs,
                    severance_costs,
                    additional_termination_costs,
                    total_hiring_costs,
                    total_termination_costs,
                    total_compensation_change_costs,
                    net_compensation_change,
                    total_budget_impact,
                    level_hiring_rate,
                    level_termination_rate,
                    level_growth_rate
                FROM int_workforce_needs_by_level
                WHERE simulation_year = ? AND scenario_id = ?
                ORDER BY level_id
                """

                results = conn.execute(query, [simulation_year, scenario_id]).fetchall()

                if not results:
                    logger.warning(f"No level breakdown found for year {simulation_year}, scenario {scenario_id}")
                    return []

                # Convert to LevelWorkforceRequirements objects
                level_requirements = []
                for result in results:
                    level_req = LevelWorkforceRequirements(
                        workforce_needs_id=result[0],
                        scenario_id=result[1],
                        simulation_year=result[2],
                        level_id=result[3],
                        current_headcount=result[4],
                        experienced_headcount=result[5],
                        new_hire_headcount=result[6],
                        avg_compensation=result[7],
                        median_compensation=result[8],
                        total_compensation=result[9],
                        expected_terminations=result[10],
                        termination_compensation_cost=result[11],
                        hiring_distribution=result[12],
                        hires_needed=result[13],
                        expected_new_hire_terminations=result[14],
                        net_headcount_change=result[15],
                        projected_ending_headcount=result[16],
                        new_hire_avg_compensation=result[17],
                        total_new_hire_compensation=result[18],
                        merit_increase_cost=result[19],
                        cola_cost=result[20],
                        expected_promotions=result[21],
                        promotion_cost=result[22],
                        recruiting_costs=result[23],
                        training_costs=result[24],
                        severance_costs=result[25],
                        additional_termination_costs=result[26],
                        total_hiring_costs=result[27],
                        total_termination_costs=result[28],
                        total_compensation_change_costs=result[29],
                        net_compensation_change=result[30],
                        total_budget_impact=result[31],
                        level_hiring_rate=result[32],
                        level_termination_rate=result[33],
                        level_growth_rate=result[34]
                    )
                    level_requirements.append(level_req)

                # Cache the result
                self._cache[cache_key] = level_requirements

                logger.info(f"✅ Retrieved level breakdown for year {simulation_year}: {len(level_requirements)} levels")
                return level_requirements

        except Exception as e:
            logger.error(f"💥 Error retrieving level breakdown: {e}")
            return []

    def clear_cache(self) -> None:
        """Clear the internal cache of workforce needs data."""
        self._cache.clear()
        logger.debug("Cache cleared")

    def validate_workforce_needs_models(
        self,
        simulation_year: int,
        scenario_id: str = "default"
    ) -> bool:
        """
        Validate that workforce needs models exist and contain expected data.

        Args:
            simulation_year: Year to validate
            scenario_id: Scenario identifier

        Returns:
            True if models are valid, False otherwise
        """
        try:
            with self.database_manager.get_connection() as conn:
                # Check int_workforce_needs table exists
                result = conn.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'int_workforce_needs'
                """).fetchone()

                if not result or result[0] == 0:
                    logger.error("❌ int_workforce_needs table does not exist")
                    return False

                # Check int_workforce_needs_by_level table exists
                result = conn.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'int_workforce_needs_by_level'
                """).fetchone()

                if not result or result[0] == 0:
                    logger.error("❌ int_workforce_needs_by_level table does not exist")
                    return False

                # Check data exists for the given year/scenario
                result = conn.execute("""
                    SELECT COUNT(*) FROM int_workforce_needs
                    WHERE simulation_year = ? AND scenario_id = ?
                """, [simulation_year, scenario_id]).fetchone()

                if not result or result[0] == 0:
                    logger.error(f"❌ No data in int_workforce_needs for year {simulation_year}, scenario {scenario_id}")
                    return False

                result = conn.execute("""
                    SELECT COUNT(*) FROM int_workforce_needs_by_level
                    WHERE simulation_year = ? AND scenario_id = ?
                """, [simulation_year, scenario_id]).fetchone()

                if not result or result[0] == 0:
                    logger.error(f"❌ No data in int_workforce_needs_by_level for year {simulation_year}, scenario {scenario_id}")
                    return False

                logger.info(f"✅ Workforce needs models validated for year {simulation_year}")
                return True

        except Exception as e:
            logger.error(f"💥 Error validating workforce needs models: {e}")
            return False
