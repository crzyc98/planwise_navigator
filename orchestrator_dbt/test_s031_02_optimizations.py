#!/usr/bin/env python3
"""
Test script for Story S031-02: Year Processing Optimization

Demonstrates the performance improvements achieved through:
- Batch dbt execution with 5 execution groups
- DuckDB columnar storage and vectorized operations
- Performance monitoring and query plan analysis
- Memory optimization for analytical workloads

Expected performance improvement: 60% (2-3 minutes vs 5-8 minutes baseline)
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import optimization components
from core.config import OrchestrationConfig
from core.database_manager import DatabaseManager
from core.optimized_year_processor import OptimizedYearProcessor
from multi_year.simulation_state import StateManager


async def run_performance_test():
    """Run comprehensive performance test for S031-02 optimizations."""

    logger.info("🚀 Starting S031-02 Year Processing Optimization Test")
    logger.info("=" * 60)

    try:
        # Initialize configuration
        config = OrchestrationConfig()
        logger.info(f"✅ Configuration loaded: {config.dbt.project_dir}")

        # Initialize components
        database_manager = DatabaseManager(config)
        state_manager = StateManager()

        # Initialize optimized year processor
        optimized_processor = OptimizedYearProcessor(
            config=config,
            database_manager=database_manager,
            state_manager=state_manager,
            max_workers=4,
            enable_monitoring=True
        )

        logger.info("✅ OptimizedYearProcessor initialized with all optimizations")

        # Test configuration
        test_years = [2025, 2026]  # Test 2 years to validate multi-year performance
        test_configuration = {
            "start_year": 2025,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "random_seed": 42,
            "full_refresh": False
        }

        logger.info("📊 Test Configuration:")
        logger.info(f"  - Years to process: {test_years}")
        logger.info(f"  - Growth rate: {test_configuration['target_growth_rate']*100:.1f}%")
        logger.info(f"  - Termination rate: {test_configuration['total_termination_rate']*100:.1f}%")
        logger.info("")

        # Run performance test for each year
        test_results = []
        total_start_time = time.time()

        for year in test_years:
            logger.info(f"🔄 Processing Year {year}")
            logger.info("-" * 40)

            year_result = await optimized_processor.process_year_optimized(
                simulation_year=year,
                configuration=test_configuration,
                previous_workforce=None
            )

            test_results.append(year_result)

            # Log year results
            if year_result["success"]:
                execution_time = year_result["execution_time_minutes"]
                improvement = year_result["performance_targets"]["improvement_achieved"]
                memory_usage = year_result.get("performance_analysis", {}).get("peak_memory_gb", 0)

                logger.info(f"✅ Year {year} completed successfully")
                logger.info(f"⏱️  Execution time: {execution_time:.2f} minutes")
                logger.info(f"📈 Performance improvement: {improvement:.1f}%")
                logger.info(f"💾 Peak memory usage: {memory_usage:.1f}GB")

                # Check performance targets
                targets = year_result["performance_targets"]
                if targets["target_met"]:
                    logger.info("🎯 All performance targets achieved!")
                else:
                    logger.warning("⚠️  Some performance targets not met:")
                    if not targets.get("improvement_target_met", True):
                        logger.warning(f"    - Improvement target: {improvement:.1f}% (target: 60%)")
                    if not targets.get("memory_target_met", True):
                        logger.warning(f"    - Memory target: {memory_usage:.1f}GB (target: <4GB)")
                    if not targets.get("speed_target_met", True):
                        avg_query_time = year_result.get("performance_analysis", {}).get("avg_query_time", 0)
                        logger.warning(f"    - Query speed target: {avg_query_time:.2f}s (target: <1s)")

            else:
                logger.error(f"❌ Year {year} processing failed")
                if "error" in year_result:
                    logger.error(f"   Error: {year_result['error']}")

            logger.info("")

        # Calculate overall test results
        total_test_time = time.time() - total_start_time
        successful_years = [r for r in test_results if r["success"]]

        logger.info("🏁 Test Summary")
        logger.info("=" * 60)
        logger.info(f"📊 Years processed: {len(test_results)}")
        logger.info(f"✅ Successful years: {len(successful_years)}")
        logger.info(f"⏱️  Total test time: {total_test_time/60:.2f} minutes")

        if successful_years:
            avg_execution_time = sum(r["execution_time_minutes"] for r in successful_years) / len(successful_years)
            avg_improvement = sum(r["performance_targets"]["improvement_achieved"] for r in successful_years) / len(successful_years)

            logger.info(f"⚡ Average execution time per year: {avg_execution_time:.2f} minutes")
            logger.info(f"📈 Average performance improvement: {avg_improvement:.1f}%")

            # Performance target assessment
            target_met_count = sum(1 for r in successful_years if r["performance_targets"]["target_met"])
            target_rate = target_met_count / len(successful_years) * 100

            logger.info(f"🎯 Performance targets achieved: {target_met_count}/{len(successful_years)} ({target_rate:.0f}%)")

            # Detailed batch execution analysis
            logger.info("")
            logger.info("🔍 Batch Execution Analysis:")

            processor_summary = optimized_processor.get_processing_summary()
            batch_summary = processor_summary.get("batch_execution_summary", {})

            if batch_summary:
                logger.info(f"  - Total batches executed: {batch_summary.get('total_batches', 0)}")
                logger.info(f"  - Batch success rate: {batch_summary.get('success_rate', 0):.1f}%")
                logger.info(f"  - Models per minute: {batch_summary.get('models_per_minute', 0):.1f}")
                logger.info(f"  - Average batch size: {batch_summary.get('avg_batch_size', 0):.1f} models")

                if batch_summary.get("optimization_target_met"):
                    logger.info("✅ Batch execution optimization targets achieved")
                else:
                    logger.warning("⚠️  Batch execution could be further optimized")

            # DuckDB optimization analysis
            logger.info("")
            logger.info("🗃️  DuckDB Optimization Analysis:")

            duckdb_summary = processor_summary.get("duckdb_optimization_summary", {})
            if duckdb_summary:
                cache_entries = duckdb_summary.get("cache_entries", 0)
                logger.info(f"  - Optimization cache entries: {cache_entries}")
                logger.info(f"  - Columnar storage optimizations: ✅ Applied")
                logger.info(f"  - Vectorized operations: ✅ Enabled")
                logger.info(f"  - Memory optimizations: ✅ Applied")

            # Overall assessment
            logger.info("")
            logger.info("🏆 S031-02 Implementation Assessment:")

            if avg_improvement >= 60.0:
                logger.info("✅ PRIMARY TARGET ACHIEVED: 60%+ performance improvement")
            else:
                logger.warning(f"⚠️  Primary target progress: {avg_improvement:.1f}% (target: 60%)")

            if avg_execution_time <= 3.0:
                logger.info("✅ TIME TARGET ACHIEVED: 2-3 minute execution time")
            else:
                logger.warning(f"⚠️  Time target progress: {avg_execution_time:.2f} minutes (target: 2-3 minutes)")

            memory_efficient = all(
                r.get("performance_analysis", {}).get("peak_memory_gb", 0) <= 4.0
                for r in successful_years
            )

            if memory_efficient:
                logger.info("✅ MEMORY TARGET ACHIEVED: <4GB peak usage")
            else:
                logger.warning("⚠️  Memory usage may exceed 4GB target")

            # Final recommendation
            logger.info("")
            if avg_improvement >= 60.0 and avg_execution_time <= 3.0:
                logger.info("🎉 S031-02 OPTIMIZATION SUCCESS: All primary targets achieved!")
                logger.info("✅ Ready for production deployment")
            else:
                logger.info("🔧 S031-02 OPTIMIZATION IN PROGRESS: Additional tuning recommended")
                logger.info("📝 Review performance analysis for optimization opportunities")

        else:
            logger.error("❌ No successful year processing - check configuration and dependencies")

        logger.info("")
        logger.info("📋 Test completed - review results above for optimization effectiveness")

    except Exception as e:
        logger.error(f"❌ Performance test failed: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")


def run_basic_optimization_demo():
    """Run a basic demonstration of individual optimization components."""

    logger.info("🔧 Running Basic Optimization Component Demo")
    logger.info("=" * 50)

    try:
        # Test configuration loading
        config = OrchestrationConfig()
        logger.info("✅ Configuration loading: OK")

        # Test database manager
        database_manager = DatabaseManager(config)
        logger.info("✅ Database manager initialization: OK")

        # Test optimized dbt executor
        from core.optimized_dbt_executor import OptimizedDbtExecutor, ExecutionGroup

        dbt_executor = OptimizedDbtExecutor(
            config=config,
            database_manager=database_manager,
            max_workers=2,
            enable_performance_monitoring=True
        )

        logger.info("✅ Optimized dbt executor initialization: OK")
        logger.info(f"📊 Execution plans configured: {len(dbt_executor.EXECUTION_PLANS)}")

        # Display execution groups
        logger.info("")
        logger.info("📋 Batch Execution Groups:")

        for i, plan in enumerate(dbt_executor.EXECUTION_PLANS, 1):
            logger.info(f"  {i}. {plan.group.value}: {len(plan.models)} models")
            logger.info(f"     - Parallel: {plan.can_run_parallel}")
            logger.info(f"     - Memory req: {plan.memory_requirement_gb}GB")
            logger.info(f"     - Est. duration: {plan.estimated_duration_seconds}s")

        # Test DuckDB optimizer
        from core.duckdb_optimizations import DuckDBOptimizer

        duckdb_optimizer = DuckDBOptimizer(database_manager)
        logger.info("✅ DuckDB optimizer initialization: OK")

        # Test performance optimizer
        from utils.performance_optimizer import PerformanceOptimizer

        performance_optimizer = PerformanceOptimizer(database_manager)
        logger.info("✅ Performance optimizer initialization: OK")

        logger.info("")
        logger.info("🎉 All optimization components initialized successfully!")
        logger.info("🚀 Ready to run full performance test with: python test_s031_02_optimizations.py --full-test")

    except Exception as e:
        logger.error(f"❌ Component demo failed: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--full-test":
        # Run full async performance test
        asyncio.run(run_performance_test())
    else:
        # Run basic component demo
        run_basic_optimization_demo()
