#!/usr/bin/env python3
"""
DuckDB Query Performance Analysis Tool

Analyzes DuckDB query profiles and provides optimization recommendations
for Navigator Orchestrator pipeline performance improvements.

Epic E068E: Engine & I/O Tuning
Target: 15-25% performance improvement through query optimization.

Usage:
    python scripts/analyze_query_performance.py profile.json
    python scripts/analyze_query_performance.py --profile-dir /tmp/profiles
    python scripts/analyze_query_performance.py --live-analysis --database dbt/simulation.duckdb
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import time

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False


class QueryProfileAnalyzer:
    """
    Analyze DuckDB query profiles to identify performance bottlenecks
    and provide E068E-aligned optimization recommendations.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

        # Performance thresholds for analysis
        self.thresholds = {
            "slow_query_seconds": 30.0,     # E068E target: <30s per complex join
            "high_memory_mb": 8192,         # 8GB memory usage threshold
            "bottleneck_percentage": 10.0,  # Operations consuming >10% of total time
            "io_intensive_mb": 1000,        # I/O operations >1GB
            "cpu_intensive_percent": 80.0,  # CPU-bound operations >80% utilization
        }

    def analyze_profile(self, profile_path: Path) -> Dict[str, Any]:
        """
        Analyze a single DuckDB query profile JSON file

        Args:
            profile_path: Path to the query profile JSON file

        Returns:
            Dictionary containing analysis results and recommendations
        """
        try:
            with open(profile_path) as f:
                profile = json.load(f)

            analysis = {
                "profile_file": str(profile_path),
                "query_info": self._extract_query_info(profile),
                "performance_metrics": self._analyze_performance_metrics(profile),
                "bottlenecks": self._identify_bottlenecks(profile),
                "optimization_recommendations": self._generate_recommendations(profile),
                "e068e_assessment": self._assess_e068e_targets(profile)
            }

            return analysis

        except Exception as e:
            self.logger.error(f"Failed to analyze profile {profile_path}: {e}")
            return {"error": str(e), "profile_file": str(profile_path)}

    def analyze_profile_directory(self, profile_dir: Path) -> Dict[str, Any]:
        """
        Analyze all query profiles in a directory

        Args:
            profile_dir: Directory containing query profile JSON files

        Returns:
            Comprehensive analysis of all profiles with aggregate recommendations
        """
        profile_files = list(profile_dir.glob("*.json"))

        if not profile_files:
            return {"error": f"No JSON profile files found in {profile_dir}"}

        analyses = []
        for profile_file in profile_files:
            analysis = self.analyze_profile(profile_file)
            if "error" not in analysis:
                analyses.append(analysis)

        # Aggregate analysis
        aggregate_analysis = {
            "total_profiles": len(profile_files),
            "successful_analyses": len(analyses),
            "profiles": analyses,
            "aggregate_metrics": self._aggregate_metrics(analyses),
            "top_bottlenecks": self._identify_top_bottlenecks(analyses),
            "priority_recommendations": self._prioritize_recommendations(analyses)
        }

        return aggregate_analysis

    def live_database_analysis(self, database_path: Path) -> Dict[str, Any]:
        """
        Perform live analysis of a DuckDB database with profiling

        Args:
            database_path: Path to DuckDB database file

        Returns:
            Analysis results from live profiling
        """
        if not DUCKDB_AVAILABLE:
            return {"error": "DuckDB not available for live analysis"}

        if not database_path.exists():
            return {"error": f"Database file not found: {database_path}"}

        try:
            conn = duckdb.connect(str(database_path))

            # Enable profiling
            conn.execute("PRAGMA enable_profiling")

            # Run sample analytical queries to profile performance
            sample_queries = self._get_sample_queries()
            query_results = []

            for query_name, query_sql in sample_queries.items():
                try:
                    start_time = time.time()
                    result = conn.execute(query_sql).fetchall()
                    execution_time = time.time() - start_time

                    # Get profiling info (DuckDB specific method would go here)
                    query_results.append({
                        "query_name": query_name,
                        "execution_time": execution_time,
                        "row_count": len(result),
                        "performance_assessment": self._assess_query_performance(execution_time, len(result))
                    })

                except Exception as e:
                    query_results.append({
                        "query_name": query_name,
                        "error": str(e),
                        "execution_time": 0
                    })

            conn.close()

            return {
                "database_path": str(database_path),
                "live_analysis": True,
                "query_results": query_results,
                "recommendations": self._generate_live_recommendations(query_results)
            }

        except Exception as e:
            return {"error": f"Live analysis failed: {e}"}

    def generate_report(self, analysis: Dict[str, Any]) -> str:
        """Generate a comprehensive performance analysis report"""

        if "error" in analysis:
            return f"Analysis failed: {analysis['error']}"

        report_lines = [
            "DuckDB Query Performance Analysis Report (E068E)",
            "=" * 60,
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]

        # Handle different analysis types
        if "profiles" in analysis:  # Directory analysis
            report_lines.extend(self._generate_directory_report(analysis))
        elif "live_analysis" in analysis:  # Live database analysis
            report_lines.extend(self._generate_live_report(analysis))
        else:  # Single profile analysis
            report_lines.extend(self._generate_single_report(analysis))

        return "\n".join(report_lines)

    def _extract_query_info(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Extract basic query information from profile"""
        return {
            "total_time": profile.get("total_time", 0),
            "memory_usage_mb": profile.get("memory_usage", 0) / (1024 * 1024) if profile.get("memory_usage") else 0,
            "query_type": profile.get("query_type", "unknown"),
            "timestamp": profile.get("timestamp", "unknown")
        }

    def _analyze_performance_metrics(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze performance metrics from the profile"""
        total_time = profile.get("total_time", 0)
        memory_usage_mb = profile.get("memory_usage", 0) / (1024 * 1024) if profile.get("memory_usage") else 0

        metrics = {
            "execution_time": total_time,
            "memory_usage_mb": memory_usage_mb,
            "performance_level": "unknown",
            "meets_e068e_targets": False
        }

        # Assess performance level based on E068E targets
        if total_time <= 30 and memory_usage_mb <= 4096:  # 30s, 4GB thresholds
            metrics["performance_level"] = "excellent"
            metrics["meets_e068e_targets"] = True
        elif total_time <= 60 and memory_usage_mb <= 8192:  # 60s, 8GB thresholds
            metrics["performance_level"] = "good"
        elif total_time <= 180:  # 3 minutes
            metrics["performance_level"] = "moderate"
        else:
            metrics["performance_level"] = "poor"

        return metrics

    def _identify_bottlenecks(self, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify performance bottlenecks from operator timings"""
        bottlenecks = []

        operators = profile.get("operators", [])
        total_time = profile.get("total_time", 1)  # Avoid division by zero

        for operator in operators:
            op_time = operator.get("time", 0)
            op_name = operator.get("name", "unknown")

            # Calculate percentage of total time
            time_percentage = (op_time / total_time) * 100 if total_time > 0 else 0

            if time_percentage >= self.thresholds["bottleneck_percentage"]:
                bottlenecks.append({
                    "operator": op_name,
                    "time_seconds": op_time,
                    "percentage_of_total": time_percentage,
                    "bottleneck_type": self._classify_bottleneck(operator),
                    "optimization_hints": self._get_operator_optimization_hints(op_name)
                })

        # Sort by time percentage (highest first)
        return sorted(bottlenecks, key=lambda x: x["percentage_of_total"], reverse=True)

    def _classify_bottleneck(self, operator: Dict[str, Any]) -> str:
        """Classify the type of bottleneck based on operator characteristics"""
        op_name = operator.get("name", "").upper()

        if "SCAN" in op_name or "READ" in op_name:
            return "I/O_BOUND"
        elif "SORT" in op_name or "ORDER" in op_name:
            return "CPU_SORT"
        elif "JOIN" in op_name or "HASH" in op_name:
            return "CPU_JOIN"
        elif "AGGREGATE" in op_name or "GROUP" in op_name:
            return "CPU_AGGREGATE"
        elif "FILTER" in op_name or "WHERE" in op_name:
            return "CPU_FILTER"
        else:
            return "UNKNOWN"

    def _get_operator_optimization_hints(self, op_name: str) -> List[str]:
        """Get optimization hints for specific operator types"""
        op_name_upper = op_name.upper()
        hints = []

        if "SCAN" in op_name_upper:
            hints = [
                "Consider adding column pruning",
                "Verify indexes are being used effectively",
                "Check if predicate pushdown is working",
                "Consider partitioning large tables"
            ]
        elif "SORT" in op_name_upper:
            hints = [
                "Consider pre-sorting data if possible",
                "Increase memory allocation for sorting",
                "Check if sort can be avoided with different query structure"
            ]
        elif "JOIN" in op_name_upper:
            hints = [
                "Verify join keys have appropriate data types",
                "Consider join order optimization",
                "Check cardinality estimates",
                "Consider broadcast vs shuffle join strategies"
            ]
        elif "AGGREGATE" in op_name_upper:
            hints = [
                "Consider pre-aggregation if possible",
                "Check group by key cardinality",
                "Verify memory allocation for aggregation"
            ]

        return hints

    def _generate_recommendations(self, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate optimization recommendations based on profile analysis"""
        recommendations = []

        query_info = self._extract_query_info(profile)
        bottlenecks = self._identify_bottlenecks(profile)

        # Query-level recommendations
        if query_info["total_time"] > self.thresholds["slow_query_seconds"]:
            recommendations.append({
                "category": "Query Performance (E068E)",
                "priority": "HIGH",
                "description": f"Query execution time {query_info['total_time']:.1f}s exceeds E068E target of {self.thresholds['slow_query_seconds']}s",
                "recommendation": "Profile slow operations, optimize query structure, consider indexing",
                "potential_improvement": "25-40% performance improvement"
            })

        if query_info["memory_usage_mb"] > self.thresholds["high_memory_mb"]:
            recommendations.append({
                "category": "Memory Optimization (E068E)",
                "priority": "MEDIUM",
                "description": f"Memory usage {query_info['memory_usage_mb']:.0f}MB is high",
                "recommendation": "Optimize data types, enable compression, increase available memory",
                "potential_improvement": "15-25% memory reduction"
            })

        # Operator-specific recommendations
        for bottleneck in bottlenecks[:3]:  # Top 3 bottlenecks
            if bottleneck["bottleneck_type"] == "I/O_BOUND":
                recommendations.append({
                    "category": "I/O Optimization (E068E)",
                    "priority": "HIGH",
                    "description": f"I/O bottleneck in {bottleneck['operator']} ({bottleneck['percentage_of_total']:.1f}% of query time)",
                    "recommendation": "Use faster storage, enable compression, optimize data layout",
                    "potential_improvement": "20-30% I/O performance improvement"
                })
            elif bottleneck["bottleneck_type"] in ["CPU_SORT", "CPU_JOIN", "CPU_AGGREGATE"]:
                recommendations.append({
                    "category": "CPU Optimization (E068E)",
                    "priority": "MEDIUM",
                    "description": f"CPU bottleneck in {bottleneck['operator']} ({bottleneck['percentage_of_total']:.1f}% of query time)",
                    "recommendation": "Increase thread count, optimize algorithms, reduce data volume",
                    "potential_improvement": "15-20% CPU performance improvement"
                })

        return sorted(recommendations, key=lambda x: {"HIGH": 1, "MEDIUM": 2, "LOW": 3}[x["priority"]])

    def _assess_e068e_targets(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Assess performance against E068E-specific targets"""
        query_info = self._extract_query_info(profile)

        assessment = {
            "query_time_target": "PASS" if query_info["total_time"] <= 30 else "FAIL",
            "memory_efficiency": "GOOD" if query_info["memory_usage_mb"] <= 4096 else "NEEDS_IMPROVEMENT",
            "overall_e068e_compliance": "UNKNOWN"
        }

        # Overall assessment
        if assessment["query_time_target"] == "PASS" and assessment["memory_efficiency"] == "GOOD":
            assessment["overall_e068e_compliance"] = "EXCELLENT"
        elif assessment["query_time_target"] == "PASS":
            assessment["overall_e068e_compliance"] = "GOOD"
        else:
            assessment["overall_e068e_compliance"] = "NEEDS_IMPROVEMENT"

        return assessment

    def _get_sample_queries(self) -> Dict[str, str]:
        """Get sample analytical queries for live database analysis"""
        return {
            "workforce_count": "SELECT COUNT(*) FROM fct_workforce_snapshot",
            "event_summary": "SELECT event_type, COUNT(*) FROM fct_yearly_events GROUP BY event_type",
            "memory_intensive": "SELECT simulation_year, employee_id, COUNT(*) FROM fct_yearly_events GROUP BY simulation_year, employee_id HAVING COUNT(*) > 1",
            "join_performance": """
                SELECT w.simulation_year, COUNT(DISTINCT w.employee_id), COUNT(e.event_id)
                FROM fct_workforce_snapshot w
                LEFT JOIN fct_yearly_events e ON w.employee_id = e.employee_id AND w.simulation_year = e.simulation_year
                GROUP BY w.simulation_year
            """
        }

    def _assess_query_performance(self, execution_time: float, row_count: int) -> str:
        """Assess individual query performance"""
        if execution_time <= 5:
            return "EXCELLENT"
        elif execution_time <= 30:  # E068E target
            return "GOOD"
        elif execution_time <= 60:
            return "MODERATE"
        else:
            return "POOR"

    def _generate_live_recommendations(self, query_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate recommendations based on live query analysis"""
        recommendations = []

        slow_queries = [q for q in query_results if q.get("execution_time", 0) > 30]

        if slow_queries:
            recommendations.append({
                "category": "Query Performance (E068E)",
                "priority": "HIGH",
                "description": f"{len(slow_queries)} queries exceed E068E 30-second target",
                "recommendation": "Enable query profiling, add indexes, optimize join strategies",
                "affected_queries": [q["query_name"] for q in slow_queries]
            })

        # Memory optimization recommendations would go here based on actual profiling data

        return recommendations

    def _aggregate_metrics(self, analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate metrics across multiple profile analyses"""
        if not analyses:
            return {}

        total_queries = len(analyses)
        total_time = sum(a["query_info"]["total_time"] for a in analyses)
        avg_time = total_time / total_queries

        slow_queries = sum(1 for a in analyses if a["query_info"]["total_time"] > 30)

        return {
            "total_queries_analyzed": total_queries,
            "average_execution_time": avg_time,
            "slow_queries_count": slow_queries,
            "slow_queries_percentage": (slow_queries / total_queries) * 100,
            "e068e_compliance_rate": ((total_queries - slow_queries) / total_queries) * 100
        }

    def _identify_top_bottlenecks(self, analyses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify most common bottlenecks across all analyses"""
        bottleneck_counts = {}

        for analysis in analyses:
            for bottleneck in analysis.get("bottlenecks", []):
                bottleneck_type = bottleneck["bottleneck_type"]
                if bottleneck_type not in bottleneck_counts:
                    bottleneck_counts[bottleneck_type] = {
                        "count": 0,
                        "total_time": 0,
                        "operators": []
                    }
                bottleneck_counts[bottleneck_type]["count"] += 1
                bottleneck_counts[bottleneck_type]["total_time"] += bottleneck["time_seconds"]
                bottleneck_counts[bottleneck_type]["operators"].append(bottleneck["operator"])

        # Convert to sorted list
        top_bottlenecks = []
        for bottleneck_type, data in bottleneck_counts.items():
            top_bottlenecks.append({
                "type": bottleneck_type,
                "frequency": data["count"],
                "total_time": data["total_time"],
                "common_operators": list(set(data["operators"]))
            })

        return sorted(top_bottlenecks, key=lambda x: x["frequency"], reverse=True)

    def _prioritize_recommendations(self, analyses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prioritize recommendations across all analyses"""
        recommendation_counts = {}

        for analysis in analyses:
            for rec in analysis.get("optimization_recommendations", []):
                category = rec["category"]
                if category not in recommendation_counts:
                    recommendation_counts[category] = {
                        "count": 0,
                        "priorities": [],
                        "potential_improvements": []
                    }
                recommendation_counts[category]["count"] += 1
                recommendation_counts[category]["priorities"].append(rec["priority"])
                if "potential_improvement" in rec:
                    recommendation_counts[category]["potential_improvements"].append(rec["potential_improvement"])

        # Convert to prioritized list
        prioritized = []
        for category, data in recommendation_counts.items():
            high_priority_count = data["priorities"].count("HIGH")
            prioritized.append({
                "category": category,
                "frequency": data["count"],
                "high_priority_instances": high_priority_count,
                "priority_score": high_priority_count * 3 + data["priorities"].count("MEDIUM") * 2 + data["priorities"].count("LOW"),
                "common_improvements": list(set(data["potential_improvements"]))
            })

        return sorted(prioritized, key=lambda x: x["priority_score"], reverse=True)

    def _generate_directory_report(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate report for directory analysis"""
        lines = [
            f"Analysis Type: Directory Analysis",
            f"Total Profiles: {analysis['total_profiles']}",
            f"Successful Analyses: {analysis['successful_analyses']}",
            "",
            "AGGREGATE METRICS",
            "-" * 20
        ]

        metrics = analysis["aggregate_metrics"]
        lines.extend([
            f"Average execution time: {metrics['average_execution_time']:.2f} seconds",
            f"Slow queries (>30s): {metrics['slow_queries_count']} ({metrics['slow_queries_percentage']:.1f}%)",
            f"E068E compliance rate: {metrics['e068e_compliance_rate']:.1f}%",
            ""
        ])

        # Top bottlenecks
        if analysis["top_bottlenecks"]:
            lines.extend([
                "TOP BOTTLENECKS",
                "-" * 15
            ])
            for bottleneck in analysis["top_bottlenecks"][:5]:
                lines.append(f"• {bottleneck['type']}: {bottleneck['frequency']} occurrences, {bottleneck['total_time']:.1f}s total")

        # Priority recommendations
        if analysis["priority_recommendations"]:
            lines.extend([
                "",
                "PRIORITY RECOMMENDATIONS",
                "-" * 25
            ])
            for rec in analysis["priority_recommendations"][:5]:
                lines.append(f"• {rec['category']}: {rec['high_priority_instances']} high-priority instances")

        return lines

    def _generate_live_report(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate report for live database analysis"""
        lines = [
            f"Analysis Type: Live Database Analysis",
            f"Database: {analysis['database_path']}",
            ""
        ]

        query_results = analysis["query_results"]
        successful_queries = [q for q in query_results if "error" not in q]
        failed_queries = [q for q in query_results if "error" in q]

        lines.extend([
            "QUERY RESULTS",
            "-" * 13,
            f"Total queries: {len(query_results)}",
            f"Successful: {len(successful_queries)}",
            f"Failed: {len(failed_queries)}",
            ""
        ])

        for query in successful_queries:
            lines.append(f"• {query['query_name']}: {query['execution_time']:.2f}s ({query['performance_assessment']})")

        if failed_queries:
            lines.extend([
                "",
                "FAILED QUERIES",
                "-" * 14
            ])
            for query in failed_queries:
                lines.append(f"• {query['query_name']}: {query['error']}")

        return lines

    def _generate_single_report(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate report for single profile analysis"""
        lines = [
            f"Profile: {analysis['profile_file']}",
            ""
        ]

        query_info = analysis["query_info"]
        metrics = analysis["performance_metrics"]

        lines.extend([
            "QUERY PERFORMANCE",
            "-" * 17,
            f"Execution time: {query_info['total_time']:.2f} seconds",
            f"Memory usage: {query_info['memory_usage_mb']:.1f} MB",
            f"Performance level: {metrics['performance_level'].upper()}",
            f"E068E compliant: {'✅' if metrics['meets_e068e_targets'] else '❌'}",
            ""
        ])

        # Bottlenecks
        bottlenecks = analysis["bottlenecks"]
        if bottlenecks:
            lines.extend([
                "PERFORMANCE BOTTLENECKS",
                "-" * 22
            ])
            for bottleneck in bottlenecks[:5]:
                lines.append(f"• {bottleneck['operator']}: {bottleneck['time_seconds']:.2f}s ({bottleneck['percentage_of_total']:.1f}%)")

        # Recommendations
        recommendations = analysis["optimization_recommendations"]
        if recommendations:
            lines.extend([
                "",
                "OPTIMIZATION RECOMMENDATIONS",
                "-" * 28
            ])
            for rec in recommendations:
                lines.extend([
                    f"🔴 {rec['priority']}: {rec['category']}",
                    f"   {rec['description']}",
                    f"   → {rec['recommendation']}",
                    ""
                ])

        return lines


def main():
    """Main entry point for the query performance analyzer"""
    parser = argparse.ArgumentParser(
        description="Analyze DuckDB query profiles for E068E performance optimization"
    )

    parser.add_argument(
        "profile_path",
        nargs="?",
        help="Path to query profile JSON file"
    )

    parser.add_argument(
        "--profile-dir",
        help="Directory containing query profile JSON files"
    )

    parser.add_argument(
        "--live-analysis",
        action="store_true",
        help="Perform live database analysis"
    )

    parser.add_argument(
        "--database",
        default="dbt/simulation.duckdb",
        help="Database path for live analysis (default: dbt/simulation.duckdb)"
    )

    parser.add_argument(
        "--output",
        help="Output file for analysis report"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    analyzer = QueryProfileAnalyzer()

    # Determine analysis type
    if args.live_analysis:
        database_path = Path(args.database)
        analysis = analyzer.live_database_analysis(database_path)
    elif args.profile_dir:
        profile_dir = Path(args.profile_dir)
        analysis = analyzer.analyze_profile_directory(profile_dir)
    elif args.profile_path:
        profile_path = Path(args.profile_path)
        analysis = analyzer.analyze_profile(profile_path)
    else:
        parser.print_help()
        return 1

    # Generate output
    if args.json:
        output = json.dumps(analysis, indent=2)
    else:
        output = analyzer.generate_report(analysis)

    # Write output
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Analysis saved to {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
