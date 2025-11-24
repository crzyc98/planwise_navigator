# Error Troubleshooting Guide

**Fidelity PlanAlign Engine Enhanced Error Handling Framework (Epic E074)**

---

## Overview

Fidelity PlanAlign Engine implements a comprehensive structured error handling framework that provides:

- **Execution Context**: Every error includes year, stage, model, and configuration details
- **Resolution Hints**: Actionable steps to resolve common issues
- **Error Catalog**: Pattern-matched resolution guidance for 90%+ of production errors
- **Correlation IDs**: Trace errors across multi-year simulations

---

## Error Categories

All Navigator errors are categorized for faster diagnosis:

| Category | Description | Common Examples |
|----------|-------------|-----------------|
| **DATABASE** | DuckDB locks, queries, connections | Lock conflicts, query failures |
| **CONFIGURATION** | Invalid or missing parameters | Missing random_seed, invalid YAML |
| **DATA_QUALITY** | Test failures, validation errors | Null values, failed dbt tests |
| **RESOURCE** | Memory, CPU, disk exhaustion | Out of memory, disk full |
| **NETWORK** | Proxy, SSL, timeout issues | Certificate errors, proxy config |
| **DEPENDENCY** | Missing models, circular deps | Upstream model not found |
| **STATE** | Checkpoint corruption, inconsistency | Invalid checkpoint version |

---

## Error Severity Levels

| Severity | Impact | Action Required |
|----------|--------|-----------------|
| **CRITICAL** | Data corruption, system-wide failure | Immediate intervention, rollback |
| **ERROR** | Stage/year failure, simulation stopped | Fix and retry |
| **RECOVERABLE** | Transient failure, retry possible | Close locks, retry |
| **WARNING** | Non-blocking, may degrade quality | Review and monitor |

---

## Common Error Patterns

### 1. Database Lock Conflict

**Symptoms**:
```
ERROR: Database lock conflict detected
Severity: RECOVERABLE | Category: database

EXECUTION CONTEXT:
  simulation_year: 2025
  workflow_stage: EVENT_GENERATION
  model_name: int_termination_events
```

**Resolution**:
1. Close database explorer in VS Code/Windsurf/DataGrip
2. Check for other Python processes: `ps aux | grep duckdb`
3. Kill stale connections: `pkill -f 'duckdb.*simulation.duckdb'`
4. Retry simulation

**Estimated Time**: 1-2 minutes

**Prevention**: Always close database connections before running simulations.

---

### 2. Memory Exhaustion

**Symptoms**:
```
ERROR: Simulation exceeded available memory (memory_used: 4096.5MB)
Severity: CRITICAL | Category: resource
```

**Resolution**:
1. Reduce dbt threads: `orchestrator.threading.dbt_threads: 1`
2. Enable adaptive memory: `optimization.adaptive_memory.enabled: true`
3. Reduce batch size: `optimization.batch_size: 250`
4. Close other memory-intensive applications
5. Consider subset mode: `--vars '{dev_employee_limit: 1000}'`

**Estimated Time**: 10 minutes

**Prevention**: Configure adaptive memory management and monitor memory usage.

---

### 3. dbt Compilation Error

**Symptoms**:
```
ERROR: dbt compilation failed due to SQL syntax or Jinja errors
Severity: ERROR | Category: database

EXECUTION CONTEXT:
  model_name: int_baseline_workforce
```

**Resolution**:
1. Review error message for line number and specific syntax issue
2. Check model file for missing CTEs or incorrect Jinja
3. Test compilation: `dbt compile --select <model>`
4. Verify dbt_vars: `dbt compile --vars '{simulation_year: 2025}'`

**Estimated Time**: 10-15 minutes

**Prevention**: Use dbt compile before running full simulations.

---

### 4. Missing Model Dependency

**Symptoms**:
```
ERROR: Required upstream model not found
Severity: ERROR | Category: dependency
```

**Resolution**:
1. Check dbt lineage: `dbt docs generate && dbt docs serve`
2. Verify model exists: `ls dbt/models/**/<model>.sql`
3. Run full build: `dbt build --full-refresh`
4. Check model selection syntax: `dbt run --select +<model>`

**Estimated Time**: 10 minutes

**Prevention**: Always verify dbt DAG before running simulations.

---

### 5. Data Quality Test Failure

**Symptoms**:
```
ERROR: Data quality test failed (test: not_null_fct_yearly_events_employee_id)
Severity: WARNING | Category: data_quality
```

**Resolution**:
1. View test results: `dbt test --select <model>`
2. Query failed records: `SELECT * FROM <model> WHERE <condition>`
3. Check upstream data quality
4. Determine if failure is expected (e.g., new data pattern)
5. Adjust test thresholds if needed or fix data issue

**Estimated Time**: 20 minutes

**Prevention**: Monitor data quality trends and implement upstream validation.

---

### 6. Network/Proxy Configuration Error

**Symptoms**:
```
ERROR: SSL certificate verification failed
Severity: RECOVERABLE | Category: network
```

**Resolution**:
1. Check proxy settings: `echo $HTTP_PROXY $HTTPS_PROXY`
2. Test connection: `curl -x $HTTP_PROXY https://example.com`
3. Set CA bundle: `export REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt`
4. Update network config: `config/network_config.yaml`

**Estimated Time**: 15 minutes

**Prevention**: Configure corporate proxy and SSL certificates in environment.

---

### 7. Checkpoint Corruption

**Symptoms**:
```
ERROR: Checkpoint file is corrupted or incompatible
Severity: ERROR | Category: state
```

**Resolution**:
1. List checkpoints: `planalign checkpoints list`
2. Clean corrupted checkpoints: `planalign checkpoints cleanup`
3. Restart simulation from scratch (no --resume flag)
4. If persistent, delete `.navigator_checkpoints/` directory

**Estimated Time**: 5 minutes

**Prevention**: Use enhanced checkpoint system and validate config hash.

---

## Using the Error Catalog

### Python API

```python
from planalign_orchestrator.error_catalog import get_error_catalog
from planalign_orchestrator.exceptions import (
    NavigatorError,
    ExecutionContext,
    ErrorCategory,
    ErrorSeverity
)

# Get global error catalog
catalog = get_error_catalog()

# Find resolution hints for an error message
hints = catalog.find_resolution_hints("Database is locked")

# Display resolution steps
for hint in hints:
    print(f"\n{hint.title}")
    print(f"  {hint.description}")
    for step in hint.steps:
        print(f"    - {step}")
    print(f"  Estimated Time: {hint.estimated_resolution_time}")
```

### Creating Structured Exceptions

```python
from planalign_orchestrator.exceptions import (
    DbtExecutionError,
    ExecutionContext
)

# Create execution context with full details
context = ExecutionContext(
    simulation_year=2025,
    workflow_stage="EVENT_GENERATION",
    model_name="int_termination_events",
    scenario_id="baseline",
    plan_design_id="default",
    random_seed=42,
    thread_count=4,
    metadata={"retry_count": 3}
)

# Raise structured exception with context
raise DbtExecutionError(
    "Database execution failed during termination event generation",
    context=context
)
```

### Exception Output Format

```
================================================================================
ERROR: Database execution failed during termination event generation
Severity: RECOVERABLE | Category: database
================================================================================

EXECUTION CONTEXT:
  simulation_year: 2025
  workflow_stage: EVENT_GENERATION
  model_name: int_termination_events
  scenario_id: baseline
  plan_design_id: default
  random_seed: 42
  thread_count: 4
  correlation_id: a4b2c9f1
  timestamp: 2025-10-07T14:32:15.123456
  retry_count: 3

RESOLUTION HINTS:

1. Review Database Error
   dbt model execution failed during database query
   Steps:
     - Check if database is locked (close IDE connections)
     - Verify upstream models completed successfully
     - Check for memory pressure: df -h and free -m
     - Review query plan: EXPLAIN <query>
   Est. Time: 5-10 minutes

================================================================================
```

---

## Diagnostic Workflow

### Step 1: Read the Error Context

Every error includes execution context. Key fields to check:

- `simulation_year`: Which year failed?
- `workflow_stage`: Which stage (FOUNDATION, EVENT_GENERATION, etc.)?
- `model_name`: Which dbt model failed?
- `correlation_id`: Unique ID to trace across logs

### Step 2: Check Error Category & Severity

- **CRITICAL**: Stop everything, investigate immediately
- **ERROR**: Fix before continuing
- **RECOVERABLE**: Retry after fixing
- **WARNING**: Note and continue

### Step 3: Review Resolution Hints

Follow the provided resolution steps in order. Most common errors have automated suggestions.

### Step 4: Check Error Frequency

If the same error pattern occurs repeatedly:

```python
from planalign_orchestrator.error_catalog import get_error_catalog

catalog = get_error_catalog()
stats = catalog.get_pattern_statistics()

# Shows most frequent errors
for error_type, frequency in stats.items():
    if frequency > 0:
        print(f"{error_type}: {frequency} occurrences")
```

### Step 5: Review Correlation IDs

For multi-year simulations, use correlation IDs to trace related failures across years.

---

## Testing the Error Framework

### Unit Tests

```bash
# Test exception hierarchy
pytest tests/test_exceptions.py -v

# Test error catalog
pytest tests/test_error_catalog.py -v

# Full test suite
pytest tests/test_exceptions.py tests/test_error_catalog.py -v --cov=planalign_orchestrator/exceptions --cov=planalign_orchestrator/error_catalog
```

### Expected Coverage

- Exception classes: 100%
- Error catalog patterns: 90%+
- Resolution hints: 100%

---

## Adding Custom Error Patterns

### Define Custom Pattern

```python
from planalign_orchestrator.error_catalog import get_error_catalog, ErrorPattern
from planalign_orchestrator.exceptions import ResolutionHint, ErrorCategory
import re

# Get global catalog
catalog = get_error_catalog()

# Define custom pattern
custom_pattern = ErrorPattern(
    pattern=re.compile(r"custom error signature", re.IGNORECASE),
    category=ErrorCategory.CONFIGURATION,
    title="Custom Configuration Error",
    description="Custom error condition detected",
    resolution_hints=[
        ResolutionHint(
            title="Fix Custom Issue",
            description="Apply custom resolution",
            steps=[
                "Step 1: Check configuration",
                "Step 2: Update settings",
                "Step 3: Retry operation"
            ],
            estimated_resolution_time="5 minutes"
        )
    ]
)

# Add to catalog
catalog.add_pattern(custom_pattern)
```

---

## Integration with Observability

The error handling framework integrates with ObservabilityManager for structured logging:

```python
from planalign_orchestrator.exceptions import NavigatorError, ExecutionContext

# Errors are automatically logged with structured context
try:
    # Simulation code
    pass
except Exception as e:
    context = ExecutionContext(simulation_year=2025)
    error = NavigatorError(
        "Simulation failed",
        context=context,
        original_exception=e
    )

    # Log structured error
    print(error.format_diagnostic_message())

    # Serialize for logging systems
    error_dict = error.to_dict()
```

---

## Best Practices

### 1. Always Provide Context

Never raise generic exceptions. Always include execution context:

```python
# ❌ BAD
raise RuntimeError("Database error")

# ✅ GOOD
context = ExecutionContext(simulation_year=2025, model_name="int_baseline_workforce")
raise DatabaseError("Database connection failed", context=context)
```

### 2. Use Specific Exception Classes

Use the most specific exception class available:

```python
# ❌ BAD
raise NavigatorError("Database locked")

# ✅ GOOD
raise DatabaseLockError(context=context)
```

### 3. Include Original Exceptions

When wrapping exceptions, always preserve the original:

```python
try:
    # Database operation
    pass
except ConnectionError as e:
    raise DatabaseError(
        "Failed to connect to database",
        context=context,
        original_exception=e
    )
```

### 4. Monitor Error Frequencies

Track error patterns to identify systemic issues:

```python
# Review error statistics weekly
catalog = get_error_catalog()
stats = catalog.get_pattern_statistics()

# Investigate patterns with frequency > 5
for pattern, freq in stats.items():
    if freq > 5:
        print(f"⚠️ {pattern} occurred {freq} times - investigate root cause")
```

---

## Success Metrics

The error handling framework targets:

- **Error Context Completeness**: 100% of errors include year, stage, model, config
- **Resolution Time**: <5 minutes average (previously 30-60 minutes)
- **Self-Service Rate**: 70% of common errors resolved without support
- **Error Catalog Coverage**: 90%+ of production errors have resolution hints

---

## Related Documentation

- **Epic E074**: Enhanced Error Handling & Diagnostic Framework
- **Epic E044**: Production Observability (structured logging foundation)
- **Epic E046**: Recovery & Checkpoint System (state error handling)
- **CLAUDE.md**: Project playbook and development guidelines

---

## Support & Escalation

### Self-Service Resolution

1. Check this troubleshooting guide for error category
2. Follow resolution hints provided in error message
3. Review error catalog statistics for frequency patterns
4. Consult CLAUDE.md for architectural context

### Escalation Criteria

Escalate if:

- Error severity is CRITICAL with data corruption risk
- Resolution hints don't resolve the issue after 2-3 attempts
- Error pattern is not in catalog (unknown error)
- Error frequency indicates systemic issue

---

**Document Version**: 1.0
**Last Updated**: 2025-10-07
**Epic**: E074 Enhanced Error Handling & Diagnostic Framework
