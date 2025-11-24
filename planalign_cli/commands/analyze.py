"""
Analyze command for Fidelity PlanAlign Engine CLI

Rich-formatted analysis commands with terminal-based visualizations
for simulation results and workforce trends.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from rich.progress import BarColumn, Progress, TextColumn

from ..integration.orchestrator_wrapper import OrchestratorWrapper
from ..ui.progress import show_error_message, show_success_message, show_warning_message
from ..utils.config_helpers import find_default_config
from planalign_orchestrator.excel_exporter import ExcelExporter

console = Console()
analyze_command = typer.Typer()

@analyze_command.callback()
def analyze_main():
    """📊 Analyze simulation results with Rich tables and terminal-based visualizations."""
    pass

@analyze_command.command("workforce")
def analyze_workforce(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
    database: Optional[str] = typer.Option(
        None, "--database", help="Path to DuckDB database file"
    ),
    start_year: Optional[int] = typer.Option(
        None, "--start-year", help="Start year for analysis"
    ),
    end_year: Optional[int] = typer.Option(
        None, "--end-year", help="End year for analysis"
    ),
    trend: bool = typer.Option(
        False, "--trend", help="Show detailed trend analysis"
    ),
    export: Optional[str] = typer.Option(
        None, "--export", help="Export format (excel, csv)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output"
    ),
):
    """
    Analyze workforce trends and metrics with Rich terminal visualizations.

    [dim]Examples:[/dim]
        planwise analyze workforce --trend           # Show detailed trends
        planwise analyze workforce --export excel    # Generate Excel report
        planwise analyze workforce --start-year 2025 --end-year 2027
    """
    try:
        console.print("📊 [bold blue]Workforce Analysis[/bold blue]")

        # Setup paths
        config_path = Path(config) if config else find_default_config()
        db_path = Path(database) if database else Path("dbt/simulation.duckdb")

        if verbose:
            console.print(f"📁 [dim]Database: {db_path}[/dim]")
            console.print(f"⚙️  [dim]Config: {config_path}[/dim]")

        # Initialize wrapper
        wrapper = OrchestratorWrapper(config_path, db_path, verbose=verbose)

        # Check database exists
        if not db_path.exists():
            show_error_message(f"Database not found: {db_path}")
            show_warning_message("Run a simulation first: planwise simulate 2025")
            raise typer.Exit(1)

        # Get workforce data
        workforce_data = _get_workforce_data(wrapper, start_year, end_year, verbose)

        if not workforce_data:
            show_warning_message("No workforce data found in database")
            show_warning_message("Run a simulation first: planwise simulate 2025-2027")
            raise typer.Exit(1)

        # Display analysis
        _display_workforce_overview(workforce_data, verbose)

        if trend:
            _display_workforce_trends(workforce_data, verbose)
            _display_department_analysis(workforce_data, verbose)

        # Export if requested
        if export:
            _export_workforce_analysis(workforce_data, export, wrapper)

        show_success_message("Workforce analysis completed")
        return 0

    except Exception as e:
        show_error_message(f"Analysis failed: {e}")
        if verbose:
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(1)

@analyze_command.command("events")
def analyze_events(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
    database: Optional[str] = typer.Option(
        None, "--database", help="Path to DuckDB database file"
    ),
    year: Optional[int] = typer.Option(
        None, "--year", help="Specific year to analyze"
    ),
    event_type: Optional[str] = typer.Option(
        None, "--type", help="Event type to analyze (hire, termination, promotion, raise)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output"
    ),
):
    """
    Analyze workforce events with Rich formatted tables and statistics.

    [dim]Examples:[/dim]
        planwise analyze events --year 2025          # Events for specific year
        planwise analyze events --type hire          # All hiring events
        planwise analyze events --type termination --verbose  # Detailed termination analysis
    """
    try:
        console.print("📈 [bold blue]Event Analysis[/bold blue]")

        # Setup paths
        config_path = Path(config) if config else find_default_config()
        db_path = Path(database) if database else Path("dbt/simulation.duckdb")

        # Initialize wrapper
        wrapper = OrchestratorWrapper(config_path, db_path, verbose=verbose)

        # Get event data
        event_data = _get_event_data(wrapper, year, event_type)

        if not event_data:
            show_warning_message("No event data found")
            raise typer.Exit(1)

        # Display analysis
        _display_event_summary(event_data, verbose)
        _display_event_trends(event_data, verbose)

        show_success_message("Event analysis completed")
        return 0

    except Exception as e:
        show_error_message(f"Event analysis failed: {e}")
        raise typer.Exit(1)

@analyze_command.command("scenario")
def analyze_scenario(
    scenario_name: str = typer.Argument(..., help="Scenario name to analyze"),
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
    compare: Optional[str] = typer.Option(
        None, "--compare", help="Compare with another scenario"
    ),
    export: Optional[str] = typer.Option(
        None, "--export", help="Export format (excel, csv)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output"
    ),
):
    """
    Analyze specific scenario results with executive summary dashboard.

    [dim]Examples:[/dim]
        planwise analyze scenario baseline           # Baseline scenario analysis
        planwise analyze scenario high_growth --compare baseline  # Scenario comparison
        planwise analyze scenario baseline --export excel  # Generate executive report
    """
    try:
        console.print(f"🎯 [bold blue]Scenario Analysis: {scenario_name}[/bold blue]")

        # Implementation for scenario analysis
        show_warning_message("Scenario analysis feature coming in next iteration")
        return 0

    except Exception as e:
        show_error_message(f"Scenario analysis failed: {e}")
        raise typer.Exit(1)

def _get_workforce_data(wrapper: OrchestratorWrapper, start_year: Optional[int], end_year: Optional[int], verbose: bool = False) -> List[Dict[str, Any]]:
    """Query workforce snapshot data from database."""
    try:
        with wrapper.db.get_connection() as conn:
            # Determine year range
            if start_year and end_year:
                year_filter = f"simulation_year BETWEEN {start_year} AND {end_year}"
            elif start_year:
                year_filter = f"simulation_year >= {start_year}"
            elif end_year:
                year_filter = f"simulation_year <= {end_year}"
            else:
                year_filter = "1=1"

            if verbose:
                console.print(f"[dim]Year filter: {year_filter}[/dim]")

            query = f"""
            SELECT
                simulation_year,
                COUNT(*) as total_employees,
                COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees,
                COUNT(CASE WHEN employment_status = 'terminated' THEN 1 END) as terminated_employees,
                COUNT(CASE WHEN is_enrolled_flag = true THEN 1 END) as enrolled_employees,
                ROUND(AVG(current_compensation), 0) as avg_compensation,
                ROUND(SUM(current_compensation), 0) as total_compensation,
                ROUND(AVG(current_age), 1) as avg_age,
                ROUND(AVG(current_tenure), 1) as avg_tenure
            FROM fct_workforce_snapshot
            WHERE {year_filter}
            GROUP BY simulation_year
            ORDER BY simulation_year
            """

            result = conn.execute(query).fetchall()

            # Convert to list of dictionaries
            columns = ['simulation_year', 'total_employees', 'active_employees', 'terminated_employees',
                      'enrolled_employees', 'avg_compensation', 'total_compensation', 'avg_age', 'avg_tenure']

            return [dict(zip(columns, row)) for row in result]

    except Exception as e:
        console.print(f"[red]Error querying workforce data: {e}[/red]")
        return []

def _get_event_data(wrapper: OrchestratorWrapper, year: Optional[int], event_type: Optional[str]) -> List[Dict[str, Any]]:
    """Query event data from database."""
    try:
        with wrapper.db.get_connection() as conn:
            # Build where clause
            conditions = []
            if year:
                conditions.append(f"simulation_year = {year}")
            if event_type:
                conditions.append(f"event_type = '{event_type}'")

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            query = f"""
            SELECT
                simulation_year,
                event_type,
                COUNT(*) as event_count,
                COUNT(DISTINCT employee_id) as unique_employees
            FROM fct_yearly_events
            {where_clause}
            GROUP BY simulation_year, event_type
            ORDER BY simulation_year, event_type
            """

            result = conn.execute(query).fetchall()

            columns = ['simulation_year', 'event_type', 'event_count', 'unique_employees']
            return [dict(zip(columns, row)) for row in result]

    except Exception as e:
        console.print(f"[red]Error querying event data: {e}[/red]")
        return []

def _display_workforce_overview(workforce_data: List[Dict[str, Any]], verbose: bool):
    """Display workforce overview with Rich tables."""
    if not workforce_data:
        return

    console.print("\n📊 [bold]Workforce Overview[/bold]")

    # Create summary table
    table = Table(title="Workforce Summary by Year", show_header=True)
    table.add_column("Year", style="bold cyan")
    table.add_column("Total Employees", style="green")
    table.add_column("Active", style="green")
    table.add_column("Enrolled", style="blue")
    table.add_column("Growth", style="yellow")
    table.add_column("Avg Compensation", style="magenta")

    previous_count = None
    for data in workforce_data:
        year = str(data['simulation_year'])
        total = f"{data['total_employees']:,}"
        active = f"{data['active_employees']:,}"
        enrolled = f"{data['enrolled_employees']:,}"

        # Calculate growth
        if previous_count:
            growth = data['total_employees'] - previous_count
            growth_pct = (growth / previous_count) * 100
            growth_str = f"+{growth} (+{growth_pct:.1f}%)" if growth > 0 else f"{growth} ({growth_pct:.1f}%)"
        else:
            growth_str = "Baseline"

        avg_comp = f"${data['avg_compensation']:,}"

        table.add_row(year, total, active, enrolled, growth_str, avg_comp)
        previous_count = data['total_employees']

    console.print(table)

def _display_workforce_trends(workforce_data: List[Dict[str, Any]], verbose: bool):
    """Display workforce trends with terminal-based visualization."""
    if len(workforce_data) < 2:
        return

    console.print("\n📈 [bold]Workforce Growth Trends[/bold]")

    # Calculate growth rates
    growth_rates = []
    for i in range(1, len(workforce_data)):
        current = workforce_data[i]['total_employees']
        previous = workforce_data[i-1]['total_employees']
        growth_rate = ((current - previous) / previous) * 100
        growth_rates.append({
            'year': workforce_data[i]['simulation_year'],
            'growth_rate': growth_rate,
            'absolute_growth': current - previous
        })

    # Create trend visualization using Rich progress bars
    console.print("\n🎯 [bold]Annual Growth Rates[/bold]")

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(complete_style="green", finished_style="blue"),
        TextColumn("[green]{task.completed:.1f}%"),
        console=console,
        transient=False,
    ) as progress:

        # Normalize growth rates for visualization (0-100 scale)
        max_rate = max(abs(g['growth_rate']) for g in growth_rates)
        if max_rate > 0:
            for growth in growth_rates:
                rate = growth['growth_rate']
                normalized_rate = abs(rate) / max_rate * 100

                task = progress.add_task(
                    f"Year {growth['year']}: {growth['absolute_growth']:+,} employees",
                    total=100
                )
                progress.update(task, completed=normalized_rate)

def _display_department_analysis(workforce_data: List[Dict[str, Any]], verbose: bool):
    """Display employment status and enrollment analysis."""
    if not workforce_data:
        return

    console.print("\n👥 [bold]Employment & Enrollment Analysis[/bold]")

    # Get latest year data
    latest_data = workforce_data[-1]

    # Create employment status breakdown
    status_table = Table(title=f"Employment Status - Year {latest_data['simulation_year']}", show_header=True)
    status_table.add_column("Category", style="bold")
    status_table.add_column("Count", style="green")
    status_table.add_column("% of Total", style="blue")
    status_table.add_column("Visual", style="cyan")

    total_employees = latest_data['total_employees']

    categories = [
        ('Active Employees', latest_data['active_employees']),
        ('Terminated Employees', latest_data['terminated_employees']),
        ('Enrolled in DC Plan', latest_data['enrolled_employees']),
    ]

    for category_name, count in categories:
        if count > 0:
            percentage = (count / total_employees) * 100
            # Create simple bar visualization
            bar_length = int(percentage / 2)  # Scale down for terminal
            bar = "█" * bar_length + "░" * (50 - bar_length)

            status_table.add_row(
                category_name,
                f"{count:,}",
                f"{percentage:.1f}%",
                bar[:25]  # Truncate for display
            )

    console.print(status_table)

    # Add workforce demographics
    console.print(f"\n📊 [bold]Workforce Demographics - Year {latest_data['simulation_year']}[/bold]")
    demo_table = Table(show_header=True)
    demo_table.add_column("Metric", style="bold cyan")
    demo_table.add_column("Value", style="green")

    demo_table.add_row("Average Age", f"{latest_data['avg_age']:.1f} years")
    demo_table.add_row("Average Tenure", f"{latest_data['avg_tenure']:.1f} years")
    demo_table.add_row("Average Compensation", f"${latest_data['avg_compensation']:,}")
    demo_table.add_row("Total Compensation", f"${latest_data['total_compensation'] / 1_000_000:.1f}M")

    # Calculate enrollment rate
    if latest_data['active_employees'] > 0:
        enrollment_rate = (latest_data['enrolled_employees'] / latest_data['active_employees']) * 100
        demo_table.add_row("DC Plan Enrollment Rate", f"{enrollment_rate:.1f}%")

    console.print(demo_table)

def _display_event_summary(event_data: List[Dict[str, Any]], verbose: bool):
    """Display event summary with Rich formatting."""
    if not event_data:
        return

    console.print("\n📋 [bold]Event Summary[/bold]")

    # Create event summary table
    table = Table(title="Event Analysis", show_header=True)
    table.add_column("Year", style="bold cyan")
    table.add_column("Event Type", style="bold")
    table.add_column("Count", style="green")
    table.add_column("Unique Employees", style="blue")

    for data in event_data:
        table.add_row(
            str(data['simulation_year']),
            data['event_type'].title(),
            f"{data['event_count']:,}",
            f"{data['unique_employees']:,}"
        )

    console.print(table)

def _display_event_trends(event_data: List[Dict[str, Any]], verbose: bool):
    """Display event trends visualization."""
    # Group by event type for trend analysis
    event_types = {}
    for data in event_data:
        event_type = data['event_type']
        if event_type not in event_types:
            event_types[event_type] = []
        event_types[event_type].append(data)

    console.print(f"\n📊 [bold]Event Trends by Type[/bold]")

    for event_type, events in event_types.items():
        if len(events) > 1:
            console.print(f"\n🔍 [cyan]{event_type.title()} Events[/cyan]")

            # Simple trend indicator
            first_count = events[0]['event_count']
            last_count = events[-1]['event_count']

            if last_count > first_count:
                trend = "📈 Increasing"
            elif last_count < first_count:
                trend = "📉 Decreasing"
            else:
                trend = "➡️  Stable"

            console.print(f"   Trend: {trend} ({first_count:,} → {last_count:,})")

def _export_workforce_analysis(workforce_data: List[Dict[str, Any]], format: str, wrapper: OrchestratorWrapper):
    """Export workforce analysis to specified format."""
    try:
        console.print(f"\n📁 [bold blue]Exporting workforce analysis to {format.upper()}[/bold blue]")

        # Create output directory
        output_dir = Path("outputs") / f"workforce_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize ExcelExporter
        exporter = ExcelExporter(wrapper.db)

        # Create mock config for ExcelExporter interface
        class MockSimulation:
            def __init__(self):
                self.target_growth_rate = 0.03

        class MockCompensation:
            def __init__(self):
                self.cola_rate = 0.025
                self.merit_budget = 0.035

        class MockConfig:
            def __init__(self):
                self.start_year = min(data['simulation_year'] for data in workforce_data) if workforce_data else 2025
                self.end_year = max(data['simulation_year'] for data in workforce_data) if workforce_data else 2025
                self.scenario_id = "workforce_analysis"
                self.simulation = MockSimulation()
                self.compensation = MockCompensation()

        config = MockConfig()

        # Export using the existing ExcelExporter
        export_path = exporter.export_scenario_results(
            scenario_name="workforce_analysis",
            output_dir=output_dir,
            config=config,
            seed=12345,  # Mock seed for analysis export
            export_format=format.lower()
        )

        console.print(f"   ✅ Analysis exported to: [green]{export_path}[/green]")
        console.print(f"   📊 Contains: workforce snapshots, event data, and metadata")

    except Exception as e:
        show_error_message(f"Export failed: {e}")
        if hasattr(console, 'print_exception'):
            console.print_exception()

# Default command
@analyze_command.command(name="", hidden=True)
def default(
    target: str = typer.Argument("workforce", help="Analysis target (workforce, events, scenario)"),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    database: Optional[str] = typer.Option(None, "--database"),
    trend: bool = typer.Option(False, "--trend"),
    export: Optional[str] = typer.Option(None, "--export"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Default analyze command - routes to workforce analysis."""
    if target == "workforce":
        analyze_workforce(
            config=config,
            database=database,
            trend=trend,
            export=export,
            verbose=verbose
        )
    else:
        console.print(f"[yellow]Unknown analysis target: {target}[/yellow]")
        console.print("Available targets: workforce, events, scenario")
        raise typer.Exit(1)
