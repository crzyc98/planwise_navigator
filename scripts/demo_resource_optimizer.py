#!/usr/bin/env python3
"""
Demonstration script for ResourceOptimizer component (Story S031-04).

This script demonstrates the key features of the ResourceOptimizer:
- Memory optimization with streaming and chunking strategies
- I/O optimization for checkpointing and result persistence
- Resource monitoring and performance tracking
- Adaptive optimization based on simulation parameters

Usage:
    python scripts/demo_resource_optimizer.py [--workforce-size SIZE] [--years YEARS]
"""

import sys
import time
import logging
from pathlib import Path
from typing import List

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator_mvp.utils.resource_optimizer import (
    ResourceOptimizer,
    PersistenceLevel,
    create_resource_optimizer,
    get_system_resource_status
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def demo_system_status():
    """Demonstrate system resource status analysis."""
    print("\n" + "="*60)
    print("SYSTEM RESOURCE STATUS ANALYSIS")
    print("="*60)

    status = get_system_resource_status()

    print(f"Memory: {status['memory']['available_gb']:.1f}GB available / {status['memory']['total_gb']:.1f}GB total")
    print(f"Memory Usage: {status['memory']['used_percentage']:.1f}% (pressure: {status['memory']['pressure_level']})")
    print(f"CPU: {status['cpu']['logical_cores']} cores, {status['cpu']['current_usage_percentage']:.1f}% current usage")
    print(f"Disk: {status['disk']['free_space_gb']:.1f}GB free space")

    print(f"\nRecommendations:")
    print(f"- Suitable for large simulation: {'Yes' if status['recommendations']['suitable_for_large_simulation'] else 'No'}")
    print(f"- Recommended max memory: {status['recommendations']['recommended_max_memory_gb']:.1f}GB")
    print(f"- Streaming recommended: {'Yes' if status['recommendations']['streaming_recommended'] else 'No'}")


def demo_memory_optimization(workforce_sizes: List[int], simulation_years: List[int]):
    """Demonstrate memory optimization for different simulation scenarios."""
    print("\n" + "="*60)
    print("MEMORY OPTIMIZATION ANALYSIS")
    print("="*60)

    optimizer = create_resource_optimizer(enable_monitoring=False)

    for workforce_size in workforce_sizes:
        print(f"\nWorkforce Size: {workforce_size:,} employees, Years: {len(simulation_years)}")
        print("-" * 50)

        try:
            # Get memory optimization recommendations
            memory_result = optimizer.optimize_memory_usage(simulation_years, workforce_size)

            print(f"Strategy: {memory_result.strategy_type}")
            print(f"Memory Savings: {memory_result.memory_savings_gb:.1f}GB")
            print(f"Efficiency Rating: {memory_result.efficiency_rating}")
            print(f"Recommended Chunk Size: {memory_result.recommended_chunk_size:,} employees")
            print(f"Estimated Processing Time: {memory_result.estimated_processing_time_minutes:.1f} minutes")

            print(f"Performance Impact: {memory_result.performance_impact}")

        except Exception as e:
            print(f"Error optimizing memory for {workforce_size:,} employees: {e}")


def demo_io_optimization():
    """Demonstrate I/O optimization for different persistence scenarios."""
    print("\n" + "="*60)
    print("I/O OPTIMIZATION ANALYSIS")
    print("="*60)

    optimizer = create_resource_optimizer(enable_monitoring=False)

    scenarios = [
        (5, PersistenceLevel.MINIMAL, "High frequency, minimal data"),
        (10, PersistenceLevel.STANDARD, "Medium frequency, standard data"),
        (25, PersistenceLevel.FULL, "Low frequency, full data"),
        (50, PersistenceLevel.COMPREHENSIVE, "Very low frequency, comprehensive data")
    ]

    for checkpoint_freq, persistence_level, description in scenarios:
        print(f"\nScenario: {description}")
        print(f"Checkpoint Frequency: Every {checkpoint_freq} events")
        print(f"Persistence Level: {persistence_level.value}")
        print("-" * 50)

        try:
            # Get I/O optimization recommendations
            io_result = optimizer.optimize_io_operations(checkpoint_freq, persistence_level)

            print(f"Total I/O Reduction: {io_result.total_io_reduction_percentage:.1%}")
            print(f"Significant Improvement: {'Yes' if io_result.is_significant_improvement else 'No'}")

            # Checkpoint optimization details
            checkpoint_opt = io_result.checkpoint_optimization
            print(f"Checkpoint Strategy: {checkpoint_opt['strategy']}")
            print(f"Checkpoint I/O Reduction: {checkpoint_opt['io_reduction_percentage']:.1%}")

            # Compression optimization details
            compression_opt = io_result.compression_optimization
            print(f"Compression Type: {compression_opt['recommended_compression']}")
            print(f"Compression Savings: {compression_opt['estimated_savings_percentage']:.1%}")

        except Exception as e:
            print(f"Error optimizing I/O for scenario: {e}")


def demo_comprehensive_recommendations(workforce_size: int, simulation_years: List[int]):
    """Demonstrate comprehensive optimization recommendations."""
    print("\n" + "="*60)
    print("COMPREHENSIVE OPTIMIZATION RECOMMENDATIONS")
    print("="*60)

    print(f"Simulation Parameters:")
    print(f"- Workforce Size: {workforce_size:,} employees")
    print(f"- Simulation Years: {len(simulation_years)} years ({min(simulation_years)}-{max(simulation_years)})")
    print(f"- Total Employee-Years: {workforce_size * len(simulation_years):,}")

    optimizer = create_resource_optimizer(enable_monitoring=True)

    try:
        # Get comprehensive recommendations
        with optimizer.resource_monitor.monitor_context("optimization_analysis"):
            recommendations = optimizer.get_optimization_recommendations(
                simulation_years=simulation_years,
                workforce_size=workforce_size,
                checkpoint_frequency=10,
                persistence_level=PersistenceLevel.STANDARD
            )

        print(f"\nOverall Assessment: {recommendations['overall_recommendation']['overall_rating'].upper()}")
        print(f"Summary: {recommendations['overall_recommendation']['summary']}")

        print(f"\nMemory Optimization:")
        memory_opt = recommendations['memory_optimization']
        print(f"- Strategy: {memory_opt['strategy']}")
        print(f"- Savings: {memory_opt['savings_gb']:.1f}GB")
        print(f"- Efficiency: {memory_opt['efficiency_rating']}")
        print(f"- Estimated Time: {memory_opt['estimated_time_minutes']:.1f} minutes")

        print(f"\nI/O Optimization:")
        io_opt = recommendations['io_optimization']
        print(f"- I/O Reduction: {io_opt['total_reduction_percentage']:.1%}")
        print(f"- Significant Improvement: {'Yes' if io_opt['significant_improvement'] else 'No'}")
        print(f"- Compression Strategy: {io_opt['compression_strategy']}")

        print(f"\nSystem Status:")
        system_status = recommendations['current_system_status']
        print(f"- Memory Used: {system_status['memory_used_gb']:.1f}GB")
        print(f"- Memory Available: {system_status['memory_available_gb']:.1f}GB")
        print(f"- Memory Pressure: {system_status['memory_pressure']}")
        print(f"- CPU Usage: {system_status['cpu_percentage']:.1%}")

        print(f"\nKey Recommendations:")
        for i, rec in enumerate(recommendations['overall_recommendation']['key_recommendations'], 1):
            print(f"{i}. {rec}")

    except Exception as e:
        print(f"Error generating recommendations: {e}")
    finally:
        optimizer.cleanup()


def demo_resource_monitoring():
    """Demonstrate resource monitoring capabilities."""
    print("\n" + "="*60)
    print("RESOURCE MONITORING DEMONSTRATION")
    print("="*60)

    optimizer = create_resource_optimizer(enable_monitoring=True)

    try:
        print("Starting resource monitoring...")

        # Simulate some work with resource monitoring
        with optimizer.resource_monitor.monitor_context("demo_workload"):
            print("Simulating workload (creating and processing data)...")

            # Simulate memory usage
            large_data = []
            for i in range(5):
                # Create some data to consume memory
                chunk = list(range(100000))  # ~400KB per chunk
                large_data.append(chunk)
                time.sleep(0.5)

                # Get current metrics
                metrics = optimizer.resource_monitor.get_current_metrics()
                print(f"  Step {i+1}: Memory {metrics.memory_used_gb:.1f}GB ({metrics.memory_percentage:.1%}), CPU {metrics.cpu_percentage:.1%}")

            # Clean up data
            del large_data

            time.sleep(1)  # Allow for cleanup

        # Get monitoring summary
        print(f"\nResource Usage Summary:")
        summary = optimizer.resource_monitor.get_metrics_summary(minutes=1)

        if 'error' not in summary:
            print(f"- Samples Collected: {summary['sample_count']}")
            print(f"- Average Memory Usage: {summary['memory_usage']['average_percentage']:.1%}")
            print(f"- Peak Memory Usage: {summary['memory_usage']['peak_percentage']:.1%}")
            print(f"- Average CPU Usage: {summary['cpu_usage']['average_percentage']:.1%}")
            print(f"- Peak CPU Usage: {summary['cpu_usage']['peak_percentage']:.1%}")
        else:
            print(f"- {summary['error']}")

    except Exception as e:
        print(f"Error during resource monitoring demo: {e}")
    finally:
        optimizer.cleanup()


def main():
    """Main demonstration function."""
    import argparse

    parser = argparse.ArgumentParser(description="Demonstrate ResourceOptimizer capabilities")
    parser.add_argument("--workforce-size", type=int, default=25000, help="Workforce size for demonstrations")
    parser.add_argument("--years", type=int, default=5, help="Number of simulation years")
    parser.add_argument("--skip-monitoring", action="store_true", help="Skip resource monitoring demo")

    args = parser.parse_args()

    simulation_years = list(range(2024, 2024 + args.years))
    workforce_sizes = [5000, args.workforce_size, 50000]  # Small, specified, large

    print("ResourceOptimizer Demonstration (Story S031-04)")
    print("Multi-Year Coordination - Memory and I/O Optimization")

    try:
        # 1. System status analysis
        demo_system_status()

        # 2. Memory optimization analysis
        demo_memory_optimization(workforce_sizes, simulation_years)

        # 3. I/O optimization analysis
        demo_io_optimization()

        # 4. Comprehensive recommendations
        demo_comprehensive_recommendations(args.workforce_size, simulation_years)

        # 5. Resource monitoring (optional)
        if not args.skip_monitoring:
            demo_resource_monitoring()

        print("\n" + "="*60)
        print("DEMONSTRATION COMPLETED SUCCESSFULLY")
        print("="*60)
        print("\nThe ResourceOptimizer provides:")
        print("✓ Memory optimization with streaming and chunking strategies")
        print("✓ I/O optimization for checkpointing and result persistence")
        print("✓ Adaptive optimization based on simulation size and system resources")
        print("✓ Real-time resource monitoring and performance tracking")
        print("✓ Comprehensive recommendations for optimal simulation performance")

    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    except Exception as e:
        print(f"\nDemo failed with error: {e}")
        logger.exception("Demo failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
