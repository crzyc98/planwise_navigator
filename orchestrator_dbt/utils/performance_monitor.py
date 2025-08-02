"""
Performance monitoring utilities for orchestrator_dbt.

Provides comprehensive performance tracking, timing analysis, and
optimization recommendations for dbt workflow execution.
"""

from __future__ import annotations

import time
import logging
from typing import Dict, Any, List, Optional, NamedTuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import json


logger = logging.getLogger(__name__)


class PerformanceMetric(NamedTuple):
    """Individual performance metric."""
    name: str
    value: float
    unit: str
    timestamp: float
    context: Dict[str, Any] = {}


@dataclass
class ExecutionProfile:
    """Profile of execution performance."""
    operation_name: str
    start_time: float
    end_time: float
    execution_time: float
    success: bool
    metrics: List[PerformanceMetric] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_str(self) -> str:
        """Human-readable duration string."""
        if self.execution_time < 1:
            return f"{self.execution_time * 1000:.0f}ms"
        elif self.execution_time < 60:
            return f"{self.execution_time:.2f}s"
        else:
            minutes = int(self.execution_time // 60)
            seconds = self.execution_time % 60
            return f"{minutes}m {seconds:.1f}s"


@dataclass
class PerformanceReport:
    """Comprehensive performance analysis report."""
    total_execution_time: float
    total_operations: int
    successful_operations: int
    failed_operations: int
    profiles: List[ExecutionProfile] = field(default_factory=list)
    bottlenecks: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_operations == 0:
            return 100.0
        return (self.successful_operations / self.total_operations) * 100.0

    @property
    def average_execution_time(self) -> float:
        """Calculate average execution time."""
        if self.total_operations == 0:
            return 0.0
        return self.total_execution_time / self.total_operations


class PerformanceMonitor:
    """
    Performance monitoring and analysis for dbt workflow operations.

    Provides comprehensive tracking of execution times, success rates,
    bottleneck identification, and optimization recommendations.
    """

    def __init__(self, enable_detailed_tracking: bool = True):
        """
        Initialize performance monitor.

        Args:
            enable_detailed_tracking: Whether to enable detailed metric collection
        """
        self.enable_detailed_tracking = enable_detailed_tracking
        self.profiles: List[ExecutionProfile] = []
        self.session_start = time.time()

        logger.info(f"Performance monitor initialized (detailed_tracking={enable_detailed_tracking})")

    def start_operation(self, operation_name: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Start tracking an operation.

        Args:
            operation_name: Name of the operation
            context: Additional context information

        Returns:
            Operation ID for tracking
        """
        operation_id = f"{operation_name}_{len(self.profiles)}"
        start_time = time.time()

        profile = ExecutionProfile(
            operation_name=operation_name,
            start_time=start_time,
            end_time=0.0,
            execution_time=0.0,
            success=False,
            context=context or {}
        )

        self.profiles.append(profile)

        if self.enable_detailed_tracking:
            logger.debug(f"Started tracking operation: {operation_name} (ID: {operation_id})")

        return operation_id

    def end_operation(self, operation_id: str, success: bool, additional_context: Optional[Dict[str, Any]] = None) -> ExecutionProfile:
        """
        End tracking an operation.

        Args:
            operation_id: Operation ID from start_operation
            success: Whether the operation succeeded
            additional_context: Additional context to add

        Returns:
            ExecutionProfile with complete timing information
        """
        try:
            # Find the profile by extracting index from operation_id
            profile_index = int(operation_id.split('_')[-1])
            profile = self.profiles[profile_index]

            end_time = time.time()
            profile.end_time = end_time
            profile.execution_time = end_time - profile.start_time
            profile.success = success

            if additional_context:
                profile.context.update(additional_context)

            if self.enable_detailed_tracking:
                logger.debug(f"Completed operation: {profile.operation_name} in {profile.duration_str} ({'✅' if success else '❌'})")

            return profile

        except (ValueError, IndexError) as e:
            logger.warning(f"Could not find operation profile for ID {operation_id}: {e}")
            # Return a dummy profile
            return ExecutionProfile(
                operation_name="unknown",
                start_time=time.time(),
                end_time=time.time(),
                execution_time=0.0,
                success=success
            )

    def add_metric(self, operation_id: str, metric_name: str, value: float, unit: str = "", context: Optional[Dict[str, Any]] = None):
        """
        Add a performance metric to an operation.

        Args:
            operation_id: Operation ID
            metric_name: Name of the metric
            value: Metric value
            unit: Unit of measurement
            context: Additional context
        """
        try:
            profile_index = int(operation_id.split('_')[-1])
            profile = self.profiles[profile_index]

            metric = PerformanceMetric(
                name=metric_name,
                value=value,
                unit=unit,
                timestamp=time.time(),
                context=context or {}
            )

            profile.metrics.append(metric)

            if self.enable_detailed_tracking:
                logger.debug(f"Added metric to {profile.operation_name}: {metric_name}={value}{unit}")

        except (ValueError, IndexError) as e:
            logger.warning(f"Could not add metric to operation {operation_id}: {e}")

    def generate_report(self) -> PerformanceReport:
        """
        Generate comprehensive performance report.

        Returns:
            PerformanceReport with analysis and recommendations
        """
        total_time = sum(p.execution_time for p in self.profiles)
        successful_ops = [p for p in self.profiles if p.success]
        failed_ops = [p for p in self.profiles if not p.success]

        report = PerformanceReport(
            total_execution_time=total_time,
            total_operations=len(self.profiles),
            successful_operations=len(successful_ops),
            failed_operations=len(failed_ops),
            profiles=self.profiles.copy()
        )

        # Identify bottlenecks
        report.bottlenecks = self._identify_bottlenecks()

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        return report

    def _identify_bottlenecks(self) -> List[Dict[str, Any]]:
        """
        Identify performance bottlenecks.

        Returns:
            List of bottleneck analyses
        """
        bottlenecks = []

        if not self.profiles:
            return bottlenecks

        # Sort by execution time
        sorted_profiles = sorted(self.profiles, key=lambda p: p.execution_time, reverse=True)
        total_time = sum(p.execution_time for p in self.profiles)

        # Identify operations taking >20% of total time
        for profile in sorted_profiles[:3]:  # Top 3 slowest
            percentage = (profile.execution_time / total_time * 100) if total_time > 0 else 0

            if percentage > 20:
                bottlenecks.append({
                    "operation": profile.operation_name,
                    "execution_time": profile.execution_time,
                    "percentage_of_total": percentage,
                    "success": profile.success,
                    "recommendations": self._get_operation_recommendations(profile)
                })

        # Identify failed operations
        failed_profiles = [p for p in self.profiles if not p.success]
        for profile in failed_profiles:
            bottlenecks.append({
                "operation": profile.operation_name,
                "execution_time": profile.execution_time,
                "percentage_of_total": (profile.execution_time / total_time * 100) if total_time > 0 else 0,
                "success": profile.success,
                "issue_type": "failure",
                "recommendations": ["Investigate failure cause", "Implement retry logic", "Check error logs"]
            })

        return bottlenecks

    def _get_operation_recommendations(self, profile: ExecutionProfile) -> List[str]:
        """
        Get recommendations for a specific operation.

        Args:
            profile: ExecutionProfile to analyze

        Returns:
            List of recommendations
        """
        recommendations = []

        if profile.operation_name.startswith("load_seed"):
            if profile.execution_time > 5:
                recommendations.extend([
                    "Consider using batch seed loading",
                    "Enable concurrent seed processing",
                    "Check for large CSV files that could be optimized"
                ])

        elif profile.operation_name.startswith("run_staging"):
            if profile.execution_time > 10:
                recommendations.extend([
                    "Consider using batch model execution",
                    "Enable concurrent model processing",
                    "Review model dependencies for parallelization opportunities"
                ])

        elif profile.operation_name.startswith("run_") and profile.execution_time > 3:
            recommendations.extend([
                "Consider batch execution",
                "Review for parallelization opportunities",
                "Check for unnecessary data processing"
            ])

        if profile.execution_time > 30:
            recommendations.append("Consider breaking down into smaller operations")

        return recommendations

    def _generate_recommendations(self, report: PerformanceReport) -> List[str]:
        """
        Generate overall optimization recommendations.

        Args:
            report: PerformanceReport to analyze

        Returns:
            List of recommendations
        """
        recommendations = []

        # Success rate recommendations
        if report.success_rate < 95:
            recommendations.append(f"Success rate is {report.success_rate:.1f}% - implement better error handling and retry logic")

        # Performance recommendations
        if report.total_execution_time > 60:
            recommendations.append("Total execution time exceeds 1 minute - consider optimizations")

        if report.total_execution_time > 30:
            recommendations.extend([
                "Enable concurrent execution where possible",
                "Use batch operations instead of individual commands",
                "Consider connection pooling and reuse"
            ])

        # Operation-specific recommendations
        seed_operations = [p for p in report.profiles if "seed" in p.operation_name.lower()]
        if len(seed_operations) > 5:
            recommendations.append("Multiple seed operations detected - use batch seed loading")

        model_operations = [p for p in report.profiles if "model" in p.operation_name.lower()]
        if len(model_operations) > 3:
            recommendations.append("Multiple model operations detected - use batch model execution")

        # Bottleneck-based recommendations
        if report.bottlenecks:
            recommendations.append(f"Address {len(report.bottlenecks)} identified bottlenecks")

        return list(set(recommendations))  # Remove duplicates

    def save_report(self, report: PerformanceReport, filepath: Path) -> None:
        """
        Save performance report to file.

        Args:
            report: PerformanceReport to save
            filepath: Path to save report
        """
        try:
            # Convert to serializable format
            report_data = {
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total_execution_time": report.total_execution_time,
                    "total_operations": report.total_operations,
                    "successful_operations": report.successful_operations,
                    "failed_operations": report.failed_operations,
                    "success_rate": report.success_rate,
                    "average_execution_time": report.average_execution_time
                },
                "profiles": [
                    {
                        "operation_name": p.operation_name,
                        "execution_time": p.execution_time,
                        "success": p.success,
                        "context": p.context,
                        "metrics": [
                            {
                                "name": m.name,
                                "value": m.value,
                                "unit": m.unit,
                                "timestamp": m.timestamp,
                                "context": m.context
                            }
                            for m in p.metrics
                        ]
                    }
                    for p in report.profiles
                ],
                "bottlenecks": report.bottlenecks,
                "recommendations": report.recommendations
            }

            with open(filepath, 'w') as f:
                json.dump(report_data, f, indent=2)

            logger.info(f"Performance report saved to {filepath}")

        except Exception as e:
            logger.error(f"Failed to save performance report: {e}")

    def print_summary(self, report: Optional[PerformanceReport] = None) -> None:
        """
        Print performance summary to console.

        Args:
            report: PerformanceReport to print (generates new one if not provided)
        """
        if report is None:
            report = self.generate_report()

        print("\n" + "=" * 60)
        print("🔍 PERFORMANCE ANALYSIS SUMMARY")
        print("=" * 60)

        print(f"📊 Overall Performance:")
        print(f"   Total execution time: {report.total_execution_time:.2f}s")
        print(f"   Total operations: {report.total_operations}")
        print(f"   Success rate: {report.success_rate:.1f}%")
        print(f"   Average operation time: {report.average_execution_time:.2f}s")

        if report.profiles:
            print(f"\n⏱️  Operation Breakdown:")
            sorted_profiles = sorted(report.profiles, key=lambda p: p.execution_time, reverse=True)
            for i, profile in enumerate(sorted_profiles[:5], 1):
                status = "✅" if profile.success else "❌"
                percentage = (profile.execution_time / report.total_execution_time * 100) if report.total_execution_time > 0 else 0
                print(f"   {i}. {profile.operation_name}: {profile.duration_str} ({percentage:.1f}%) {status}")

        if report.bottlenecks:
            print(f"\n🚨 Bottlenecks Identified ({len(report.bottlenecks)}):")
            for bottleneck in report.bottlenecks[:3]:
                print(f"   • {bottleneck['operation']}: {bottleneck['execution_time']:.2f}s ({bottleneck['percentage_of_total']:.1f}%)")

        if report.recommendations:
            print(f"\n💡 Optimization Recommendations:")
            for rec in report.recommendations[:5]:
                print(f"   • {rec}")

        print("=" * 60 + "\n")


class PerformanceMonitorError(Exception):
    """Exception raised for performance monitoring errors."""
    pass
