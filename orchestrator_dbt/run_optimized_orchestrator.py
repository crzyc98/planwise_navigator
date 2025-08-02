#!/usr/bin/env python3
"""
Optimized orchestrator entry point for orchestrator_dbt.

This script provides the main entry point for running the optimized dbt setup workflow
with concurrent execution, batch operations, performance monitoring, and error recovery.
"""

import sys
import logging
import argparse
import time
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator_dbt.core.workflow_orchestrator import WorkflowOrchestrator
from orchestrator_dbt.core.config import OrchestrationConfig
from orchestrator_dbt.utils.performance_monitor import PerformanceMonitor
from orchestrator_dbt.utils.error_recovery import error_recovery
from orchestrator_dbt.utils.logging_utils import setup_logging


def setup_argument_parser() -> argparse.ArgumentParser:
    """Setup command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Optimized dbt setup workflow orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run optimized workflow with default settings
  python run_optimized_orchestrator.py

  # Run with custom worker count and performance monitoring
  python run_optimized_orchestrator.py --max-workers 6 --enable-monitoring

  # Run quick setup (foundation models only)
  python run_optimized_orchestrator.py --quick-setup

  # Run standard workflow (sequential execution)
  python run_optimized_orchestrator.py --use-standard-workflow

  # Enable detailed performance analysis
  python run_optimized_orchestrator.py --enable-monitoring --save-performance-report
        """
    )

    # Execution options
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of concurrent workers (default: 4)"
    )

    parser.add_argument(
        "--quick-setup",
        action="store_true",
        help="Run quick setup (foundation models only)"
    )

    parser.add_argument(
        "--use-standard-workflow",
        action="store_true",
        help="Use standard sequential workflow instead of optimized concurrent execution"
    )

    # Performance and monitoring options
    parser.add_argument(
        "--enable-monitoring",
        action="store_true",
        help="Enable detailed performance monitoring"
    )

    parser.add_argument(
        "--save-performance-report",
        action="store_true",
        help="Save performance report to file"
    )

    parser.add_argument(
        "--performance-report-path",
        type=str,
        help="Path to save performance report (default: auto-generated)"
    )

    # Configuration options
    parser.add_argument(
        "--config-path",
        type=str,
        help="Path to configuration YAML file"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )

    # Analysis options
    parser.add_argument(
        "--analyze-performance",
        action="store_true",
        help="Analyze performance potential and show recommendations"
    )

    parser.add_argument(
        "--show-system-status",
        action="store_true",
        help="Show system status and readiness information"
    )

    return parser


def analyze_performance_potential(orchestrator: WorkflowOrchestrator) -> None:
    """
    Analyze performance optimization potential.

    Args:
        orchestrator: WorkflowOrchestrator instance
    """
    print("\n" + "=" * 60)
    print("🔍 PERFORMANCE OPTIMIZATION ANALYSIS")
    print("=" * 60)

    try:
        metrics = orchestrator.get_workflow_performance_metrics()

        print("📊 Current System Metrics:")

        # Seed loading metrics
        seed_metrics = metrics.get("seed_loading", {})
        print(f"   Seeds available: {seed_metrics.get('total_seeds_available', 0)}")
        print(f"   Seeds with dependencies: {seed_metrics.get('seeds_with_dependencies', 0)}")
        print(f"   Max dependency depth: {seed_metrics.get('max_dependency_depth', 0)}")
        print(f"   Parallelization ratio: {seed_metrics.get('parallelization_ratio', 0):.1%}")

        # Staging model metrics
        staging_metrics = metrics.get("staging_models", {})
        print(f"   Staging models available: {staging_metrics.get('total_models_available', 0)}")
        print(f"   Models with dependencies: {staging_metrics.get('models_with_dependencies', 0)}")
        print(f"   Dependency levels: {staging_metrics.get('dependency_levels', 0)}")
        print(f"   Max concurrent models: {staging_metrics.get('max_concurrent_models', 0)}")
        print(f"   Parallelization potential: {staging_metrics.get('parallelization_potential', 0):.1%}")

        # Recommendations
        recommendations = metrics.get("optimization_recommendations", [])
        if recommendations:
            print(f"\n💡 Optimization Recommendations:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")

        # Time savings estimate
        estimated_savings = metrics.get("estimated_time_savings", 0)
        if estimated_savings > 0:
            print(f"\n⏱️  Estimated Time Savings: {estimated_savings:.1f} seconds")
            print(f"   Potential speedup: ~{estimated_savings / 47 * 100:.0f}% improvement over baseline")

    except Exception as e:
        print(f"❌ Error analyzing performance: {e}")

    print("=" * 60 + "\n")


def show_system_status(orchestrator: WorkflowOrchestrator) -> None:
    """
    Show system status and readiness.

    Args:
        orchestrator: WorkflowOrchestrator instance
    """
    print("\n" + "=" * 60)
    print("🔧 SYSTEM STATUS & READINESS")
    print("=" * 60)

    try:
        status = orchestrator.get_system_status()

        print("📋 System Status:")
        print(f"   Configuration valid: {'✅' if status.get('config_valid', False) else '❌'}")
        print(f"   Database accessible: {'✅' if status.get('database_accessible', False) else '❌'}")
        print(f"   dbt available: {'✅' if status.get('dbt_available', False) else '❌'}")
        print(f"   Seeds available: {'✅' if status.get('seeds_available', False) else '❌'}")
        print(f"   Staging models available: {'✅' if status.get('staging_models_available', False) else '❌'}")

        print(f"\n📊 Resource Counts:")
        if 'database_details' in status:
            db_details = status['database_details']
            print(f"   Total tables: {db_details.get('total_tables', 0)}")
            print(f"   Staging tables: {db_details.get('staging_tables', 0)}")
            print(f"   Fact tables: {db_details.get('fact_tables', 0)}")

        print(f"   Seeds: {status.get('seeds_count', 0)}")
        print(f"   Staging models: {status.get('staging_models_count', 0)}")

        if status.get('dbt_version'):
            print(f"\n🔧 dbt Version: {status['dbt_version']}")

        print(f"\n🚀 Ready for setup: {'✅ YES' if status.get('ready_for_setup', False) else '❌ NO'}")

        if not status.get('ready_for_setup', False):
            print("\n⚠️  Issues detected:")
            for key, value in status.items():
                if key.endswith('_error'):
                    print(f"   • {key.replace('_error', '').title()}: {value}")

    except Exception as e:
        print(f"❌ Error checking system status: {e}")

    print("=" * 60 + "\n")


def main():
    """Main entry point for optimized orchestrator."""
    parser = setup_argument_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(level=args.log_level)
    logger = logging.getLogger(__name__)

    print("\n" + "=" * 60)
    print("🚀 OPTIMIZED DBT SETUP ORCHESTRATOR")
    print("=" * 60)
    print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Max workers: {args.max_workers}")
    print(f"Performance monitoring: {'✅' if args.enable_monitoring else '❌'}")
    print("=" * 60)

    start_time = time.time()
    performance_monitor = None

    try:
        # Initialize performance monitoring if enabled
        if args.enable_monitoring:
            performance_monitor = PerformanceMonitor(enable_detailed_tracking=True)
            logger.info("Performance monitoring enabled")

        # Load configuration
        config_path = Path(args.config_path) if args.config_path else None
        config = OrchestrationConfig(config_path)
        logger.info(f"Configuration loaded from: {config.config_path}")

        # Initialize orchestrator
        orchestrator = WorkflowOrchestrator(config_path)
        logger.info("Workflow orchestrator initialized")

        # Show system status if requested
        if args.show_system_status:
            show_system_status(orchestrator)

        # Analyze performance potential if requested
        if args.analyze_performance:
            analyze_performance_potential(orchestrator)
            return

        # Start performance monitoring
        operation_id = None
        if performance_monitor:
            operation_id = performance_monitor.start_operation(
                "complete_workflow",
                {"max_workers": args.max_workers, "workflow_type": "optimized" if not args.use_standard_workflow else "standard"}
            )

        # Execute workflow
        if args.quick_setup:
            logger.info("Running quick setup workflow...")
            result = orchestrator.run_quick_setup()
        elif args.use_standard_workflow:
            logger.info("Running standard sequential workflow...")
            result = orchestrator.run_complete_setup_workflow()
        else:
            logger.info("Running optimized concurrent workflow...")
            result = orchestrator.run_optimized_setup_workflow(max_workers=args.max_workers)

        # End performance monitoring
        if performance_monitor and operation_id:
            performance_monitor.end_operation(operation_id, result.success)

        # Print results
        total_time = time.time() - start_time
        print("\n" + "=" * 60)
        print("📊 WORKFLOW EXECUTION RESULTS")
        print("=" * 60)

        if result.success:
            print("✅ Workflow completed successfully!")
            print(f"   Steps completed: {result.steps_completed}/{result.steps_total}")
            print(f"   Total execution time: {result.total_execution_time:.2f}s")
            print(f"   Completion rate: {result.completion_rate:.1f}%")
        else:
            print("❌ Workflow failed!")
            print(f"   Steps completed: {result.steps_completed}/{result.steps_total}")
            print(f"   Total execution time: {result.total_execution_time:.2f}s")

            failed_steps = result.get_failed_steps()
            if failed_steps:
                print(f"   Failed steps: {[s.step_name for s in failed_steps]}")

        # Show validation results
        if result.final_validation:
            if result.final_validation.is_valid:
                print(f"   📊 Validation: {result.final_validation.passed_checks}/{result.final_validation.total_checks} checks passed")
            else:
                print(f"   ⚠️  Validation: {result.final_validation.failed_checks} failures, {result.final_validation.warnings} warnings")

        # Show performance analysis if monitoring is enabled
        if performance_monitor:
            print("\n" + "=" * 60)
            print("🔍 PERFORMANCE ANALYSIS")
            print("=" * 60)

            report = performance_monitor.generate_report()
            performance_monitor.print_summary(report)

            # Save performance report if requested
            if args.save_performance_report:
                report_path = args.performance_report_path
                if not report_path:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    report_path = f"performance_report_{timestamp}.json"

                performance_monitor.save_report(report, Path(report_path))
                print(f"📄 Performance report saved to: {report_path}")

        # Show error recovery summary
        error_summary = error_recovery.get_error_summary()
        if error_summary['total_errors'] > 0:
            print("\n" + "=" * 60)
            print("🚨 ERROR RECOVERY SUMMARY")
            print("=" * 60)

            print(f"   Total errors encountered: {error_summary['total_errors']}")
            print(f"   Error types: {error_summary['error_types']}")

            if error_summary['circuit_breakers']:
                print(f"   Circuit breakers: {len(error_summary['circuit_breakers'])} active")

        print("=" * 60)
        print(f"🏁 Total runtime: {total_time:.2f}s")
        print(f"Completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60 + "\n")

        # Exit with appropriate code
        sys.exit(0 if result.success else 1)

    except KeyboardInterrupt:
        logger.warning("Workflow interrupted by user")
        print("\n❌ Workflow interrupted by user")
        sys.exit(130)

    except Exception as e:
        logger.error(f"Workflow failed with exception: {e}")
        print(f"\n💥 Workflow failed with exception: {e}")

        # End performance monitoring on error
        if performance_monitor and operation_id:
            performance_monitor.end_operation(operation_id, False, {"error": str(e)})

            # Show performance summary even on failure
            report = performance_monitor.generate_report()
            performance_monitor.print_summary(report)

        sys.exit(1)


if __name__ == "__main__":
    main()
