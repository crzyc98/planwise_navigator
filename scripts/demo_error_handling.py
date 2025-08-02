"""
Demonstration script for comprehensive error handling framework.

This script shows how to use the circuit breaker patterns, retry mechanisms,
checkpoint management, and resilient multi-year simulation orchestrator.
"""

import sys
import os
import logging
import time
from typing import Dict, Any

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator_mvp.utils import (
    CircuitBreakerConfig, RetryConfig, with_circuit_breaker, with_retry,
    with_error_handling, error_handling_context, get_all_circuit_breaker_stats,
    CheckpointType, get_checkpoint_manager,
    get_resilient_dbt_executor, get_resilient_db_manager, get_orchestration_resilience
)
from orchestrator_mvp.core.resilient_multi_year_orchestrator import ResilientMultiYearSimulationOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def demo_circuit_breaker():
    """Demonstrate circuit breaker functionality."""
    print("\n" + "="*60)
    print("🔌 CIRCUIT BREAKER DEMONSTRATION")
    print("="*60)

    # Configure circuit breaker for demo
    config = CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout_seconds=2,
        success_threshold=2
    )

    failure_count = 0

    @with_circuit_breaker("demo_operation", config)
    def unreliable_operation():
        nonlocal failure_count
        failure_count += 1

        if failure_count <= 4:
            print(f"   ❌ Operation failed (attempt {failure_count})")
            raise Exception(f"Simulated failure #{failure_count}")
        else:
            print(f"   ✅ Operation succeeded (attempt {failure_count})")
            return "success"

    # Demonstrate circuit breaker behavior
    print("1. Testing circuit breaker with repeated failures:")

    for attempt in range(7):
        try:
            result = unreliable_operation()
            print(f"   Attempt {attempt + 1}: {result}")
        except Exception as e:
            print(f"   Attempt {attempt + 1}: {type(e).__name__} - {str(e)}")

        # Add delay to show recovery timeout
        if attempt == 4:
            print("   ⏱️  Waiting for circuit breaker recovery timeout...")
            time.sleep(2.5)

    # Show final circuit breaker stats
    stats = get_all_circuit_breaker_stats()
    demo_stats = stats.get("demo_operation", {})
    print(f"\n📊 Final circuit breaker stats:")
    print(f"   State: {demo_stats.get('state', 'unknown')}")
    print(f"   Failure count: {demo_stats.get('failure_count', 0)}")
    print(f"   Success count: {demo_stats.get('success_count', 0)}")


def demo_retry_mechanism():
    """Demonstrate retry mechanism with exponential backoff."""
    print("\n" + "="*60)
    print("🔄 RETRY MECHANISM DEMONSTRATION")
    print("="*60)

    # Configure retry for demo
    config = RetryConfig(
        max_attempts=4,
        base_delay_seconds=0.5,
        exponential_backoff_multiplier=2.0,
        jitter_enabled=True
    )

    attempt_count = 0

    @with_retry("demo_retry", config)
    def flaky_operation():
        nonlocal attempt_count
        attempt_count += 1

        if attempt_count <= 2:
            print(f"   ❌ Transient failure on attempt {attempt_count}")
            raise ConnectionError(f"Network timeout on attempt {attempt_count}")
        else:
            print(f"   ✅ Success on attempt {attempt_count}")
            return f"Success after {attempt_count} attempts"

    print("1. Testing retry mechanism with transient failures:")

    try:
        result = flaky_operation()
        print(f"   Final result: {result}")
    except Exception as e:
        print(f"   Final failure: {type(e).__name__} - {str(e)}")

    print(f"   Total attempts made: {attempt_count}")

    # Test non-retryable error
    print("\n2. Testing with non-retryable error:")

    attempt_count = 0

    @with_retry("demo_retry_persistent", config)
    def persistent_failure():
        nonlocal attempt_count
        attempt_count += 1
        print(f"   ❌ Persistent error on attempt {attempt_count}")
        raise ValueError(f"Configuration error - not retryable")

    try:
        result = persistent_failure()
    except Exception as e:
        print(f"   Expected non-retry behavior: {type(e).__name__} - {str(e)}")
        print(f"   Attempts made: {attempt_count} (should be 1)")


def demo_comprehensive_error_handling():
    """Demonstrate comprehensive error handling with both circuit breaker and retry."""
    print("\n" + "="*60)
    print("🛡️  COMPREHENSIVE ERROR HANDLING DEMONSTRATION")
    print("="*60)

    # Configure comprehensive error handling
    circuit_config = CircuitBreakerConfig(
        failure_threshold=2,
        recovery_timeout_seconds=1,
        success_threshold=1
    )

    retry_config = RetryConfig(
        max_attempts=3,
        base_delay_seconds=0.2,
        exponential_backoff_multiplier=1.5
    )

    operation_count = 0

    @with_error_handling(
        "comprehensive_demo",
        circuit_config,
        retry_config
    )
    def comprehensive_operation():
        nonlocal operation_count
        operation_count += 1

        if operation_count <= 3:
            print(f"   ❌ Operation {operation_count} failed (will retry)")
            raise ConnectionError(f"Temporary failure #{operation_count}")
        else:
            print(f"   ✅ Operation {operation_count} succeeded")
            return f"Success on operation {operation_count}"

    # First set of operations - should trigger retries
    print("1. Testing comprehensive error handling:")

    try:
        result = comprehensive_operation()
        print(f"   Result: {result}")
    except Exception as e:
        print(f"   Failed after retries: {type(e).__name__}")

    # Reset and test circuit breaker
    operation_count = 0

    print("\n2. Testing circuit breaker activation:")

    for i in range(4):
        try:
            result = comprehensive_operation()
            print(f"   Call {i+1}: {result}")
        except Exception as e:
            print(f"   Call {i+1}: {type(e).__name__} - {str(e)}")


def demo_checkpoint_management():
    """Demonstrate checkpoint management and state recovery."""
    print("\n" + "="*60)
    print("💾 CHECKPOINT MANAGEMENT DEMONSTRATION")
    print("="*60)

    # Get checkpoint manager
    checkpoint_manager = get_checkpoint_manager(".demo_checkpoints")

    print("1. Creating simulation checkpoints:")

    # Create various types of checkpoints
    checkpoints = []

    # Simulation start checkpoint
    start_checkpoint = checkpoint_manager.create_checkpoint(
        CheckpointType.SIMULATION_START,
        2025,
        {"status": "starting", "config": {"growth_rate": 0.03}},
        metadata={"demo": True}
    )
    checkpoints.append(start_checkpoint)
    print(f"   ✅ Created simulation start checkpoint: {start_checkpoint.checkpoint_id}")

    # Year completion checkpoints
    for year in [2025, 2026]:
        year_checkpoint = checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_COMPLETE,
            year,
            {"year": year, "workforce_count": 1000 + year - 2025, "status": "completed"},
            metadata={"employees": 1000 + year - 2025}
        )
        checkpoints.append(year_checkpoint)
        print(f"   ✅ Created year {year} completion checkpoint: {year_checkpoint.checkpoint_id}")

    # Step completion checkpoint
    step_checkpoint = checkpoint_manager.create_checkpoint(
        CheckpointType.STEP_COMPLETE,
        2027,
        {"step": "event_generation", "events_created": 500, "status": "completed"},
        step_name="event_generation"
    )
    checkpoints.append(step_checkpoint)
    print(f"   ✅ Created step completion checkpoint: {step_checkpoint.checkpoint_id}")

    print("\n2. Retrieving checkpoints:")

    # Get latest checkpoint for a year
    latest_2026 = checkpoint_manager.get_latest_checkpoint(2026)
    if latest_2026:
        print(f"   Latest 2026 checkpoint: {latest_2026.checkpoint_id} ({latest_2026.checkpoint_type.value})")

    # Get specific type of checkpoint
    year_complete = checkpoint_manager.get_latest_checkpoint(2026, CheckpointType.YEAR_COMPLETE)
    if year_complete:
        print(f"   Year complete checkpoint: {year_complete.checkpoint_id}")

    # Check resume capability
    resume_info = checkpoint_manager.get_resume_checkpoint(2025, 2029)
    if resume_info:
        resume_year, checkpoint = resume_info
        print(f"   Can resume from year {resume_year} using checkpoint: {checkpoint.checkpoint_id}")

    print("\n3. Checkpoint summary:")
    summary = checkpoint_manager.get_checkpoint_summary()
    print(f"   Total checkpoints: {summary['total_checkpoints']}")
    print(f"   Years with checkpoints: {summary['years_with_checkpoints']}")
    print(f"   Checkpoint types: {list(summary['checkpoint_types'].keys())}")

    if summary['latest_checkpoint']:
        latest = summary['latest_checkpoint']
        print(f"   Latest: {latest['checkpoint_id']} (year {latest['year']}, {latest['type']})")


def demo_resilient_components():
    """Demonstrate resilient dbt executor and database manager."""
    print("\n" + "="*60)
    print("🔧 RESILIENT COMPONENTS DEMONSTRATION")
    print("="*60)

    # Get resilient components
    dbt_executor = get_resilient_dbt_executor()
    db_manager = get_resilient_db_manager()
    orchestration_resilience = get_orchestration_resilience("demo")

    print("1. Resilient dbt executor:")
    print(f"   Name: {dbt_executor.name}")
    print(f"   Model config failure threshold: {dbt_executor.model_config.failure_threshold}")
    print(f"   Retry config max attempts: {dbt_executor.retry_config.max_attempts}")
    print(f"   Available fallback strategies: {list(dbt_executor.fallback_strategies.keys())}")

    # Test error classification
    compilation_error = Exception("dbt compilation failed due to syntax error")
    error_type = dbt_executor._classify_dbt_error(compilation_error, "test_model")
    print(f"   Error classification test: '{str(compilation_error)[:50]}...' → {error_type}")

    print("\n2. Resilient database manager:")
    print(f"   Name: {db_manager.name}")
    print(f"   Database config failure threshold: {db_manager.db_config.failure_threshold}")
    print(f"   Retry config max attempts: {db_manager.retry_config.max_attempts}")

    print("\n3. Multi-year orchestration resilience:")
    print(f"   Orchestrator name: {orchestration_resilience.orchestrator_name}")
    print(f"   Year transition config: {orchestration_resilience.year_transition_config.failure_threshold} failures")
    print(f"   Step execution config: {orchestration_resilience.step_execution_config.max_attempts} attempts")

    # Show execution statistics
    dbt_stats = dbt_executor.get_execution_stats()
    print(f"\n4. Execution statistics:")
    print(f"   dbt operations: {dbt_stats['total_dbt_operations']}")
    print(f"   Overall health: {dbt_stats['overall_health']}")


def demo_error_handling_context():
    """Demonstrate error handling context manager."""
    print("\n" + "="*60)
    print("📝 ERROR HANDLING CONTEXT DEMONSTRATION")
    print("="*60)

    print("1. Successful operation with context:")

    with error_handling_context("demo_successful_operation", {"input": "test_data"}):
        print("   ✅ Performing successful operation...")
        time.sleep(0.1)  # Simulate work
        print("   ✅ Operation completed successfully")

    print("\n2. Failed operation with context and recovery:")

    try:
        with error_handling_context("demo_failed_operation", {"input": "invalid_data"}):
            print("   ❌ Performing operation that will fail...")
            time.sleep(0.1)  # Simulate work
            raise ValueError("Simulated operation failure")
    except ValueError as e:
        print(f"   ❌ Operation failed as expected: {e}")

    print("\n3. Error context provides detailed logging and recovery information")


def demo_simulation_configuration():
    """Show how to configure the resilient multi-year orchestrator."""
    print("\n" + "="*60)
    print("⚙️  RESILIENT ORCHESTRATOR CONFIGURATION")
    print("="*60)

    # Sample configuration
    config = {
        'target_growth_rate': 0.03,
        'workforce': {
            'total_termination_rate': 0.12,
            'new_hire_termination_rate': 0.25
        },
        'eligibility': {
            'waiting_period_days': 365
        },
        'enrollment': {
            'auto_enrollment': {
                'hire_date_cutoff': '2024-01-01',
                'scope': 'new_hires_only'
            }
        },
        'random_seed': 42
    }

    print("1. Configuration example:")
    import json
    print(json.dumps(config, indent=2))

    print("\n2. Orchestrator initialization options:")

    initialization_options = {
        'start_year': 2025,
        'end_year': 2027,
        'config': config,
        'force_clear': False,
        'preserve_data': True,
        'enable_checkpoints': True,
        'checkpoint_frequency': 'step'  # 'step', 'year', or 'major'
    }

    print("   Resilient orchestrator options:")
    for key, value in initialization_options.items():
        if key != 'config':
            print(f"     {key}: {value}")

    print("\n3. Error handling features enabled:")
    features = [
        "✅ Circuit breaker protection for all major operations",
        "✅ Retry mechanisms with exponential backoff",
        "✅ Automatic checkpoint creation and recovery",
        "✅ State validation and consistency checking",
        "✅ Graceful degradation and fallback strategies",
        "✅ Resume capability from any simulation year",
        "✅ Comprehensive error reporting and recovery guidance"
    ]

    for feature in features:
        print(f"   {feature}")


def main():
    """Run all demonstrations."""
    print("🚀 COMPREHENSIVE ERROR HANDLING FRAMEWORK DEMONSTRATION")
    print("="*80)
    print("This demonstration shows the key features of the error handling system")
    print("implemented for the multi-year simulation orchestrator.")
    print("="*80)

    try:
        # Run individual demonstrations
        demo_circuit_breaker()
        demo_retry_mechanism()
        demo_comprehensive_error_handling()
        demo_checkpoint_management()
        demo_resilient_components()
        demo_error_handling_context()
        demo_simulation_configuration()

        print("\n" + "="*80)
        print("🎉 DEMONSTRATION COMPLETED SUCCESSFULLY")
        print("="*80)
        print("All error handling components demonstrated successfully!")
        print("\nKey takeaways:")
        print("• Circuit breakers protect against cascading failures")
        print("• Retry mechanisms handle transient errors automatically")
        print("• Checkpoints enable resume capability and state recovery")
        print("• Resilient components provide fallback strategies")
        print("• Comprehensive logging aids in debugging and monitoring")
        print("\nThe system is ready for production use with robust error handling!")

    except Exception as e:
        logger.error(f"Demonstration failed: {e}")
        print(f"\n❌ Demonstration failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
