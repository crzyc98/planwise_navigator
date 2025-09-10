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
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import SimulationConfig, load_simulation_config
from .excel_exporter import ExcelExporter
from .pipeline import PipelineOrchestrator
from .utils import DatabaseConnectionManager


class ScenarioBatchRunner:
    """Execute multiple scenarios with isolated databases and Excel export.

    Guarantees:
    - Deterministic runs per scenario via persisted random seeds
    - Reproducible outputs with metadata capture and audit trail
    - Graceful continuation on per-scenario failure
    """

    def __init__(self, scenarios_dir: Path, output_dir: Path, base_config_path: Optional[Path] = None):
        """Initialize batch runner with scenario and output directories.

        Args:
            scenarios_dir: Directory containing scenario YAML configuration files
            output_dir: Base output directory for batch results
            base_config_path: Optional base configuration file (defaults to config/simulation_config.yaml)
        """
        self.scenarios_dir = Path(scenarios_dir)
        self.output_dir = Path(output_dir)
        self.base_config_path = base_config_path or Path("config/simulation_config.yaml")
        self.batch_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.batch_output_dir = self.output_dir / f"batch_{self.batch_timestamp}"

        # Create output directory
        self.batch_output_dir.mkdir(parents=True, exist_ok=True)

    def run_batch(self, scenario_names: Optional[List[str]] = None, export_format: str = "excel") -> Dict[str, Any]:
        """Execute batch of scenarios with isolated databases.

        Args:
            scenario_names: Optional list of specific scenario names to run (defaults to all)
            export_format: Export format ('excel' or 'csv')

        Returns:
            Dictionary mapping scenario names to their execution results
        """
        scenarios = self._discover_scenarios(scenario_names)

        if not scenarios:
            print(f"❌ No scenarios found in {self.scenarios_dir}")
            return {}

        results = {}
        print(f"🎯 Starting batch execution: {len(scenarios)} scenarios")
        print(f"📂 Output directory: {self.batch_output_dir}")

        for i, (name, config_path) in enumerate(scenarios.items(), 1):
            print(f"\n[{i}/{len(scenarios)}] Processing scenario: {name}")

            try:
                result = self._run_isolated_scenario(name, config_path, export_format)
                results[name] = result
                print(f"✅ Scenario {name} completed successfully")

            except Exception as e:
                print(f"❌ Scenario {name} failed: {e}")
                print(f"   Traceback: {traceback.format_exc()}")
                results[name] = {"status": "failed", "error": str(e), "traceback": traceback.format_exc()}

        # Generate batch summary report
        self._generate_batch_summary(results)

        # Generate comparison report if we have successful scenarios
        successful_scenarios = {k: v for k, v in results.items() if v.get("status") == "completed"}
        if len(successful_scenarios) > 1:
            self._generate_comparison_report(successful_scenarios)

        return results

    def _discover_scenarios(self, scenario_names: Optional[List[str]] = None) -> Dict[str, Path]:
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

    def _run_isolated_scenario(self, scenario_name: str, config_path: Path, export_format: str) -> Dict[str, Any]:
        """Run single scenario with isolated database.

        Args:
            scenario_name: Name of the scenario
            config_path: Path to the scenario configuration file
            export_format: Export format ('excel' or 'csv')

        Returns:
            Dictionary with execution results and metadata
        """
        # Create scenario output directory
        scenario_dir = self.batch_output_dir / scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)

        # Create isolated database path
        scenario_db = scenario_dir / f"{scenario_name}.duckdb"

        # Load and merge scenario configuration with base config
        config = self._load_merged_config(config_path)
        self._validate_config(config)

        # Ensure deterministic run: set/persist a random seed per scenario
        seed_path = scenario_dir / "seed.txt"
        if seed_path.exists():
            seed = int(seed_path.read_text().strip())
            print(f"   📌 Using existing seed: {seed}")
        else:
            seed = getattr(config.simulation, 'random_seed', None) or int(datetime.now().timestamp())
            seed_path.write_text(str(seed))
            print(f"   📌 Generated new seed: {seed}")

        # Update config with determined seed
        config.simulation.random_seed = seed

        # Setup isolated database connection manager
        db_manager = DatabaseConnectionManager(scenario_db)

        # Setup PipelineOrchestrator (importing here to avoid circular imports)
        from .factory import create_orchestrator

        orchestrator = create_orchestrator(config, db_manager)

        # Execute multi-year simulation
        print(f"   🔄 Running simulation: {config.simulation.start_year}-{config.simulation.end_year}")
        start_time = datetime.now()

        summary = orchestrator.execute_multi_year_simulation(
            start_year=config.simulation.start_year,
            end_year=config.simulation.end_year,
            fail_on_validation_error=False  # Continue batch processing even with validation warnings
        )

        execution_time = (datetime.now() - start_time).total_seconds()
        print(f"   ⏱️  Execution time: {execution_time:.1f} seconds")

        # Export results
        print(f"   📊 Exporting results ({export_format})")
        excel_exporter = ExcelExporter(db_manager)
        export_path = excel_exporter.export_scenario_results(
            scenario_name=scenario_name,
            output_dir=scenario_dir,
            config=config,
            seed=seed,
            export_format=export_format
        )

        # Save scenario configuration for reference
        config_copy_path = scenario_dir / f"{scenario_name}_config.yaml"
        self._save_config_copy(config, config_copy_path)

        return {
            "status": "completed",
            "summary": summary,
            "database_path": str(scenario_db),
            "export_path": str(export_path),
            "scenario_dir": str(scenario_dir),
            "execution_time_seconds": execution_time,
            "seed": seed,
            "config_path": str(config_copy_path)
        }

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

    def _deep_merge(self, base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries, with overrides taking precedence.

        Args:
            base: Base dictionary
            overrides: Override values to merge in

        Returns:
            Merged dictionary
        """
        merged = base.copy()

        for key, value in overrides.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
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

    def _save_config_copy(self, config: SimulationConfig, output_path: Path) -> None:
        """Save a copy of the merged configuration for reference.

        Args:
            config: Configuration to save
            output_path: Path to save the configuration
        """
        try:
            config_dict = config.model_dump()
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            print(f"   ⚠️  Warning: Could not save config copy: {e}")

    def _generate_batch_summary(self, results: Dict[str, Any]) -> None:
        """Generate batch execution summary.

        Args:
            results: Dictionary of scenario execution results
        """
        summary_path = self.batch_output_dir / "batch_summary.json"

        successful = [name for name, result in results.items() if result.get("status") == "completed"]
        failed = [name for name, result in results.items() if result.get("status") == "failed"]

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
            "scenarios": {
                "successful": successful,
                "failed": failed
            },
            "detailed_results": results
        }

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"\n📋 Batch Summary:")
        print(f"   ✅ Successful: {len(successful)} scenarios")
        print(f"   ❌ Failed: {len(failed)} scenarios")
        print(f"   🎯 Success Rate: {summary['success_rate']:.1%}")
        print(f"   ⏱️  Total Time: {total_time:.1f} seconds")
        print(f"   📄 Summary saved: {summary_path}")

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
                scenario_results=successful_scenarios,
                output_path=comparison_path
            )

            print(f"   📊 Comparison report saved: {comparison_path}")

        except Exception as e:
            print(f"   ⚠️  Warning: Could not generate comparison report: {e}")

    def get_git_metadata(self) -> Dict[str, Any]:
        """Get git metadata for the current repository state.

        Returns:
            Dictionary with git metadata (SHA, branch, etc.)
        """
        metadata = {}

        try:
            # Get git SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True
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
                check=True
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
                check=True
            )
            metadata["git_clean"] = len(result.stdout.strip()) == 0
        except Exception:
            metadata["git_clean"] = False

        return metadata
