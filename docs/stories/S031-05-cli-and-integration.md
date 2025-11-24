# Story S031-05: CLI and Integration (5 points)

## Story Overview

**As a** system user
**I want** a modern CLI interface with enhanced monitoring and error handling
**So that** I get clear feedback, performance insights, and reliable execution

**Epic**: E031 - Optimized Multi-Year Simulation System
**Story Points**: 5
**Priority**: High
**Status**: 🔴 Not Started

## Acceptance Criteria

- [ ] New `run_multi_year.py` CLI with same interface as existing system
- [ ] Built-in performance monitoring with bottleneck identification
- [ ] Enhanced error messages with troubleshooting guidance
- [ ] Progress tracking with real-time performance metrics
- [ ] Comprehensive logging with optimization recommendations

## Technical Requirements

### CLI Design and Interface

#### Command Structure
```bash
# Primary execution modes
python orchestrator_dbt/run_multi_year.py [OPTIONS]

# Advanced usage patterns
python orchestrator_dbt/run_multi_year.py --config custom_config.yaml --verbose --profile performance
python orchestrator_dbt/run_multi_year.py --years 2024-2030 --dry-run --optimization-report
python orchestrator_dbt/run_multi_year.py --resume simulation_checkpoint_20241201.json
```

#### Argument Parsing Implementation
```python
import argparse
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class CLIConfig:
    """Type-safe CLI configuration with validation"""
    config_path: Path
    start_year: int
    end_year: int
    verbose: bool = False
    profile: str = "default"
    dry_run: bool = False
    resume_checkpoint: Optional[Path] = None
    optimization_level: int = 1  # 0=none, 1=basic, 2=advanced
    output_format: str = "table"  # table, json, yaml
    log_level: str = "INFO"

def parse_cli_arguments() -> CLIConfig:
    """Parse and validate CLI arguments with comprehensive error handling"""
    parser = argparse.ArgumentParser(
        description="Fidelity PlanAlign Engine Multi-Year Simulation CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --years 2024-2030 --verbose
  %(prog)s --config custom.yaml --profile performance
  %(prog)s --resume checkpoint.json --optimization-level 2
        """
    )

    # Core simulation parameters
    parser.add_argument('--config', type=Path, default='config/simulation_config.yaml',
                       help='Path to simulation configuration file')
    parser.add_argument('--years', type=str, metavar='START-END',
                       help='Simulation year range (e.g., 2024-2030)')

    # Execution modes
    parser.add_argument('--dry-run', action='store_true',
                       help='Validate configuration without running simulation')
    parser.add_argument('--resume', type=Path, metavar='CHECKPOINT',
                       help='Resume from checkpoint file')

    # Performance and monitoring
    parser.add_argument('--profile', choices=['default', 'performance', 'debug'],
                       default='default', help='Execution profile')
    parser.add_argument('--optimization-level', type=int, choices=[0, 1, 2],
                       default=1, help='Optimization analysis detail level')

    # Output and logging
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose output')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Suppress non-essential output')
    parser.add_argument('--output-format', choices=['table', 'json', 'yaml'],
                       default='table', help='Output format for results')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO', help='Logging level')

    return CLIConfig(**vars(parser.parse_args()))
```

### Performance Monitoring System

#### Real-Time Metrics Collection
```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import psutil
import threading
import time

@dataclass
class PerformanceMetrics:
    """Comprehensive performance tracking"""
    start_time: datetime = field(default_factory=datetime.now)
    cpu_usage: List[float] = field(default_factory=list)
    memory_usage: List[float] = field(default_factory=list)
    disk_io: Dict[str, float] = field(default_factory=dict)
    network_io: Dict[str, float] = field(default_factory=dict)
    database_operations: Dict[str, int] = field(default_factory=dict)
    year_processing_times: List[float] = field(default_factory=list)
    bottlenecks: List[str] = field(default_factory=list)

class PerformanceMonitor:
    """Real-time system performance monitoring"""

    def __init__(self, sampling_interval: float = 1.0):
        self.metrics = PerformanceMetrics()
        self.sampling_interval = sampling_interval
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None

    def start_monitoring(self):
        """Start background performance monitoring"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        """Stop monitoring and return final metrics"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        return self.metrics

    def _monitor_loop(self):
        """Background monitoring loop"""
        while self.monitoring:
            # System metrics
            self.metrics.cpu_usage.append(psutil.cpu_percent())
            self.metrics.memory_usage.append(psutil.virtual_memory().percent)

            # I/O metrics
            disk_io = psutil.disk_io_counters()
            if disk_io:
                self.metrics.disk_io.update({
                    'read_bytes': disk_io.read_bytes,
                    'write_bytes': disk_io.write_bytes
                })

            time.sleep(self.sampling_interval)

    def identify_bottlenecks(self) -> List[str]:
        """Analyze metrics to identify performance bottlenecks"""
        bottlenecks = []

        if self.metrics.cpu_usage and max(self.metrics.cpu_usage) > 90:
            bottlenecks.append("High CPU usage detected - consider parallel processing optimization")

        if self.metrics.memory_usage and max(self.metrics.memory_usage) > 85:
            bottlenecks.append("High memory usage - consider chunked processing or data streaming")

        return bottlenecks
```

#### Performance Dashboard Implementation
```python
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from rich.live import Live
from rich.layout import Layout
import time

class PerformanceDashboard:
    """Real-time performance dashboard using Rich"""

    def __init__(self, console: Console):
        self.console = console
        self.layout = Layout()
        self.performance_monitor = PerformanceMonitor()

    def create_dashboard_layout(self) -> Layout:
        """Create responsive dashboard layout"""
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=5)
        )

        self.layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        return self.layout

    def update_performance_table(self, metrics: PerformanceMetrics) -> Table:
        """Generate real-time performance table"""
        table = Table(title="System Performance")
        table.add_column("Metric", style="cyan")
        table.add_column("Current", style="green")
        table.add_column("Average", style="yellow")
        table.add_column("Peak", style="red")

        if metrics.cpu_usage:
            table.add_row(
                "CPU Usage (%)",
                f"{metrics.cpu_usage[-1]:.1f}",
                f"{sum(metrics.cpu_usage)/len(metrics.cpu_usage):.1f}",
                f"{max(metrics.cpu_usage):.1f}"
            )

        if metrics.memory_usage:
            table.add_row(
                "Memory Usage (%)",
                f"{metrics.memory_usage[-1]:.1f}",
                f"{sum(metrics.memory_usage)/len(metrics.memory_usage):.1f}",
                f"{max(metrics.memory_usage):.1f}"
            )

        return table

    def run_dashboard(self, simulation_progress: Progress):
        """Run live performance dashboard"""
        with Live(self.create_dashboard_layout(), refresh_per_second=2) as live:
            self.performance_monitor.start_monitoring()

            try:
                while True:
                    metrics = self.performance_monitor.metrics

                    # Update dashboard components
                    self.layout["header"].update(f"Fidelity PlanAlign Engine - Multi-Year Simulation")
                    self.layout["left"].update(self.update_performance_table(metrics))
                    self.layout["right"].update(simulation_progress)

                    time.sleep(0.5)

            finally:
                self.performance_monitor.stop_monitoring()
```

### Enhanced Error Handling System

#### Contextual Error Messages
```python
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
import traceback

class ErrorCategory(Enum):
    """Error categorization for targeted troubleshooting"""
    CONFIGURATION = "configuration"
    DATABASE = "database"
    PERFORMANCE = "performance"
    DATA_QUALITY = "data_quality"
    SYSTEM_RESOURCE = "system_resource"
    INTEGRATION = "integration"

@dataclass
class ErrorContext:
    """Rich error context with troubleshooting guidance"""
    category: ErrorCategory
    message: str
    technical_details: str
    troubleshooting_steps: List[str]
    recovery_suggestions: List[str]
    related_docs: List[str]
    log_references: List[str]

class EnhancedErrorHandler:
    """Advanced error handling with contextual guidance"""

    def __init__(self):
        self.error_patterns = self._build_error_patterns()
        self.recovery_strategies = self._build_recovery_strategies()

    def _build_error_patterns(self) -> Dict[str, ErrorContext]:
        """Build comprehensive error pattern database"""
        return {
            "DuckDB.*locked": ErrorContext(
                category=ErrorCategory.DATABASE,
                message="Database is locked by another process",
                technical_details="DuckDB connection conflict detected",
                troubleshooting_steps=[
                    "1. Close any open database connections in IDE/tools",
                    "2. Check for running Dagster processes: ps aux | grep dagster",
                    "3. Verify no other simulation instances are running",
                    "4. Restart Dagster development server if necessary"
                ],
                recovery_suggestions=[
                    "Use 'pkill -f dagster' to terminate stuck processes",
                    "Remove .dagster/daemon.yaml if present",
                    "Consider using connection pooling for concurrent access"
                ],
                related_docs=[
                    "/docs/troubleshooting.md#database-locks",
                    "https://duckdb.org/docs/connect/concurrency"
                ],
                log_references=["dagster.log", "simulation.log"]
            ),

            "Memory.*exceeded": ErrorContext(
                category=ErrorCategory.SYSTEM_RESOURCE,
                message="Insufficient memory for simulation processing",
                technical_details="System memory exhausted during simulation",
                troubleshooting_steps=[
                    "1. Check available system memory: free -h",
                    "2. Review simulation configuration for large datasets",
                    "3. Consider reducing batch sizes or year range",
                    "4. Monitor memory usage during execution"
                ],
                recovery_suggestions=[
                    "Reduce simulation year range: --years 2024-2026",
                    "Enable chunked processing in configuration",
                    "Increase system swap space temporarily",
                    "Use memory-optimized processing profile: --profile performance"
                ],
                related_docs=[
                    "/docs/performance-tuning.md#memory-optimization",
                    "/config/simulation_config.yaml"
                ],
                log_references=["system.log", "performance.log"]
            )
        }

    def handle_error(self, error: Exception, context: Optional[str] = None) -> ErrorContext:
        """Process error with contextual guidance"""
        error_str = str(error)

        # Pattern matching for known errors
        for pattern, error_context in self.error_patterns.items():
            if pattern in error_str:
                return error_context

        # Generic error handling
        return ErrorContext(
            category=ErrorCategory.INTEGRATION,
            message=f"Unexpected error: {error_str}",
            technical_details=traceback.format_exc(),
            troubleshooting_steps=[
                "1. Check simulation logs for detailed error information",
                "2. Verify configuration file syntax and values",
                "3. Ensure all required dependencies are installed",
                "4. Try running with --verbose flag for more details"
            ],
            recovery_suggestions=[
                "Use --dry-run to validate configuration",
                "Check recent changes to configuration or data",
                "Consider reverting to last known working state"
            ],
            related_docs=["/docs/troubleshooting.md"],
            log_references=["simulation.log"]
        )

    def display_error_guidance(self, error_context: ErrorContext, console: Console):
        """Display comprehensive error guidance"""
        console.print(f"\n[bold red]Error: {error_context.message}[/bold red]")
        console.print(f"[yellow]Category: {error_context.category.value}[/yellow]\n")

        console.print("[bold blue]Troubleshooting Steps:[/bold blue]")
        for step in error_context.troubleshooting_steps:
            console.print(f"  {step}")

        console.print("\n[bold green]Recovery Suggestions:[/bold green]")
        for suggestion in error_context.recovery_suggestions:
            console.print(f"  • {suggestion}")

        if error_context.related_docs:
            console.print("\n[bold cyan]Related Documentation:[/bold cyan]")
            for doc in error_context.related_docs:
                console.print(f"  📖 {doc}")
```

### Progress Tracking and ETA System

#### Intelligent Progress Tracking
```python
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import statistics

@dataclass
class SimulationPhase:
    """Individual simulation phase tracking"""
    name: str
    total_steps: int
    completed_steps: int = 0
    start_time: Optional[datetime] = None
    completion_time: Optional[datetime] = None
    estimated_duration: Optional[timedelta] = None

    @property
    def progress_percentage(self) -> float:
        return (self.completed_steps / self.total_steps) * 100 if self.total_steps > 0 else 0

    @property
    def is_complete(self) -> bool:
        return self.completed_steps >= self.total_steps

class ETACalculator:
    """Intelligent ETA calculation with adaptive learning"""

    def __init__(self):
        self.phase_history: Dict[str, List[float]] = {}
        self.performance_factors = {
            'cpu_load': 1.0,
            'memory_pressure': 1.0,
            'io_contention': 1.0
        }

    def update_phase_history(self, phase_name: str, duration_seconds: float):
        """Update historical performance data"""
        if phase_name not in self.phase_history:
            self.phase_history[phase_name] = []
        self.phase_history[phase_name].append(duration_seconds)

        # Keep only recent history (last 10 runs)
        if len(self.phase_history[phase_name]) > 10:
            self.phase_history[phase_name] = self.phase_history[phase_name][-10:]

    def calculate_eta(self, phases: List[SimulationPhase],
                     current_metrics: PerformanceMetrics) -> timedelta:
        """Calculate adaptive ETA based on historical data and current performance"""
        total_remaining_seconds = 0

        for phase in phases:
            if phase.is_complete:
                continue

            remaining_steps = phase.total_steps - phase.completed_steps

            # Get historical average for this phase type
            if phase.name in self.phase_history and self.phase_history[phase.name]:
                avg_step_duration = statistics.mean(self.phase_history[phase.name]) / phase.total_steps
            else:
                # Fallback estimation based on phase type
                avg_step_duration = self._estimate_step_duration(phase.name)

            # Apply performance factor adjustments
            performance_factor = self._calculate_performance_factor(current_metrics)
            adjusted_duration = avg_step_duration * performance_factor

            phase_remaining_time = remaining_steps * adjusted_duration
            total_remaining_seconds += phase_remaining_time

        return timedelta(seconds=total_remaining_seconds)

    def _estimate_step_duration(self, phase_name: str) -> float:
        """Fallback step duration estimation"""
        duration_estimates = {
            'foundation_setup': 2.0,
            'year_processing': 15.0,
            'event_generation': 8.0,
            'coordination': 3.0,
            'finalization': 5.0
        }
        return duration_estimates.get(phase_name, 10.0)

    def _calculate_performance_factor(self, metrics: PerformanceMetrics) -> float:
        """Calculate performance adjustment factor"""
        factor = 1.0

        # CPU load factor
        if metrics.cpu_usage:
            avg_cpu = sum(metrics.cpu_usage[-5:]) / len(metrics.cpu_usage[-5:])
            if avg_cpu > 80:
                factor *= 1.3  # Slower when CPU is heavily loaded
            elif avg_cpu < 30:
                factor *= 0.8  # Faster when CPU is lightly loaded

        # Memory pressure factor
        if metrics.memory_usage:
            avg_memory = sum(metrics.memory_usage[-5:]) / len(metrics.memory_usage[-5:])
            if avg_memory > 85:
                factor *= 1.5  # Much slower when memory is constrained

        return factor

class ProgressTracker:
    """Comprehensive progress tracking with Rich UI"""

    def __init__(self, console: Console):
        self.console = console
        self.eta_calculator = ETACalculator()
        self.phases: List[SimulationPhase] = []
        self.overall_progress: Optional[Progress] = None

    def setup_phases(self, year_range: range) -> List[SimulationPhase]:
        """Setup simulation phases based on configuration"""
        self.phases = [
            SimulationPhase("Foundation Setup", 1),
            SimulationPhase("Year Processing", len(year_range)),
            SimulationPhase("Event Generation", len(year_range) * 4),  # 4 event types per year
            SimulationPhase("Multi-Year Coordination", 1),
            SimulationPhase("Finalization", 1)
        ]
        return self.phases

    def create_progress_display(self) -> Progress:
        """Create Rich progress display"""
        return Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            TextColumn("[cyan]ETA: {task.fields[eta]}"),
            console=self.console
        )

    def update_progress(self, phase_name: str, completed_steps: int,
                       performance_metrics: PerformanceMetrics):
        """Update progress with ETA calculation"""
        phase = next((p for p in self.phases if p.name == phase_name), None)
        if not phase:
            return

        phase.completed_steps = completed_steps

        # Calculate ETA
        eta = self.eta_calculator.calculate_eta(self.phases, performance_metrics)

        # Update progress display
        if self.overall_progress:
            self.overall_progress.update(phase_name, completed=completed_steps,
                                       eta=str(eta).split('.')[0])  # Remove microseconds
```

### Integration Architecture

#### Optimized Component Integration
```python
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

@runtime_checkable
class OptimizedComponent(Protocol):
    """Protocol for optimized simulation components"""

    def initialize(self, config: Dict) -> bool:
        """Initialize component with configuration"""
        ...

    def process(self, data: Any) -> Any:
        """Process data through component"""
        ...

    def get_metrics(self) -> Dict[str, Any]:
        """Return component performance metrics"""
        ...

    def cleanup(self) -> None:
        """Cleanup component resources"""
        ...

class IntegratedCLIOrchestrator:
    """Main orchestrator integrating all optimized components"""

    def __init__(self, config: CLIConfig):
        self.config = config
        self.components: Dict[str, OptimizedComponent] = {}
        self.performance_monitor = PerformanceMonitor()
        self.progress_tracker = ProgressTracker(Console())
        self.error_handler = EnhancedErrorHandler()

    def register_component(self, name: str, component: OptimizedComponent):
        """Register optimized component"""
        self.components[name] = component

    async def execute_simulation(self) -> Dict[str, Any]:
        """Execute integrated multi-year simulation"""
        console = Console()

        try:
            # Initialize all components
            await self._initialize_components()

            # Setup progress tracking
            year_range = range(self.config.start_year, self.config.end_year + 1)
            phases = self.progress_tracker.setup_phases(year_range)

            # Start monitoring
            self.performance_monitor.start_monitoring()

            with self.progress_tracker.create_progress_display() as progress:
                # Execute simulation phases
                results = await self._execute_phases(phases, progress)

                # Generate optimization recommendations
                recommendations = await self._generate_optimization_recommendations()

                return {
                    'results': results,
                    'performance_metrics': self.performance_monitor.metrics,
                    'optimization_recommendations': recommendations
                }

        except Exception as e:
            error_context = self.error_handler.handle_error(e)
            self.error_handler.display_error_guidance(error_context, console)
            raise

        finally:
            self.performance_monitor.stop_monitoring()
            await self._cleanup_components()

    async def _initialize_components(self):
        """Initialize all registered components"""
        for name, component in self.components.items():
            if not component.initialize(self.config.__dict__):
                raise RuntimeError(f"Failed to initialize component: {name}")

    async def _execute_phases(self, phases: List[SimulationPhase],
                            progress: Progress) -> Dict[str, Any]:
        """Execute simulation phases with progress tracking"""
        results = {}

        for phase in phases:
            phase_task = progress.add_task(phase.name, total=phase.total_steps, eta="Calculating...")
            phase.start_time = datetime.now()

            try:
                # Execute phase through appropriate component
                phase_results = await self._execute_phase(phase, progress, phase_task)
                results[phase.name] = phase_results

                phase.completion_time = datetime.now()
                phase.completed_steps = phase.total_steps

            except Exception as e:
                progress.update(phase_task, description=f"[red]{phase.name} - ERROR")
                raise

        return results

    async def _generate_optimization_recommendations(self) -> List[str]:
        """Generate actionable optimization recommendations"""
        recommendations = []
        metrics = self.performance_monitor.metrics

        # CPU optimization recommendations
        if metrics.cpu_usage and max(metrics.cpu_usage) > 90:
            recommendations.append(
                "Consider enabling parallel processing: --optimization-level 2"
            )

        # Memory optimization recommendations
        if metrics.memory_usage and max(metrics.memory_usage) > 85:
            recommendations.append(
                "Enable memory optimization: add 'memory_optimization: true' to config"
            )

        # Performance profile recommendations
        year_times = metrics.year_processing_times
        if year_times and statistics.mean(year_times) > 60:
            recommendations.append(
                "Slow year processing detected. Consider using --profile performance"
            )

        return recommendations
```

### Optimization Recommendation Engine

#### Runtime Analysis and Recommendations
```python
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
import statistics

@dataclass
class OptimizationRecommendation:
    """Actionable optimization recommendation"""
    category: str
    priority: str  # high, medium, low
    title: str
    description: str
    implementation: str
    expected_improvement: str
    effort_level: str  # low, medium, high

class OptimizationEngine:
    """Analyze runtime performance and generate optimization recommendations"""

    def __init__(self):
        self.analysis_rules = self._build_analysis_rules()

    def _build_analysis_rules(self) -> List[Callable]:
        """Build comprehensive analysis rule set"""
        return [
            self._analyze_cpu_utilization,
            self._analyze_memory_patterns,
            self._analyze_io_bottlenecks,
            self._analyze_database_performance,
            self._analyze_year_processing_efficiency,
            self._analyze_event_generation_patterns
        ]

    def analyze_performance(self, metrics: PerformanceMetrics,
                          simulation_config: Dict[str, Any]) -> List[OptimizationRecommendation]:
        """Generate comprehensive optimization recommendations"""
        recommendations = []

        for rule in self.analysis_rules:
            rule_recommendations = rule(metrics, simulation_config)
            recommendations.extend(rule_recommendations)

        # Sort by priority and expected improvement
        return sorted(recommendations,
                     key=lambda r: (r.priority == 'high', r.expected_improvement),
                     reverse=True)

    def _analyze_cpu_utilization(self, metrics: PerformanceMetrics,
                               config: Dict[str, Any]) -> List[OptimizationRecommendation]:
        """Analyze CPU usage patterns"""
        recommendations = []

        if not metrics.cpu_usage:
            return recommendations

        avg_cpu = statistics.mean(metrics.cpu_usage)
        max_cpu = max(metrics.cpu_usage)

        if max_cpu > 95:
            recommendations.append(OptimizationRecommendation(
                category="CPU",
                priority="high",
                title="CPU Saturation Detected",
                description=f"CPU usage peaked at {max_cpu:.1f}%, indicating potential bottleneck",
                implementation="Enable parallel processing: --optimization-level 2 or add 'parallel_workers: 4' to config",
                expected_improvement="30-50% performance improvement",
                effort_level="low"
            ))
        elif avg_cpu < 30:
            recommendations.append(OptimizationRecommendation(
                category="CPU",
                priority="medium",
                title="CPU Underutilization",
                description=f"Average CPU usage only {avg_cpu:.1f}%, suggesting single-threaded bottleneck",
                implementation="Consider increasing batch sizes or enabling more aggressive parallel processing",
                expected_improvement="20-40% faster execution",
                effort_level="medium"
            ))

        return recommendations

    def _analyze_memory_patterns(self, metrics: PerformanceMetrics,
                               config: Dict[str, Any]) -> List[OptimizationRecommendation]:
        """Analyze memory usage patterns"""
        recommendations = []

        if not metrics.memory_usage:
            return recommendations

        peak_memory = max(metrics.memory_usage)

        if peak_memory > 90:
            recommendations.append(OptimizationRecommendation(
                category="Memory",
                priority="high",
                title="Memory Pressure Critical",
                description=f"Memory usage peaked at {peak_memory:.1f}%, risking system instability",
                implementation="Reduce year range, enable chunked processing, or add 'memory_limit_mb: 8192' to config",
                expected_improvement="Prevent system crashes and swapping",
                effort_level="low"
            ))
        elif peak_memory > 75:
            recommendations.append(OptimizationRecommendation(
                category="Memory",
                priority="medium",
                title="High Memory Usage",
                description=f"Memory usage reached {peak_memory:.1f}%, may benefit from optimization",
                implementation="Enable streaming processing: 'streaming_mode: true' in config",
                expected_improvement="Reduce memory footprint by 40-60%",
                effort_level="medium"
            ))

        return recommendations

    def _analyze_database_performance(self, metrics: PerformanceMetrics,
                                    config: Dict[str, Any]) -> List[OptimizationRecommendation]:
        """Analyze database operation patterns"""
        recommendations = []

        if metrics.database_operations:
            total_ops = sum(metrics.database_operations.values())
            if total_ops > 10000:
                recommendations.append(OptimizationRecommendation(
                    category="Database",
                    priority="medium",
                    title="High Database Operation Count",
                    description=f"Detected {total_ops} database operations, suggesting potential for batching",
                    implementation="Enable batch operations: 'batch_size: 1000' in database config",
                    expected_improvement="50-70% reduction in database round-trips",
                    effort_level="low"
                ))

        return recommendations

    def generate_optimization_report(self, recommendations: List[OptimizationRecommendation],
                                   console: Console):
        """Generate comprehensive optimization report"""
        if not recommendations:
            console.print("[green]✅ No optimization opportunities identified - performance is optimal![/green]")
            return

        console.print("\n[bold cyan]🚀 Performance Optimization Recommendations[/bold cyan]\n")

        # Group by priority
        high_priority = [r for r in recommendations if r.priority == 'high']
        medium_priority = [r for r in recommendations if r.priority == 'medium']
        low_priority = [r for r in recommendations if r.priority == 'low']

        for priority_group, recommendations_group in [
            ("🔴 High Priority", high_priority),
            ("🟡 Medium Priority", medium_priority),
            ("🟢 Low Priority", low_priority)
        ]:
            if not recommendations_group:
                continue

            console.print(f"[bold]{priority_group}[/bold]")

            for i, rec in enumerate(recommendations_group, 1):
                console.print(f"\n{i}. [bold]{rec.title}[/bold] ({rec.category})")
                console.print(f"   📋 {rec.description}")
                console.print(f"   🛠️  Implementation: {rec.implementation}")
                console.print(f"   📈 Expected improvement: {rec.expected_improvement}")
                console.print(f"   ⚡ Effort level: {rec.effort_level}")

        console.print("\n[bold blue]💡 Next Steps:[/bold blue]")
        console.print("1. Implement high-priority recommendations first")
        console.print("2. Test changes with --dry-run before full simulation")
        console.print("3. Monitor performance improvements with --profile performance")
        console.print("4. Refer to /docs/performance-tuning.md for detailed guidance")
```

## Definition of Done

- [ ] CLI entry point `orchestrator_dbt/run_multi_year.py` functional with comprehensive argument parsing
- [ ] Performance monitoring dashboard operational with real-time metrics and bottleneck identification
- [ ] Enhanced error handling providing contextual troubleshooting guidance and recovery suggestions
- [ ] Progress tracking with intelligent ETA calculations based on historical performance data
- [ ] Optimization recommendation engine providing actionable insights based on runtime analysis
- [ ] Unit tests covering CLI functionality, error handling, and optimization recommendations
- [ ] Integration tests validating CLI with full multi-year simulation workflow
- [ ] Performance benchmarks demonstrating CLI overhead is <5% of total simulation time

## Technical Notes

### Performance Baseline
- **Current**: Basic CLI with minimal feedback and error reporting
- **Target**: Rich CLI with real-time monitoring, performance insights, and optimization guidance
- **Features**: Progress tracking, bottleneck identification, ETA calculations, troubleshooting guidance

### Architecture Considerations
- Modern CLI interface maintaining backward compatibility with existing scripts
- Real-time performance monitoring with configurable overhead (0.5-2% CPU impact)
- Enhanced error handling with pattern matching and contextual troubleshooting guidance
- Progress tracking with adaptive ETA calculations based on historical performance data
- Optimization recommendation engine with rule-based analysis and actionable suggestions
- Integration architecture supporting hot-swappable optimized components

### CLI Performance Requirements
- Startup time: <2 seconds
- Memory overhead: <50MB additional
- Real-time update frequency: 2Hz (0.5 second intervals)
- Error pattern matching: <100ms response time
- ETA calculation: <50ms update time

## Testing Strategy

- [ ] Unit tests for CLI argument parsing and validation
- [ ] Error handling and recovery scenario tests with mock error injection
- [ ] Performance monitoring accuracy tests with known workload patterns
- [ ] Progress tracking and ETA calculation tests with simulated phase execution
- [ ] Optimization recommendation tests with controlled performance scenarios
- [ ] Integration tests with full multi-year simulation workflow validation
- [ ] Load testing to ensure CLI scales with simulation complexity
- [ ] User experience testing with different terminal environments

## Dependencies

- ✅ Foundation integration system (S031-01)
- ✅ Year processing optimization (S031-02)
- ✅ Event generation performance (S031-03)
- ✅ Multi-year coordination (S031-04)

## Risks & Mitigation

- **Risk**: CLI complexity reduces usability
  - **Mitigation**: Maintain simple default behavior with progressive disclosure of advanced features
- **Risk**: Performance monitoring overhead impacts simulation performance
  - **Mitigation**: Lightweight monitoring with configurable detail levels and sampling rates
- **Risk**: Error handling masks underlying issues
  - **Mitigation**: Comprehensive logging with debug modes and technical detail preservation
- **Risk**: ETA calculations become inaccurate under varying system loads
  - **Mitigation**: Adaptive algorithms with performance factor adjustments and confidence intervals
- **Risk**: Optimization recommendations lead to configuration complexity
  - **Mitigation**: Provide implementation examples and automated configuration assistance
