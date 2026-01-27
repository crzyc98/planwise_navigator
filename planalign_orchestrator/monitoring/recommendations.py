"""
Performance optimization recommendations for DuckDB operations.

Provides E068E-specific optimization recommendations based on
collected performance checkpoint data.
"""

from typing import List, TYPE_CHECKING

from .data_models import PerformanceOptimization

if TYPE_CHECKING:
    from .data_models import PerformanceCheckpoint


def generate_optimization_recommendations(
    checkpoints: List["PerformanceCheckpoint"],
    thresholds: dict,
) -> List[PerformanceOptimization]:
    """
    Generate E068E-specific optimization recommendations based on performance data.

    Args:
        checkpoints: List of performance checkpoints from monitoring session
        thresholds: Dictionary of performance thresholds

    Returns:
        List of PerformanceOptimization recommendations sorted by priority
    """
    recommendations: List[PerformanceOptimization] = []

    if not checkpoints:
        return recommendations

    # Calculate statistics from checkpoints
    memory_values = [c.memory_usage_gb for c in checkpoints]
    cpu_values = [c.cpu_percent for c in checkpoints]
    db_sizes = [c.database_size_gb for c in checkpoints]

    peak_memory = max(memory_values)
    avg_cpu = sum(cpu_values) / len(cpu_values)
    db_growth = db_sizes[-1] - db_sizes[0] if len(db_sizes) > 1 else 0

    # Memory optimization recommendations (E068E focus)
    recommendations.extend(
        _generate_memory_recommendations(peak_memory, thresholds)
    )

    # CPU optimization recommendations (E068E focus)
    cpu_cores = checkpoints[0].cpu_count if checkpoints else 1
    recommendations.extend(
        _generate_cpu_recommendations(avg_cpu, cpu_cores, thresholds)
    )

    # I/O optimization recommendations (E068E specific)
    recommendations.extend(
        _generate_io_recommendations(checkpoints, thresholds)
    )

    # Database growth optimization (E068E target: <1GB per year)
    recommendations.extend(
        _generate_storage_recommendations(db_growth, thresholds)
    )

    # Stage-specific recommendations
    recommendations.extend(
        _generate_stage_recommendations(checkpoints, thresholds)
    )

    return sorted(recommendations, key=lambda x: x.priority)


def _generate_memory_recommendations(
    peak_memory: float,
    thresholds: dict,
) -> List[PerformanceOptimization]:
    """Generate memory-related optimization recommendations."""
    recommendations = []

    if peak_memory > 40:
        recommendations.append(
            PerformanceOptimization(
                category="Memory Management (E068E Critical)",
                severity="critical",
                description=f"Peak memory {peak_memory:.1f}GB exceeds E068E target of 40GB",
                recommendation="Implement PRAGMA memory_limit='48GB', reduce batch sizes, enable adaptive memory management",
                potential_improvement="20-30% performance improvement, meets E068E memory targets",
                priority=1,
            )
        )
    elif peak_memory > 24:
        recommendations.append(
            PerformanceOptimization(
                category="Memory Optimization (E068E)",
                severity="warning",
                description=f"Peak memory {peak_memory:.1f}GB is high, E068E targets <10GB typical, <40GB peak",
                recommendation="Enable PRAGMA enable_object_cache=true, optimize temp_directory placement",
                potential_improvement="10-15% performance improvement through memory optimization",
                priority=2,
            )
        )
    elif peak_memory < 8:
        recommendations.append(
            PerformanceOptimization(
                category="Resource Utilization (E068E)",
                severity="info",
                description=f"Low peak memory {peak_memory:.1f}GB suggests underutilization of 64GB system",
                recommendation="Increase PRAGMA memory_limit, enable larger batch processing",
                potential_improvement="15-25% performance improvement through better resource utilization",
                priority=3,
            )
        )

    return recommendations


def _generate_cpu_recommendations(
    avg_cpu: float,
    cpu_cores: int,
    thresholds: dict,
) -> List[PerformanceOptimization]:
    """Generate CPU-related optimization recommendations."""
    recommendations = []

    if avg_cpu > 90:
        recommendations.append(
            PerformanceOptimization(
                category="CPU Management (E068E Critical)",
                severity="critical",
                description=f"High CPU {avg_cpu:.1f}% on {cpu_cores}-core system indicates resource contention",
                recommendation="Optimize PRAGMA threads configuration, reduce concurrent operations",
                potential_improvement="15-20% performance improvement through reduced CPU contention",
                priority=1,
            )
        )
    elif avg_cpu < 60:
        recommendations.append(
            PerformanceOptimization(
                category="CPU Utilization (E068E)",
                severity="warning",
                description=f"CPU utilization {avg_cpu:.1f}% is below E068E target of >80%",
                recommendation="Increase PRAGMA threads=16, enable model parallelization",
                potential_improvement="20-30% performance improvement through better CPU utilization",
                priority=2,
            )
        )

    return recommendations


def _generate_io_recommendations(
    checkpoints: List["PerformanceCheckpoint"],
    thresholds: dict,
) -> List[PerformanceOptimization]:
    """Generate I/O-related optimization recommendations."""
    recommendations = []

    if len(checkpoints) > 2:
        total_io_gb = 0
        for i in range(1, len(checkpoints)):
            curr = checkpoints[i]
            prev = checkpoints[i - 1]
            io_delta = (
                curr.io_read_bytes
                + curr.io_write_bytes
                - prev.io_read_bytes
                - prev.io_write_bytes
            ) / (1024**3)
            total_io_gb += io_delta

        if total_io_gb > 10:  # High I/O workload
            recommendations.append(
                PerformanceOptimization(
                    category="I/O Optimization (E068E)",
                    severity="warning",
                    description=f"High I/O workload detected ({total_io_gb:.1f}GB total)",
                    recommendation="Use NVMe temp_directory, enable Parquet with ZSTD compression, optimize storage placement",
                    potential_improvement="15-25% performance improvement through I/O optimization",
                    priority=2,
                )
            )

    return recommendations


def _generate_storage_recommendations(
    db_growth: float,
    thresholds: dict,
) -> List[PerformanceOptimization]:
    """Generate storage-related optimization recommendations."""
    recommendations = []

    if db_growth > 2:
        recommendations.append(
            PerformanceOptimization(
                category="Storage Optimization (E068E)",
                severity="warning",
                description=f"Database growth {db_growth:.2f}GB exceeds E068E target of <1GB per simulation year",
                recommendation="Enable compression, convert CSV seeds to Parquet, implement incremental strategies",
                potential_improvement="10-20% performance improvement through reduced I/O overhead",
                priority=2,
            )
        )

    return recommendations


def _generate_stage_recommendations(
    checkpoints: List["PerformanceCheckpoint"],
    thresholds: dict,
) -> List[PerformanceOptimization]:
    """Generate stage-specific optimization recommendations."""
    recommendations = []

    slow_stages = []
    for i in range(1, len(checkpoints)):
        curr = checkpoints[i]
        prev = checkpoints[i - 1]
        stage_duration = curr.elapsed_time - prev.elapsed_time

        if stage_duration > 60:  # Slow stage
            slow_stages.append((curr.stage_name, stage_duration))

    if slow_stages:
        stage_names = ", ".join([s[0] for s in slow_stages[:3]])  # First 3 slow stages
        recommendations.append(
            PerformanceOptimization(
                category="Query Optimization (E068E)",
                severity="warning",
                description=f"Slow stages detected: {stage_names} (E068E target: <30s per complex join)",
                recommendation="Enable query profiling, optimize indexes, review dbt model dependencies",
                potential_improvement="25-40% performance improvement through query optimization",
                priority=1,
            )
        )

    return recommendations
