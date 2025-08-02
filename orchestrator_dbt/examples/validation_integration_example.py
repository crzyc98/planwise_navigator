"""
Multi-Year Validation Framework Integration Example

This example demonstrates how to use the enhanced MultiYearValidationFramework
with the MultiYearOrchestrator for comprehensive data quality validation
across multi-year simulations.

Key Features Demonstrated:
- Real-time validation during simulation execution
- Comprehensive multi-year validation with audit trail integrity
- Performance-optimized validation with circuit breaker pattern
- Validation reporting and alerting with data quality metrics
- Event sourcing integrity validation with UUID tracking
- Business logic compliance validation across years

Usage:
    python validation_integration_example.py
"""

import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the enhanced components
from ..multi_year.multi_year_orchestrator import (
    MultiYearOrchestrator,
    MultiYearConfig,
    OptimizationLevel,
    create_multi_year_orchestrator
)
from ..core.config import OrchestrationConfig
from ..core.validation_reporting import ValidationReporter, ReportFormat
from ..core.multi_year_validation_framework import MultiYearValidationFramework


async def demonstrate_enhanced_validation():
    """Demonstrate enhanced multi-year validation capabilities."""

    logger.info("🚀 Starting Multi-Year Validation Framework Integration Example")
    logger.info("=" * 80)

    try:
        # Step 1: Initialize Multi-Year Orchestrator with Validation
        logger.info("📋 Step 1: Initialize Multi-Year Orchestrator with Enhanced Validation")

        orchestrator = create_multi_year_orchestrator(
            start_year=2025,
            end_year=2027,  # 3-year simulation for demonstration
            optimization_level=OptimizationLevel.HIGH,
            enable_validation=True,  # Enable validation
            fail_fast=False,  # Continue on validation warnings
            performance_monitoring=True
        )

        logger.info(f"✅ Orchestrator initialized with validation enabled")
        logger.info(f"   📊 Simulation ID: {orchestrator.simulation_id}")
        logger.info(f"   🔍 Real-time validation: {orchestrator.multi_year_validation.enable_real_time_validation}")
        logger.info(f"   ⚡ Validation mode: {orchestrator.multi_year_validation.validation_mode}")

        # Step 2: Initialize Validation Reporter
        logger.info("\n📊 Step 2: Initialize Validation Reporter")

        validation_reporter = ValidationReporter(
            orchestrator.base_config,
            orchestrator.database_manager
        )

        logger.info("✅ Validation reporter initialized")

        # Step 3: Execute Multi-Year Simulation with Real-Time Validation
        logger.info("\n🎯 Step 3: Execute Multi-Year Simulation with Enhanced Validation")

        # Execute the simulation (this will include all validation steps)
        simulation_result = await orchestrator.execute_multi_year_simulation()

        logger.info(f"✅ Multi-year simulation completed")
        logger.info(f"   📈 Overall success: {simulation_result.success}")
        logger.info(f"   ⏱️  Total execution time: {simulation_result.total_execution_time:.2f}s")
        logger.info(f"   📅 Completed years: {simulation_result.completed_years}")

        if simulation_result.failed_years:
            logger.warning(f"   ⚠️  Failed years: {simulation_result.failed_years}")

        # Step 4: Demonstrate Targeted Validation
        logger.info("\n🔍 Step 4: Execute Targeted Validation for Specific Years")

        targeted_validation = orchestrator.validate_specific_years(
            start_year=2025,
            end_year=2027,
            scenario_id=orchestrator.simulation_id
        )

        logger.info("✅ Targeted validation completed")
        logger.info(f"   📊 Overall validation passed: {targeted_validation['summary']['overall_passed']}")
        logger.info(f"   🔗 Cross-year integrity checks: {len(targeted_validation['cross_year_integrity'])}")
        logger.info(f"   📝 Event sourcing validation: {targeted_validation['event_sourcing']['passed']}")
        logger.info(f"   💼 Business logic validation: {targeted_validation['business_logic']['passed']}")
        logger.info(f"   💰 Financial calculations validation: {targeted_validation['financial_calculations']['passed']}")
        logger.info(f"   🆔 UUID integrity validation: {targeted_validation['uuid_integrity']['passed']}")

        # Step 5: Generate Comprehensive Validation Report
        logger.info("\n📋 Step 5: Generate Comprehensive Validation Report")

        # First, run a final comprehensive validation
        final_validation = orchestrator.multi_year_validation.validate_multi_year_simulation(
            start_year=2025,
            end_year=2027,
            scenario_id=orchestrator.simulation_id
        )

        # Generate comprehensive report
        validation_report = validation_reporter.generate_comprehensive_report(
            final_validation,
            include_trends=True,
            include_recommendations=True
        )

        logger.info("✅ Comprehensive validation report generated")
        logger.info(f"   📄 Report ID: {validation_report.report_id}")
        logger.info(f"   ⏱️  Report generation time: {validation_report.timestamp.isoformat()}")
        logger.info(f"   📊 Overall status: {validation_report.summary['overall_status']}")
        logger.info(f"   📈 Success rate: {validation_report.summary['success_rate']:.1f}%")
        logger.info(f"   🚨 Total alerts: {len(validation_report.alerts)}")
        logger.info(f"   💡 Recommendations: {len(validation_report.recommendations)}")

        # Step 6: Demonstrate Alert Management
        logger.info("\n🚨 Step 6: Demonstrate Alert Management")

        if validation_report.alerts:
            # Send alerts through configured channels
            alert_results = validation_reporter.send_validation_alerts(validation_report.alerts)

            logger.info(f"✅ Sent {alert_results['alerts_sent']} alerts")
            logger.info(f"   📡 Channels used: {alert_results['channels_used']}")

            # Show alert details
            for alert in validation_report.alerts[:3]:  # Show first 3 alerts
                logger.info(f"   🚨 {alert.severity.value.upper()}: {alert.check_name} - {alert.message}")
        else:
            logger.info("✅ No alerts generated - excellent data quality!")

        # Step 7: Export Validation Report
        logger.info("\n💾 Step 7: Export Validation Report")

        # Export in multiple formats
        json_path = validation_reporter.export_report(validation_report, ReportFormat.JSON)
        markdown_path = validation_reporter.export_report(validation_report, ReportFormat.MARKDOWN)
        html_path = validation_reporter.export_report(validation_report, ReportFormat.HTML)

        logger.info("✅ Validation reports exported")
        logger.info(f"   📄 JSON report: {json_path}")
        logger.info(f"   📝 Markdown report: {markdown_path}")
        logger.info(f"   🌐 HTML report: {html_path}")

        # Step 8: Demonstrate Performance Metrics and Circuit Breaker
        logger.info("\n⚡ Step 8: Validation Performance Metrics and Circuit Breaker Status")

        validation_summary = orchestrator.get_validation_summary()
        performance_metrics = orchestrator.multi_year_validation.get_comprehensive_performance_metrics()

        logger.info("✅ Performance metrics retrieved")
        logger.info(f"   🔧 Validation enabled: {validation_summary['validation_enabled']}")
        logger.info(f"   ⚡ Real-time validation: {validation_summary['real_time_validation_enabled']}")
        logger.info(f"   🛡️  Circuit breaker open: {performance_metrics['circuit_breaker_status']['open']}")
        logger.info(f"   🔄 Failure count: {performance_metrics['circuit_breaker_status']['failure_count']}")
        logger.info(f"   ⚡ Performance optimization: {performance_metrics['enable_performance_optimization']}")
        logger.info(f"   📊 Validation history: {performance_metrics['validation_history_count']} entries")

        # Step 9: Demonstrate Data Quality Dashboard Data
        logger.info("\n📊 Step 9: Data Quality Dashboard Data")

        dashboard_data = validation_reporter.get_validation_dashboard_data()
        data_quality_score = dashboard_data['data_quality_score']

        logger.info("✅ Dashboard data generated")
        logger.info(f"   🎯 Data Quality Score: {data_quality_score['score']:.1f}/100")
        logger.info(f"   🏆 Data Quality Grade: {data_quality_score['grade']}")
        logger.info(f"   🚨 Active alerts: {dashboard_data['active_alerts_count']}")
        logger.info(f"   🔴 Critical alerts: {dashboard_data['critical_alerts_count']}")
        logger.info(f"   📈 Recent reports: {dashboard_data['recent_reports_count']}")

        # Step 10: Demonstrate Specific Validation Features
        logger.info("\n🔬 Step 10: Demonstrate Specific Validation Features")

        # Test financial calculations integrity
        financial_validation = orchestrator.multi_year_validation.validate_financial_calculations_integrity(
            2025, 2027, orchestrator.simulation_id
        )
        logger.info(f"   💰 Financial calculations integrity: {'✅ PASSED' if financial_validation.passed else '❌ FAILED'}")

        # Test UUID integrity
        uuid_validation = orchestrator.multi_year_validation.validate_uuid_integrity_comprehensive(
            2025, 2027, orchestrator.simulation_id
        )
        logger.info(f"   🆔 UUID integrity comprehensive: {'✅ PASSED' if uuid_validation.passed else '❌ FAILED'}")

        # Test event sourcing integrity
        event_sourcing_validation = orchestrator.multi_year_validation.validate_event_sourcing_integrity(
            2025, 2027, orchestrator.simulation_id
        )
        logger.info(f"   📝 Event sourcing integrity: {'✅ PASSED' if event_sourcing_validation.passed else '❌ FAILED'}")
        logger.info(f"       Events validated: {event_sourcing_validation.events_validated:,}")

        # Test business logic compliance
        business_logic_validation = orchestrator.multi_year_validation.validate_business_logic_compliance(
            2025, 2027, orchestrator.simulation_id
        )
        logger.info(f"   💼 Business logic compliance: {'✅ PASSED' if business_logic_validation.passed else '❌ FAILED'}")
        logger.info(f"       Rules checked: {business_logic_validation.business_rules_checked}")

        # Final Summary
        logger.info("\n" + "=" * 80)
        logger.info("🎉 Multi-Year Validation Framework Integration Example Complete!")
        logger.info(f"   📊 Simulation ID: {orchestrator.simulation_id}")
        logger.info(f"   📅 Years simulated: {simulation_result.start_year}-{simulation_result.end_year}")
        logger.info(f"   ✅ Overall success: {simulation_result.success}")
        logger.info(f"   📈 Data quality score: {data_quality_score['score']:.1f}/100 ({data_quality_score['grade']})")
        logger.info(f"   ⏱️  Total execution time: {simulation_result.total_execution_time:.2f}s")
        logger.info(f"   🔍 Validation checks completed: {final_validation.total_checks}")
        logger.info(f"   📋 Validation reports generated: 3 formats")

        if validation_report.recommendations:
            logger.info(f"   💡 Key recommendations:")
            for i, rec in enumerate(validation_report.recommendations[:3], 1):
                logger.info(f"      {i}. {rec}")

        logger.info("=" * 80)

        return {
            "simulation_result": simulation_result,
            "validation_report": validation_report,
            "dashboard_data": dashboard_data,
            "targeted_validation": targeted_validation,
            "exported_reports": {
                "json": str(json_path),
                "markdown": str(markdown_path),
                "html": str(html_path)
            }
        }

    except Exception as e:
        logger.error(f"💥 Example execution failed: {e}")
        raise


async def demonstrate_validation_error_handling():
    """Demonstrate validation error handling and circuit breaker functionality."""

    logger.info("\n🔧 Demonstrating Validation Error Handling and Circuit Breaker")
    logger.info("-" * 60)

    try:
        # Create orchestrator with strict validation settings
        orchestrator = create_multi_year_orchestrator(
            start_year=2025,
            end_year=2026,  # Short simulation for error testing
            optimization_level=OptimizationLevel.MEDIUM,
            enable_validation=True,
            fail_fast=True,  # Enable fail-fast for error demonstration
            performance_monitoring=True
        )

        # Demonstrate circuit breaker reset
        logger.info("🛡️  Testing circuit breaker functionality")

        # Check initial circuit breaker status
        initial_metrics = orchestrator.multi_year_validation.get_comprehensive_performance_metrics()
        logger.info(f"   Initial circuit breaker status: {'OPEN' if initial_metrics['circuit_breaker_status']['open'] else 'CLOSED'}")

        # Reset circuit breaker if it's open
        if initial_metrics['circuit_breaker_status']['open']:
            orchestrator.reset_validation_circuit_breaker()
            logger.info("   ✅ Circuit breaker reset")

        # Demonstrate validation reproducibility check
        logger.info("🔄 Testing validation reproducibility")

        # This would normally compare two simulation runs
        # For demonstration, we'll show the method signature
        logger.info("   📊 Reproducibility validation available for comparing simulation runs")

        # Demonstrate performance optimization
        logger.info("⚡ Validation performance optimization enabled")
        perf_metrics = orchestrator.multi_year_validation.get_comprehensive_performance_metrics()
        logger.info(f"   Batch size: {perf_metrics['batch_size']}")
        logger.info(f"   Performance optimization: {perf_metrics['enable_performance_optimization']}")
        logger.info(f"   Max validation time: {perf_metrics['max_validation_time_seconds']}s")

        logger.info("✅ Error handling demonstration completed successfully")

    except Exception as e:
        logger.error(f"Error handling demonstration failed: {e}")
        raise


def demonstrate_validation_configuration():
    """Demonstrate validation configuration options."""

    logger.info("\n⚙️  Demonstrating Validation Configuration Options")
    logger.info("-" * 60)

    try:
        # Load configuration
        config = OrchestrationConfig()

        # Show multi-year validation configuration
        multi_year_config = config.get_multi_year_config()

        logger.info("📋 Multi-Year Validation Configuration:")
        logger.info(f"   Validation mode: {multi_year_config.error_handling.validation_mode}")
        logger.info(f"   Fail fast: {multi_year_config.error_handling.fail_fast}")
        logger.info(f"   Max retries: {multi_year_config.error_handling.max_retries}")
        logger.info(f"   Retry delay: {multi_year_config.error_handling.retry_delay_seconds}s")
        logger.info(f"   Performance monitoring: {multi_year_config.monitoring.enable_performance_monitoring}")
        logger.info(f"   Progress reporting: {multi_year_config.monitoring.enable_progress_reporting}")
        logger.info(f"   Memory profiling: {multi_year_config.monitoring.enable_memory_profiling}")

        # Show optimization configuration
        logger.info("⚡ Optimization Configuration:")
        logger.info(f"   Optimization level: {multi_year_config.optimization.level}")
        logger.info(f"   Max workers: {multi_year_config.optimization.max_workers}")
        logger.info(f"   Batch size: {multi_year_config.optimization.batch_size}")
        logger.info(f"   Memory limit: {multi_year_config.optimization.memory_limit_gb}GB")

        # Show validation-specific settings
        validation_config = config.validation
        logger.info("🔍 Validation-Specific Configuration:")
        logger.info(f"   Min baseline workforce: {validation_config.min_baseline_workforce_count:,}")
        logger.info(f"   Max workforce variance: {validation_config.max_workforce_variance:.1%}")
        logger.info(f"   Required seed tables: {len(validation_config.required_seed_tables)}")
        logger.info(f"   Required staging models: {len(validation_config.required_staging_models)}")

        logger.info("✅ Configuration demonstration completed")

    except Exception as e:
        logger.error(f"Configuration demonstration failed: {e}")
        raise


async def main():
    """Main example execution function."""

    logger.info("🚀 Multi-Year Validation Framework Integration Example")
    logger.info(f"Started at: {datetime.utcnow().isoformat()}")
    logger.info("=" * 80)

    try:
        # Run configuration demonstration first
        demonstrate_validation_configuration()

        # Run main validation demonstration
        results = await demonstrate_enhanced_validation()

        # Run error handling demonstration
        await demonstrate_validation_error_handling()

        logger.info("\n🎉 All demonstrations completed successfully!")
        logger.info(f"Completed at: {datetime.utcnow().isoformat()}")

        return results

    except Exception as e:
        logger.error(f"💥 Example execution failed: {e}")
        raise


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())
