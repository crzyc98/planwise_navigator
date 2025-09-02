#!/usr/bin/env python3
"""
Test and Demonstration Script for Story S067-03: Advanced Memory Management & Optimization

This script demonstrates the capabilities of the ResourceManager system including:
- Memory usage monitoring per thread with configurable limits
- Real-time memory and CPU tracking during execution
- Memory pressure detection with automatic throttling mechanisms
- Adaptive thread scaling based on available system resources
- Resource contention detection and mitigation strategies
- Performance benchmarking framework for thread count optimization
- Graceful degradation when memory limits are approached

Usage:
    python scripts/test_resource_management.py [--config CONFIG_FILE] [--benchmark]
"""

import argparse
import time
from pathlib import Path
import sys

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from navigator_orchestrator.resource_manager import ResourceManager, PerformanceBenchmarker
from navigator_orchestrator.config import load_simulation_config
from navigator_orchestrator.logger import ProductionLogger


def simulate_memory_intensive_task(duration_seconds: float = 5.0, memory_mb: float = 100.0):
    """Simulate a memory-intensive task for testing purposes."""
    print(f"   🔬 Simulating memory-intensive task: {memory_mb:.0f}MB for {duration_seconds:.1f}s")

    # Allocate memory to simulate workload
    data = []
    chunk_size = 1024 * 1024  # 1MB chunks
    chunks_needed = int(memory_mb)

    for i in range(chunks_needed):
        # Allocate 1MB of data
        chunk = bytearray(chunk_size)
        data.append(chunk)

        # Brief pause to allow monitoring
        time.sleep(duration_seconds / chunks_needed)

        if i % 10 == 0:
            print(f"   📊 Allocated {i+1}/{chunks_needed} MB")

    # Keep data in memory for the remaining duration
    remaining_time = max(0, duration_seconds - 1.0)
    if remaining_time > 0:
        time.sleep(remaining_time)

    print(f"   ✅ Task completed, releasing {len(data)}MB")
    return len(data)


def simulate_cpu_intensive_task(duration_seconds: float = 5.0, intensity: float = 0.8):
    """Simulate a CPU-intensive task for testing purposes."""
    print(f"   🔬 Simulating CPU-intensive task: {intensity*100:.0f}% intensity for {duration_seconds:.1f}s")

    start_time = time.time()
    work_time = duration_seconds * intensity
    sleep_time = duration_seconds * (1 - intensity)

    # Alternate between CPU work and sleep
    while time.time() - start_time < duration_seconds:
        # CPU intensive work
        work_start = time.time()
        count = 0
        while time.time() - work_start < 0.1:  # 100ms bursts
            count += 1

        # Brief sleep to control overall CPU usage
        if sleep_time > 0:
            time.sleep(0.1 * (1 - intensity))

    print(f"   ✅ CPU task completed, performed {count} operations")
    return count


def test_memory_monitoring(resource_manager: ResourceManager):
    """Test memory monitoring capabilities."""
    print("🧠 Testing Memory Monitoring")
    print("=" * 50)

    # Get baseline memory usage
    initial_status = resource_manager.get_resource_status()
    print(f"Initial memory usage: {initial_status['memory']['usage_mb']:.0f}MB")
    print(f"Initial memory pressure: {initial_status['memory']['pressure']}")

    # Test memory pressure detection with different load levels
    test_scenarios = [
        (50, 2.0, "Light load"),
        (200, 3.0, "Moderate load"),
        (500, 2.0, "Heavy load"),
    ]

    for memory_mb, duration, description in test_scenarios:
        print(f"\n📊 {description}: {memory_mb}MB for {duration}s")

        with resource_manager.monitor_execution(f"memory_test_{description.lower().replace(' ', '_')}", 1):
            simulate_memory_intensive_task(duration, memory_mb)

        # Check resource status
        status = resource_manager.get_resource_status()
        print(f"   Memory after test: {status['memory']['usage_mb']:.0f}MB")
        print(f"   Memory pressure: {status['memory']['pressure']}")
        print(f"   Leak detected: {status['memory']['leak_detected']}")

        # Allow memory to settle
        time.sleep(1.0)

    # Test memory trends analysis
    print("\n📈 Memory Trends Analysis")
    trends = resource_manager.memory_monitor.get_memory_trends(window_minutes=2)
    print(f"   Trend: {trends['trend']}")
    print(f"   Growth rate: {trends['growth_rate_mb_per_minute']:.1f} MB/min")
    print(f"   Peak usage: {trends['peak_usage_mb']:.0f}MB")
    print(f"   Average usage: {trends['average_usage_mb']:.0f}MB")


def test_cpu_monitoring(resource_manager: ResourceManager):
    """Test CPU monitoring capabilities."""
    print("\n🖥️ Testing CPU Monitoring")
    print("=" * 50)

    # Get baseline CPU usage
    initial_status = resource_manager.get_resource_status()
    print(f"Initial CPU usage: {initial_status['cpu']['current_percent']:.1f}%")

    # Test CPU pressure detection with different intensities
    test_scenarios = [
        (0.3, 3.0, "Light CPU load"),
        (0.6, 3.0, "Moderate CPU load"),
        (0.9, 2.0, "Heavy CPU load"),
    ]

    for intensity, duration, description in test_scenarios:
        print(f"\n📊 {description}: {intensity*100:.0f}% intensity for {duration}s")

        with resource_manager.monitor_execution(f"cpu_test_{description.lower().replace(' ', '_')}", 1):
            simulate_cpu_intensive_task(duration, intensity)

        # Check resource status
        status = resource_manager.get_resource_status()
        print(f"   CPU after test: {status['cpu']['current_percent']:.1f}%")
        print(f"   CPU pressure: {resource_manager.cpu_monitor.get_current_pressure()}")

        # Allow CPU to settle
        time.sleep(1.0)

    # Test CPU trends analysis
    print("\n📈 CPU Trends Analysis")
    trends = resource_manager.cpu_monitor.get_cpu_trends(window_minutes=2)
    print(f"   Average CPU: {trends['average_cpu']:.1f}%")
    print(f"   Peak CPU: {trends['peak_cpu']:.1f}%")
    print(f"   Load average: {trends['load_average_1m']:.2f}")


def test_adaptive_thread_scaling(resource_manager: ResourceManager):
    """Test adaptive thread count optimization."""
    print("\n🔧 Testing Adaptive Thread Scaling")
    print("=" * 50)

    # Test thread count recommendations under different load conditions
    test_scenarios = [
        (1, "baseline"),
        (2, "low_load"),
        (4, "moderate_load"),
        (6, "high_load"),
        (8, "max_load"),
    ]

    for thread_count, scenario in test_scenarios:
        print(f"\n📊 Testing with {thread_count} threads ({scenario})")

        # Simulate some load to influence recommendations
        if scenario != "baseline":
            with resource_manager.monitor_execution(f"scaling_test_{scenario}", thread_count):
                # Simulate mixed workload
                simulate_memory_intensive_task(1.5, 100 * thread_count)
                simulate_cpu_intensive_task(1.5, 0.5)

        # Get thread count recommendation
        optimal_threads, reason = resource_manager.optimize_thread_count(
            thread_count,
            {"test_scenario": scenario}
        )

        print(f"   Current threads: {thread_count}")
        print(f"   Recommended threads: {optimal_threads}")
        print(f"   Reason: {reason}")

        # Record performance data
        execution_time = 3.0 + (thread_count * 0.1)  # Simulate decreasing execution time
        resource_manager.thread_adjuster.record_performance(thread_count, execution_time)

        time.sleep(0.5)  # Brief pause between tests


def test_performance_benchmarking(resource_manager: ResourceManager):
    """Test performance benchmarking framework."""
    print("\n🏆 Testing Performance Benchmarking")
    print("=" * 50)

    def benchmark_function(thread_count: int) -> float:
        """Simulate a benchmark function that benefits from parallelization."""
        print(f"   Running benchmark with {thread_count} threads...")

        # Simulate work that benefits from parallelization with diminishing returns
        base_time = 10.0
        parallel_efficiency = min(1.0, thread_count * 0.7)  # 70% efficiency per thread
        execution_time = base_time / parallel_efficiency

        # Add some realistic variation
        import random
        variation = random.uniform(0.9, 1.1)
        execution_time *= variation

        # Simulate memory usage that increases with thread count
        memory_usage = 50 * thread_count
        simulate_memory_intensive_task(execution_time * 0.1, memory_usage)

        # Brief CPU work
        simulate_cpu_intensive_task(execution_time * 0.2, 0.5)

        # Simulate remaining execution time
        time.sleep(execution_time * 0.7)

        return execution_time

    # Run benchmark suite
    benchmarker = PerformanceBenchmarker(
        resource_manager.memory_monitor,
        resource_manager.cpu_monitor
    )

    results = benchmarker.run_benchmark_suite(
        benchmark_function,
        baseline_thread_count=1,
        max_thread_count=6
    )

    # Analyze results
    analysis = benchmarker.analyze_benchmark_results(results)

    print(f"\n📊 Benchmark Results Summary:")
    print(f"   Optimal thread count: {analysis['optimal_thread_count']}")
    print(f"   Best efficiency: {analysis['max_efficiency']:.2f}")
    print(f"   Best speedup: {analysis['max_speedup']:.2f}x")
    print(f"   Recommendation: {analysis['recommendation']}")

    print(f"\n📋 Detailed Results:")
    for result in analysis['results_summary']:
        print(f"   {result['threads']} threads: {result['speedup']:.2f}x speedup, "
              f"{result['efficiency']:.2f} efficiency, {result['memory_mb']:.0f}MB memory")


def test_resource_cleanup(resource_manager: ResourceManager):
    """Test resource cleanup functionality."""
    print("\n🧹 Testing Resource Cleanup")
    print("=" * 50)

    # Get initial state
    initial_status = resource_manager.get_resource_status()
    print(f"Initial memory: {initial_status['memory']['usage_mb']:.0f}MB")

    # Create some memory pressure
    print("Creating memory pressure...")
    simulate_memory_intensive_task(2.0, 300)

    # Check memory before cleanup
    before_cleanup = resource_manager.get_resource_status()
    print(f"Memory before cleanup: {before_cleanup['memory']['usage_mb']:.0f}MB")

    # Trigger cleanup
    cleanup_result = resource_manager.trigger_resource_cleanup()
    print(f"Memory freed: {cleanup_result['memory_freed_mb']:+.1f}MB")
    print(f"Cleanup effective: {cleanup_result['cleanup_effective']}")

    # Check memory after cleanup
    after_cleanup = resource_manager.get_resource_status()
    print(f"Memory after cleanup: {after_cleanup['memory']['usage_mb']:.0f}MB")


def main():
    """Main test runner for Resource Management system."""
    parser = argparse.ArgumentParser(description="Test Advanced Resource Management System")
    parser.add_argument(
        "--config",
        type=str,
        default="config/simulation_config_with_resource_management.yaml",
        help="Path to simulation configuration file"
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run performance benchmarking tests"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    print("🚀 PlanWise Navigator - Advanced Resource Management Test Suite")
    print("=" * 70)
    print("Story S067-03: Advanced Memory Management & Optimization")
    print("=" * 70)

    try:
        # Load configuration
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"❌ Configuration file not found: {config_path}")
            print("   Please run from the project root or specify --config path")
            return 1

        print(f"📖 Loading configuration from: {config_path}")
        config = load_simulation_config(config_path)

        # Check if resource management is enabled
        if not (hasattr(config, 'orchestrator') and
                config.orchestrator and
                hasattr(config.orchestrator.threading, 'resource_management') and
                config.orchestrator.threading.resource_management.enabled):
            print("❌ Resource management is not enabled in configuration")
            print("   Please use config/simulation_config_with_resource_management.yaml")
            return 1

        # Create logger
        logger = ProductionLogger(log_level="INFO" if args.verbose else "WARNING")

        # Build resource manager configuration
        rm_config = config.orchestrator.threading.resource_management
        resource_config = {
            "memory": {
                "monitoring_interval": rm_config.memory_monitoring.monitoring_interval_seconds,
                "history_size": rm_config.memory_monitoring.history_size,
                "thresholds": {
                    "moderate_mb": rm_config.memory_monitoring.thresholds.moderate_mb,
                    "high_mb": rm_config.memory_monitoring.thresholds.high_mb,
                    "critical_mb": rm_config.memory_monitoring.thresholds.critical_mb,
                    "gc_trigger_mb": rm_config.memory_monitoring.thresholds.gc_trigger_mb,
                    "fallback_trigger_mb": rm_config.memory_monitoring.thresholds.fallback_trigger_mb
                }
            },
            "cpu": {
                "monitoring_interval": rm_config.cpu_monitoring.monitoring_interval_seconds,
                "history_size": rm_config.cpu_monitoring.history_size,
                "thresholds": {
                    "moderate_percent": rm_config.cpu_monitoring.thresholds.moderate_percent,
                    "high_percent": rm_config.cpu_monitoring.thresholds.high_percent,
                    "critical_percent": rm_config.cpu_monitoring.thresholds.critical_percent
                }
            }
        }

        # Create ResourceManager
        print("🏗️ Initializing ResourceManager...")
        resource_manager = ResourceManager(config=resource_config, logger=logger)

        # Configure thread adjuster
        resource_manager.thread_adjuster.min_threads = rm_config.min_threads
        resource_manager.thread_adjuster.max_threads = rm_config.max_threads
        resource_manager.thread_adjuster.adjustment_cooldown = rm_config.adjustment_cooldown_seconds

        # Start monitoring
        resource_manager.start_monitoring()
        print("✅ Resource monitoring started")

        # Wait for monitoring to initialize
        time.sleep(2.0)

        try:
            # Run test suite
            test_memory_monitoring(resource_manager)
            test_cpu_monitoring(resource_manager)
            test_adaptive_thread_scaling(resource_manager)
            test_resource_cleanup(resource_manager)

            if args.benchmark:
                test_performance_benchmarking(resource_manager)

            # Final summary
            print("\n📊 Final Resource Summary")
            print("=" * 50)
            final_status = resource_manager.get_resource_status()
            print(f"Final memory usage: {final_status['memory']['usage_mb']:.0f}MB")
            print(f"Final memory pressure: {final_status['memory']['pressure']}")
            print(f"Final CPU usage: {final_status['cpu']['current_percent']:.1f}%")
            print(f"Memory leak detected: {final_status['memory']['leak_detected']}")

            # Thread adjustment history
            history = resource_manager.thread_adjuster.adjustment_history
            if history:
                print(f"Thread adjustments made: {len(history)}")
                for adj in history[-3:]:
                    print(f"   {adj['old_thread_count']} → {adj['new_thread_count']} ({adj['reason']})")
            else:
                print("No thread adjustments were made during testing")

            print("\n🎉 All tests completed successfully!")
            return 0

        finally:
            # Stop monitoring
            print("\n🛑 Stopping resource monitoring...")
            resource_manager.stop_monitoring()
            print("✅ Resource monitoring stopped")

    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
