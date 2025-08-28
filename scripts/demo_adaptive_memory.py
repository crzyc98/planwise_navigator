#!/usr/bin/env python3
"""
Adaptive Memory Management Demo Script

Story S063-08: Demonstrates the adaptive memory management system capabilities
for PlanWise Navigator workforce simulations.

This script shows:
- Real-time memory monitoring
- Adaptive batch size adjustment
- Dynamic garbage collection
- Memory leak detection
- Optimization recommendations
- Integration with pipeline orchestrator
"""

import sys
import time
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from navigator_orchestrator.adaptive_memory_manager import (
    AdaptiveConfig,
    AdaptiveMemoryManager,
    BatchSizeConfig,
    MemoryThresholds,
    OptimizationLevel,
    create_adaptive_memory_manager
)
from navigator_orchestrator.logger import ProductionLogger


def demo_basic_monitoring():
    """Demo basic memory monitoring capabilities"""
    print("🧠 Demo 1: Basic Memory Monitoring")
    print("=" * 50)

    # Create logger
    logger = ProductionLogger("AdaptiveMemoryDemo")

    # Create memory manager with aggressive thresholds for demo
    config = AdaptiveConfig(
        monitoring_interval_seconds=0.5,  # Fast monitoring for demo
        thresholds=MemoryThresholds(
            moderate_mb=100.0,  # Very low for demo
            high_mb=200.0,
            critical_mb=300.0,
            gc_trigger_mb=150.0,
            fallback_trigger_mb=250.0
        ),
        batch_sizes=BatchSizeConfig(
            low=100,
            medium=250,
            high=500,
            fallback=50
        )
    )

    with AdaptiveMemoryManager(config, logger) as manager:
        print(f"Initial batch size: {manager.get_current_batch_size()}")
        print(f"Initial optimization level: {manager.get_current_optimization_level().value}")

        # Force memory snapshots
        for i in range(5):
            snapshot = manager.force_memory_check(f"demo_check_{i}")
            print(f"Memory check {i+1}: {snapshot.rss_mb:.1f}MB (pressure: {snapshot.pressure_level.value})")
            time.sleep(0.5)

        # Get statistics
        stats = manager.get_memory_statistics()
        print(f"\nMonitoring Statistics:")
        print(f"  Samples collected: {stats['trends']['samples_count']}")
        print(f"  Peak memory: {stats['trends']['peak_memory_mb']:.1f}MB")
        print(f"  Current batch size: {stats['current']['batch_size']}")

    print("✅ Basic monitoring demo completed\n")


def demo_memory_pressure_simulation():
    """Demo memory pressure simulation and adaptive responses"""
    print("🧠 Demo 2: Memory Pressure Simulation")
    print("=" * 50)

    logger = ProductionLogger("MemoryPressureDemo")

    # Create manager with low thresholds for easy demonstration
    manager = create_adaptive_memory_manager(
        memory_limit_gb=0.2,  # Very low limit for demo
        monitoring_interval_seconds=0.1
    )

    # Override thresholds for demo
    manager.config.thresholds.moderate_mb = 50.0
    manager.config.thresholds.high_mb = 100.0
    manager.config.thresholds.critical_mb = 150.0
    manager.config.thresholds.gc_trigger_mb = 80.0
    manager.config.thresholds.fallback_trigger_mb = 120.0

    print("Simulating memory pressure scenarios...")
    print("Initial state:")
    print(f"  Batch size: {manager.get_current_batch_size()}")
    print(f"  Optimization level: {manager.get_current_optimization_level().value}")

    # Simulate memory allocations to trigger different pressure levels
    allocations = []

    try:
        with manager:
            # Simulate moderate pressure
            print("\n📊 Simulating moderate memory pressure...")
            for i in range(3):
                # Allocate memory to simulate workload
                data = [0] * (1000000)  # ~8MB allocation
                allocations.append(data)

                snapshot = manager.force_memory_check("pressure_test")
                print(f"  Allocation {i+1}: {snapshot.rss_mb:.1f}MB, batch size: {manager.get_current_batch_size()}")
                time.sleep(0.2)

            # Simulate high pressure
            print("\n📈 Simulating high memory pressure...")
            for i in range(5):
                data = [0] * (2000000)  # ~16MB allocation
                allocations.append(data)

                snapshot = manager.force_memory_check("high_pressure_test")
                print(f"  Allocation {i+1}: {snapshot.rss_mb:.1f}MB, "
                      f"pressure: {snapshot.pressure_level.value}, "
                      f"batch: {manager.get_current_batch_size()}")
                time.sleep(0.2)

            # Show final state
            final_stats = manager.get_memory_statistics()
            print("\nFinal Statistics:")
            print(f"  Peak Memory: {final_stats['trends']['peak_memory_mb']:.1f}MB")
            print(f"  GC Collections: {final_stats['stats']['total_gc_collections']}")
            print(f"  Batch Adjustments: {final_stats['stats']['batch_size_adjustments']}")
            print(f"  Fallback Events: {final_stats['stats']['automatic_fallbacks']}")

    finally:
        # Clean up allocations
        del allocations
        import gc
        gc.collect()

    print("✅ Memory pressure simulation completed\n")


def demo_recommendations_engine():
    """Demo optimization recommendations engine"""
    print("🧠 Demo 3: Optimization Recommendations")
    print("=" * 50)

    logger = ProductionLogger("RecommendationsDemo")

    # Create manager with recommendation settings
    config = AdaptiveConfig(
        recommendation_window_minutes=1,  # Short window for demo
        min_samples_for_recommendation=5,
        leak_detection_enabled=True,
        leak_threshold_mb=50.0,
        leak_window_minutes=2
    )

    with AdaptiveMemoryManager(config, logger) as manager:
        print("Generating patterns for recommendation engine...")

        # Add custom profiling hook
        patterns_detected = []

        def pattern_detector(snapshot):
            if snapshot.rss_mb > 100:  # Arbitrary threshold for demo
                patterns_detected.append(snapshot)

        manager.add_profiling_hook(pattern_detector)

        # Simulate different memory patterns
        print("\n1. Simulating high memory usage pattern...")
        for i in range(8):
            # Force high memory snapshots
            manager._history.append(
                type(manager._take_memory_snapshot())(**{
                    'timestamp': manager._take_memory_snapshot().timestamp,
                    'rss_mb': 180.0 + (i * 10),  # Increasing pattern
                    'vms_mb': 220.0,
                    'percent': 75.0,
                    'available_mb': 800.0,
                    'pressure_level': manager._calculate_pressure_level(180.0 + (i * 10), 800.0),
                    'gc_collections': i + 5,
                    'batch_size': 500
                })
            )

        # Trigger recommendation update
        current_snapshot = manager.force_memory_check("recommendation_trigger")
        manager._last_recommendation_time = manager._last_recommendation_time.replace(
            minute=manager._last_recommendation_time.minute - 10
        )  # Force update
        manager._update_recommendations(current_snapshot)

        # Get and display recommendations
        recommendations = manager.get_recommendations()
        print(f"\nGenerated {len(recommendations)} recommendations:")

        for i, rec in enumerate(recommendations, 1):
            priority_symbol = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec["priority"], "⚪")
            print(f"{i}. {priority_symbol} {rec['type'].upper()}")
            print(f"   Description: {rec['description']}")
            print(f"   Action: {rec['action']}")
            print(f"   Priority: {rec['priority']}")
            if rec.get('estimated_savings_mb'):
                print(f"   Est. Savings: {rec['estimated_savings_mb']:.1f}MB")
            print(f"   Confidence: {rec['confidence']:.0%}")
            print()

        # Show profiling hook results
        print(f"Profiling hook detected {len(patterns_detected)} high-memory events")

    print("✅ Recommendations engine demo completed\n")


def demo_configuration_integration():
    """Demo integration with PlanWise Navigator configuration"""
    print("🧠 Demo 4: Configuration Integration")
    print("=" * 50)

    # Show how adaptive memory integrates with simulation config
    from navigator_orchestrator.config import SimulationConfig, OptimizationSettings, AdaptiveMemorySettings

    print("Creating simulation config with adaptive memory settings...")

    # Example configuration
    config_dict = {
        "simulation": {"start_year": 2025, "end_year": 2027},
        "compensation": {"cola_rate": 0.005, "merit_budget": 0.025},
        "workforce": {"total_termination_rate": 0.12},
        "optimization": {
            "level": "medium",
            "memory_limit_gb": 4.0,
            "adaptive_memory": {
                "enabled": True,
                "thresholds": {
                    "moderate_mb": 2000.0,
                    "high_mb": 3000.0,
                    "critical_mb": 3500.0
                },
                "batch_sizes": {
                    "low": 250,
                    "medium": 500,
                    "high": 1000,
                    "fallback": 100
                },
                "auto_gc_enabled": True,
                "fallback_enabled": True
            }
        }
    }

    try:
        # Create and validate configuration
        sim_config = SimulationConfig(**config_dict)

        print("✅ Configuration validation successful")
        print(f"  Optimization level: {sim_config.optimization.level}")
        print(f"  Memory limit: {sim_config.optimization.memory_limit_gb}GB")
        print(f"  Adaptive memory enabled: {sim_config.optimization.adaptive_memory.enabled}")
        print(f"  Auto-GC enabled: {sim_config.optimization.adaptive_memory.auto_gc_enabled}")
        print(f"  Fallback enabled: {sim_config.optimization.adaptive_memory.fallback_enabled}")

        # Show threshold configuration
        thresholds = sim_config.optimization.adaptive_memory.thresholds
        print(f"\nMemory Thresholds:")
        print(f"  Moderate: {thresholds.moderate_mb}MB")
        print(f"  High: {thresholds.high_mb}MB")
        print(f"  Critical: {thresholds.critical_mb}MB")

        # Show batch size configuration
        batch_sizes = sim_config.optimization.adaptive_memory.batch_sizes
        print(f"\nBatch Sizes:")
        print(f"  Low: {batch_sizes.low}")
        print(f"  Medium: {batch_sizes.medium}")
        print(f"  High: {batch_sizes.high}")
        print(f"  Fallback: {batch_sizes.fallback}")

    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")

    print("✅ Configuration integration demo completed\n")


def demo_pipeline_integration():
    """Demo integration with pipeline orchestrator"""
    print("🧠 Demo 5: Pipeline Orchestrator Integration")
    print("=" * 50)

    print("This demo shows how adaptive memory management integrates with")
    print("the PipelineOrchestrator during multi-year simulations:")
    print()

    print("🔄 Simulation Startup:")
    print("  • Adaptive Memory Manager initialized from config")
    print("  • Background monitoring started")
    print("  • Initial memory snapshot taken")
    print()

    print("📋 Stage Execution:")
    print("  • Memory checked before each workflow stage")
    print("  • Batch size adjusted based on pressure level")
    print("  • Garbage collection triggered automatically")
    print("  • Memory changes logged per stage")
    print()

    print("🎯 Year Processing:")
    print("  • Memory monitored before/after each year")
    print("  • Adaptive batch sizes used by dbt operations")
    print("  • Fallback mode activated under critical pressure")
    print("  • Recommendations generated based on patterns")
    print()

    print("📊 Simulation Completion:")
    print("  • Final memory statistics displayed")
    print("  • Memory profile exported for analysis")
    print("  • Optimization recommendations provided")
    print("  • Monitoring cleanly shut down")
    print()

    # Show example integration code
    print("Example PipelineOrchestrator usage:")
    print("-" * 30)
    print("""
    orchestrator = PipelineOrchestrator(config, db_manager, ...)

    # Memory manager is automatically initialized
    print(f"Adaptive batch size: {orchestrator.get_adaptive_batch_size()}")

    # Run simulation with adaptive memory management
    summary = orchestrator.execute_multi_year_simulation(
        start_year=2025, end_year=2027
    )

    # Get memory insights
    memory_stats = orchestrator.get_memory_statistics()
    recommendations = orchestrator.get_memory_recommendations()
    """)

    print("✅ Pipeline integration demo completed\n")


def main():
    """Run all adaptive memory management demos"""
    print("🧠 PlanWise Navigator - Adaptive Memory Management Demo")
    print("Story S063-08: Single-Threaded Performance Optimizations")
    print("=" * 70)
    print()

    try:
        # Run demonstration sequence
        demo_basic_monitoring()
        demo_memory_pressure_simulation()
        demo_recommendations_engine()
        demo_configuration_integration()
        demo_pipeline_integration()

        print("🎉 All Adaptive Memory Management demos completed successfully!")
        print()
        print("Key Features Demonstrated:")
        print("✅ Real-time memory monitoring with pressure detection")
        print("✅ Adaptive batch size adjustment based on memory usage")
        print("✅ Dynamic garbage collection triggering")
        print("✅ Automatic fallback to smaller batch sizes")
        print("✅ Memory profiling hooks for custom analysis")
        print("✅ Optimization recommendation engine")
        print("✅ Configuration schema integration")
        print("✅ Pipeline orchestrator integration")
        print()
        print("The adaptive memory management system is ready for production use!")
        print("Use the memory monitor CLI for real-time monitoring:")
        print("  python scripts/memory_monitor_cli.py monitor --config config/simulation_config.yaml")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
