"""
Validate command for PlanWise Navigator CLI

Configuration validation with detailed reporting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ..integration.orchestrator_wrapper import OrchestratorWrapper
from ..ui.progress import show_error_message, show_success_message, show_warning_message
from ..utils.config_helpers import find_default_config

console = Console()
validate_command = typer.Typer()

@validate_command.callback()
def validate_main():
    """✅ Validate configuration files and system setup."""
    pass

@validate_command.command("config")
def validate_config(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
    enforce_identifiers: bool = typer.Option(
        False, "--enforce-identifiers", help="Require scenario_id and plan_design_id"
    ),
):
    """Validate simulation configuration."""
    try:
        config_path = Path(config) if config else find_default_config()
        console.print(f"✅ [bold blue]Validating configuration: {config_path}[/bold blue]")

        if not config_path.exists():
            show_error_message(f"Configuration file not found: {config_path}")
            raise typer.Exit(1)

        wrapper = OrchestratorWrapper(config_path, Path("dbt/simulation.duckdb"))
        validation_result = wrapper.validate_configuration(enforce_identifiers=enforce_identifiers)

        if validation_result["valid"]:
            show_success_message("Configuration is valid")

            # Show configuration summary
            config_dict = validation_result.get("config_dict", {})
            if config_dict:
                summary_info = []
                if "scenario_id" in config_dict and config_dict["scenario_id"]:
                    summary_info.append(f"📊 Scenario ID: {config_dict['scenario_id']}")
                if "plan_design_id" in config_dict and config_dict["plan_design_id"]:
                    summary_info.append(f"📋 Plan Design ID: {config_dict['plan_design_id']}")

                # Show simulation years if available
                simulation = config_dict.get("simulation", {})
                if simulation:
                    start_year = simulation.get("start_year")
                    end_year = simulation.get("end_year")
                    if start_year and end_year:
                        summary_info.append(f"📅 Years: {start_year}-{end_year}")

                if summary_info:
                    console.print(Panel("\n".join(summary_info), title="Configuration Summary", border_style="green"))

            # Show warnings
            warnings = validation_result.get("warnings", [])
            for warning in warnings:
                show_warning_message(warning)

            # Show recommendations
            recommendations = validation_result.get("recommendations", [])
            if recommendations:
                console.print("\n💡 [bold]Recommendations:[/bold]")
                for rec in recommendations:
                    console.print(f"  • [dim]{rec}[/dim]")

            return 0

        else:
            show_error_message(f"Configuration is invalid: {validation_result['error']}")
            raise typer.Exit(1)

    except Exception as e:
        show_error_message(f"Validation failed: {e}")
        raise typer.Exit(1)

# Default command
@validate_command.command(name="", hidden=True)
def default(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    enforce_identifiers: bool = typer.Option(False, "--enforce-identifiers"),
):
    """Default validate command."""
    validate_config(config=config, enforce_identifiers=enforce_identifiers)
