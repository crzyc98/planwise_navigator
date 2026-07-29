#!/usr/bin/env python3
"""
Scenario Batch Runner for E069: Streamlined Scenario Batch Processing

Executes multiple scenarios with isolated databases and Excel export.

Features:
- Database isolation with unique .duckdb files per scenario
- Error resilience - continues batch when individual scenarios fail
- Base config inheritance - scenarios override specific parameters only
- Progress tracking with real-time status updates
- Deterministic runs via persisted random seeds
"""

from __future__ import annotations

import json
import logging
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import SimulationConfig, load_simulation_config
from .excel_exporter import ExcelExporter
from .run_pool import (
    EventKind,
    PoolEvent,
    ScenarioJob,
    ScenarioRunPool,
    WorkerBudget,
    resolve_worker_count,
)
from .utils import DatabaseConnectionManager, ExecutionMutex

logger = logging.getLogger(__name__)


def execute_scenario_job(job: ScenarioJob) -> Dict[str, Any]:
    """Run one fully-resolved scenario and export its results.

    This is the pool's worker entry point, so it must stay a module-level
    function (workers receive it by pickled reference) and must depend only on
    ``job`` — nothing about the parent's state survives the process boundary.
    Everything non-deterministic (config merge, seed resolution) is already
    settled by :meth:`ScenarioBatchRunner._prepare_job`, which is what makes a
    parallel run reproduce the serial one.
    """
    scenario_dir = Path(job.payload["scenario_dir"])
    export_format = str(job.payload["export_format"])

    # Per-scenario lock, not a global one: distinct scenarios own distinct
    # databases, so parallel workers never contend here. It still guards
    # against a second batch touching the same scenario concurrently.
    with ExecutionMutex(f"scenario_{job.name}"):
        db_manager = DatabaseConnectionManager(job.db_path)
        from .construction import ConstructionSpec, build_orchestrator

        try:
            result = build_orchestrator(
                ConstructionSpec(
                    config=job.config,
                    database=db_manager,
                    threads=job.threads,
                    entry_point="batch",
                    dbt_artifacts_dir=job.dbt_artifacts_dir,
                )
            )
            orchestrator = result.orchestrator
            orchestrator.construction_signature = result.signature

            logger.info(
                "Running simulation: %d-%d",
                job.config.simulation.start_year,
                job.config.simulation.end_year,
            )
            start_time = datetime.now()

            summary = orchestrator.execute_multi_year_simulation(
                start_year=job.config.simulation.start_year,
                end_year=job.config.simulation.end_year,
                # Continue batch processing even with validation warnings
                fail_on_validation_error=False,
            )

            execution_time = (datetime.now() - start_time).total_seconds()
            logger.debug("Execution time: %.1f seconds", execution_time)

            logger.info("Exporting results (%s)", export_format)
            excel_exporter = ExcelExporter(db_manager)
            export_path = excel_exporter.export_scenario_results(
                scenario_name=job.name,
                output_dir=scenario_dir,
                config=job.config,
                seed=job.seed,
                export_format=export_format,
            )

            config_copy_path = scenario_dir / f"{job.name}_config.yaml"
            _save_config_copy(job.config, config_copy_path)

            return {
                "status": "completed",
                "summary": summary,
                "database_path": str(job.db_path),
                "export_path": str(export_path),
                "scenario_dir": str(scenario_dir),
                "execution_time_seconds": execution_time,
                "seed": job.seed,
                "config_path": str(config_copy_path),
            }

        finally:
            try:
                db_manager.close_all()
            except Exception as e:
                logger.debug("Non-fatal: failed closing connections: %s", e)


def _save_config_copy(config: SimulationConfig, output_path: Path) -> None:
    """Save a copy of the merged configuration for reference."""
    try:
        config_dict = config.model_dump()
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        logger.warning("Could not save config copy: %s", e)


class ScenarioBatchRunner:
    """Execute multiple scenarios with isolated databases and Excel export.

    Guarantees:
    - Deterministic runs per scenario via persisted random seeds
    - Reproducible outputs with metadata capture and audit trail
    - Graceful continuation on per-scenario failure
    """

    def __init__(
        self,
        scenarios_dir: Path,
        output_dir: Path,
        base_config_path: Optional[Path] = None,
    ):
        """Initialize batch runner with scenario and output directories.

        Args:
            scenarios_dir: Directory containing scenario YAML configuration files
            output_dir: Base output directory for batch results
            base_config_path: Optional base configuration file (defaults to config/simulation_config.yaml)
        """
        self.scenarios_dir = Path(scenarios_dir)
        self.output_dir = Path(output_dir)
        self.base_config_path = base_config_path or Path(
            "config/simulation_config.yaml"
        )
        self.batch_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.batch_output_dir = self.output_dir / f"batch_{self.batch_timestamp}"
        # Populated by run_batch; lets the CLI report the resolved fan-out.
        self.worker_budget: Optional[WorkerBudget] = None

        # Create output directory
        self.batch_output_dir.mkdir(parents=True, exist_ok=True)

    def run_batch(
        self,
        scenario_names: Optional[List[str]] = None,
        export_format: str = "excel",
        threads: int = 1,
        optimization: str = "medium",
        clean_databases: bool = False,
        parallel: Optional[int] = None,
        on_event: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute batch of scenarios with isolated databases.

        Args:
            scenario_names: Optional list of specific scenario names to run (defaults to all)
            export_format: Export format ('excel' or 'csv')
            threads: Number of dbt threads for parallel execution
            optimization: Optimization level ('low', 'medium', 'high')
            clean_databases: If True, delete existing DuckDB databases before running
            parallel: Worker processes to fan scenarios out across. ``None``
                sizes it from measured memory and CPU budgets; ``1`` runs
                scenarios serially in this process.
            on_event: Optional callback receiving :class:`PoolEvent` updates.

        Returns:
            Dictionary mapping scenario names to their execution results
        """
        scenarios = self._discover_scenarios(scenario_names)

        if scenario_names:
            missing = sorted(set(scenario_names) - set(scenarios))
            if missing:
                raise ValueError(
                    f"Scenario(s) not found in {self.scenarios_dir}: "
                    f"{', '.join(missing)}. Available: "
                    f"{', '.join(sorted(self._discover_scenarios())) or '(none)'}"
                )

        if not scenarios:
            logger.error("No scenarios found in %s", self.scenarios_dir)
            return {}

        # Clean up any stale lock files before starting
        self._cleanup_stale_locks()

        # Clean databases if requested
        if clean_databases:
            self._clean_scenario_databases(list(scenarios.keys()))

        logger.info("Starting batch execution: %d scenarios", len(scenarios))
        logger.info("Output directory: %s", self.batch_output_dir)
        logger.info("Configuration: %d threads, %s optimization", threads, optimization)

        budget = resolve_worker_count(parallel, len(scenarios))
        self.worker_budget = budget
        logger.info("Scenario fan-out: %s", budget.describe())

        # Prepare every job before any of them runs. Config merge and seed
        # resolution decide what a scenario computes, so they must not depend
        # on which worker picks the job up or in what order.
        jobs: List[ScenarioJob] = []
        results: Dict[str, Any] = {}
        for name, config_path in scenarios.items():
            try:
                jobs.append(
                    self._prepare_job(
                        name,
                        config_path,
                        export_format=export_format,
                        threads=threads,
                        isolate_dbt_artifacts=budget.workers > 1,
                    )
                )
            except Exception as e:
                logger.error(
                    "Scenario %s failed during setup: %s", name, e, exc_info=True
                )
                results[name] = {
                    "status": "failed",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }

        if jobs:
            pool = ScenarioRunPool(max_workers=budget.workers)
            job_results = pool.run(
                execute_scenario_job,
                jobs,
                on_event=self._make_event_handler(on_event, len(jobs)),
            )
            for name, job_result in job_results.items():
                if job_result.succeeded and job_result.value is not None:
                    results[name] = job_result.value
                else:
                    results[name] = {
                        "status": "failed",
                        "error": job_result.error or "unknown failure",
                        "traceback": job_result.traceback,
                    }

        # Generate batch summary report
        self._generate_batch_summary(results)

        # Generate comparison report if we have successful scenarios
        successful_scenarios = {
            k: v for k, v in results.items() if v.get("status") == "completed"
        }
        if len(successful_scenarios) > 1:
            self._generate_comparison_report(successful_scenarios)

        return results

    def _discover_scenarios(
        self, scenario_names: Optional[List[str]] = None
    ) -> Dict[str, Path]:
        """Discover scenario configuration files in the scenarios directory.

        Args:
            scenario_names: Optional list of specific scenario names to find

        Returns:
            Dictionary mapping scenario names to their configuration file paths
        """
        if not self.scenarios_dir.exists():
            return {}

        scenarios = {}

        # Find all YAML files in scenarios directory
        for yaml_file in self.scenarios_dir.glob("*.yaml"):
            scenario_name = yaml_file.stem

            # Filter by specific scenario names if provided
            if scenario_names and scenario_name not in scenario_names:
                continue

            scenarios[scenario_name] = yaml_file

        # Also check for .yml files
        for yml_file in self.scenarios_dir.glob("*.yml"):
            scenario_name = yml_file.stem

            # Don't override .yaml files
            if scenario_name in scenarios:
                continue

            # Filter by specific scenario names if provided
            if scenario_names and scenario_name not in scenario_names:
                continue

            scenarios[scenario_name] = yml_file

        return scenarios

    def _cleanup_stale_locks(self) -> None:
        """Clean up stale lock files that may prevent scenario execution."""
        import time
        from pathlib import Path

        # Look for lock files in current directory
        for lock_file in Path(".").glob(".*.lock"):
            try:
                # Remove locks older than 1 hour
                if time.time() - lock_file.stat().st_mtime > 3600:
                    lock_file.unlink()
                    logger.debug("Cleaned up stale lock file: %s", lock_file)
            except Exception:
                pass  # Best effort cleanup

    def _clean_scenario_databases(self, scenario_names: List[str]) -> None:
        """Delete DuckDB databases for the specified scenarios.

        Args:
            scenario_names: List of scenario names whose databases should be deleted
        """
        dbt_dir = Path("dbt").absolute()
        deleted_count = 0

        logger.info("Cleaning databases for %d scenario(s)...", len(scenario_names))

        for scenario_name in scenario_names:
            scenario_db = dbt_dir / f"{scenario_name}.duckdb"

            if scenario_db.exists():
                try:
                    scenario_db.unlink()
                    deleted_count += 1
                    logger.info("Deleted: %s", scenario_db)
                except Exception as e:
                    logger.warning("Failed to delete %s: %s", scenario_db, e)

        if deleted_count > 0:
            logger.info("Deleted %d database file(s)", deleted_count)
        else:
            logger.info("No existing databases found to clean")

    def _prepare_job(
        self,
        scenario_name: str,
        config_path: Path,
        *,
        export_format: str,
        threads: int = 1,
        isolate_dbt_artifacts: bool = False,
    ) -> ScenarioJob:
        """Resolve one scenario into a self-contained, runnable job.

        Everything here happens in the parent, before any worker starts, so a
        scenario computes the same thing whether it runs serially or on a
        worker: the merged config and the seed are fixed up front rather than
        re-derived under concurrency.
        """
        # Create scenario output directory
        scenario_dir = self.batch_output_dir / scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)

        # Create isolated database path in dbt/ folder
        dbt_dir = Path("dbt").absolute()
        scenario_db = dbt_dir / f"{scenario_name}.duckdb"

        # Ensure database file exists and is valid (DuckDB requires this)
        if not scenario_db.exists():
            logger.debug("Creating database file: %s", scenario_db)
            # Create a proper DuckDB database file
            import duckdb

            conn = duckdb.connect(str(scenario_db))
            conn.close()
            logger.debug("Database file created successfully")

        # Load and merge scenario configuration with base config
        config = self._load_merged_config(config_path)
        self._validate_config(config)

        # Ensure deterministic run: set/persist a random seed per scenario.
        # Seeds live under output_dir/seeds/ (NOT the timestamped batch dir)
        # so a re-run of the same scenario reuses the same seed even when the
        # config doesn't pin one.
        seed = self._resolve_scenario_seed(scenario_name, config)
        (scenario_dir / "seed.txt").write_text(str(seed))

        # Update config with determined seed
        config.simulation.random_seed = seed

        # Only redirect dbt's target/ and logs/ when scenarios actually run
        # concurrently. Serial batches keep writing to dbt/target so the usual
        # post-mortem workflow ("look at dbt/target/run_results.json") is
        # unchanged for anyone not opting into fan-out.
        artifacts_dir = (
            scenario_dir / "dbt_artifacts" if isolate_dbt_artifacts else None
        )
        if artifacts_dir is not None:
            (artifacts_dir / "target").mkdir(parents=True, exist_ok=True)
            (artifacts_dir / "logs").mkdir(parents=True, exist_ok=True)

        return ScenarioJob(
            name=scenario_name,
            config=config,
            db_path=scenario_db,
            seed=seed,
            threads=threads,
            dbt_artifacts_dir=artifacts_dir,
            payload={
                "scenario_dir": str(scenario_dir),
                "export_format": export_format,
            },
        )

    def _make_event_handler(self, on_event: Optional[Any], total: int) -> Any:
        """Wrap the caller's handler with pool-level progress logging.

        Aggregating here — rather than letting workers write to the terminal —
        is what keeps concurrent output from interleaving into garbage.
        """
        state = {"done": 0}

        def handle(event: PoolEvent) -> None:
            if event.kind is EventKind.JOB_STARTED:
                logger.info(
                    "[%d/%d] Started scenario: %s",
                    state["done"] + 1,
                    total,
                    event.job_name,
                )
            else:
                state["done"] += 1
                if event.kind is EventKind.JOB_COMPLETED:
                    logger.info(
                        "[%d/%d] Scenario %s completed in %.1fs",
                        state["done"],
                        total,
                        event.job_name,
                        event.duration_seconds or 0.0,
                    )
                else:
                    logger.error(
                        "[%d/%d] Scenario %s failed: %s",
                        state["done"],
                        total,
                        event.job_name,
                        event.error,
                    )
            if on_event is not None:
                on_event(event)

        return handle

    def _resolve_scenario_seed(
        self, scenario_name: str, config: SimulationConfig
    ) -> int:
        """Resolve the random seed for a scenario, stable across batch runs.

        Precedence: config ``random_seed`` > previously persisted seed
        (``output_dir/seeds/<scenario>.txt``) > newly generated wall-clock
        seed (persisted for future runs).
        """
        configured = getattr(config.simulation, "random_seed", None)
        if configured:
            logger.debug("Using configured seed: %d", configured)
            return int(configured)

        seed_dir = self.output_dir / "seeds"
        seed_path = seed_dir / f"{scenario_name}.txt"
        if seed_path.exists():
            seed = int(seed_path.read_text().strip())
            logger.debug("Reusing persisted seed: %d", seed)
            return seed

        seed = int(datetime.now().timestamp())
        seed_dir.mkdir(parents=True, exist_ok=True)
        seed_path.write_text(str(seed))
        logger.debug("Generated and persisted new seed: %d", seed)
        return seed

    def _load_merged_config(self, scenario_config_path: Path) -> SimulationConfig:
        """Load and merge scenario configuration with base configuration.

        Args:
            scenario_config_path: Path to the scenario-specific configuration

        Returns:
            Merged SimulationConfig with scenario overrides applied
        """
        # Load base configuration
        base_config = load_simulation_config(self.base_config_path)

        # Load scenario overrides
        with open(scenario_config_path, "r", encoding="utf-8") as f:
            scenario_overrides = yaml.safe_load(f) or {}

        # Convert base config back to dict for merging
        base_dict = base_config.model_dump()

        # Deep merge scenario overrides into base configuration
        merged_dict = self._deep_merge(base_dict, scenario_overrides)

        # Create new SimulationConfig from merged dictionary
        return SimulationConfig(**merged_dict)

    def _deep_merge(
        self, base: Dict[str, Any], overrides: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deep merge two dictionaries, with overrides taking precedence.

        Args:
            base: Base dictionary
            overrides: Override values to merge in

        Returns:
            Merged dictionary
        """
        merged = base.copy()

        for key, value in overrides.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value

        return merged

    def _validate_config(self, config: SimulationConfig) -> None:
        """Validate required fields before execution.

        Args:
            config: Configuration to validate

        Raises:
            ValueError: If configuration is invalid
        """
        if config.simulation.start_year is None:
            raise ValueError("simulation.start_year is required")
        if config.simulation.end_year is None:
            raise ValueError("simulation.end_year is required")
        if config.simulation.end_year < config.simulation.start_year:
            raise ValueError("simulation.end_year must be >= simulation.start_year")

        # Validate threading configuration if present
        try:
            config.validate_threading_configuration()
        except ValueError as e:
            raise ValueError(f"Invalid threading configuration: {e}")

        # Validate eligibility configuration (emits warnings for contradictory settings)
        config.validate_eligibility_configuration()

    def _generate_batch_summary(self, results: Dict[str, Any]) -> None:
        """Generate batch execution summary.

        Args:
            results: Dictionary of scenario execution results
        """
        summary_path = self.batch_output_dir / "batch_summary.json"

        successful = [
            name
            for name, result in results.items()
            if result.get("status") == "completed"
        ]
        failed = [
            name for name, result in results.items() if result.get("status") == "failed"
        ]

        total_time = sum(
            result.get("execution_time_seconds", 0)
            for result in results.values()
            if result.get("status") == "completed"
        )

        summary = {
            "batch_timestamp": self.batch_timestamp,
            "total_scenarios": len(results),
            "successful_scenarios": len(successful),
            "failed_scenarios": len(failed),
            "success_rate": len(successful) / len(results) if results else 0,
            "total_execution_time_seconds": total_time,
            "scenarios": {"successful": successful, "failed": failed},
            "detailed_results": results,
        }

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(
            "Batch Summary:\n"
            "   Successful: %d scenarios\n"
            "   Failed: %d scenarios\n"
            "   Success Rate: %.1f%%\n"
            "   Total Time: %.1f seconds\n"
            "   Summary saved: %s",
            len(successful),
            len(failed),
            summary["success_rate"] * 100,
            total_time,
            summary_path,
        )

    def _generate_comparison_report(self, successful_scenarios: Dict[str, Any]) -> None:
        """Generate comparison report across successful scenarios.

        Args:
            successful_scenarios: Dictionary of successful scenario results
        """
        try:
            comparison_path = self.batch_output_dir / "comparison_summary.xlsx"

            # Use ExcelExporter to create comparison workbook
            # We'll use the first scenario's database manager as a template
            first_scenario = next(iter(successful_scenarios.values()))
            first_db_path = Path(first_scenario["database_path"])
            template_db_manager = DatabaseConnectionManager(first_db_path)

            exporter = ExcelExporter(template_db_manager)
            exporter.create_comparison_workbook(
                scenario_results=successful_scenarios, output_path=comparison_path
            )

            logger.info("Comparison report saved: %s", comparison_path)

        except Exception as e:
            logger.warning("Could not generate comparison report: %s", e)

    def get_git_metadata(self) -> Dict[str, Any]:
        """Get git metadata for the current repository state.

        Returns:
            Dictionary with git metadata (SHA, branch, etc.)
        """
        metadata: Dict[str, Any] = {}

        try:
            # Get git SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            metadata["git_sha"] = result.stdout.strip()
        except Exception:
            metadata["git_sha"] = "unknown"

        try:
            # Get git branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            metadata["git_branch"] = result.stdout.strip()
        except Exception:
            metadata["git_branch"] = "unknown"

        try:
            # Check if working directory is clean
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            metadata["git_clean"] = len(result.stdout.strip()) == 0
        except Exception:
            metadata["git_clean"] = False

        return metadata
