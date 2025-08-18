#!/usr/bin/env python3
"""
Observability Framework Demonstration

Shows the production observability framework in action with realistic
simulation scenarios, structured logging, and comprehensive monitoring.
"""

import time
import random
from pathlib import Path

from navigator_orchestrator import observability_session


def simulate_data_processing(obs, operation_name: str, record_count: int,
                           failure_rate: float = 0.0):
    """Simulate data processing operation with observability"""
    with obs.track_operation(operation_name, records=record_count) as metrics:
        # Simulate processing time based on record count
        processing_time = record_count / 10000  # 10k records per second
        time.sleep(min(processing_time, 2.0))  # Cap at 2 seconds for demo

        # Simulate potential failure
        if random.random() < failure_rate:
            raise RuntimeError(f"Processing failed for {operation_name}")

        # Log progress
        obs.log_info(f"Processed {record_count} records in {operation_name}",
                    records_processed=record_count,
                    processing_rate=record_count / (time.time() - metrics.start_time))


def demonstrate_basic_logging():
    """Demonstrate basic structured logging capabilities"""
    print("\n=== Demonstrating Basic Structured Logging ===")

    with observability_session(run_id="demo-basic-logging") as obs:
        # Different log levels
        obs.log_info("Starting basic logging demonstration", demo_type="basic")
        obs.logger.debug("Debug message with details", component="logger", level="debug")
        obs.log_warning("This is a warning message", severity="medium", component="demo")
        obs.log_error("This is an error message", error_code="DEMO_001", component="demo")

        # Structured data logging
        obs.log_info("User action logged",
                    user_id="demo_user",
                    action="view_dashboard",
                    duration_ms=250,
                    success=True)

        # Custom metrics
        obs.add_metric("demo_score", 95.5, "Demonstration success score")
        obs.add_metric("active_users", 42, "Number of active demo users")

        summary = obs.finalize_run("success")
        print(f"✅ Basic logging demo completed - Run ID: {obs.get_run_id()}")
        print(f"   Artifacts saved to: artifacts/runs/{obs.get_run_id()}/")


def demonstrate_performance_monitoring():
    """Demonstrate performance monitoring and resource tracking"""
    print("\n=== Demonstrating Performance Monitoring ===")

    with observability_session(run_id="demo-performance") as obs:
        obs.log_info("Starting performance monitoring demonstration")

        # Simulate different operations with varying performance characteristics
        operations = [
            ("data_loading", 5000, 0.0),
            ("data_validation", 2500, 0.0),
            ("complex_calculation", 1000, 0.1),  # 10% failure rate
            ("report_generation", 750, 0.0),
            ("data_export", 3000, 0.05)  # 5% failure rate
        ]

        for op_name, record_count, failure_rate in operations:
            try:
                simulate_data_processing(obs, op_name, record_count, failure_rate)
                obs.add_metric(f"{op_name}_records", record_count)
            except RuntimeError as e:
                obs.log_error(f"Operation failed: {op_name}",
                             operation=op_name,
                             records=record_count,
                             error=str(e))

        # Add some data quality checks
        obs.log_data_quality_check(2025, "record_count", 12250, 15000)
        obs.log_data_quality_check(2025, "error_rate", 0.075, 0.05)  # Exceeds threshold
        obs.log_data_quality_check(2025, "processing_time", 3.2, 5.0)

        summary = obs.finalize_run("partial")  # Some operations failed
        print(f"⚠️  Performance demo completed with issues - Run ID: {obs.get_run_id()}")

        # Show performance summary
        perf_summary = obs.get_performance_summary()
        print(f"   Total operations: {perf_summary['total_operations']}")
        print(f"   Successful: {perf_summary['successful_operations']}")
        print(f"   Failed: {perf_summary['failed_operations']}")
        if perf_summary['slowest_operation']:
            slowest = perf_summary['slowest_operation']
            print(f"   Slowest operation: {slowest['name']} ({slowest['duration']}s)")


def demonstrate_simulation_workflow():
    """Demonstrate full simulation workflow with observability"""
    print("\n=== Demonstrating Simulation Workflow ===")

    with observability_session(run_id="demo-simulation") as obs:
        # Set simulation configuration
        config = {
            "start_year": 2025,
            "end_year": 2027,
            "target_growth_rate": 0.03,
            "cola_rate": 0.005,
            "merit_budget": 0.025,
            "random_seed": 42
        }
        obs.set_configuration(config)
        obs.log_info("Simulation configuration set", **config)

        # Simulate backup creation
        obs.set_backup_path("demo_backups/simulation_backup_20250818.sql")

        # Process each year
        years = list(range(config['start_year'], config['end_year'] + 1))
        total_employees = 40000
        total_events = 0

        for year in years:
            year_context = {"year": year, "progress": f"{year-2024}/{len(years)}"}

            # Simulate year-specific processing
            with obs.track_operation(f"process_year_{year}", **year_context):
                obs.log_info(f"Processing simulation year {year}", **year_context)

                # Simulate various year operations
                operations = [
                    "load_baseline_workforce",
                    "calculate_compensation",
                    "generate_hiring_events",
                    "generate_termination_events",
                    "generate_promotion_events",
                    "consolidate_events",
                    "create_workforce_snapshot"
                ]

                year_events = 0
                for operation in operations:
                    with obs.track_operation(f"{operation}_{year}", **year_context):
                        # Simulate processing
                        time.sleep(random.uniform(0.05, 0.2))

                        # Generate some events
                        if "events" in operation:
                            event_count = random.randint(100, 500)
                            year_events += event_count
                            obs.add_metric(f"{operation}_count_{year}", event_count)

                # Update workforce size (simulate growth)
                total_employees = int(total_employees * (1 + config['target_growth_rate']))
                total_events += year_events

                # Log year completion
                obs.add_metric(f"workforce_size_year_{year}", total_employees)
                obs.add_metric(f"events_generated_year_{year}", year_events)
                obs.log_data_quality_check(year, "workforce_size", total_employees, 50000)
                obs.log_data_quality_check(year, "events_generated", year_events, 2000)

                obs.log_info(f"Year {year} completed successfully",
                            workforce_size=total_employees,
                            events_generated=year_events,
                            **year_context)

        # Final simulation metrics
        obs.add_metric("total_years_processed", len(years))
        obs.add_metric("final_workforce_size", total_employees)
        obs.add_metric("total_events_generated", total_events)

        # Simulate a minor issue for demonstration
        obs.log_warning("Memory usage above 80% during peak processing",
                       memory_usage_percent=85.2,
                       recommendation="Consider increasing memory allocation")

        summary = obs.finalize_run("success")
        print(f"✅ Simulation workflow completed successfully - Run ID: {obs.get_run_id()}")
        print(f"   Years processed: {len(years)}")
        print(f"   Final workforce: {total_employees:,} employees")
        print(f"   Total events: {total_events:,}")


def demonstrate_error_handling():
    """Demonstrate error handling and exception tracking"""
    print("\n=== Demonstrating Error Handling ===")

    with observability_session(run_id="demo-errors") as obs:
        obs.log_info("Starting error handling demonstration")

        # Simulate various types of errors
        try:
            with obs.track_operation("risky_operation"):
                obs.log_info("Attempting risky operation")
                time.sleep(0.1)
                raise ValueError("Simulated critical error in processing")
        except ValueError as e:
            obs.log_exception("Critical error occurred during risky operation",
                             operation="risky_operation",
                             error_type="ValueError")

        # Simulate a database connection error
        obs.log_error("Database connection failed",
                     database="simulation.duckdb",
                     error_code="CONNECTION_TIMEOUT",
                     retry_count=3,
                     severity="high")

        # Simulate a data validation error
        obs.log_warning("Data validation warning detected",
                       validation_rule="employee_id_unique",
                       duplicate_count=5,
                       severity="medium")

        # Add error metrics
        obs.add_metric("total_errors_encountered", 2)
        obs.add_metric("total_warnings_encountered", 1)

        summary = obs.finalize_run("failed")
        print(f"❌ Error handling demo completed - Run ID: {obs.get_run_id()}")

        # Show issue summary
        issues = obs.get_issue_summary()
        print(f"   Total errors: {issues['total_errors']}")
        print(f"   Total warnings: {issues['total_warnings']}")


def show_log_analysis_examples():
    """Show examples of how to analyze the generated logs"""
    print("\n=== Log Analysis Examples ===")

    log_file = Path("logs/navigator.log")
    if not log_file.exists():
        print("❌ No log file found. Run a demonstration first.")
        return

    print(f"📊 Log file location: {log_file}")
    print(f"📊 Log file size: {log_file.stat().st_size / 1024:.1f} KB")

    print("\n🔍 Example log analysis commands:")
    print("   # View all logs with pretty formatting:")
    print("   tail -f logs/navigator.log | jq '.'")
    print()
    print("   # Find all errors:")
    print("   grep '\"level\":\"ERROR\"' logs/navigator.log | jq '.message'")
    print()
    print("   # Track specific run:")
    print("   grep '\"run_id\":\"demo-simulation\"' logs/navigator.log | jq '.'")
    print()
    print("   # Find performance bottlenecks:")
    print("   grep '\"duration_seconds\"' logs/navigator.log | jq '.duration_seconds' | sort -n")
    print()
    print("   # Data quality issues:")
    print("   grep '\"status\":\"warning\"' logs/navigator.log | jq '.check'")


def main():
    """Run all observability demonstrations"""
    print("🔍 PlanWise Navigator - Production Observability Framework Demo")
    print("=" * 70)

    # Ensure directories exist
    Path("logs").mkdir(exist_ok=True)
    Path("artifacts/runs").mkdir(parents=True, exist_ok=True)

    # Run demonstrations
    demonstrate_basic_logging()
    demonstrate_performance_monitoring()
    demonstrate_simulation_workflow()
    demonstrate_error_handling()
    show_log_analysis_examples()

    print("\n" + "=" * 70)
    print("🎉 All demonstrations completed!")
    print("\n📁 Check the following locations for outputs:")
    print("   • Structured logs: logs/navigator.log")
    print("   • Run artifacts: artifacts/runs/*/")
    print("   • Performance data: artifacts/runs/*/performance.json")
    print("   • Error reports: artifacts/runs/*/errors.json")
    print("\n💡 Try running the log analysis commands shown above!")


if __name__ == "__main__":
    main()
