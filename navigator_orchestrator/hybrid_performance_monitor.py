#!/usr/bin/env python3
"""
Hybrid Pipeline Performance Monitor for E068G

Monitors and compares performance between SQL and Polars event generation modes,
providing detailed metrics and recommendations for optimal mode selection.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import psutil


@dataclass
class EventGenerationMetrics:
    """Performance metrics for event generation modes."""
    mode: str  # 'sql' or 'polars'
    start_time: float
    end_time: float
    execution_time: float
    total_events: int
    years_processed: List[int]
    memory_usage_mb: float
    cpu_usage_percent: float
    events_per_second: float
    peak_memory_mb: float
    fallback_used: bool = False
    error_count: int = 0
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            'mode': self.mode,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'execution_time': self.execution_time,
            'total_events': self.total_events,
            'years_processed': self.years_processed,
            'memory_usage_mb': self.memory_usage_mb,
            'cpu_usage_percent': self.cpu_usage_percent,
            'events_per_second': self.events_per_second,
            'peak_memory_mb': self.peak_memory_mb,
            'fallback_used': self.fallback_used,
            'error_count': self.error_count,
            'success': self.success,
            'timestamp': datetime.fromtimestamp(self.start_time).isoformat()
        }


@dataclass
class PerformanceComparison:
    """Performance comparison between SQL and Polars modes."""
    sql_metrics: Optional[EventGenerationMetrics] = None
    polars_metrics: Optional[EventGenerationMetrics] = None
    speedup_factor: Optional[float] = None
    memory_efficiency: Optional[float] = None
    recommendation: str = ""
    comparison_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def calculate_comparison(self) -> None:
        """Calculate performance comparison metrics."""
        if not self.sql_metrics or not self.polars_metrics:
            self.recommendation = "Insufficient data for comparison"
            return

        if not self.sql_metrics.success or not self.polars_metrics.success:
            self.recommendation = "One or both modes failed - cannot compare"
            return

        # Calculate speedup factor (positive means Polars is faster)
        if self.sql_metrics.execution_time > 0:
            self.speedup_factor = self.sql_metrics.execution_time / self.polars_metrics.execution_time

        # Calculate memory efficiency (positive means Polars uses less memory)
        if self.polars_metrics.peak_memory_mb > 0:
            self.memory_efficiency = self.sql_metrics.peak_memory_mb / self.polars_metrics.peak_memory_mb

        # Generate recommendation
        self._generate_recommendation()

    def _generate_recommendation(self) -> None:
        """Generate performance-based recommendation."""
        recommendations = []

        # Performance recommendation
        if self.speedup_factor and self.speedup_factor > 2.0:
            recommendations.append(f"Polars is {self.speedup_factor:.1f}x faster - strongly recommend Polars mode")
        elif self.speedup_factor and self.speedup_factor > 1.5:
            recommendations.append(f"Polars is {self.speedup_factor:.1f}x faster - recommend Polars mode")
        elif self.speedup_factor and self.speedup_factor < 0.8:
            recommendations.append("SQL mode is faster - recommend SQL mode for this dataset size")
        else:
            recommendations.append("Performance is similar between modes")

        # Memory recommendation
        if self.memory_efficiency and self.memory_efficiency > 1.3:
            recommendations.append("Polars is more memory efficient")
        elif self.memory_efficiency and self.memory_efficiency < 0.8:
            recommendations.append("SQL mode is more memory efficient")

        # Reliability recommendation
        if self.polars_metrics and self.polars_metrics.fallback_used:
            recommendations.append("Polars mode required fallback - SQL mode may be more reliable")

        self.recommendation = "; ".join(recommendations)

    def to_dict(self) -> Dict[str, Any]:
        """Convert comparison to dictionary for JSON serialization."""
        return {
            'sql_metrics': self.sql_metrics.to_dict() if self.sql_metrics else None,
            'polars_metrics': self.polars_metrics.to_dict() if self.polars_metrics else None,
            'speedup_factor': self.speedup_factor,
            'memory_efficiency': self.memory_efficiency,
            'recommendation': self.recommendation,
            'comparison_timestamp': self.comparison_timestamp
        }


class HybridPerformanceMonitor:
    """
    Performance monitor for hybrid SQL/Polars event generation pipeline.

    Tracks performance metrics for both modes and provides comparative
    analysis to help optimize event generation performance.
    """

    def __init__(self, reports_dir: Path = Path("reports/hybrid_performance")):
        """Initialize hybrid performance monitor."""
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(__name__)
        self.metrics_history: List[EventGenerationMetrics] = []
        self.comparisons_history: List[PerformanceComparison] = []

        # Current monitoring session
        self._current_session_start: Optional[float] = None
        self._baseline_memory_mb: Optional[float] = None
        self._peak_memory_mb: float = 0.0

    def start_monitoring_session(self) -> None:
        """Start a new monitoring session."""
        self._current_session_start = time.time()
        self._baseline_memory_mb = self._get_memory_usage_mb()
        self._peak_memory_mb = self._baseline_memory_mb

        self.logger.info("Started hybrid performance monitoring session")

    def start_event_generation_monitoring(self, mode: str, years: List[int]) -> Dict[str, Any]:
        """
        Start monitoring event generation for a specific mode.

        Returns monitoring context that should be passed to end_monitoring.
        """
        context = {
            'mode': mode,
            'start_time': time.time(),
            'years': years,
            'start_memory_mb': self._get_memory_usage_mb(),
            'start_cpu_percent': self._get_cpu_usage_percent()
        }

        self.logger.info(f"Started monitoring {mode.upper()} event generation for years {years}")
        return context

    def end_event_generation_monitoring(
        self,
        context: Dict[str, Any],
        total_events: int,
        success: bool = True,
        fallback_used: bool = False,
        error_count: int = 0
    ) -> EventGenerationMetrics:
        """
        End monitoring for event generation and calculate metrics.

        Args:
            context: Monitoring context from start_event_generation_monitoring
            total_events: Total number of events generated
            success: Whether event generation succeeded
            fallback_used: Whether fallback mode was used
            error_count: Number of errors encountered

        Returns:
            EventGenerationMetrics object with performance data
        """
        end_time = time.time()
        execution_time = end_time - context['start_time']
        current_memory_mb = self._get_memory_usage_mb()

        # Update peak memory
        if current_memory_mb > self._peak_memory_mb:
            self._peak_memory_mb = current_memory_mb

        # Calculate events per second
        events_per_second = total_events / execution_time if execution_time > 0 else 0

        metrics = EventGenerationMetrics(
            mode=context['mode'],
            start_time=context['start_time'],
            end_time=end_time,
            execution_time=execution_time,
            total_events=total_events,
            years_processed=context['years'],
            memory_usage_mb=current_memory_mb,
            cpu_usage_percent=self._get_cpu_usage_percent(),
            events_per_second=events_per_second,
            peak_memory_mb=self._peak_memory_mb,
            fallback_used=fallback_used,
            error_count=error_count,
            success=success
        )

        self.metrics_history.append(metrics)

        self.logger.info(
            f"Completed monitoring {context['mode'].upper()} event generation: "
            f"{total_events:,} events in {execution_time:.1f}s "
            f"({events_per_second:.0f} events/sec)"
        )

        return metrics

    def compare_modes(
        self,
        sql_metrics: Optional[EventGenerationMetrics] = None,
        polars_metrics: Optional[EventGenerationMetrics] = None
    ) -> PerformanceComparison:
        """
        Compare performance between SQL and Polars modes.

        If metrics are not provided, uses the most recent metrics from history.
        """
        if not sql_metrics:
            sql_metrics = self._get_latest_metrics_by_mode('sql')

        if not polars_metrics:
            polars_metrics = self._get_latest_metrics_by_mode('polars')

        comparison = PerformanceComparison(
            sql_metrics=sql_metrics,
            polars_metrics=polars_metrics
        )
        comparison.calculate_comparison()

        self.comparisons_history.append(comparison)

        return comparison

    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        report = {
            'session_info': {
                'session_start': self._current_session_start,
                'session_duration': time.time() - self._current_session_start if self._current_session_start else 0,
                'total_runs': len(self.metrics_history),
                'generated_at': datetime.now().isoformat()
            },
            'metrics_history': [m.to_dict() for m in self.metrics_history],
            'comparisons': [c.to_dict() for c in self.comparisons_history],
            'summary': self._generate_summary(),
            'recommendations': self._generate_recommendations()
        }

        return report

    def save_performance_report(self, filename: Optional[str] = None) -> Path:
        """Save performance report to JSON file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"hybrid_performance_report_{timestamp}.json"

        report_path = self.reports_dir / filename
        report = self.generate_performance_report()

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        self.logger.info(f"Performance report saved to: {report_path}")
        return report_path

    def display_performance_summary(self) -> None:
        """Display performance summary to console."""
        if not self.metrics_history:
            print("No performance metrics available")
            return

        print("\n" + "="*60)
        print("HYBRID PIPELINE PERFORMANCE SUMMARY")
        print("="*60)

        # Group metrics by mode
        sql_metrics = [m for m in self.metrics_history if m.mode == 'sql']
        polars_metrics = [m for m in self.metrics_history if m.mode == 'polars']

        if sql_metrics:
            latest_sql = sql_metrics[-1]
            print(f"SQL Mode Performance:")
            print(f"  Execution Time: {latest_sql.execution_time:.1f}s")
            print(f"  Total Events: {latest_sql.total_events:,}")
            print(f"  Events/Second: {latest_sql.events_per_second:.0f}")
            print(f"  Peak Memory: {latest_sql.peak_memory_mb:.1f}MB")

        if polars_metrics:
            latest_polars = polars_metrics[-1]
            print(f"Polars Mode Performance:")
            print(f"  Execution Time: {latest_polars.execution_time:.1f}s")
            print(f"  Total Events: {latest_polars.total_events:,}")
            print(f"  Events/Second: {latest_polars.events_per_second:.0f}")
            print(f"  Peak Memory: {latest_polars.peak_memory_mb:.1f}MB")
            if latest_polars.fallback_used:
                print(f"  ⚠️  Fallback was used")

        # Show latest comparison
        if self.comparisons_history:
            latest_comparison = self.comparisons_history[-1]
            if latest_comparison.speedup_factor:
                if latest_comparison.speedup_factor > 1:
                    print(f"\n⚡ Polars is {latest_comparison.speedup_factor:.1f}x faster than SQL")
                else:
                    print(f"\n⚡ SQL is {1/latest_comparison.speedup_factor:.1f}x faster than Polars")

            if latest_comparison.recommendation:
                print(f"💡 Recommendation: {latest_comparison.recommendation}")

        print("="*60)

    def _get_latest_metrics_by_mode(self, mode: str) -> Optional[EventGenerationMetrics]:
        """Get the latest metrics for a specific mode."""
        mode_metrics = [m for m in self.metrics_history if m.mode == mode]
        return mode_metrics[-1] if mode_metrics else None

    def _get_memory_usage_mb(self) -> float:
        """Get current memory usage in MB."""
        try:
            process = psutil.Process()
            return process.memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0

    def _get_cpu_usage_percent(self) -> float:
        """Get current CPU usage percentage."""
        try:
            return psutil.cpu_percent(interval=0.1)
        except Exception:
            return 0.0

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate performance summary statistics."""
        summary = {
            'total_runs': len(self.metrics_history),
            'sql_runs': len([m for m in self.metrics_history if m.mode == 'sql']),
            'polars_runs': len([m for m in self.metrics_history if m.mode == 'polars']),
            'successful_runs': len([m for m in self.metrics_history if m.success]),
            'fallback_runs': len([m for m in self.metrics_history if m.fallback_used])
        }

        if self.metrics_history:
            # Calculate averages
            successful_metrics = [m for m in self.metrics_history if m.success]
            if successful_metrics:
                total_events = sum(m.total_events for m in successful_metrics)
                total_time = sum(m.execution_time for m in successful_metrics)

                summary.update({
                    'total_events_generated': total_events,
                    'total_execution_time': total_time,
                    'average_events_per_second': total_events / total_time if total_time > 0 else 0,
                    'average_memory_usage_mb': sum(m.memory_usage_mb for m in successful_metrics) / len(successful_metrics)
                })

        return summary

    def _generate_recommendations(self) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []

        if not self.metrics_history:
            return ["No performance data available for recommendations"]

        # Analyze mode performance
        sql_metrics = [m for m in self.metrics_history if m.mode == 'sql' and m.success]
        polars_metrics = [m for m in self.metrics_history if m.mode == 'polars' and m.success]

        if sql_metrics and polars_metrics:
            avg_sql_time = sum(m.execution_time for m in sql_metrics) / len(sql_metrics)
            avg_polars_time = sum(m.execution_time for m in polars_metrics) / len(polars_metrics)

            if avg_polars_time < avg_sql_time * 0.5:
                recommendations.append("Polars mode shows significant performance advantages - recommend as primary mode")
            elif avg_polars_time < avg_sql_time * 0.8:
                recommendations.append("Polars mode shows moderate performance improvements - consider as primary mode")

        # Memory usage analysis
        high_memory_runs = [m for m in self.metrics_history if m.peak_memory_mb > 4000]  # >4GB
        if high_memory_runs:
            recommendations.append("High memory usage detected - consider batch size optimization or memory limits")

        # Fallback usage analysis
        fallback_runs = [m for m in self.metrics_history if m.fallback_used]
        if fallback_runs:
            recommendations.append("Fallback mode was used - investigate Polars mode reliability issues")

        # Performance target analysis (60s target from Epic E068G)
        long_runs = [m for m in self.metrics_history if m.execution_time > 60]
        if long_runs:
            recommendations.append("Some runs exceeded 60s target - consider optimization or mode switching")

        return recommendations if recommendations else ["Performance is within acceptable ranges"]
