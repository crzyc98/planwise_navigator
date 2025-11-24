# Auto-Optimize Technical Integration Guide - Fidelity PlanAlign Engine

**Epic E012 Compensation Tuning System - S047 Optimization Engine**
**Last Updated:** July 2025
**Target Audience:** Software Developers, DevOps Engineers, Technical Architects

---

## Overview

This guide provides comprehensive technical details for integrating with Fidelity PlanAlign Engine's enhanced Auto-Optimize capabilities. The S047 Optimization Engine implements advanced SciPy-based multi-objective optimization with constraint handling, evidence generation, and comprehensive monitoring.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Auto-Optimize System Architecture             │
├─────────────────────────────────────────────────────────────────┤
│  Streamlit UI Layer                                             │
│  ├─ compensation_tuning.py (Basic Optimization)                 │
│  ├─ advanced_optimization.py (SciPy Multi-Objective)            │
│  └─ optimization_utils.py (Shared Utilities)                    │
├─────────────────────────────────────────────────────────────────┤
│  Orchestration Layer (Dagster Assets)                          │
│  ├─ advanced_optimization_engine (Main Asset)                   │
│  ├─ optimization_progress_tracker (Real-time Monitoring)        │
│  └─ evidence_report_generator (Business Impact Reports)         │
├─────────────────────────────────────────────────────────────────┤
│  Optimization Engine Core                                       │
│  ├─ constraint_solver.py (SciPy Integration)                    │
│  ├─ objective_functions.py (Multi-Objective Functions)          │
│  ├─ evidence_generator.py (Report Generation)                   │
│  ├─ sensitivity_analysis.py (Parameter Impact Analysis)         │
│  └─ optimization_schemas.py (Type Safety & Validation)          │
├─────────────────────────────────────────────────────────────────┤
│  Data Layer                                                     │
│  ├─ DuckDB Storage (Results & Cache)                            │
│  ├─ Parameter Schema (comp_levers.csv)                          │
│  └─ Optimization Cache (Performance Optimization)               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. CompensationOptimizer Class

**Location:** `orchestrator/optimization/constraint_solver.py`

The main optimization engine implementing SciPy-based multi-objective optimization:

```python
from orchestrator.optimization.constraint_solver import CompensationOptimizer
from orchestrator.resources.duckdb_resource import DuckDBResource

# Initialize optimizer
optimizer = CompensationOptimizer(
    duckdb_resource=duckdb_resource,
    scenario_id="my_optimization_scenario",
    use_synthetic=False  # Set to True for testing
)

# Add objectives with weights
optimizer.add_objective(cost_objective, weight=0.4)
optimizer.add_objective(equity_objective, weight=0.3)
optimizer.add_objective(growth_objective, weight=0.3)

# Run optimization
result = optimizer.optimize(
    initial_parameters=parameter_dict,
    objectives={"cost": 0.4, "equity": 0.3, "targets": 0.3},
    method="SLSQP",
    max_evaluations=100,
    timeout_minutes=60,
    random_seed=42
)
```

#### Key Features

- **Multi-Start Optimization**: Automatic random initialization for robustness
- **Algorithm Support**: SLSQP, Differential Evolution, L-BFGS-B, TNC, COBYLA
- **Constraint Handling**: Automatic parameter bounds and custom constraints
- **Performance Monitoring**: Real-time progress tracking and caching
- **Error Recovery**: Graceful handling of numerical failures

#### Supported Algorithms

| Algorithm | Type | Best For | Notes |
|-----------|------|----------|--------|
| SLSQP | Gradient-based | Smooth objectives | Default choice |
| Differential Evolution | Evolutionary | Non-smooth objectives | Global optimization |
| L-BFGS-B | Quasi-Newton | Large problems | Memory efficient |
| TNC | Truncated Newton | Constrained problems | Robust convergence |
| COBYLA | Direct search | Nonlinear constraints | Derivative-free |

### 2. Optimization Schemas

**Location:** `streamlit_dashboard/optimization_schemas.py`

Type-safe parameter definitions and validation:

```python
from streamlit_dashboard.optimization_schemas import (
    ParameterSchema,
    ParameterDefinition,
    ParameterBounds,
    OptimizationRequest,
    OptimizationResult
)

# Access parameter schema
schema = ParameterSchema()
merit_param = schema.get_parameter("merit_rate_level_1")

# Validate parameter value
is_valid, warnings, risk_level = merit_param.validate_value(0.045)

# Create optimization request
request = OptimizationRequest(
    scenario_id="test_scenario",
    initial_parameters={"merit_rate_level_1": 0.045},
    objectives={"cost": 0.5, "equity": 0.5},
    algorithm="SLSQP",
    max_evaluations=50
)
```

#### Parameter Categories

- **Merit Parameters**: Level-specific merit increase rates
- **COLA Parameters**: Cost of living adjustments
- **Promotion Parameters**: Promotion probabilities and raises
- **New Hire Parameters**: Salary adjustment multipliers
- **Termination Parameters**: Turnover rate controls

### 3. Objective Functions

**Location:** `orchestrator/optimization/objective_functions.py`

Multi-objective optimization functions supporting both synthetic and real simulation modes:

```python
from orchestrator.optimization.objective_functions import ObjectiveFunctions

# Initialize objective functions
obj_funcs = ObjectiveFunctions(
    duckdb_resource=duckdb_resource,
    scenario_id="scenario_123",
    use_synthetic=False
)

# Calculate individual objectives
cost_score = obj_funcs.cost_objective(parameters)
equity_score = obj_funcs.equity_objective(parameters)
growth_score = obj_funcs.growth_target_objective(parameters, target_growth=0.025)

# Calculate combined weighted objective
combined_score = obj_funcs.combined_objective(
    parameters,
    objectives={"cost": 0.4, "equity": 0.3, "targets": 0.3}
)
```

#### Objective Function Definitions

**Cost Objective**: Minimize total compensation costs
- Calculation: Total compensation growth rate
- Target: Lower values preferred
- Weight Range: 0.0 - 1.0

**Equity Objective**: Minimize compensation variance across levels
- Calculation: Coefficient of variation in compensation changes
- Target: Lower variance preferred
- Weight Range: 0.0 - 1.0

**Growth Target Objective**: Meet specific growth rate targets
- Calculation: Absolute difference from target growth rate
- Target: Minimize deviation from target
- Weight Range: 0.0 - 1.0

### 4. Evidence Generator

**Location:** `orchestrator/optimization/evidence_generator.py`

Automated business impact report generation:

```python
from orchestrator.optimization.evidence_generator import EvidenceGenerator

# Generate evidence report
generator = EvidenceGenerator(optimization_result)
report_path = generator.generate_mdx_report(output_dir="/tmp")

# Report includes:
# - Executive summary
# - Technical optimization details
# - Parameter analysis with insights
# - Business impact assessment
# - Risk analysis and mitigation strategies
# - Implementation recommendations
```

---

## Integration Patterns

### 1. Dagster Asset Integration

**Main Asset:** `advanced_optimization_engine`

```python
@asset(
    group_name="optimization",
    compute_kind="optimization"
)
def advanced_optimization_engine(
    context: AssetExecutionContext,
    duckdb: DuckDBResource
) -> Dict[str, Any]:
    """Run advanced SciPy-based optimization."""

    # Load configuration
    config = load_optimization_config()

    # Initialize optimizer
    optimizer = CompensationOptimizer(
        duckdb_resource=duckdb,
        scenario_id=config["scenario_id"],
        use_synthetic=config.get("use_synthetic", False)
    )

    # Run optimization
    result = optimizer.optimize(
        initial_parameters=config["initial_parameters"],
        objectives=config["objectives"],
        method=config.get("method", "SLSQP"),
        max_evaluations=config.get("max_evaluations", 100),
        timeout_minutes=config.get("timeout_minutes", 60),
        random_seed=config.get("random_seed", 42)
    )

    # Store results
    save_optimization_result(result)

    return result.dict() if hasattr(result, 'dict') else result.__dict__
```

### 2. Configuration Management

**Configuration File:** `/tmp/planwise_optimization_config.yaml`

```yaml
optimization:
  scenario_id: "advanced_optimization_20250704_1445"
  initial_parameters:
    merit_rate_level_1: 0.045
    merit_rate_level_2: 0.040
    cola_rate: 0.025
    new_hire_salary_adjustment: 1.15
  objectives:
    cost: 0.4
    equity: 0.3
    targets: 0.3
  method: "SLSQP"
  max_evaluations: 100
  timeout_minutes: 60
  random_seed: 42
  use_synthetic: false
```

### 3. Real-time Progress Monitoring

```python
# Monitor optimization progress
@asset(
    deps=[advanced_optimization_engine],
    compute_kind="monitoring"
)
def optimization_progress_tracker(
    context: AssetExecutionContext,
    advanced_optimization_engine: Dict[str, Any]
) -> Dict[str, Any]:
    """Track optimization progress and performance."""

    progress_data = {
        "iterations": advanced_optimization_engine.get("iterations", 0),
        "function_evaluations": advanced_optimization_engine.get("function_evaluations", 0),
        "runtime_seconds": advanced_optimization_engine.get("runtime_seconds", 0),
        "converged": advanced_optimization_engine.get("converged", False),
        "objective_value": advanced_optimization_engine.get("objective_value", float('inf'))
    }

    # Log progress
    context.log.info(f"Optimization Progress: {progress_data}")

    return progress_data
```

---

## API Reference

### OptimizationResult Schema

```python
class OptimizationResult(BaseModel):
    scenario_id: str
    converged: bool
    optimal_parameters: Dict[str, float]
    objective_value: float
    algorithm_used: str
    iterations: int
    function_evaluations: int
    runtime_seconds: float
    estimated_cost_impact: Dict[str, Any]
    estimated_employee_impact: Dict[str, Any]
    risk_assessment: str  # "LOW", "MEDIUM", "HIGH"
    constraint_violations: Dict[str, float]
    solution_quality_score: float
    evidence_report_url: Optional[str]
    schema_version: str = "1.0.0"
```

### Parameter Schema Format

```python
PARAMETER_SCHEMA = {
    "merit_rate_level_1": {
        "type": "float",
        "unit": "percentage",
        "range": [0.02, 0.08],
        "description": "Staff merit increase rate",
        "category": "merit",
        "default": 0.045
    },
    # ... additional parameters
}
```

### Constraint Functions

```python
def add_budget_constraint(optimizer: CompensationOptimizer, max_budget: float):
    """Add budget constraint to optimization."""

    def budget_constraint(parameters: Dict[str, float]) -> float:
        """Constraint function: returns positive if constraint satisfied."""
        estimated_cost = calculate_total_cost(parameters)
        return max_budget - estimated_cost

    optimizer.add_constraint(budget_constraint)
```

---

## Performance Optimization

### 1. Caching Strategy

The optimization engine includes intelligent caching:

```python
class OptimizationCache:
    """Smart caching for optimization function evaluations."""

    def __init__(self, cache_size: int = 10000):
        self.cache = {}
        self.cache_size = cache_size
        self.hits = 0
        self.misses = 0

    def get(self, parameters: Dict[str, float]) -> Optional[float]:
        """Get cached objective value."""
        key = self._hash_parameters(parameters)
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
```

### 2. Synthetic Mode for Development

Use synthetic objective functions for fast development and testing:

```python
# Enable synthetic mode for 100x speed improvement
optimizer = CompensationOptimizer(
    duckdb_resource=duckdb_resource,
    scenario_id="dev_testing",
    use_synthetic=True  # ~5-10 seconds vs 30-60 minutes
)
```

### 3. Parallel Evaluation

For evolutionary algorithms, function evaluations can be parallelized:

```python
# Differential Evolution with parallel evaluation
result = optimizer.optimize(
    method="DE",
    max_evaluations=200,
    # DE automatically uses multiple workers
    workers=4  # Utilize multiple CPU cores
)
```

---

## Error Handling and Debugging

### 1. Common Error Patterns

**Numerical Instability**
```python
try:
    result = optimizer.optimize(parameters)
except OptimizationError as e:
    if e.error_type == "NUMERICAL":
        # Try different algorithm or starting point
        result = optimizer.optimize(parameters, method="DE")
```

**Constraint Violations**
```python
if result.constraint_violations:
    logger.warning(f"Constraint violations: {result.constraint_violations}")
    # Adjust bounds or relax constraints
```

**Timeout Handling**
```python
result = optimizer.optimize(
    parameters,
    timeout_minutes=120,  # Extended timeout for complex problems
    max_evaluations=50    # Reduced evaluations to fit timeout
)
```

### 2. Debug Logging

Enable detailed logging for troubleshooting:

```python
import logging

# Configure optimization logger
logging.getLogger('orchestrator.optimization').setLevel(logging.DEBUG)

# Monitor function evaluations
optimizer.monitor.log_evaluation(objective_value, parameters)
print(f"Evaluation {optimizer.monitor.evaluations}: {objective_value:.6f}")
```

### 3. Validation Tools

```python
# Validate parameter bounds
def validate_optimization_setup(parameters: Dict[str, float]):
    """Validate optimization configuration."""
    schema = ParameterSchema()

    for param_name, value in parameters.items():
        param_def = schema.get_parameter(param_name)
        is_valid, messages, risk = param_def.validate_value(value)

        if not is_valid:
            raise ValueError(f"Invalid {param_name}: {messages}")
        if risk == "HIGH":
            logger.warning(f"High risk parameter {param_name}: {value}")
```

---

## Testing and Validation

### 1. Unit Tests

```python
def test_optimization_convergence():
    """Test that optimization converges for simple problems."""
    optimizer = CompensationOptimizer(
        duckdb_resource=mock_duckdb,
        scenario_id="test",
        use_synthetic=True
    )

    result = optimizer.optimize(
        initial_parameters=get_test_parameters(),
        objectives={"cost": 1.0},
        method="SLSQP",
        max_evaluations=50
    )

    assert result.converged
    assert result.objective_value < 1.0
```

### 2. Integration Tests

```python
def test_dagster_asset_execution():
    """Test full Dagster asset execution."""
    from definitions import defs

    # Create test configuration
    test_config = create_test_optimization_config()
    save_config_file(test_config)

    # Execute asset
    result = defs.get_asset_def("advanced_optimization_engine").execute_in_process()

    assert result.success
    assert "optimal_parameters" in result.output
```

### 3. Performance Benchmarks

```python
def benchmark_optimization_performance():
    """Benchmark optimization performance across algorithms."""
    algorithms = ["SLSQP", "DE", "L-BFGS-B"]
    results = {}

    for algorithm in algorithms:
        start_time = time.time()
        result = run_optimization(algorithm=algorithm, use_synthetic=True)
        runtime = time.time() - start_time

        results[algorithm] = {
            "runtime": runtime,
            "converged": result.converged,
            "function_evaluations": result.function_evaluations
        }

    return results
```

---

## Deployment Considerations

### 1. Environment Configuration

```bash
# Required environment variables
export DAGSTER_HOME=~/dagster_home_planwise
export PLANWISE_DB_PATH=/Users/nicholasamaral/planalign_engine/simulation.duckdb

# Python dependencies
pip install scipy>=1.11.0
pip install scikit-optimize>=0.9.0
pip install plotly>=5.15.0
```

### 2. Resource Requirements

**Minimum Requirements:**
- RAM: 4GB for synthetic mode, 8GB for real simulations
- CPU: 2 cores minimum, 4+ cores recommended for parallel algorithms
- Disk: 1GB for temporary files and cache

**Recommended for Production:**
- RAM: 16GB for large-scale optimizations
- CPU: 8+ cores for parallel processing
- Disk: 10GB SSD for performance
- Network: Stable connection for Dagster UI monitoring

### 3. Security Considerations

```python
# Parameter validation prevents injection attacks
def sanitize_parameters(params: Dict[str, Any]) -> Dict[str, float]:
    """Sanitize and validate input parameters."""
    sanitized = {}
    schema = ParameterSchema()

    for name, value in params.items():
        if name not in schema.get_all_parameter_names():
            raise ValueError(f"Unknown parameter: {name}")

        # Type conversion with bounds checking
        float_value = float(value)
        param_def = schema.get_parameter(name)

        if not (param_def.bounds.min_value <= float_value <= param_def.bounds.max_value):
            raise ValueError(f"Parameter {name} out of bounds")

        sanitized[name] = float_value

    return sanitized
```

---

## Future Enhancements

### 1. Multi-Objective Pareto Optimization

```python
# Planned enhancement: Pareto frontier analysis
from scipy.optimize import NonlinearConstraint

def pareto_optimization(optimizer: CompensationOptimizer):
    """Find Pareto optimal solutions across multiple objectives."""
    # Implementation for Pareto frontier exploration
    pass
```

### 2. Machine Learning Integration

```python
# Planned: ML-based parameter prediction
from sklearn.ensemble import RandomForestRegressor

class MLParameterPredictor:
    """Predict optimal parameters using historical data."""

    def predict_optimal_parameters(
        self,
        business_context: Dict[str, Any]
    ) -> Dict[str, float]:
        """Predict starting parameters based on business context."""
        pass
```

### 3. Real-time Optimization

```python
# Planned: Real-time parameter adjustment
class RealTimeOptimizer:
    """Continuously optimize parameters based on live data."""

    def start_continuous_optimization(self):
        """Start background optimization process."""
        pass
```

---

## Support and Resources

### Documentation Links
- [Algorithm Selection Guide](algorithm_selection_guide.md)
- [User Guide](auto_optimize_user_guide.md)
- [Troubleshooting Guide](auto_optimize_troubleshooting.md)
- [Best Practices Guide](auto_optimize_best_practices.md)

### Technical Support
- **Code Issues**: Check GitHub repository issues
- **Algorithm Questions**: Consult SciPy documentation
- **Performance Issues**: Review profiling guidelines
- **Integration Help**: Contact development team

### Reference Materials
- SciPy Optimize Documentation: https://docs.scipy.org/doc/scipy/reference/optimize.html
- Dagster Asset Documentation: https://docs.dagster.io/concepts/assets
- DuckDB Python API: https://duckdb.org/docs/api/python

---

*This guide is part of the Fidelity PlanAlign Engine E012 Compensation Tuning System documentation suite.*
