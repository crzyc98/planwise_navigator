"""
Performance monitoring and optimization utilities for Story S031-02.

Provides query plan analysis, execution time tracking, and performance
bottleneck identification for DuckDB analytical workloads.

Features:
- Query execution plan analysis
- Performance bottleneck detection
- Memory usage monitoring
- Batch execution timing analysis
- Performance regression detection
"""

from __future__ import annotations

import logging
import time
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import json

from ..core.database_manager import DatabaseManager


logger = logging.getLogger(__name__)


@dataclass
class QueryPerformanceMetrics:
    """Performance metrics for a single query."""
    query_id: str
    query_type: str  # e.g., "SELECT", "INSERT", "CREATE"
    execution_time: float
    rows_processed: int
    memory_usage_mb: float = 0.0
    scan_operations: int = 0
    join_operations: int = 0
    aggregation_operations: int = 0
    index_usage: bool = False
    parallel_execution: bool = False
    optimization_opportunities: List[str] = field(default_factory=list)
    execution_plan: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BatchPerformanceAnalysis:
    """Analysis of batch execution performance."""
    batch_name: str
    total_execution_time: float
    model_count: int
    queries: List[QueryPerformanceMetrics] = field(default_factory=list)
    bottlenecks: List[str] = field(default_factory=list)
    optimization_suggestions: List[str] = field(default_factory=list)
    performance_score: float = 0.0  # 0-100 score
    baseline_comparison: Optional[float] = None  # % improvement vs baseline

    def __post_init__(self):
        """Calculate performance score."""
        if self.queries:
            avg_query_time = self.total_execution_time / len(self.queries)
            # Score based on query efficiency (lower time = higher score)
            self.performance_score = max(0, 100 - (avg_query_time * 10))


class PerformanceOptimizer:
    """
    Performance monitoring and optimization for DuckDB analytical workloads.

    Tracks query execution patterns, identifies bottlenecks, and provides
    optimization recommendations for workforce simulation queries.
    """

    def __init__(
        self,
        database_manager: DatabaseManager,
        performance_history_path: Optional[Path] = None
    ):
        """
        Initialize performance optimizer.

        Args:
            database_manager: Database manager for query execution
            performance_history_path: Path to store performance history
        """
        self.database_manager = database_manager
        self.performance_history_path = performance_history_path or Path("performance_history.json")

        # Performance tracking
        self.query_metrics: List[QueryPerformanceMetrics] = []
        self.batch_analyses: List[BatchPerformanceAnalysis] = []
        self.baseline_metrics: Dict[str, float] = {}

        # Load existing performance history
        self._load_performance_history()

        logger.info("PerformanceOptimizer initialized with query plan analysis")

    async def analyze_query_performance(
        self,
        query: str,
        query_id: str,
        query_type: str = "SELECT"
    ) -> QueryPerformanceMetrics:
        """
        Analyze performance of a single query with execution plan analysis.

        Args:
            query: SQL query to analyze
            query_id: Unique identifier for the query
            query_type: Type of query (SELECT, INSERT, etc.)

        Returns:
            Performance metrics for the query
        """
        logger.debug(f"Analyzing query performance: {query_id}")
        start_time = time.time()

        try:
            with self.database_manager.get_connection() as conn:
                # Get execution plan
                explain_query = f"EXPLAIN ANALYZE {query}"
                execution_plan = None
                rows_processed = 0

                try:
                    explain_result = conn.execute(explain_query).fetchall()
                    execution_plan = "\n".join(str(row) for row in explain_result)

                    # Parse execution plan for metrics
                    plan_metrics = self._parse_execution_plan(execution_plan)

                except Exception as e:
                    logger.debug(f"Could not get execution plan for {query_id}: {e}")
                    plan_metrics = {
                        "scan_operations": 0,
                        "join_operations": 0,
                        "aggregation_operations": 0,
                        "index_usage": False,
                        "parallel_execution": False,
                        "rows_processed": 0
                    }

                # Execute actual query for timing
                query_start = time.time()
                try:
                    result = conn.execute(query).fetchall()
                    rows_processed = len(result) if result else 0
                except Exception as e:
                    logger.debug(f"Query execution failed for {query_id}: {e}")
                    rows_processed = 0

                execution_time = time.time() - query_start

                # Identify optimization opportunities
                optimization_opportunities = self._identify_optimization_opportunities(
                    query, execution_plan, plan_metrics
                )

                # Create performance metrics
                metrics = QueryPerformanceMetrics(
                    query_id=query_id,
                    query_type=query_type,
                    execution_time=execution_time,
                    rows_processed=max(rows_processed, plan_metrics.get("rows_processed", 0)),
                    scan_operations=plan_metrics.get("scan_operations", 0),
                    join_operations=plan_metrics.get("join_operations", 0),
                    aggregation_operations=plan_metrics.get("aggregation_operations", 0),
                    index_usage=plan_metrics.get("index_usage", False),
                    parallel_execution=plan_metrics.get("parallel_execution", False),
                    optimization_opportunities=optimization_opportunities,
                    execution_plan=execution_plan
                )

                # Store metrics
                self.query_metrics.append(metrics)

                logger.debug(f"Query {query_id} analyzed: {execution_time:.3f}s, {rows_processed} rows")
                return metrics

        except Exception as e:
            logger.error(f"Query performance analysis failed for {query_id}: {e}")

            # Return basic metrics on failure
            execution_time = time.time() - start_time
            return QueryPerformanceMetrics(
                query_id=query_id,
                query_type=query_type,
                execution_time=execution_time,
                rows_processed=0,
                optimization_opportunities=[f"Analysis failed: {str(e)}"]
            )

    def _parse_execution_plan(self, execution_plan: str) -> Dict[str, Any]:
        """Parse DuckDB execution plan for performance metrics."""
        if not execution_plan:
            return {}

        plan_lower = execution_plan.lower()

        metrics = {
            "scan_operations": plan_lower.count("scan") + plan_lower.count("seq_scan"),
            "join_operations": (
                plan_lower.count("join") +
                plan_lower.count("hash_join") +
                plan_lower.count("merge_join") +
                plan_lower.count("nested_loop")
            ),
            "aggregation_operations": (
                plan_lower.count("aggregate") +
                plan_lower.count("group_by") +
                plan_lower.count("window")
            ),
            "index_usage": (
                "index" in plan_lower and
                "index_scan" in plan_lower
            ),
            "parallel_execution": (
                "parallel" in plan_lower or
                "worker" in plan_lower
            ),
            "rows_processed": 0  # DuckDB doesn't always provide row estimates in EXPLAIN
        }

        # Try to extract row count estimates
        import re
        row_pattern = r'(\d+)\s+rows'
        row_matches = re.findall(row_pattern, execution_plan)
        if row_matches:
            metrics["rows_processed"] = max(int(match) for match in row_matches)

        return metrics

    def _identify_optimization_opportunities(
        self,
        query: str,
        execution_plan: Optional[str],
        plan_metrics: Dict[str, Any]
    ) -> List[str]:
        """Identify optimization opportunities based on query and execution plan."""
        opportunities = []

        query_lower = query.lower()
        plan_lower = execution_plan.lower() if execution_plan else ""

        # Check for missing indexes
        if plan_metrics.get("scan_operations", 0) > 0 and not plan_metrics.get("index_usage", False):
            if "where" in query_lower and ("simulation_year" in query_lower or "employee_id" in query_lower):
                opportunities.append("Consider adding index on simulation_year or employee_id")

        # Check for expensive joins
        if plan_metrics.get("join_operations", 0) > 2:
            opportunities.append("Multiple joins detected - consider pre-aggregation or materialized views")

        # Check for large aggregations
        if plan_metrics.get("aggregation_operations", 0) > 0 and plan_metrics.get("rows_processed", 0) > 10000:
            opportunities.append("Large aggregation detected - consider partitioning or incremental processing")

        # Check for lack of parallelization
        if not plan_metrics.get("parallel_execution", False) and plan_metrics.get("rows_processed", 0) > 5000:
            opportunities.append("Query could benefit from parallel execution")

        # Check for SELECT * usage
        if "select *" in query_lower:
            opportunities.append("Avoid SELECT * - specify only needed columns for columnar efficiency")

        # Check for suboptimal WHERE clauses
        if "where" in query_lower and "function" in plan_lower:
            opportunities.append("Functions in WHERE clause may prevent index usage")

        # Check for unnecessary ORDER BY
        if "order by" in query_lower and "limit" not in query_lower:
            opportunities.append("ORDER BY without LIMIT may be unnecessary for analytical queries")

        return opportunities

    async def analyze_batch_performance(
        self,
        batch_name: str,
        queries: List[Tuple[str, str]],  # (query, query_id) pairs
        execution_time: float
    ) -> BatchPerformanceAnalysis:
        """
        Analyze performance of a batch of queries.

        Args:
            batch_name: Name of the batch
            queries: List of (query, query_id) tuples
            execution_time: Total batch execution time

        Returns:
            Batch performance analysis
        """
        logger.info(f"Analyzing batch performance: {batch_name}")

        # Analyze individual queries in batch
        query_metrics = []
        for query, query_id in queries:
            metrics = await self.analyze_query_performance(query, query_id)
            query_metrics.append(metrics)

        # Identify bottlenecks
        bottlenecks = self._identify_batch_bottlenecks(query_metrics, execution_time)

        # Generate optimization suggestions
        optimization_suggestions = self._generate_batch_optimizations(query_metrics, bottlenecks)

        # Calculate baseline comparison if available
        baseline_comparison = None
        if batch_name in self.baseline_metrics:
            baseline_time = self.baseline_metrics[batch_name]
            baseline_comparison = ((baseline_time - execution_time) / baseline_time) * 100

        # Create batch analysis
        analysis = BatchPerformanceAnalysis(
            batch_name=batch_name,
            total_execution_time=execution_time,
            model_count=len(queries),
            queries=query_metrics,
            bottlenecks=bottlenecks,
            optimization_suggestions=optimization_suggestions,
            baseline_comparison=baseline_comparison
        )

        # Store analysis
        self.batch_analyses.append(analysis)

        logger.info(f"Batch {batch_name} analysis: {analysis.performance_score:.1f}/100 score")

        return analysis

    def _identify_batch_bottlenecks(
        self,
        query_metrics: List[QueryPerformanceMetrics],
        total_execution_time: float
    ) -> List[str]:
        """Identify performance bottlenecks in batch execution."""
        bottlenecks = []

        if not query_metrics:
            return bottlenecks

        # Find slowest queries (top 20% by execution time)
        sorted_queries = sorted(query_metrics, key=lambda x: x.execution_time, reverse=True)
        slow_query_threshold = len(sorted_queries) // 5 or 1
        slow_queries = sorted_queries[:slow_query_threshold]

        if slow_queries:
            slowest_time = slow_queries[0].execution_time
            bottlenecks.append(f"Slowest query: {slow_queries[0].query_id} ({slowest_time:.2f}s)")

        # Check for queries with many operations
        high_operation_queries = [q for q in query_metrics if
                                (q.scan_operations + q.join_operations + q.aggregation_operations) > 10]
        if high_operation_queries:
            bottlenecks.append(f"{len(high_operation_queries)} queries with high operation count")

        # Check for queries without index usage
        no_index_queries = [q for q in query_metrics if not q.index_usage and q.rows_processed > 1000]
        if no_index_queries:
            bottlenecks.append(f"{len(no_index_queries)} queries without index usage on large datasets")

        # Check for non-parallel queries on large datasets
        non_parallel_queries = [q for q in query_metrics if not q.parallel_execution and q.rows_processed > 5000]
        if non_parallel_queries:
            bottlenecks.append(f"{len(non_parallel_queries)} large queries without parallel execution")

        return bottlenecks

    def _generate_batch_optimizations(
        self,
        query_metrics: List[QueryPerformanceMetrics],
        bottlenecks: List[str]
    ) -> List[str]:
        """Generate optimization suggestions for batch execution."""
        suggestions = []

        # Collect all optimization opportunities
        all_opportunities = []
        for metrics in query_metrics:
            all_opportunities.extend(metrics.optimization_opportunities)

        # Count common opportunities
        opportunity_counts = {}
        for opp in all_opportunities:
            opportunity_counts[opp] = opportunity_counts.get(opp, 0) + 1

        # Suggest most common optimizations
        for opp, count in sorted(opportunity_counts.items(), key=lambda x: x[1], reverse=True):
            if count >= 2:  # Appears in multiple queries
                suggestions.append(f"{opp} (affects {count} queries)")

        # Add batch-specific suggestions
        if len(query_metrics) > 8:
            suggestions.append("Consider breaking large batch into smaller parallel groups")

        total_execution_time = sum(q.execution_time for q in query_metrics)
        if total_execution_time > 300:  # 5 minutes
            suggestions.append("Batch execution time exceeds 5 minutes - consider performance optimization")

        # Suggest materialized views for common patterns
        aggregation_queries = [q for q in query_metrics if q.aggregation_operations > 0]
        if len(aggregation_queries) >= 3:
            suggestions.append("Multiple aggregation queries - consider materialized views")

        return suggestions

    def set_baseline_metrics(self, batch_name: str, execution_time: float) -> None:
        """Set baseline metrics for performance comparison."""
        self.baseline_metrics[batch_name] = execution_time
        logger.info(f"Set baseline for {batch_name}: {execution_time:.2f}s")

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        if not self.query_metrics:
            return {"message": "No performance data available"}

        # Query-level statistics
        total_queries = len(self.query_metrics)
        total_query_time = sum(q.execution_time for q in self.query_metrics)
        avg_query_time = total_query_time / total_queries

        # Find performance outliers
        sorted_queries = sorted(self.query_metrics, key=lambda x: x.execution_time, reverse=True)
        slowest_queries = sorted_queries[:3]
        fastest_queries = sorted_queries[-3:]

        # Batch-level statistics
        batch_summaries = []
        for analysis in self.batch_analyses:
            batch_summaries.append({
                "batch_name": analysis.batch_name,
                "execution_time": analysis.total_execution_time,
                "model_count": analysis.model_count,
                "performance_score": analysis.performance_score,
                "baseline_improvement": analysis.baseline_comparison,
                "bottleneck_count": len(analysis.bottlenecks),
                "optimization_count": len(analysis.optimization_suggestions)
            })

        # Overall performance trends
        recent_queries = [q for q in self.query_metrics if
                         (datetime.utcnow() - q.timestamp) < timedelta(hours=1)]

        performance_trends = {
            "queries_last_hour": len(recent_queries),
            "avg_time_last_hour": sum(q.execution_time for q in recent_queries) / len(recent_queries) if recent_queries else 0,
            "optimization_opportunities": sum(len(q.optimization_opportunities) for q in recent_queries)
        }

        return {
            "query_statistics": {
                "total_queries": total_queries,
                "total_execution_time": total_query_time,
                "average_query_time": avg_query_time,
                "slowest_queries": [{"id": q.query_id, "time": q.execution_time} for q in slowest_queries],
                "fastest_queries": [{"id": q.query_id, "time": q.execution_time} for q in fastest_queries]
            },
            "batch_summaries": batch_summaries,
            "performance_trends": performance_trends,
            "optimization_impact": {
                "total_opportunities": sum(len(q.optimization_opportunities) for q in self.query_metrics),
                "common_optimizations": self._get_common_optimizations(),
                "baseline_comparisons": {name: time for name, time in self.baseline_metrics.items()}
            }
        }

    def _get_common_optimizations(self) -> List[Tuple[str, int]]:
        """Get most common optimization opportunities."""
        all_opportunities = []
        for q in self.query_metrics:
            all_opportunities.extend(q.optimization_opportunities)

        opportunity_counts = {}
        for opp in all_opportunities:
            opportunity_counts[opp] = opportunity_counts.get(opp, 0) + 1

        return sorted(opportunity_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    def _load_performance_history(self) -> None:
        """Load performance history from file."""
        try:
            if self.performance_history_path.exists():
                with open(self.performance_history_path, 'r') as f:
                    history_data = json.load(f)
                    self.baseline_metrics = history_data.get("baseline_metrics", {})
                    logger.info(f"Loaded performance history with {len(self.baseline_metrics)} baselines")
        except Exception as e:
            logger.debug(f"Could not load performance history: {e}")

    def save_performance_history(self) -> None:
        """Save performance history to file."""
        try:
            history_data = {
                "baseline_metrics": self.baseline_metrics,
                "last_updated": datetime.utcnow().isoformat(),
                "total_queries_analyzed": len(self.query_metrics),
                "total_batches_analyzed": len(self.batch_analyses)
            }

            with open(self.performance_history_path, 'w') as f:
                json.dump(history_data, f, indent=2)

            logger.info(f"Saved performance history to {self.performance_history_path}")

        except Exception as e:
            logger.warning(f"Could not save performance history: {e}")

    def reset_performance_data(self) -> None:
        """Reset all performance tracking data."""
        self.query_metrics.clear()
        self.batch_analyses.clear()
        logger.info("Performance tracking data reset")
