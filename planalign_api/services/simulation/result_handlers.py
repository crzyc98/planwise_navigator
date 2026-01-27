"""
Result handling utilities for simulation exports.

Provides Excel export functionality for simulation results.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def export_results_to_excel(
    scenario_path: Path,
    scenario_name: str,
    config: Dict[str, Any],
    seed: int,
    run_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Export simulation results to Excel after successful completion.

    Args:
        scenario_path: Path to the scenario directory
        scenario_name: Name of the scenario
        config: Simulation configuration dictionary
        seed: Random seed used for the simulation
        run_dir: Optional path to run-specific directory for output

    Returns:
        Path to the Excel file if successful, None otherwise
    """
    try:
        from planalign_orchestrator.utils import DatabaseConnectionManager
        from planalign_orchestrator.excel_exporter import ExcelExporter
        from planalign_orchestrator.config import SimulationConfig

        # Find the database - prefer run-specific database if run_dir provided
        if run_dir and (run_dir / "simulation.duckdb").exists():
            db_path = run_dir / "simulation.duckdb"
        else:
            db_path = scenario_path / "simulation.duckdb"

        if not db_path.exists():
            logger.warning(f"Database not found at {db_path}, skipping Excel export")
            return None

        # Use run directory if provided, otherwise create results directory
        if run_dir:
            results_dir = run_dir
        else:
            results_dir = scenario_path / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database connection manager
        db_manager = DatabaseConnectionManager(db_path)

        # Create exporter
        exporter = ExcelExporter(db_manager)

        # Try to create a SimulationConfig object from the config dict
        # If that fails, create a minimal mock config
        try:
            sim_config = SimulationConfig.from_dict(config)
        except Exception as e:
            logger.warning(f"Could not create SimulationConfig from dict: {e}")
            # Create a minimal mock config object
            sim_config = _create_mock_config(config)

        # Export to Excel
        excel_path = exporter.export_scenario_results(
            scenario_name=scenario_name,
            output_dir=results_dir,
            config=sim_config,
            seed=seed,
            export_format="excel",
        )

        logger.info(f"Excel export created at: {excel_path}")
        return excel_path

    except ImportError as e:
        logger.error(f"Failed to import excel exporter: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to export results to Excel: {e}")
        return None


def _create_mock_config(config: Dict[str, Any]) -> Any:
    """Create a minimal mock config object when full config parsing fails."""

    class MockSimulation:
        start_year = config.get("simulation", {}).get("start_year", 2025)
        end_year = config.get("simulation", {}).get("end_year", 2027)
        target_growth_rate = config.get("simulation", {}).get("growth_target", 0.05)

    class MockCompensation:
        cola_rate = config.get("compensation", {}).get("cola_rate", 0.03)
        merit_budget = config.get("compensation", {}).get("merit_budget", 0.03)

    class MockConfig:
        simulation = MockSimulation()
        compensation = MockCompensation()

        def model_dump(self):
            return config

    return MockConfig()
