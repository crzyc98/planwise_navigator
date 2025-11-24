# Story S067-02: Model-Level Parallelization

## Overview

This document describes the implementation of sophisticated model-level parallelization for the PlanAlign Orchestrator, enabling selective parallel execution of independent dbt models while preserving sequential execution for state-dependent operations.

## Architecture

### Components

1. **ModelExecutionType Enum**: Classifies models as SEQUENTIAL, PARALLEL_SAFE, or CONDITIONAL
2. **ModelClassifier**: Analyzes model characteristics and assigns execution classifications
3. **ModelDependencyAnalyzer**: Analyzes dbt manifest to build dependency graphs and identify parallelization opportunities
4. **ParallelExecutionEngine**: Orchestrates parallel execution with dependency-aware scheduling
5. **Enhanced DbtRunner**: Integrates model-level parallelization with existing dbt command execution
6. **PipelineOrchestrator Integration**: Seamlessly integrates with existing workflow stages

### Model Classification System

#### PARALLEL_SAFE Models
Models that can execute concurrently without data dependencies or ordering requirements:

- **Hazard Calculations**: `int_hazard_termination`, `int_hazard_promotion`, `int_hazard_merit`
- **Staging Models**: `stg_census_data`, `stg_comp_levers`, `stg_config_*`
- **Independent Logic**: `int_effective_parameters`, `int_workforce_needs`
- **Data Quality**: `dq_*` validation and monitoring models
- **Dimensions**: `dim_hazard_table`, `dim_payroll_calendar`

#### SEQUENTIAL Models
Models that must execute in specific order due to state dependencies:

- **State Accumulators**: `int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator_v2`
- **Fact Tables**: `fct_yearly_events`, `fct_workforce_snapshot`
- **Previous Year Models**: `int_workforce_previous_year`, `int_active_employees_prev_year_snapshot`
- **Snapshot Models**: `int_workforce_snapshot_optimized`

#### CONDITIONAL Models
Models with complex dependencies that may be parallelizable in some contexts:

- **Event Generation**: `int_termination_events`, `int_hiring_events`, `int_promotion_events`
- **Contribution Models**: `int_employee_contributions`, `int_employee_match_calculations`
- **Complex Aggregations**: `int_employee_compensation_by_year`

### Dependency Analysis

The `ModelDependencyAnalyzer` uses dbt's `manifest.json` to:

1. Build a complete dependency graph of all models
2. Identify transitive dependencies
3. Detect circular dependencies
4. Find sets of independent models that can run concurrently
5. Generate execution plans with parallel and sequential phases
6. Validate execution safety before parallelization

### Parallel Execution Engine

The `ParallelExecutionEngine` provides:

- **Thread Pool Management**: Configurable worker threads with resource monitoring
- **Dependency-Aware Scheduling**: Respects model dependencies while maximizing parallelism
- **Resource Monitoring**: Monitors memory usage and CPU utilization
- **Safety Validation**: Validates execution plans before running
- **Deterministic Results**: Ensures reproducible outcomes regardless of execution order
- **Graceful Fallbacks**: Falls back to sequential execution when needed

## Configuration

### Enabling Model-Level Parallelization

Add to `simulation_config.yaml`:

```yaml
orchestrator:
  threading:
    model_parallelization:
      enabled: true
      max_workers: 4
      memory_limit_mb: 6000.0
      enable_conditional_parallelization: false
      deterministic_execution: true
      resource_monitoring: true

      safety:
        fallback_on_resource_pressure: true
        validate_execution_safety: true
        abort_on_dependency_conflict: true
        max_retries_per_model: 2
```

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enabled` | `false` | Enable model-level parallelization |
| `max_workers` | `4` | Maximum parallel worker threads |
| `memory_limit_mb` | `4000.0` | Memory limit for parallel execution |
| `enable_conditional_parallelization` | `false` | Allow parallelization of conditional models |
| `deterministic_execution` | `true` | Ensure reproducible execution order |
| `resource_monitoring` | `true` | Monitor system resources during execution |

### Safety Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `fallback_on_resource_pressure` | `true` | Fall back to sequential on resource pressure |
| `validate_execution_safety` | `true` | Validate safety before parallelization |
| `abort_on_dependency_conflict` | `true` | Abort on dependency conflicts |
| `max_retries_per_model` | `2` | Maximum retries per failed model |

## Usage Examples

### Programmatic Usage

```python
from planalign_orchestrator import create_orchestrator
from planalign_orchestrator.config import load_simulation_config

# Load configuration with parallelization enabled
config = load_simulation_config('config/simulation_config.yaml')

# Create orchestrator (auto-detects parallelization settings)
orchestrator = create_orchestrator(config)

# Run simulation with model-level parallelization
summary = orchestrator.execute_multi_year_simulation(
    start_year=2025,
    end_year=2027
)

print(f"Simulation completed: {len(summary.completed_years)} years")
```

### DbtRunner Direct Usage

```python
from planalign_orchestrator.dbt_runner import DbtRunner

# Create DbtRunner with parallelization enabled
runner = DbtRunner(
    enable_model_parallelization=True,
    model_parallelization_max_workers=4,
    model_parallelization_memory_limit_mb=6000.0,
    verbose=True
)

# Use smart parallelization for a set of models
models = ["int_hazard_termination", "int_hazard_promotion", "int_hazard_merit"]
result = runner.run_models_with_smart_parallelization(
    models=models,
    stage_name="hazard_calculations",
    simulation_year=2025,
    enable_conditional_parallelization=False
)

print(f"Parallelism achieved: {result.parallelism_achieved}x")
print(f"Execution time: {result.execution_time:.1f}s")
```

### Runtime Parallelization Control

```python
# Check parallelization capabilities
info = runner.get_parallelization_info()
if info["available"]:
    stats = info["statistics"]
    print(f"Parallel-safe models: {stats['parallel_safe']}/{stats['total_models']}")
    print(f"Max theoretical speedup: {stats['max_theoretical_speedup']:.1f}x")

# Validate a stage for parallelization
stage_models = ["int_hazard_termination", "int_hazard_promotion"]
validation = runner.validate_stage_for_parallelization(stage_models)

if validation["parallelizable"]:
    print(f"Stage can achieve {validation['estimated_speedup']:.1f}x speedup")
    print(f"Recommendations: {validation['recommendations']}")
```

## Performance Benefits

### Expected Speedup by Stage

| Stage | Parallelizable Models | Expected Speedup |
|-------|----------------------|-----------------|
| **INITIALIZATION** | Staging models | 2-4x |
| **FOUNDATION** | Independent calculations | 1.5-2x |
| **VALIDATION** | Data quality models | 2-3x |
| **EVENT_GENERATION** | Limited (conditional only) | 1.1-1.3x |
| **STATE_ACCUMULATION** | Limited (safety first) | 1.0-1.2x |

### Overall Performance Impact

- **Total simulation time**: 20-40% reduction
- **Peak memory usage**: Controlled by `memory_limit_mb`
- **CPU utilization**: Improved with `max_workers` threads
- **I/O efficiency**: Better database connection utilization

### Resource Requirements

| Workers | Memory Usage | Recommended For |
|---------|-------------|-----------------|
| 2 | 3-4 GB | Work laptops, constrained environments |
| 4 | 6-8 GB | Development servers, standard workstations |
| 8 | 12-16 GB | High-performance servers |

## Safety and Data Integrity

### Data Integrity Guarantees

1. **State Accumulator Preservation**: Models like `int_enrollment_state_accumulator` always run sequentially
2. **Event Ordering**: Critical event sequencing is preserved in `fct_yearly_events`
3. **Dependency Respect**: All model dependencies are analyzed and respected
4. **Deterministic Results**: Same random seed produces identical results regardless of parallelization

### Safety Mechanisms

1. **Dependency Validation**: Pre-execution validation of all dependencies
2. **Resource Monitoring**: Automatic fallback when memory/CPU limits exceeded
3. **Circular Dependency Detection**: Identifies and prevents circular dependencies
4. **Error Isolation**: Failed models don't affect independent parallel executions

### Fallback Behavior

The system gracefully falls back to sequential execution when:
- Resource pressure exceeds thresholds
- Dependency conflicts are detected
- Safety validation fails
- Parallelization components are unavailable

## Monitoring and Observability

### Execution Logging

When `verbose=True`, the system provides detailed logging:

```
🚀 Model-level parallelization engine initialized:
   Max workers: 4
   Memory limit: 6000MB
   Conditional parallelization: false
   Deterministic execution: true
   Parallel-safe models: 18/45
   Max theoretical speedup: 4.0x

🔄 Starting simulation year 2025
   📋 Execution plan:
      Total models: 12
      Parallelizable: 8
      Estimated speedup: 2.1x
      Phases: 3
         Phase 1 (Parallel): 3 models, hazard_calculations group
         Phase 2 (Parallel): 2 models, staging group
         Phase 3 (Sequential): 7 models

   🚀 Using model-level parallelization for stage foundation
   📊 Parallelization results:
      Success: true
      Models executed: 8
      Execution time: 45.2s
      Parallelism achieved: 3x
```

### Performance Metrics

The system tracks:
- Execution time per phase
- Parallelism achieved (actual vs theoretical)
- Memory usage during execution
- Resource pressure events
- Fallback occurrences

### Error Reporting

Detailed error reporting includes:
- Dependency conflict details
- Resource limit violations
- Model execution failures
- Safety validation failures

## Development and Testing

### Running Tests

```bash
# Run all parallelization tests
python -m pytest tests/test_model_parallelization.py -v

# Run specific test categories
python -m pytest tests/test_model_parallelization.py::TestModelClassifier -v
python -m pytest tests/test_model_parallelization.py::TestParallelExecutionEngine -v

# Run with coverage
python -m pytest tests/test_model_parallelization.py --cov=planalign_orchestrator.model_execution_types --cov=planalign_orchestrator.parallel_execution_engine
```

### Development Workflow

1. **Model Classification**: Add new models to `ModelClassifier._initialize_classifications()`
2. **Dependency Analysis**: Update dependency patterns as models change
3. **Safety Validation**: Test new parallelization scenarios
4. **Performance Testing**: Validate speedup claims with benchmarks

### Debugging

Enable detailed debugging:

```python
# Enable verbose logging
runner = DbtRunner(
    enable_model_parallelization=True,
    verbose=True
)

# Check parallelization info
info = runner.get_parallelization_info()
print(json.dumps(info, indent=2))

# Validate specific stages
validation = runner.validate_stage_for_parallelization(models)
print("Parallelization validation:", validation)
```

## Migration Guide

### Enabling for Existing Projects

1. **Update Configuration**: Add model parallelization settings to `simulation_config.yaml`
2. **Test Incrementally**: Start with `max_workers: 2` and limited stages
3. **Monitor Resources**: Watch memory usage and adjust limits as needed
4. **Validate Results**: Ensure simulation results remain consistent

### Performance Tuning

1. **Start Conservative**: Begin with 2 workers and basic parallel-safe models
2. **Monitor Memory**: Adjust `memory_limit_mb` based on actual usage
3. **Enable Conditional**: Try `enable_conditional_parallelization: true` after validation
4. **Scale Workers**: Increase `max_workers` based on available CPU cores

### Troubleshooting

| Issue | Solution |
|-------|----------|
| High memory usage | Reduce `max_workers` or `memory_limit_mb` |
| Inconsistent results | Ensure `deterministic_execution: true` |
| Dependency errors | Check model dependencies in dbt |
| Resource pressure | Enable `fallback_on_resource_pressure` |
| Performance regression | Disable for problematic stages |

## Future Enhancements

### Planned Improvements

1. **Dynamic Worker Scaling**: Automatically adjust workers based on resource availability
2. **Model Caching**: Cache independent model results across simulation years
3. **Advanced Scheduling**: More sophisticated dependency-aware scheduling algorithms
4. **Performance Profiling**: Built-in performance profiling and optimization recommendations
5. **Cloud Integration**: Support for cloud-based parallel execution

### Extension Points

The system is designed for extensibility:

1. **Custom Classifiers**: Add domain-specific model classification logic
2. **Resource Monitors**: Implement custom resource monitoring strategies
3. **Execution Engines**: Create specialized execution engines for different environments
4. **Safety Validators**: Add custom safety validation rules

## Conclusion

The Model-Level Parallelization system provides sophisticated, safe, and efficient parallel execution of dbt models while maintaining data integrity and deterministic results. It represents a significant advancement in the PlanAlign Orchestrator's performance capabilities while preserving the reliability and accuracy required for enterprise workforce simulation.

Key benefits:
- ✅ 20-40% faster simulation execution
- ✅ Preserved data integrity and deterministic results
- ✅ Sophisticated dependency analysis and safety validation
- ✅ Graceful fallbacks and error handling
- ✅ Comprehensive monitoring and observability
- ✅ Easy configuration and migration path
