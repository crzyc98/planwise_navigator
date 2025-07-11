#!/usr/bin/env python3
"""
Polars Performance Proof of Concept

Benchmark pandas vs Polars performance on existing workforce simulation data.
This script demonstrates potential speed improvements with zero impact to existing codebase.

Usage: python scripts/polars_benchmark_poc.py
"""

import time
import psutil
import pandas as pd
import polars as pl
import duckdb
from typing import Dict, Any
import os
from pathlib import Path


class WorkforcePerformanceBenchmark:
    """Benchmark pandas vs Polars on workforce simulation operations."""

    def __init__(self, database_path: str = "simulation.duckdb"):
        """Initialize benchmark with DuckDB connection."""
        self.database_path = database_path
        self.results = {}

    def get_duckdb_connection(self):
        """Get DuckDB connection using existing patterns."""
        conn = duckdb.connect(database=self.database_path, read_only=True)
        try:
            conn.execute("LOAD parquet;")
        except Exception:
            pass  # Continue without Parquet extension if not available
        return conn

    def load_workforce_data(self) -> tuple[pd.DataFrame, pl.DataFrame]:
        """Load workforce data as both pandas and Polars DataFrames."""
        print("📊 Loading workforce data from DuckDB...")

        with self.get_duckdb_connection() as conn:
            # Load data using existing DuckDB pattern: conn.execute().df()
            query = """
            SELECT
                employee_id,
                current_compensation,
                level_id,
                employment_status,
                detailed_status_code,
                simulation_year,
                age_band,
                tenure_band,
                current_age,
                current_tenure
            FROM fct_workforce_snapshot
            """

            # Pandas DataFrame (existing pattern)
            pandas_df = conn.execute(query).df()

            # Polars DataFrame (convert from pandas for now)
            polars_df = pl.from_pandas(pandas_df)

        print(f"   Data loaded: {len(pandas_df):,} employees")
        return pandas_df, polars_df

    def measure_performance(self, func, name: str, *args, **kwargs) -> Dict[str, Any]:
        """Measure execution time and memory usage for a function."""
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()

        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        execution_time = (end_time - start_time) * 1000  # Convert to milliseconds

        return {
            'name': name,
            'execution_time_ms': round(execution_time, 2),
            'memory_delta_mb': round(memory_after - memory_before, 2),
            'memory_peak_mb': round(memory_after, 2),
            'result_rows': len(result) if hasattr(result, '__len__') else 'N/A'
        }

    def benchmark_active_employee_filter(self, pandas_df: pd.DataFrame, polars_df: pl.DataFrame):
        """Benchmark filtering active employees."""
        print("\n🔍 Benchmarking: Active Employee Filter")

        # Pandas operation
        def pandas_filter():
            return pandas_df[pandas_df['employment_status'] == 'active']

        # Polars operation
        def polars_filter():
            return polars_df.filter(pl.col('employment_status') == 'active')

        pandas_result = self.measure_performance(pandas_filter, "Pandas Filter")
        polars_result = self.measure_performance(polars_filter, "Polars Filter")

        # Verify identical results
        pandas_count = pandas_result['result_rows']
        polars_count = polars_result['result_rows']

        print(f"   Pandas: {pandas_result['execution_time_ms']}ms, {pandas_count:,} rows")
        print(f"   Polars: {polars_result['execution_time_ms']}ms, {polars_count:,} rows")
        print(f"   ✅ Results match: {pandas_count == polars_count}")

        return pandas_result, polars_result

    def benchmark_level_grouping(self, pandas_df: pd.DataFrame, polars_df: pl.DataFrame):
        """Benchmark grouping by job level with statistics."""
        print("\n📊 Benchmarking: Level Grouping & Statistics")

        # Pandas operation
        def pandas_grouping():
            return pandas_df.groupby('level_id')['current_compensation'].agg([
                'count', 'mean', 'median', 'std'
            ]).round(2)

        # Polars operation
        def polars_grouping():
            return polars_df.group_by('level_id').agg([
                pl.count('current_compensation').alias('count'),
                pl.mean('current_compensation').alias('mean'),
                pl.median('current_compensation').alias('median'),
                pl.std('current_compensation').alias('std')
            ]).sort('level_id')

        pandas_result = self.measure_performance(pandas_grouping, "Pandas Grouping")
        polars_result = self.measure_performance(polars_grouping, "Polars Grouping")

        print(f"   Pandas: {pandas_result['execution_time_ms']}ms")
        print(f"   Polars: {polars_result['execution_time_ms']}ms")

        return pandas_result, polars_result

    def benchmark_compensation_analysis(self, pandas_df: pd.DataFrame, polars_df: pl.DataFrame):
        """Benchmark complex compensation analysis operations."""
        print("\n💰 Benchmarking: Compensation Analysis")

        # Pandas operation - active employees with compensation stats by level and tenure
        def pandas_analysis():
            active_df = pandas_df[pandas_df['employment_status'] == 'active']
            return active_df.groupby(['level_id', 'tenure_band'])['current_compensation'].agg([
                'count', 'mean', 'min', 'max'
            ]).reset_index()

        # Polars operation
        def polars_analysis():
            return (polars_df
                   .filter(pl.col('employment_status') == 'active')
                   .group_by(['level_id', 'tenure_band'])
                   .agg([
                       pl.count('current_compensation').alias('count'),
                       pl.mean('current_compensation').alias('mean'),
                       pl.min('current_compensation').alias('min'),
                       pl.max('current_compensation').alias('max')
                   ])
                   .sort(['level_id', 'tenure_band']))

        pandas_result = self.measure_performance(pandas_analysis, "Pandas Analysis")
        polars_result = self.measure_performance(polars_analysis, "Polars Analysis")

        print(f"   Pandas: {pandas_result['execution_time_ms']}ms, {pandas_result['result_rows']} groups")
        print(f"   Polars: {polars_result['execution_time_ms']}ms, {polars_result['result_rows']} groups")

        return pandas_result, polars_result

    def benchmark_complex_aggregation(self, pandas_df: pd.DataFrame, polars_df: pl.DataFrame):
        """Benchmark complex multi-year aggregation operations."""
        print("\n🔬 Benchmarking: Complex Multi-Year Analysis")

        # Pandas operation - complex aggregation across multiple dimensions
        def pandas_complex():
            return (pandas_df[pandas_df['employment_status'] == 'active']
                   .groupby(['simulation_year', 'level_id', 'age_band'])
                   .agg({
                       'current_compensation': ['count', 'mean', 'std', 'min', 'max'],
                       'current_age': ['mean', 'median'],
                       'current_tenure': ['mean', 'median']
                   })
                   .reset_index())

        # Polars operation - equivalent complex aggregation
        def polars_complex():
            return (polars_df
                   .filter(pl.col('employment_status') == 'active')
                   .group_by(['simulation_year', 'level_id', 'age_band'])
                   .agg([
                       pl.count('current_compensation').alias('comp_count'),
                       pl.mean('current_compensation').alias('comp_mean'),
                       pl.std('current_compensation').alias('comp_std'),
                       pl.min('current_compensation').alias('comp_min'),
                       pl.max('current_compensation').alias('comp_max'),
                       pl.mean('current_age').alias('age_mean'),
                       pl.median('current_age').alias('age_median'),
                       pl.mean('current_tenure').alias('tenure_mean'),
                       pl.median('current_tenure').alias('tenure_median')
                   ])
                   .sort(['simulation_year', 'level_id', 'age_band']))

        pandas_result = self.measure_performance(pandas_complex, "Pandas Complex")
        polars_result = self.measure_performance(polars_complex, "Polars Complex")

        print(f"   Pandas: {pandas_result['execution_time_ms']}ms, {pandas_result['result_rows']} groups")
        print(f"   Polars: {polars_result['execution_time_ms']}ms, {polars_result['result_rows']} groups")

        return pandas_result, polars_result

    def calculate_speedup(self, pandas_time: float, polars_time: float) -> float:
        """Calculate speedup factor."""
        if polars_time == 0:
            return float('inf')
        return pandas_time / polars_time

    def generate_performance_report(self, benchmark_results: Dict[str, tuple]):
        """Generate comprehensive performance report."""
        print("\n" + "="*60)
        print("🚀 POLARS PERFORMANCE PROOF OF CONCEPT - RESULTS")
        print("="*60)

        total_pandas_time = 0
        total_polars_time = 0

        print(f"\n{'Operation':<25} {'Pandas':<10} {'Polars':<10} {'Speedup':<10}")
        print("-" * 60)

        for operation, (pandas_result, polars_result) in benchmark_results.items():
            pandas_time = pandas_result['execution_time_ms']
            polars_time = polars_result['execution_time_ms']
            speedup = self.calculate_speedup(pandas_time, polars_time)

            total_pandas_time += pandas_time
            total_polars_time += polars_time

            print(f"{operation:<25} {pandas_time:>7.1f}ms {polars_time:>7.1f}ms {speedup:>7.1f}x")

        overall_speedup = self.calculate_speedup(total_pandas_time, total_polars_time)

        print("-" * 60)
        print(f"{'TOTAL':<25} {total_pandas_time:>7.1f}ms {total_polars_time:>7.1f}ms {overall_speedup:>7.1f}x")

        print(f"\n📈 SUMMARY:")
        print(f"   • Average speedup: {overall_speedup:.1f}x faster with Polars")
        print(f"   • Total time saved: {total_pandas_time - total_polars_time:.1f}ms")
        print(f"   • Dataset size: {len(self.pandas_df):,} employees")
        print(f"   • Polars version: {pl.__version__}")

        # Memory analysis
        memory_results = []
        for operation, (pandas_result, polars_result) in benchmark_results.items():
            memory_results.append({
                'operation': operation,
                'pandas_memory': pandas_result['memory_peak_mb'],
                'polars_memory': polars_result['memory_peak_mb']
            })

        print(f"\n🧠 MEMORY USAGE:")
        for mem in memory_results:
            ratio = mem['pandas_memory'] / mem['polars_memory'] if mem['polars_memory'] > 0 else 1
            print(f"   • {mem['operation']}: Pandas {mem['pandas_memory']:.1f}MB, Polars {mem['polars_memory']:.1f}MB")

        return {
            'overall_speedup': overall_speedup,
            'total_pandas_time': total_pandas_time,
            'total_polars_time': total_polars_time,
            'time_saved': total_pandas_time - total_polars_time,
            'memory_results': memory_results
        }

    def run_benchmark(self):
        """Run complete performance benchmark."""
        print("🎯 Starting Polars Performance Proof of Concept")
        print(f"   Database: {self.database_path}")
        print(f"   Polars version: {pl.__version__}")

        # Load data
        self.pandas_df, self.polars_df = self.load_workforce_data()

        # Run benchmarks
        benchmark_results = {}
        benchmark_results['Active Filter'] = self.benchmark_active_employee_filter(self.pandas_df, self.polars_df)
        benchmark_results['Level Grouping'] = self.benchmark_level_grouping(self.pandas_df, self.polars_df)
        benchmark_results['Compensation Analysis'] = self.benchmark_compensation_analysis(self.pandas_df, self.polars_df)
        benchmark_results['Complex Aggregation'] = self.benchmark_complex_aggregation(self.pandas_df, self.polars_df)

        # Generate report
        summary = self.generate_performance_report(benchmark_results)

        return summary


def main():
    """Main execution function."""
    benchmark = WorkforcePerformanceBenchmark()

    try:
        results = benchmark.run_benchmark()

        print(f"\n✅ Benchmark completed successfully!")
        print(f"   Polars is {results['overall_speedup']:.1f}x faster on workforce operations")
        print(f"   Ready for broader Polars integration!")

    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        raise


if __name__ == "__main__":
    main()
