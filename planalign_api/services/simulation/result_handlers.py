"""
Result handling utilities for simulation exports.

Provides Excel export functionality for simulation results.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from planalign_core.constants import DATABASE_FILENAME

logger = logging.getLogger(__name__)


def find_results_export(
    scenario_path: Path,
    scenario_name: str,
    extension: str,
    selected_run_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Find an export for the selected successful run, or for legacy storage."""
    search_dir = selected_run_dir or scenario_path / "results"
    for filename in (
        f"{scenario_name}_results.{extension}",
        f"results.{extension}",
    ):
        candidate = search_dir / filename
        if candidate.is_file():
            return candidate
    return next(search_dir.glob(f"*_results.{extension}"), None)


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
        db_path = (
            run_dir / DATABASE_FILENAME
            if run_dir is not None
            else scenario_path / DATABASE_FILENAME
        )

        if not db_path.exists():
            logger.warning(f"Database not found at {db_path}, skipping Excel export")
            return None

        # Use run directory if provided, otherwise create results directory
        if run_dir:
            results_dir = run_dir
        else:
            results_dir = scenario_path / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database connection manager as a context manager so its pooled
        # read-write connections are released before this function returns. Otherwise
        # they stay open for the whole (long-lived) API process and block the
        # subsequent read-only connection in publish_current_result -> _validate_target
        # ("Can't open a connection to same database file with a different
        # configuration than existing connections").
        with DatabaseConnectionManager(db_path) as db_manager:
            # Create exporter
            exporter = ExcelExporter(db_manager)

            # Build a SimulationConfig from the scenario config dict. If validation
            # fails (e.g. a partial or legacy config), fall back to a minimal mock
            # config so the Excel export still succeeds.
            try:
                sim_config: Any = SimulationConfig.model_validate(config)
            except Exception as e:
                # Improved error logging: include exception type for diagnostics
                logger.warning(
                    f"Could not create SimulationConfig from dict: "
                    f"{type(e).__name__}: {e}"
                )
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
        cola_rate = config.get("compensation", {}).get("cola_rate", 0.02)
        merit_budget = config.get("compensation", {}).get("merit_budget", 0.035)

    class MockConfig:
        simulation = MockSimulation()
        compensation = MockCompensation()

        def model_dump(self):
            return config

    return MockConfig()
