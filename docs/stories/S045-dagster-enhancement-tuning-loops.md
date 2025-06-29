# S045: Dagster Enhancement for Tuning Loops

**Epic:** E012 - Analyst-Driven Compensation Tuning System
**Story Points:** 13 (Large)
**Status:** Planned
**Assignee:** TBD
**Start Date:** TBD
**Target Date:** TBD

## Business Value

Analysts can run iterative "what-if" scenarios automatically, with the system finding optimal parameter combinations to hit budget targets without manual intervention.

**User Story:**
As an analyst, I want the system to automatically iterate through parameter adjustments to find optimal settings that meet my budget targets, so I can focus on business strategy rather than manual parameter tuning.

## Technical Approach

Extend existing Dagster pipeline with iteration logic that uses `fct_workforce_snapshot` for cost calculations vs targets. Build feedback loop: run dbt → compare outcomes → adjust parameters → repeat until convergence. Leverage existing DuckDB performance optimizations and asset-based architecture.

## Implementation Details

### Existing Models/Tables to Modify

**Dagster Assets:**
- `orchestrator/assets.py` → Add tuning loop assets
- `orchestrator/simulator_pipeline.py` → Extend with optimization operations
- `definitions.py` → Register new tuning assets and jobs

**dbt Models:**
- `fct_workforce_snapshot.sql` → Add cost aggregation views for optimization
- `fct_compensation_growth.sql` → Add target comparison logic
- New: `fct_optimization_metrics.sql` → Consolidate optimization KPIs

### New Dagster Assets

**Core Tuning Assets:**
```python
@asset(group_name="optimization")
def tune_compensation_parameters(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    simulation_config: dict
) -> Dict[str, Any]:
    """
    Main tuning orchestrator that iteratively adjusts parameters
    to hit budget targets within specified tolerance.
    """

@asset(group_name="optimization", deps=["tune_compensation_parameters"])
def parameter_optimization_results(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """
    Consolidates optimization run results, convergence metrics,
    and final parameter recommendations.
    """

@asset(group_name="optimization")
def optimization_scenario_state(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    tune_compensation_parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Tracks optimization state across iterations, including
    parameter history and convergence tracking.
    """
```

**Supporting Operations:**
```python
@op
def compare_outcomes_to_targets(
    context: OpExecutionContext,
    duckdb_resource: DuckDBResource,
    scenario_id: str
) -> Dict[str, float]:
    """
    Compares simulation outcomes against defined targets.
    Returns variance metrics for optimization feedback.
    """

@op
def adjust_parameters_based_on_variance(
    context: OpExecutionContext,
    duckdb_resource: DuckDBResource,
    scenario_id: str,
    variance_metrics: Dict[str, float]
) -> Dict[str, float]:
    """
    Calculates parameter adjustments based on target variance.
    Uses gradient descent or similar optimization approach.
    """

@op
def check_convergence_criteria(
    context: OpExecutionContext,
    variance_metrics: Dict[str, float],
    iteration_count: int,
    convergence_config: Dict[str, Any]
) -> bool:
    """
    Determines if optimization has converged based on
    tolerance thresholds and maximum iterations.
    """
```

### New Dagster Jobs

**Optimization Jobs:**
```python
@job(resource_defs={"duckdb_resource": duckdb_resource})
def compensation_tuning_job():
    """
    End-to-end compensation parameter tuning workflow.
    Runs iterative optimization until convergence.
    """

@job(resource_defs={"duckdb_resource": duckdb_resource})
def single_iteration_tuning_job():
    """
    Single iteration of parameter tuning for testing
    and debugging optimization logic.
    """
```

### dbt Integration Points

**Enhanced dbt Asset Integration:**
```python
# Extend existing dbt assets with optimization context
@dbt_assets(
    manifest=DBT_PROJECT_DIR / "target" / "manifest.json",
    select="fct_workforce_snapshot fct_compensation_growth fct_optimization_metrics"
)
def optimization_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """
    Runs optimization-specific dbt models with scenario context.
    """
    scenario_id = context.partition_key or "default"
    yield from dbt.cli(
        ["build", "--vars", f"scenario_id:{scenario_id}"],
        context=context
    ).stream()
```

**Variable Passing Enhancement:**
- Extend current `--vars` parameter system with optimization context
- Add iteration tracking and convergence state to dbt variables
- Dynamic scenario selection based on optimization state

### Data Flow Changes

```
Enhanced Dagster Pipeline:
simulation_config → initialize_optimization_scenario →
tune_compensation_parameters → run_optimization_dbt_models →
compare_outcomes_to_targets → adjust_parameters →
check_convergence → (repeat until converged) →
parameter_optimization_results
```

**Optimization Loop Logic:**
```python
def optimization_loop(scenario_id: str, targets: Dict[str, float]) -> Dict[str, Any]:
    max_iterations = 10
    tolerance = 0.02  # 2% tolerance

    for iteration in range(max_iterations):
        # Run simulation with current parameters
        run_dbt_models(scenario_id)

        # Compare outcomes to targets
        variance = calculate_target_variance(scenario_id, targets)

        # Check convergence
        if all(abs(v) < tolerance for v in variance.values()):
            return {"converged": True, "iterations": iteration + 1}

        # Adjust parameters based on variance
        adjust_parameters(scenario_id, variance)

    return {"converged": False, "iterations": max_iterations}
```

## Acceptance Criteria

### Functional Requirements
- [ ] Tuning loop runs within existing Dagster UI
- [ ] Convergence achieved within 10 iterations for standard scenarios
- [ ] Multiple optimization targets supported (cost, equity, growth rates)
- [ ] Integration maintained with existing `single_year_simulation` job
- [ ] Graceful handling of non-convergent scenarios

### Technical Requirements
- [ ] Performance optimized for 8GB DuckDB configuration
- [ ] Comprehensive logging for each optimization iteration
- [ ] Asset lineage clearly shows optimization dependencies
- [ ] Memory usage stays within existing resource constraints
- [ ] Integration with existing dbt asset definitions

### Operational Requirements
- [ ] Optimization state persisted between iterations
- [ ] Rollback capability to previous parameter sets
- [ ] Progress monitoring through Dagster UI
- [ ] Error handling and recovery for failed iterations

## Dependencies

**Prerequisite Stories:**
- S044 (Model Integration) - Requires parameter-driven models

**Dependent Stories:**
- S047 (Optimization Engine) - Will enhance basic tuning with advanced algorithms

**External Dependencies:**
- Existing Dagster pipeline architecture
- Current DuckDB resource configuration
- Established dbt asset integration patterns

## Testing Strategy

### Unit Tests
```python
def test_parameter_adjustment_logic():
    """Test parameter adjustment calculations"""

def test_convergence_detection():
    """Test convergence criteria evaluation"""

def test_optimization_state_persistence():
    """Test state management across iterations"""
```

### Integration Tests
- End-to-end optimization loop execution
- dbt asset integration with optimization context
- Performance testing with large employee datasets
- Error recovery and rollback scenarios

### Asset Tests (Dagster)
```python
@asset_check(asset="tune_compensation_parameters")
def validate_optimization_convergence(context, asset_result):
    """Validate optimization converged within tolerance"""

@asset_check(asset="parameter_optimization_results")
def validate_optimization_results_quality(context, asset_result):
    """Validate optimization produced valid parameter recommendations"""
```

## Implementation Steps

1. **Create optimization assets** and operations
2. **Implement basic tuning loop** with convergence logic
3. **Integrate with existing dbt assets** for scenario execution
4. **Add comprehensive logging** and state management
5. **Create optimization jobs** for different use cases
6. **Performance testing** and optimization
7. **Error handling** and recovery mechanisms
8. **Documentation** and usage examples

## Performance Considerations

**Optimization Strategy:**
- **Parallel Execution:** Run independent optimization iterations in parallel where possible
- **Incremental Updates:** Only recalculate affected models when parameters change
- **Memory Management:** Reuse DuckDB connections, manage parameter table sizes
- **Caching:** Cache intermediate optimization results

**Performance Targets:**
- Single optimization iteration <2 minutes
- Full optimization convergence <20 minutes
- Memory usage increase <20% during optimization
- DuckDB connection efficiency >90%

## Configuration

**Optimization Configuration:**
```yaml
# orchestrator/resources/optimization_config.py
optimization:
  max_iterations: 10
  convergence_tolerance: 0.02
  adjustment_factor: 0.1
  parallel_scenarios: false

targets:
  total_compensation_cost:
    target_value: 50000000  # $50M
    tolerance_pct: 0.02     # ±2%
    priority: high

  median_merit_increase:
    target_value: 0.04      # 4%
    tolerance_pct: 0.05     # ±5%
    priority: medium
```

## Success Metrics

**Functional Success:**
- 90% of optimization runs converge within 10 iterations
- Target achievement accuracy within specified tolerances
- Zero data corruption during optimization loops

**Performance Success:**
- <2 minutes per optimization iteration
- <20 minutes total optimization time
- <20% memory usage increase during optimization

**Operational Success:**
- Complete optimization audit trail maintained
- Error recovery success rate >95%
- Integration with existing Dagster monitoring

---

**Story Dependencies:** S044 (Model Integration)
**Blocked By:** S044
**Blocking:** S047 (Optimization Engine)
**Related Stories:** S046 (Analyst Interface), S048 (Governance)
