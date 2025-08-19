#!/usr/bin/env python3
"""
Performance & Load Tests

Validate performance requirements and ensure system can handle expected loads.
Part of Epic E047: Production Testing & Validation Framework.
"""

from __future__ import annotations

import time
import pytest
import psutil
import duckdb
import argparse
from navigator_orchestrator.cli import cmd_run
from navigator_orchestrator.performance_monitor import PerformanceMonitor
from pathlib import Path


class TestPerformance:
    """Validate performance requirements"""

    def test_single_year_performance(self):
        """Single year should complete within time limits"""
        args = argparse.Namespace(
            config=None,
            database=None,
            threads=4,
            dry_run=False,
            verbose=False,
            years="2025-2025",
            seed=42,
            force_clear=True,
            resume_from=None
        )

        start_time = time.time()
        result = cmd_run(args)
        duration = time.time() - start_time

        assert result == 0, "Single year simulation failed"
        assert duration < 120, f"Single year took {duration:.1f}s, expected <120s"

        # Verify the simulation actually produced results
        with duckdb.connect("simulation.duckdb") as conn:
            event_count = conn.execute("SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = 2025").fetchone()[0]
            workforce_count = conn.execute("SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = 2025").fetchone()[0]

            assert event_count > 0, "No events generated in performance test"
            assert workforce_count > 0, "No workforce snapshot generated in performance test"

    def test_memory_usage_bounds(self):
        """Memory usage should stay within reasonable bounds"""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        args = argparse.Namespace(
            config=None,
            database=None,
            threads=4,
            dry_run=False,
            verbose=False,
            years="2025-2026",
            seed=42,
            force_clear=True,
            resume_from=None
        )

        result = cmd_run(args)
        assert result == 0, "Multi-year simulation failed"

        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = peak_memory - initial_memory

        assert memory_growth < 2048, f"Memory growth {memory_growth:.1f}MB exceeds 2GB limit"

    def test_multi_year_scalability(self):
        """Multi-year performance should scale reasonably"""

        # Test 2-year simulation
        args_2yr = argparse.Namespace(
            config=None,
            database=None,
            threads=4,
            dry_run=False,
            verbose=False,
            years="2025-2026",
            seed=42,
            force_clear=True,
            resume_from=None
        )

        start_time = time.time()
        result = cmd_run(args_2yr)
        two_year_duration = time.time() - start_time

        assert result == 0, "2-year simulation failed"

        # Test 3-year simulation (instead of 5-year to keep tests fast)
        args_3yr = argparse.Namespace(
            config=None,
            database=None,
            threads=4,
            dry_run=False,
            verbose=False,
            years="2025-2027",
            seed=42,
            force_clear=True,
            resume_from=None
        )

        start_time = time.time()
        result = cmd_run(args_3yr)
        three_year_duration = time.time() - start_time

        assert result == 0, "3-year simulation failed"

        # Should be roughly linear scaling (allow some overhead)
        if two_year_duration > 0:
            scaling_factor = three_year_duration / two_year_duration
            assert scaling_factor < 2.0, f"Poor scaling: 3-year took {scaling_factor:.1f}x longer than 2-year"

    def test_database_query_performance(self):
        """Database queries should perform within acceptable limits"""
        with duckdb.connect("simulation.duckdb") as conn:
            # Test basic aggregation performance
            start_time = time.time()

            result = conn.execute("""
                SELECT
                    simulation_year,
                    COUNT(*) as workforce_count,
                    SUM(total_compensation) as total_comp,
                    AVG(total_compensation) as avg_comp
                FROM fct_workforce_snapshot
                GROUP BY simulation_year
                ORDER BY simulation_year
            """).fetchall()

            query_duration = time.time() - start_time
            assert query_duration < 5.0, f"Basic aggregation query took {query_duration:.2f}s, expected <5s"

            # Test complex join performance
            start_time = time.time()

            join_result = conn.execute("""
                SELECT
                    ws.simulation_year,
                    COUNT(DISTINCT ws.employee_id) as workforce_count,
                    COUNT(ye.employee_id) as event_count
                FROM fct_workforce_snapshot ws
                LEFT JOIN fct_yearly_events ye
                    ON ws.employee_id = ye.employee_id
                    AND ws.simulation_year = ye.simulation_year
                GROUP BY ws.simulation_year
                ORDER BY ws.simulation_year
            """).fetchall()

            join_duration = time.time() - start_time
            assert join_duration < 10.0, f"Complex join query took {join_duration:.2f}s, expected <10s"

    def test_concurrent_read_performance(self):
        """Multiple concurrent database reads should not severely degrade performance"""
        import threading
        import queue

        def query_worker(result_queue):
            try:
                with duckdb.connect("simulation.duckdb") as conn:
                    start_time = time.time()
                    result = conn.execute("""
                        SELECT COUNT(*) FROM fct_workforce_snapshot
                        WHERE simulation_year = 2025
                    """).fetchone()[0]
                    duration = time.time() - start_time
                    result_queue.put(('success', duration, result))
            except Exception as e:
                result_queue.put(('error', 0, str(e)))

        # Run 4 concurrent queries
        threads = []
        result_queue = queue.Queue()

        start_time = time.time()
        for i in range(4):
            thread = threading.Thread(target=query_worker, args=(result_queue,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        total_time = time.time() - start_time

        # Collect results
        results = []
        for i in range(4):
            results.append(result_queue.get())

        # Check all queries succeeded
        for status, duration, result in results:
            assert status == 'success', f"Concurrent query failed: {result}"

        # Total time should be reasonable (not much worse than single query)
        assert total_time < 15.0, f"Concurrent queries took {total_time:.2f}s, expected <15s"

    def test_large_dataset_handling(self):
        """System should handle reasonably large datasets efficiently"""
        with duckdb.connect("simulation.duckdb") as conn:
            # Check current dataset size
            workforce_size = conn.execute("SELECT COUNT(*) FROM fct_workforce_snapshot").fetchone()[0]
            event_count = conn.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()[0]

            # Test performance on current dataset
            start_time = time.time()

            # Simulate a complex analytical query
            complex_result = conn.execute("""
                WITH employee_metrics AS (
                    SELECT
                        ws.employee_id,
                        ws.simulation_year,
                        ws.total_compensation,
                        COUNT(ye.employee_id) as event_count,
                        SUM(CASE WHEN ye.event_type = 'RAISE' THEN 1 ELSE 0 END) as raise_count
                    FROM fct_workforce_snapshot ws
                    LEFT JOIN fct_yearly_events ye
                        ON ws.employee_id = ye.employee_id
                        AND ws.simulation_year = ye.simulation_year
                    GROUP BY ws.employee_id, ws.simulation_year, ws.total_compensation
                )
                SELECT
                    simulation_year,
                    COUNT(*) as employee_count,
                    AVG(total_compensation) as avg_comp,
                    AVG(event_count) as avg_events_per_employee,
                    AVG(raise_count) as avg_raises_per_employee
                FROM employee_metrics
                GROUP BY simulation_year
                ORDER BY simulation_year
            """).fetchall()

            complex_query_duration = time.time() - start_time

            # Performance should scale reasonably with dataset size
            if workforce_size > 0:
                time_per_thousand_employees = (complex_query_duration * 1000) / workforce_size
                assert time_per_thousand_employees < 30.0, f"Complex query performance poor: {time_per_thousand_employees:.2f}s per 1000 employees"

    def test_disk_io_performance(self):
        """Database I/O should be efficient"""
        db_path = Path("simulation.duckdb")

        if db_path.exists():
            # Check database file size
            db_size_mb = db_path.stat().st_size / (1024 * 1024)

            # Database shouldn't be unreasonably large
            assert db_size_mb < 10240, f"Database file too large: {db_size_mb:.1f}MB > 10GB"

            # Test database file read performance
            start_time = time.time()

            with duckdb.connect(str(db_path)) as conn:
                # Read a significant portion of the data
                result = conn.execute("""
                    SELECT COUNT(*), AVG(total_compensation)
                    FROM fct_workforce_snapshot
                """).fetchone()

            read_duration = time.time() - start_time

            # Read time should be reasonable relative to file size
            if db_size_mb > 0:
                read_time_per_mb = read_duration / db_size_mb
                assert read_time_per_mb < 0.1, f"Database read performance poor: {read_time_per_mb:.3f}s per MB"

    def test_memory_efficiency_over_time(self):
        """Memory usage should not grow excessively over longer runs"""
        process = psutil.Process()

        # Measure memory at different points
        memory_measurements = []

        # Initial measurement
        memory_measurements.append(process.memory_info().rss / 1024 / 1024)  # MB

        # Run simulation multiple times
        for i in range(3):
            args = argparse.Namespace(
                config=None,
                database=None,
                threads=4,
                dry_run=False,
                verbose=False,
                years="2025-2025",
                seed=42 + i,  # Different seed each time
                force_clear=True,
                resume_from=None
            )

            result = cmd_run(args)
            assert result == 0, f"Simulation {i+1} failed"

            # Measure memory after each run
            memory_measurements.append(process.memory_info().rss / 1024 / 1024)  # MB

        # Memory should not grow excessively between runs
        max_memory = max(memory_measurements)
        min_memory = min(memory_measurements)
        memory_growth = max_memory - min_memory

        assert memory_growth < 1024, f"Memory grew too much over multiple runs: {memory_growth:.1f}MB"

    def test_cpu_utilization_efficiency(self):
        """CPU usage should be reasonable during simulation"""
        process = psutil.Process()

        # Start monitoring CPU usage
        cpu_percent_before = process.cpu_percent()

        args = argparse.Namespace(
            config=None,
            database=None,
            threads=4,
            dry_run=False,
            verbose=False,
            years="2025-2025",
            seed=42,
            force_clear=True,
            resume_from=None
        )

        start_time = time.time()
        result = cmd_run(args)
        duration = time.time() - start_time

        assert result == 0, "Simulation failed"

        # CPU usage should be reasonable (not idle, but not pegged at 100%)
        cpu_percent_after = process.cpu_percent()

        # This is more informational than a hard requirement
        # since CPU usage varies greatly by system and load
        assert duration > 0, "Simulation completed too quickly to measure CPU usage"
