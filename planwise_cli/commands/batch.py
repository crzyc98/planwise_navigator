"""
Batch command for PlanWise Navigator CLI

Run multiple scenarios with Excel export and enhanced progress tracking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..integration.orchestrator_wrapper import OrchestratorWrapper
from ..ui.progress import create_batch_progress, show_error_message, show_success_message
from ..utils.config_helpers import find_default_config, find_scenarios_directory

console = Console()
batch_command = typer.Typer()

@batch_command.callback()
def batch_main():
    """📊 Run multiple scenarios with Excel export."""
    pass

@batch_command.command("run")
def run_batch(
    scenarios: Optional[list[str]] = typer.Option(
        None, "--scenarios", help="Specific scenario names to run"
    ),
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Base configuration file"
    ),
    scenarios_dir: Optional[str] = typer.Option(
        None, "--scenarios-dir", help="Directory containing scenario YAML files"
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", help="Output directory for batch results"
    ),
    export_format: str = typer.Option(
        "excel", "--export-format", help="Export format (excel, csv)"
    ),
    threads: int = typer.Option(
        1, "--threads", help="Number of dbt threads"
    ),
    optimization: str = typer.Option(
        "medium", "--optimization", help="Optimization level (low, medium, high)"
    ),
    clean: bool = typer.Option(
        False, "--clean", help="Delete DuckDB databases before running for a clean start"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output"
    ),
):
    """Run multiple scenarios with Excel export."""
    try:
        # Handle comma-separated scenario names for user convenience
        if scenarios and len(scenarios) == 1 and "," in scenarios[0]:
            scenarios = [s.strip() for s in scenarios[0].split(",")]

        console.print("📊 [bold blue]Starting batch scenario processing[/bold blue]")

        # Setup paths
        base_config_path = Path(config) if config else find_default_config()
        scenarios_path = Path(scenarios_dir) if scenarios_dir else find_scenarios_directory()
        output_path = Path(output_dir) if output_dir else Path("outputs")

        if not scenarios_path.exists():
            show_error_message(f"Scenarios directory not found: {scenarios_path}")
            raise typer.Exit(1)

        # Create wrapper and batch runner
        wrapper = OrchestratorWrapper(base_config_path, Path("dbt/simulation.duckdb"), verbose=verbose)
        batch_runner = wrapper.create_batch_runner(scenarios_path, output_path)

        # Determine scenario count for progress tracking
        available_scenario_files = list(scenarios_path.glob("*.yaml"))
        if scenarios:
            scenario_count = len(scenarios)
            console.print(f"🎯 [blue]Running {scenario_count} specified scenarios: {', '.join(scenarios)}[/blue]")
        else:
            scenario_count = len(available_scenario_files)
            console.print(f"🎯 [blue]Running all {scenario_count} available scenarios[/blue]")

        # Execute batch processing with enhanced progress tracking
        with create_batch_progress(scenario_count) as (progress, main_task):
            progress.update(main_task, description="📊 Starting batch processing...")

            # Show status before starting
            console.print(f"⚙️  [dim]Configuration: {base_config_path}[/dim]")
            console.print(f"📁 [dim]Scenarios: {scenarios_path}[/dim]")
            console.print(f"📊 [dim]Export format: {export_format}[/dim]")
            console.print("")

            # Execute the batch run
            try:
                results = batch_runner.run_batch(
                    scenario_names=scenarios,
                    export_format=export_format,
                    threads=threads,
                    optimization=optimization,
                    clean_databases=clean
                )
                progress.update(main_task, completed=scenario_count, description="✅ Batch processing complete")
            except Exception as e:
                progress.update(main_task, description="❌ Batch processing failed")
                raise

        if not results:
            show_error_message("No scenarios were processed")
            raise typer.Exit(1)

        # Report results
        successful = [name for name, result in results.items() if result.get("status") == "completed"]
        failed = [name for name, result in results.items() if result.get("status") == "failed"]

        console.print(f"\n🎯 [bold blue]Batch execution completed[/bold blue]")
        console.print(f"  ✅ Successful: {len(successful)} scenarios")
        if successful:
            console.print(f"     [dim]{', '.join(successful)}[/dim]")

        console.print(f"  ❌ Failed: {len(failed)} scenarios")
        if failed:
            console.print(f"     [dim red]{', '.join(failed)}[/dim red]")

        if successful:
            console.print(f"  📊 Outputs: [dim]{batch_runner.batch_output_dir}[/dim]")

        return 0 if not failed else 1

    except Exception as e:
        show_error_message(f"Batch processing failed: {e}")
        raise typer.Exit(1)

# Default command
@batch_command.command(name="", hidden=True)
def default(
    scenarios: Optional[list[str]] = typer.Option(None, "--scenarios"),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    scenarios_dir: Optional[str] = typer.Option(None, "--scenarios-dir"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir"),
    export_format: str = typer.Option("excel", "--export-format"),
    threads: int = typer.Option(1, "--threads"),
    optimization: str = typer.Option("medium", "--optimization"),
    clean: bool = typer.Option(False, "--clean"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Default batch command."""
    run_batch(
        scenarios=scenarios,
        config=config,
        scenarios_dir=scenarios_dir,
        output_dir=output_dir,
        export_format=export_format,
        threads=threads,
        optimization=optimization,
        clean=clean,
        verbose=verbose,
    )
