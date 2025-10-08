"""
Performance monitoring and execution tracing for PlanWise Navigator.

This module provides execution profiling capabilities to track model runtimes,
memory usage, and identify performance bottlenecks during multi-year simulations.
"""

from __future__ import annotations
import time
import psutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from pathlib import Path
import json
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class ExecutionTrace:
    """Single execution trace for a dbt model."""
    model_name: str
    simulation_year: int
    stage: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    memory_mb_before: float = 0.0
    memory_mb_after: float = 0.0
    memory_delta_mb: float = 0.0
    success: bool = True
    error: Optional[str] = None

    def finalize(self, success: bool = True, error: Optional[str] = None) -> None:
        """Finalize trace with end time and duration."""
        self.end_time = datetime.now()
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()
        self.success = success
        self.error = error


class ExecutionTracer:
    """Track execution performance across simulation runs."""

    def __init__(self):
        self.traces: List[ExecutionTrace] = []
        self.current_trace: Optional[ExecutionTrace] = None
        self.process = psutil.Process()

    def start_trace(self, model_name: str, simulation_year: int, stage: str) -> ExecutionTrace:
        """Start tracking a model execution."""
        memory_mb = self.process.memory_info().rss / 1024 / 1024

        trace = ExecutionTrace(
            model_name=model_name,
            simulation_year=simulation_year,
            stage=stage,
            start_time=datetime.now(),
            memory_mb_before=memory_mb,
        )

        self.current_trace = trace
        return trace

    def end_trace(self, success: bool = True, error: Optional[str] = None) -> None:
        """End current trace and record results."""
        if not self.current_trace:
            return

        memory_mb = self.process.memory_info().rss / 1024 / 1024
        self.current_trace.memory_mb_after = memory_mb
        self.current_trace.memory_delta_mb = memory_mb - self.current_trace.memory_mb_before
        self.current_trace.finalize(success=success, error=error)

        self.traces.append(self.current_trace)
        self.current_trace = None

    def get_slowest_models(self, top_n: int = 10) -> List[ExecutionTrace]:
        """Get the N slowest model executions."""
        return sorted(
            [t for t in self.traces if t.duration_seconds],
            key=lambda t: t.duration_seconds,
            reverse=True,
        )[:top_n]

    def get_highest_memory_models(self, top_n: int = 10) -> List[ExecutionTrace]:
        """Get models with highest memory consumption."""
        return sorted(
            self.traces,
            key=lambda t: abs(t.memory_delta_mb),
            reverse=True,
        )[:top_n]

    def get_total_execution_time(self) -> float:
        """Calculate total execution time across all traces."""
        return sum(t.duration_seconds for t in self.traces if t.duration_seconds)

    def export_to_dataframe(self) -> pd.DataFrame:
        """Export traces to pandas DataFrame for analysis."""
        data = [
            {
                "model_name": t.model_name,
                "simulation_year": t.simulation_year,
                "stage": t.stage,
                "duration_seconds": t.duration_seconds,
                "memory_delta_mb": t.memory_delta_mb,
                "success": t.success,
                "start_time": t.start_time,
            }
            for t in self.traces
        ]
        return pd.DataFrame(data)

    def export_to_json(self, output_file: Path) -> None:
        """Export traces to JSON file."""
        data = [
            {
                "model_name": t.model_name,
                "simulation_year": t.simulation_year,
                "stage": t.stage,
                "duration_seconds": t.duration_seconds,
                "memory_delta_mb": t.memory_delta_mb,
                "success": t.success,
                "error": t.error,
                "start_time": t.start_time.isoformat(),
                "end_time": t.end_time.isoformat() if t.end_time else None,
            }
            for t in self.traces
        ]

        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

        console.print(f"[green]Exported {len(self.traces)} traces to {output_file}[/green]")

    def print_performance_report(self) -> None:
        """Print beautiful performance report."""
        if not self.traces:
            console.print("[yellow]No execution traces available[/yellow]")
            return

        console.print(f"\n[bold]Execution Performance Report[/bold]")
        console.print(f"Total models executed: {len(self.traces)}")
        console.print(f"Total execution time: {self.get_total_execution_time():.1f}s")
        console.print(f"Successful: {sum(1 for t in self.traces if t.success)}")
        console.print(f"Failed: {sum(1 for t in self.traces if not t.success)}")

        # Slowest models
        slowest = self.get_slowest_models(5)
        if slowest:
            table = Table(title="\nTop 5 Slowest Models", show_header=True)
            table.add_column("Model", style="cyan")
            table.add_column("Year", style="blue")
            table.add_column("Duration", style="magenta")
            table.add_column("Memory Δ", style="green")

            for trace in slowest:
                table.add_row(
                    trace.model_name,
                    str(trace.simulation_year),
                    f"{trace.duration_seconds:.2f}s",
                    f"{trace.memory_delta_mb:+.1f} MB",
                )

            console.print(table)

        # Memory hogs
        memory_hogs = self.get_highest_memory_models(5)
        if memory_hogs:
            table = Table(title="\nTop 5 Memory-Intensive Models", show_header=True)
            table.add_column("Model", style="cyan")
            table.add_column("Year", style="blue")
            table.add_column("Memory Δ", style="red")
            table.add_column("Duration", style="magenta")

            for trace in memory_hogs:
                table.add_row(
                    trace.model_name,
                    str(trace.simulation_year),
                    f"{trace.memory_delta_mb:+.1f} MB",
                    f"{trace.duration_seconds:.2f}s",
                )

            console.print(table)
