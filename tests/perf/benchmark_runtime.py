# filename: tests/perf/benchmark_runtime.py
"""Performance benchmark harness for PlanWise Navigator."""

import time
import psutil
import pandas as pd
from contextlib import contextmanager
from typing import Dict, Any, List
import duckdb
from pathlib import Path
import json
from datetime import datetime

from planwise_navigator.config.schema import SimulationConfig
from orchestrator.resources.duckdb_resource import DuckDBResource

class BenchmarkResult:
    """Container for benchmark results."""
    
    def __init__(self, name: str):
        self.name = name
        self.start_time = None
        self.end_time = None
        self.duration = None
        self.memory_start = None
        self.memory_peak = None
        self.memory_end = None
        self.cpu_percent = []
        self.metrics = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'duration_seconds': self.duration,
            'memory_start_mb': self.memory_start,
            'memory_peak_mb': self.memory_peak,
            'memory_delta_mb': self.memory_end - self.memory_start if self.memory_end and self.memory_start else None,
            'avg_cpu_percent': sum(self.cpu_percent) / len(self.cpu_percent) if self.cpu_percent else 0,
            'metrics': self.metrics
        }

@contextmanager
def benchmark(name: str) -> BenchmarkResult:
    """Context manager for benchmarking code blocks."""
    result = BenchmarkResult(name)
    process = psutil.Process()
    
    # Start measurements
    result.memory_start = process.memory_info().rss / 1024 / 1024  # MB
    result.start_time = time.time()
    
    # CPU monitoring in background
    cpu_samples = []
    
    try:
        yield result
    finally:
        # End measurements
        result.end_time = time.time()
        result.duration = result.end_time - result.start_time
        result.memory_end = process.memory_info().rss / 1024 / 1024
        result.memory_peak = max(result.memory_start, result.memory_end)  # TODO: Track actual peak
        
        print(f"[{name}] Duration: {result.duration:.2f}s, "
              f"Memory: {result.memory_start:.1f}MB -> {result.memory_end:.1f}MB")

def benchmark_data_loading(db_path: str, num_employees: int) -> BenchmarkResult:
    """Benchmark census data loading."""
    with benchmark(f"data_loading_{num_employees}_employees") as result:
        conn = duckdb.connect(db_path)
        
        # Create and load data
        conn.execute("""
            CREATE TABLE IF NOT EXISTS census_data (
                employee_id VARCHAR PRIMARY KEY,
                level_id INTEGER,
                age INTEGER,
                tenure_years DECIMAL,
                current_compensation DECIMAL,
                active_flag BOOLEAN
            )
        """)
        
        # Generate data
        df = pd.DataFrame({
            'employee_id': [f'E{i:06d}' for i in range(num_employees)],
            'level_id': [((i % 5) + 1) for i in range(num_employees)],
            'age': [(25 + (i % 40)) for i in range(num_employees)],
            'tenure_years': [(i % 20) * 0.5 for i in range(num_employees)],
            'current_compensation': [40000 + (i % 5) * 20000 for i in range(num_employees)],
            'active_flag': [True] * num_employees
        })
        
        conn.register('census_df', df)
        conn.execute("INSERT INTO census_data SELECT * FROM census_df")
        
        result.metrics['rows_loaded'] = num_employees
        conn.close()
    
    return result

def benchmark_simulation_year(db_path: str, year: int) -> BenchmarkResult:
    """Benchmark single year simulation."""
    with benchmark(f"simulation_year_{year}") as result:
        conn = duckdb.connect(db_path)
        
        # Simulate event generation
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS events_{year} AS
            SELECT 
                'EV' || ROW_NUMBER() OVER () as event_id,
                employee_id,
                CASE 
                    WHEN RANDOM() < 0.15 THEN 'promotion'
                    WHEN RANDOM() < 0.12 THEN 'termination'
                    WHEN RANDOM() < 0.8 THEN 'merit'
                    ELSE 'none'
                END as event_type,
                {year} as simulation_year
            FROM census_data
            WHERE active_flag = true
        """)
        
        event_count = conn.execute(f"SELECT COUNT(*) FROM events_{year}").fetchone()[0]
        result.metrics['events_generated'] = event_count
        
        # Create workforce snapshot
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS workforce_snapshot_{year} AS
            SELECT 
                c.*,
                {year} as simulation_year,
                COUNT(e.event_id) as event_count
            FROM census_data c
            LEFT JOIN events_{year} e ON c.employee_id = e.employee_id
            GROUP BY c.employee_id, c.level_id, c.age, c.tenure_years, 
                     c.current_compensation, c.active_flag
        """)
        
        snapshot_count = conn.execute(f"SELECT COUNT(*) FROM workforce_snapshot_{year}").fetchone()[0]
        result.metrics['snapshot_size'] = snapshot_count
        
        conn.close()
    
    return result

def benchmark_analytics_queries(db_path: str) -> List[BenchmarkResult]:
    """Benchmark analytical queries."""
    queries = [
        ("level_distribution", """
            SELECT level_id, COUNT(*) as count, AVG(current_compensation) as avg_comp
            FROM workforce_snapshot_2025
            GROUP BY level_id
            ORDER BY level_id
        """),
        ("age_analysis", """
            SELECT 
                CASE 
                    WHEN age < 30 THEN 'Under 30'
                    WHEN age < 40 THEN '30-39'
                    WHEN age < 50 THEN '40-49'
                    ELSE '50+'
                END as age_band,
                COUNT(*) as count,
                AVG(current_compensation) as avg_comp
            FROM workforce_snapshot_2025
            GROUP BY age_band
            ORDER BY age_band
        """),
        ("complex_aggregation", """
            WITH ranked_employees AS (
                SELECT 
                    *,
                    ROW_NUMBER() OVER (PARTITION BY level_id ORDER BY current_compensation DESC) as comp_rank
                FROM workforce_snapshot_2025
            )
            SELECT 
                level_id,
                COUNT(*) as total,
                AVG(CASE WHEN comp_rank <= 10 THEN current_compensation END) as top10_avg_comp,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY current_compensation) as median_comp
            FROM ranked_employees
            GROUP BY level_id
        """)
    ]
    
    results = []
    conn = duckdb.connect(db_path)
    
    for query_name, query in queries:
        with benchmark(f"query_{query_name}") as result:
            df = conn.execute(query).df()
            result.metrics['rows_returned'] = len(df)
            results.append(result)
    
    conn.close()
    return results

def run_full_benchmark():
    """Run complete benchmark suite."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_path = f"benchmark_{timestamp}.duckdb"
    
    all_results = []
    
    try:
        # Test different data sizes
        for num_employees in [1000, 10000, 50000, 100000]:
            print(f"\n=== Benchmarking with {num_employees} employees ===")
            
            # Data loading
            result = benchmark_data_loading(db_path, num_employees)
            all_results.append(result.to_dict())
            
            # Single year simulation
            result = benchmark_simulation_year(db_path, 2025)
            all_results.append(result.to_dict())
            
            # Analytics queries
            query_results = benchmark_analytics_queries(db_path)
            all_results.extend([r.to_dict() for r in query_results])
            
            # Multi-year simulation
            with benchmark(f"multi_year_5years_{num_employees}_employees") as result:
                for year in range(2025, 2030):
                    benchmark_simulation_year(db_path, year)
                result.metrics['years_simulated'] = 5
                result.metrics['employee_count'] = num_employees
                all_results.append(result.to_dict())
        
        # Save results
        results_df = pd.DataFrame(all_results)
        results_df['timestamp'] = timestamp
        
        output_path = f"benchmark_results_{timestamp}.csv"
        results_df.to_csv(output_path, index=False)
        
        print(f"\n=== Benchmark Results Summary ===")
        print(results_df.groupby('name')[['duration_seconds', 'memory_delta_mb']].mean())
        print(f"\nDetailed results saved to: {output_path}")
        
    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)

if __name__ == "__main__":
    run_full_benchmark()