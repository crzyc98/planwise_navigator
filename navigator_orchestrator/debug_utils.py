"""
Debug utilities for PlanWise Navigator.

Provides instant database health checks, event inspection, state visualization,
and dependency analysis for debugging workforce simulation issues.
"""

from __future__ import annotations
import duckdb
import json
import re
from pathlib import Path
from typing import Literal, Optional, Any, Set, List, Tuple
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from rich.console import Console
from rich.table import Table
from navigator_orchestrator.config import get_database_path

console = Console()

@dataclass
class YearSnapshot:
    """Snapshot of simulation state for a single year."""
    year: int
    workforce_count: int
    hire_events: int
    termination_events: int
    promotion_events: int
    raise_events: int
    enrollment_events: int
    total_events: int
    avg_salary: float
    total_compensation_cost: float
    data_quality_issues: list[str]

    @property
    def net_workforce_change(self) -> int:
        return self.hire_events - self.termination_events

class DatabaseInspector:
    """Fast database inspection and health checks."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_database_path()
        self.conn = duckdb.connect(str(self.db_path), read_only=True)

    def quick_stats(self, year: Optional[int] = None) -> dict:
        """Get instant database statistics.

        Args:
            year: Optional year filter. If None, returns all years.

        Returns:
            Dictionary with table counts, event statistics, and health metrics.
        """
        year_filter = f"WHERE simulation_year = {year}" if year else ""

        query = f"""
        SELECT
            COUNT(*) as total_events,
            COUNT(DISTINCT simulation_year) as total_years,
            MIN(simulation_year) as first_year,
            MAX(simulation_year) as last_year,
            COUNT(DISTINCT employee_id) as unique_employees,
            COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as hires,
            COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as terminations,
            COUNT(CASE WHEN event_type = 'promotion' THEN 1 END) as promotions,
            COUNT(CASE WHEN event_type = 'raise' THEN 1 END) as raises,
            COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) as enrollments
        FROM fct_yearly_events
        {year_filter}
        """

        result = self.conn.execute(query).fetchone()

        return {
            "total_events": result[0],
            "total_years": result[1],
            "year_range": (result[2], result[3]) if result[2] else None,
            "unique_employees": result[4],
            "event_counts": {
                "hire": result[5],
                "termination": result[6],
                "promotion": result[7],
                "raise": result[8],
                "enrollment": result[9],
            },
            "net_workforce_change": result[5] - result[6],
        }

    def get_year_snapshot(self, year: int) -> YearSnapshot:
        """Get comprehensive snapshot for a single year."""

        # Event statistics
        event_query = f"""
        SELECT
            COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as hires,
            COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as terminations,
            COUNT(CASE WHEN event_type = 'promotion' THEN 1 END) as promotions,
            COUNT(CASE WHEN event_type = 'raise' THEN 1 END) as raises,
            COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) as enrollments,
            COUNT(*) as total_events
        FROM fct_yearly_events
        WHERE simulation_year = {year}
        """
        events = self.conn.execute(event_query).fetchone()

        # Workforce metrics
        workforce_query = f"""
        SELECT
            COUNT(*) as workforce_count,
            AVG(current_compensation) as avg_salary,
            SUM(current_compensation) as total_comp_cost
        FROM fct_workforce_snapshot
        WHERE simulation_year = {year} AND employment_status = 'active'
        """
        workforce = self.conn.execute(workforce_query).fetchone()

        # Data quality checks
        dq_issues = self._check_data_quality(year)

        return YearSnapshot(
            year=year,
            workforce_count=workforce[0] or 0,
            hire_events=events[0],
            termination_events=events[1],
            promotion_events=events[2],
            raise_events=events[3],
            enrollment_events=events[4],
            total_events=events[5],
            avg_salary=workforce[1] or 0.0,
            total_compensation_cost=workforce[2] or 0.0,
            data_quality_issues=dq_issues,
        )

    def _check_data_quality(self, year: int) -> list[str]:
        """Run fast data quality checks for a year."""
        issues = []

        # Check for duplicate enrollments
        dup_check = f"""
        SELECT COUNT(*) FROM (
            SELECT employee_id, COUNT(*) as cnt
            FROM fct_yearly_events
            WHERE simulation_year = {year} AND event_type = 'enrollment'
            GROUP BY employee_id
            HAVING COUNT(*) > 1
        )
        """
        dup_count = self.conn.execute(dup_check).fetchone()[0]
        if dup_count > 0:
            issues.append(f"⚠️  {dup_count} employees with duplicate enrollment events")

        # Check for enrollments without enrollment dates
        missing_dates = f"""
        SELECT COUNT(*) FROM (
            SELECT e.employee_id
            FROM fct_yearly_events e
            LEFT JOIN fct_workforce_snapshot w
                ON e.employee_id = w.employee_id
                AND e.simulation_year = w.simulation_year
            WHERE e.simulation_year = {year}
                AND e.event_type = 'enrollment'
                AND w.employee_enrollment_date IS NULL
        )
        """
        missing_count = self.conn.execute(missing_dates).fetchone()[0]
        if missing_count > 0:
            issues.append(f"❌ {missing_count} enrollment events missing employee_enrollment_date in snapshot")

        # Check for zero workforce
        if self.conn.execute(f"SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = {year}").fetchone()[0] == 0:
            issues.append(f"🚨 Zero workforce records for year {year}")

        return issues

    def event_timeline(self, employee_id: str) -> pd.DataFrame:
        """Get complete event timeline for an employee."""
        query = f"""
        SELECT
            simulation_year,
            event_type,
            effective_date,
            event_details
        FROM fct_yearly_events
        WHERE employee_id = '{employee_id}'
        ORDER BY simulation_year, effective_date
        """
        return self.conn.execute(query).df()

    def print_year_report(self, year: int) -> None:
        """Print beautiful terminal report for a year."""
        snapshot = self.get_year_snapshot(year)

        # Create Rich table
        table = Table(title=f"Simulation Year {year} Report", show_header=True)
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        table.add_row("Workforce Count", f"{snapshot.workforce_count:,}")
        table.add_row("Average Salary", f"${snapshot.avg_salary:,.2f}")
        table.add_row("Total Compensation", f"${snapshot.total_compensation_cost:,.2f}")
        table.add_row("", "")
        table.add_row("Hire Events", f"{snapshot.hire_events:,}")
        table.add_row("Termination Events", f"{snapshot.termination_events:,}")
        table.add_row("Net Change", f"{snapshot.net_workforce_change:+,}")
        table.add_row("Promotion Events", f"{snapshot.promotion_events:,}")
        table.add_row("Raise Events", f"{snapshot.raise_events:,}")
        table.add_row("Enrollment Events", f"{snapshot.enrollment_events:,}")
        table.add_row("", "")
        table.add_row("Total Events", f"{snapshot.total_events:,}")

        console.print(table)

        # Print data quality issues
        if snapshot.data_quality_issues:
            console.print("\n[bold red]Data Quality Issues:[/bold red]")
            for issue in snapshot.data_quality_issues:
                console.print(f"  {issue}")
        else:
            console.print("\n[bold green]✓ No data quality issues detected[/bold green]")

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


@dataclass
class CheckpointMetadata:
    """Metadata for a simulation checkpoint."""
    year: int
    stage: str
    timestamp: datetime
    duration_seconds: float
    success: bool
    error: Optional[str]
    models_executed: list[str]


class StateVisualizer:
    """Visualize checkpoint and registry state."""

    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = checkpoint_dir

    def list_checkpoints(self) -> list[CheckpointMetadata]:
        """List all available checkpoints."""
        checkpoints = []

        if not self.checkpoint_dir.exists():
            return checkpoints

        for checkpoint_file in self.checkpoint_dir.glob("checkpoint_*.json"):
            try:
                with open(checkpoint_file) as f:
                    data = json.load(f)

                    # Handle different checkpoint formats
                    checkpoints.append(CheckpointMetadata(
                        year=data.get("year", 0),
                        stage=data.get("stage", "unknown"),
                        timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
                        duration_seconds=data.get("duration_seconds", 0.0),
                        success=data.get("success", True),
                        error=data.get("error"),
                        models_executed=data.get("models_executed", []),
                    ))
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                console.print(f"[yellow]Warning: Could not parse {checkpoint_file}: {e}[/yellow]")
                continue

        return sorted(checkpoints, key=lambda c: (c.year, c.timestamp))

    def get_registry_state(self, year: int) -> dict[str, Any]:
        """Load registry state for a year from checkpoint."""
        checkpoint_file = self.checkpoint_dir / f"checkpoint_{year}.json"

        if not checkpoint_file.exists():
            raise FileNotFoundError(f"No checkpoint found for year {year}")

        with open(checkpoint_file) as f:
            data = json.load(f)

        return {
            "eligibility_registry": data.get("eligibility_registry", {}),
            "enrollment_registry": data.get("enrollment_registry", {}),
            "vesting_registry": data.get("vesting_registry", {}),
            "contribution_registry": data.get("contribution_registry", {}),
        }

    def compare_years(self, year1: int, year2: int) -> dict:
        """Compare registry state between two years."""
        state1 = self.get_registry_state(year1)
        state2 = self.get_registry_state(year2)

        comparison = {}

        for registry_name in state1.keys():
            reg1 = state1[registry_name]
            reg2 = state2[registry_name]

            comparison[registry_name] = {
                "year1_count": len(reg1),
                "year2_count": len(reg2),
                "added": set(reg2.keys()) - set(reg1.keys()),
                "removed": set(reg1.keys()) - set(reg2.keys()),
                "unchanged": set(reg1.keys()) & set(reg2.keys()),
            }

        return comparison

    def print_checkpoint_summary(self) -> None:
        """Print beautiful checkpoint summary."""
        checkpoints = self.list_checkpoints()

        if not checkpoints:
            console.print("[yellow]No checkpoints found[/yellow]")
            return

        table = Table(title="Checkpoint Summary", show_header=True)
        table.add_column("Year", style="cyan")
        table.add_column("Stage", style="blue")
        table.add_column("Timestamp", style="magenta")
        table.add_column("Duration", style="green")
        table.add_column("Status", style="white")

        for cp in checkpoints:
            status = "✓ Success" if cp.success else f"✗ Failed: {cp.error}"
            table.add_row(
                str(cp.year),
                cp.stage,
                cp.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                f"{cp.duration_seconds:.1f}s",
                status,
            )

        console.print(table)


class DependencyAnalyzer:
    """Analyze dbt model dependencies and detect cycles."""

    def __init__(self, dbt_project_dir: Path):
        self.dbt_project_dir = dbt_project_dir
        self.models_dir = dbt_project_dir / "models"
        self.graph = nx.DiGraph()

    def parse_model_refs(self, model_file: Path) -> Set[str]:
        """Extract ref() dependencies from a dbt model file."""
        refs = set()

        with open(model_file) as f:
            content = f.read()

        # Match {{ ref('model_name') }} or {{ ref("model_name") }}
        pattern = r"{{\s*ref\(\s*['\"]([^'\"]+)['\"]\s*\)\s*}}"
        matches = re.findall(pattern, content)
        refs.update(matches)

        return refs

    def build_dependency_graph(self) -> nx.DiGraph:
        """Build complete dependency graph from dbt models."""
        self.graph.clear()

        # Find all SQL model files
        model_files = list(self.models_dir.rglob("*.sql"))

        for model_file in model_files:
            # Extract model name from file path
            model_name = model_file.stem

            # Skip non-model files (macros, tests, etc.)
            if model_name.startswith("_"):
                continue

            # Add node
            self.graph.add_node(model_name, file=str(model_file))

            # Add edges for dependencies
            refs = self.parse_model_refs(model_file)
            for ref in refs:
                self.graph.add_edge(ref, model_name)

        return self.graph

    def find_circular_dependencies(self) -> List[List[str]]:
        """Detect circular dependencies in the dependency graph."""
        try:
            cycles = list(nx.simple_cycles(self.graph))
            return cycles
        except Exception:
            return []

    def get_model_depth(self, model_name: str) -> int:
        """Calculate depth of a model in the dependency tree."""
        if model_name not in self.graph:
            return 0

        # Find shortest path from any source (model with no dependencies)
        sources = [n for n in self.graph.nodes() if self.graph.in_degree(n) == 0]

        if not sources:
            return 0

        depths = []
        for source in sources:
            if nx.has_path(self.graph, source, model_name):
                depth = nx.shortest_path_length(self.graph, source, model_name)
                depths.append(depth)

        return max(depths) if depths else 0

    def get_critical_path(self) -> List[str]:
        """Find the longest dependency chain (critical path)."""
        if not self.graph.nodes():
            return []

        # Find longest path using DAG longest path
        try:
            return nx.dag_longest_path(self.graph)
        except nx.NetworkXError:
            # Graph has cycles
            return []

    def visualize_graph(self, output_file: Path, highlight_cycles: bool = True) -> None:
        """Generate visual dependency graph."""
        if not self.graph.nodes():
            self.build_dependency_graph()

        plt.figure(figsize=(20, 12))

        # Use hierarchical layout
        pos = nx.spring_layout(self.graph, k=2, iterations=50)

        # Color nodes by layer (staging, intermediate, marts)
        node_colors = []
        for node in self.graph.nodes():
            if node.startswith("stg_"):
                node_colors.append("lightblue")
            elif node.startswith("int_"):
                node_colors.append("lightgreen")
            elif node.startswith("fct_") or node.startswith("dim_"):
                node_colors.append("lightcoral")
            else:
                node_colors.append("lightgray")

        # Draw graph
        nx.draw(
            self.graph,
            pos,
            node_color=node_colors,
            with_labels=True,
            node_size=1000,
            font_size=8,
            font_weight="bold",
            arrows=True,
            edge_color="gray",
            alpha=0.7,
        )

        # Highlight cycles
        if highlight_cycles:
            cycles = self.find_circular_dependencies()
            for cycle in cycles:
                cycle_edges = [(cycle[i], cycle[(i+1) % len(cycle)]) for i in range(len(cycle))]
                nx.draw_networkx_edges(
                    self.graph,
                    pos,
                    edgelist=cycle_edges,
                    edge_color="red",
                    width=3,
                    alpha=0.8,
                )

        plt.title("dbt Model Dependency Graph", fontsize=16)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches="tight")
        console.print(f"[green]Saved dependency graph to {output_file}[/green]")

    def print_dependency_report(self) -> None:
        """Print detailed dependency analysis report."""
        if not self.graph.nodes():
            self.build_dependency_graph()

        # Basic stats
        console.print(f"\n[bold]Dependency Analysis Report[/bold]")
        console.print(f"Total models: {self.graph.number_of_nodes()}")
        console.print(f"Total dependencies: {self.graph.number_of_edges()}")

        # Circular dependencies
        cycles = self.find_circular_dependencies()
        if cycles:
            console.print(f"\n[bold red]⚠️  Found {len(cycles)} circular dependencies:[/bold red]")
            for i, cycle in enumerate(cycles, 1):
                console.print(f"  {i}. {' → '.join(cycle + [cycle[0]])}")
        else:
            console.print("\n[bold green]✓ No circular dependencies detected[/bold green]")

        # Critical path
        critical_path = self.get_critical_path()
        if critical_path:
            console.print(f"\n[bold]Critical Path ({len(critical_path)} models):[/bold]")
            console.print(f"  {' → '.join(critical_path)}")

        # Most depended-upon models
        in_degrees = [(node, self.graph.in_degree(node)) for node in self.graph.nodes()]
        top_dependencies = sorted(in_degrees, key=lambda x: x[1], reverse=True)[:5]

        console.print("\n[bold]Most Depended-Upon Models:[/bold]")
        for model, degree in top_dependencies:
            console.print(f"  {model}: {degree} downstream dependencies")
