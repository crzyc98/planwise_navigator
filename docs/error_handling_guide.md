# Comprehensive Error Handling Framework Guide

This guide covers the comprehensive error handling framework implemented for the multi-year simulation system, including circuit breaker patterns, retry mechanisms, checkpoint management, and state recovery capabilities.

## Table of Contents

1. [Overview](#overview)
2. [Core Components](#core-components)
3. [Circuit Breaker Pattern](#circuit-breaker-pattern)
4. [Retry Mechanisms](#retry-mechanisms)
5. [Error Classification](#error-classification)
6. [Checkpoint Management](#checkpoint-management)
7. [Multi-Year State Recovery](#multi-year-state-recovery)
8. [Resilient Components](#resilient-components)
9. [Usage Examples](#usage-examples)
10. [Configuration](#configuration)
11. [Monitoring and Debugging](#monitoring-and-debugging)
12. [Best Practices](#best-practices)

## Overview

The error handling framework provides enterprise-grade resilience for multi-year simulations through:

- **Circuit Breaker Protection**: Prevents cascading failures by temporarily blocking operations that consistently fail
- **Intelligent Retry Logic**: Automatically retries transient failures with exponential backoff and jitter
- **Error Classification**: Distinguishes between retryable and non-retryable errors
- **Checkpoint Management**: Creates recovery points for resuming interrupted simulations
- **State Recovery**: Detects and repairs incomplete simulations
- **Graceful Degradation**: Falls back to alternative strategies when primary approaches fail

## Core Components

### Error Handling Module (`orchestrator_mvp/utils/error_handling.py`)

The core error handling module provides:

- `CircuitBreaker`: State machine for failure detection and recovery
- `RetryHandler`: Exponential backoff retry logic with jitter
- `ErrorClassifier`: Automatic error categorization and retry decisions
- `ErrorRecoveryManager`: Pluggable recovery strategies
- Decorators: `@with_circuit_breaker`, `@with_retry`, `@with_error_handling`

### Multi-Year Error Handling (`orchestrator_mvp/utils/multi_year_error_handling.py`)

Specialized for multi-year simulations:

- `CheckpointManager`: Creates and manages simulation checkpoints
- `MultiYearStateRecovery`: Detects and repairs incomplete simulations
- `SimulationCheckpoint`: Immutable recovery points with integrity validation
- Recovery strategies for year-level and step-level failures

### Simulation Resilience (`orchestrator_mvp/utils/simulation_resilience.py`)

Production-ready utilities:

- `ResilientDbtExecutor`: dbt operations with fallback strategies
- `ResilientDatabaseManager`: Database operations with connection pooling
- `MultiYearOrchestrationResilience`: Comprehensive simulation orchestration

## Circuit Breaker Pattern

### How It Works

Circuit breakers monitor operation failures and transition between three states:

1. **CLOSED**: Normal operation, requests pass through
2. **OPEN**: Circuit is open, requests are blocked (fail-fast)
3. **HALF_OPEN**: Testing recovery, limited requests allowed

### Configuration

```python
from orchestrator_mvp.utils import CircuitBreakerConfig, with_circuit_breaker

# Configure circuit breaker
config = CircuitBreakerConfig(
    failure_threshold=5,           # Open after 5 failures
    recovery_timeout_seconds=60,   # Wait 60s before attempting recovery
    success_threshold=3,           # Close after 3 successes in half-open
    failure_rate_threshold=0.5,    # Open if failure rate > 50%
    minimum_requests=10            # Minimum requests before calculating rate
)

# Apply to function
@with_circuit_breaker("database_operation", config)
def execute_database_query():
    # Your database operation here
    pass
```

### Advanced Features

- **Sliding Window**: Tracks failure rates over time
- **Automatic Recovery**: Periodically tests if service has recovered
- **Comprehensive Monitoring**: Detailed statistics and health metrics
- **Thread-Safe**: Safe for concurrent access

## Retry Mechanisms

### Exponential Backoff with Jitter

```python
from orchestrator_mvp.utils import RetryConfig, with_retry

config = RetryConfig(
    max_attempts=3,                        # Maximum retry attempts
    base_delay_seconds=1.0,               # Initial delay
    max_delay_seconds=60.0,               # Maximum delay cap
    exponential_backoff_multiplier=2.0,   # Exponential factor
    jitter_enabled=True,                  # Add randomness
    jitter_max_seconds=1.0                # Maximum jitter
)

@with_retry("api_call", config)
def call_external_api():
    # Your API call here
    pass
```

### Smart Retry Decisions

The system automatically determines which errors should be retried:

- **Retryable**: Network timeouts, connection errors, temporary resource issues
- **Non-Retryable**: Configuration errors, authentication failures, data corruption
- **Custom Logic**: Override retry decisions based on specific error patterns

## Error Classification

### Automatic Classification

```python
from orchestrator_mvp.utils import ErrorClassifier

# Classify any exception
error = ConnectionError("Network timeout")
severity, category = ErrorClassifier.classify_error(error)

# Check if retryable
is_retryable = ErrorClassifier.is_retryable(error)
```

### Error Categories

- **TRANSIENT**: Temporary issues (network, locks, timeouts)
- **PERSISTENT**: Configuration or logic errors
- **RESOURCE**: Memory, disk, CPU issues
- **DATA_QUALITY**: Invalid or corrupted data
- **DEPENDENCY**: External service failures
- **VALIDATION**: Business rule violations

## Checkpoint Management

### Creating Checkpoints

```python
from orchestrator_mvp.utils import get_checkpoint_manager, CheckpointType

checkpoint_manager = get_checkpoint_manager()

# Create checkpoint at key points
checkpoint = checkpoint_manager.create_checkpoint(
    CheckpointType.YEAR_COMPLETE,
    simulation_year=2025,
    state_data={
        "workforce_count": 10000,
        "events_generated": 5000,
        "status": "completed"
    },
    metadata={"execution_time": 120.5}
)
```

### Checkpoint Types

- **SIMULATION_START**: Beginning of multi-year simulation
- **YEAR_START**: Beginning of a simulation year
- **STEP_COMPLETE**: Completion of a simulation step
- **YEAR_COMPLETE**: Completion of a simulation year
- **SIMULATION_COMPLETE**: End of multi-year simulation
- **ERROR_CHECKPOINT**: Created when errors occur for recovery

### Recovery from Checkpoints

```python
# Find best resume point
resume_info = checkpoint_manager.get_resume_checkpoint(start_year=2025, end_year=2029)

if resume_info:
    resume_year, checkpoint = resume_info
    print(f"Can resume from year {resume_year}")
    print(f"Using checkpoint: {checkpoint.checkpoint_id}")
```

## Multi-Year State Recovery

### Detecting Incomplete Simulations

```python
from orchestrator_mvp.utils import get_state_recovery

state_recovery = get_state_recovery()

# Detect incomplete state
detection = state_recovery.detect_incomplete_simulation(2025, 2029)

if detection["incomplete_simulation_detected"]:
    print(f"Can resume from year: {detection['resume_recommendation']}")
    print(f"Completed years: {detection['completed_years']}")
    print(f"Missing years: {detection['missing_years']}")
```

### Data Consistency Validation

```python
# Validate multi-year consistency
validation = state_recovery.validate_multi_year_consistency(2025, 2029)

if not validation["consistent"]:
    print("Data inconsistencies found:")
    for issue in validation["inconsistencies"]:
        print(f"  - {issue}")
```

### Automatic Repair

```python
# Attempt automatic repair
repair_success = state_recovery.repair_simulation_state(
    start_year=2025,
    end_year=2029,
    repair_strategy="auto"  # "auto", "rollback", or "rebuild"
)

if repair_success:
    print("Simulation state repaired successfully")
```

## Resilient Components

### Resilient dbt Executor

```python
from orchestrator_mvp.utils import get_resilient_dbt_executor

dbt_executor = get_resilient_dbt_executor()

# Run model with comprehensive error handling
result = dbt_executor.run_model_with_resilience(
    model_name="fct_yearly_events",
    vars_dict={"simulation_year": 2025},
    full_refresh=False
)

# Run seeds with fallback strategies
result = dbt_executor.run_seeds_with_resilience([
    "config_job_levels",
    "comp_levers"
])
```

### Resilient Database Manager

```python
from orchestrator_mvp.utils import get_resilient_db_manager

db_manager = get_resilient_db_manager()

# Execute query with circuit breaker protection
result = db_manager.execute_query_with_resilience(
    "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
    params=[2025],
    operation_name="workforce_count"
)

# Validate data consistency
validation = db_manager.validate_data_consistency("fct_yearly_events", 2025)
```

## Usage Examples

### Basic Error Handling

```python
from orchestrator_mvp.utils import with_error_handling, CircuitBreakerConfig, RetryConfig

# Comprehensive error handling decorator
@with_error_handling(
    operation_name="critical_operation",
    circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3),
    retry_config=RetryConfig(max_attempts=3),
    enable_circuit_breaker=True,
    enable_retry=True
)
def critical_operation():
    # Your critical operation here
    pass
```

### Error Handling Context

```python
from orchestrator_mvp.utils import error_handling_context

with error_handling_context("data_processing", {"input_file": "data.csv"}):
    # Process data with automatic error logging and recovery attempts
    process_data_file("data.csv")
```

### Resilient Multi-Year Simulation

```python
from orchestrator_mvp.core.resilient_multi_year_orchestrator import ResilientMultiYearSimulationOrchestrator

# Initialize resilient orchestrator
orchestrator = ResilientMultiYearSimulationOrchestrator(
    start_year=2025,
    end_year=2029,
    config=simulation_config,
    enable_checkpoints=True,
    checkpoint_frequency="step"
)

# Run with comprehensive error handling
results = orchestrator.run_simulation(
    skip_breaks=True,
    auto_recover=True
)

# Get resilience report
resilience_report = orchestrator.get_resilience_report()
```

## Configuration

### Environment Variables

```bash
# Optional: Set custom checkpoint directory
export CHECKPOINT_DIR="/path/to/checkpoints"

# Optional: Enable debug logging
export LOG_LEVEL="DEBUG"
```

### Configuration Files

Create a `resilience_config.yaml` file:

```yaml
circuit_breakers:
  database:
    failure_threshold: 5
    recovery_timeout_seconds: 30
    success_threshold: 2

  dbt:
    failure_threshold: 3
    recovery_timeout_seconds: 60
    success_threshold: 1

retry_policies:
  default:
    max_attempts: 3
    base_delay_seconds: 1.0
    exponential_backoff_multiplier: 2.0

  database:
    max_attempts: 5
    base_delay_seconds: 0.5
    max_delay_seconds: 30.0

checkpoints:
  enabled: true
  frequency: "step"  # "step", "year", "major"
  cleanup_days: 7
```

## Monitoring and Debugging

### Circuit Breaker Statistics

```python
from orchestrator_mvp.utils import get_all_circuit_breaker_stats

# Get all circuit breaker statistics
stats = get_all_circuit_breaker_stats()

for name, breaker_stats in stats.items():
    print(f"Circuit Breaker: {name}")
    print(f"  State: {breaker_stats['state']}")
    print(f"  Failures: {breaker_stats['failure_count']}")
    print(f"  Failure Rate: {breaker_stats['failure_rate']:.2%}")
```

### Checkpoint Summary

```python
from orchestrator_mvp.utils import get_checkpoint_manager

checkpoint_manager = get_checkpoint_manager()
summary = checkpoint_manager.get_checkpoint_summary()

print(f"Total checkpoints: {summary['total_checkpoints']}")
print(f"Years with checkpoints: {summary['years_with_checkpoints']}")
print(f"Latest checkpoint: {summary['latest_checkpoint']}")
```

### Error Summary

```python
# From resilient orchestrator results
error_summary = results['error_summary']

print(f"Total errors handled: {error_summary['total_errors']}")
print(f"Successful recoveries: {error_summary['recoverable_errors']}")
print(f"Circuit breaker trips: {error_summary['circuit_breaker_trips']}")
print(f"Checkpoint recoveries: {error_summary['checkpoint_recoveries']}")
```

## Best Practices

### 1. Circuit Breaker Configuration

- **Set appropriate thresholds**: Too low causes false positives, too high delays failure detection
- **Configure recovery timeouts**: Based on expected service recovery time
- **Monitor failure rates**: Use sliding windows for better accuracy

### 2. Retry Strategy

- **Use exponential backoff**: Prevents overwhelming already struggling services
- **Add jitter**: Reduces thundering herd effects
- **Classify errors correctly**: Don't retry persistent failures

### 3. Checkpoint Management

- **Checkpoint at logical boundaries**: Year completion, major step completion
- **Include sufficient state**: Enable full recovery without recomputation
- **Regular cleanup**: Remove old checkpoints to save space

### 4. Error Handling

- **Log comprehensively**: Include context, error details, and recovery actions
- **Provide actionable guidance**: Help users understand how to resolve issues
- **Test failure scenarios**: Regularly test error handling paths

### 5. Monitoring

- **Track key metrics**: Error rates, circuit breaker states, recovery success
- **Set up alerts**: For circuit breaker openings and repeated failures
- **Regular health checks**: Validate system resilience periodically

### 6. Recovery Testing

- **Test checkpoint recovery**: Regularly validate checkpoint integrity
- **Simulate failures**: Test error handling under various failure conditions
- **Practice disaster recovery**: Ensure procedures work when needed

## Troubleshooting

### Common Issues

1. **Circuit Breaker Stuck Open**
   - Check service health
   - Reduce failure threshold temporarily
   - Manual circuit breaker reset if needed

2. **Excessive Retries**
   - Review error classification
   - Adjust retry configuration
   - Check for persistent vs transient errors

3. **Checkpoint Corruption**
   - Validate checkpoint integrity
   - Use backup checkpoints
   - Implement checkpoint versioning

4. **Recovery Failures**
   - Check data consistency
   - Validate dependencies
   - Use manual recovery procedures

### Debug Commands

```python
# Reset all circuit breakers
from orchestrator_mvp.utils import reset_all_circuit_breakers
reset_all_circuit_breakers()

# Validate checkpoint
checkpoint_manager._validate_checkpoint(checkpoint)

# Get detailed error context
with error_handling_context("debug_operation") as ctx:
    # Your operation here
    pass
```

## Performance Considerations

- **Circuit breaker overhead**: Minimal (~0.1ms per operation)
- **Retry delays**: Factor into total execution time
- **Checkpoint storage**: Monitor disk usage for large simulations
- **Memory usage**: Circuit breakers maintain sliding windows in memory

## Security Considerations

- **Checkpoint data**: May contain sensitive simulation parameters
- **Error logs**: Avoid logging sensitive data in error messages
- **Recovery operations**: Ensure proper access controls

This comprehensive error handling framework provides production-ready resilience for multi-year simulations while maintaining performance and usability.
