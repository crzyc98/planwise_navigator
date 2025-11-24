# Auto-Optimize API Documentation - Fidelity PlanAlign Engine

**Epic E012 Compensation Tuning System - S047 Optimization Engine**
**Last Updated:** July 2025
**Target Audience:** API Developers, Integration Engineers, Technical Users

---

## Overview

This document provides comprehensive API documentation for Fidelity PlanAlign Engine's Auto-Optimize system. The S047 Optimization Engine exposes both programmatic APIs and Dagster asset interfaces for advanced compensation parameter optimization.

### API Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          API Layer Structure                    │
├─────────────────────────────────────────────────────────────────┤
│  Public APIs                                                    │
│  ├─ CompensationOptimizer (Primary Interface)                   │
│  ├─ ObjectiveFunctions (Objective Calculations)                 │
│  ├─ EvidenceGenerator (Report Generation)                       │
│  └─ ParameterSchema (Validation & Metadata)                     │
├─────────────────────────────────────────────────────────────────┤
│  Dagster Assets (Orchestration)                                │
│  ├─ advanced_optimization_engine                                │
│  ├─ optimization_progress_tracker                               │
│  └─ evidence_report_generator                                   │
├─────────────────────────────────────────────────────────────────┤
│  Data Models (Type Safety)                                     │
│  ├─ OptimizationRequest                                         │
│  ├─ OptimizationResult                                          │
│  ├─ OptimizationError                                           │
│  └─ ParameterDefinition                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core API Classes

### 1. CompensationOptimizer

**Module:** `orchestrator.optimization.constraint_solver`

The primary interface for running optimization algorithms.

#### Constructor

```python
class CompensationOptimizer:
    def __init__(
        self,
        duckdb_resource: DuckDBResource,
        scenario_id: str,
        use_synthetic: bool = False
    ) -> None
```

**Parameters:**
- `duckdb_resource`: Database connection resource
- `scenario_id`: Unique identifier for optimization scenario
- `use_synthetic`: Whether to use synthetic objectives (faster for testing)

**Example:**
```python
from orchestrator.optimization.constraint_solver import CompensationOptimizer
from orchestrator.resources.duckdb_resource import DuckDBResource

optimizer = CompensationOptimizer(
    duckdb_resource=duckdb_resource,
    scenario_id="quarterly_optimization_2025_q2",
    use_synthetic=False
)
```

#### Methods

##### optimize()

Run multi-objective parameter optimization.

```python
def optimize(
    self,
    initial_parameters: Dict[str, float],
    objectives: Dict[str, float],
    method: str = 'SLSQP',
    max_evaluations: int = 200,
    timeout_minutes: int = 30,
    random_seed: Optional[int] = 42
) -> Union[OptimizationResult, OptimizationError]
```

**Parameters:**
- `initial_parameters`: Starting parameter values
- `objectives`: Objective weights (must sum to 1.0)
- `method`: Optimization algorithm ("SLSQP", "DE", "L-BFGS-B", "TNC", "COBYLA")
- `max_evaluations`: Maximum function evaluations
- `timeout_minutes`: Maximum runtime in minutes
- `random_seed`: Random seed for reproducibility (None for random)

**Returns:**
- `OptimizationResult`: Successful optimization results
- `OptimizationError`: Error details if optimization fails

**Example:**
```python
result = optimizer.optimize(
    initial_parameters={
        "merit_rate_level_1": 0.045,
        "merit_rate_level_2": 0.040,
        "cola_rate": 0.025,
        "new_hire_salary_adjustment": 1.15
    },
    objectives={
        "cost": 0.4,        # 40% weight on cost minimization
        "equity": 0.3,      # 30% weight on equity optimization
        "targets": 0.3      # 30% weight on growth targets
    },
    method="SLSQP",
    max_evaluations=100,
    timeout_minutes=60,
    random_seed=42
)

if isinstance(result, OptimizationResult):
    print(f"Optimization converged: {result.converged}")
    print(f"Optimal parameters: {result.optimal_parameters}")
    print(f"Objective value: {result.objective_value:.6f}")
else:
    print(f"Optimization failed: {result.error_message}")
```

##### add_objective()

Add custom objective function with weight.

```python
def add_objective(
    self,
    objective_func: Callable[[Dict[str, float]], float],
    weight: float = 1.0
) -> None
```

**Parameters:**
- `objective_func`: Function that takes parameters and returns objective value
- `weight`: Relative weight for this objective

**Example:**
```python
def custom_retention_objective(parameters: Dict[str, float]) -> float:
    """Custom objective to optimize employee retention."""
    # Implementation details...
    return retention_score

optimizer.add_objective(custom_retention_objective, weight=0.2)
```

##### add_constraint()

Add constraint function to optimization.

```python
def add_constraint(
    self,
    constraint_func: Callable[[Dict[str, float]], float]
) -> None
```

**Parameters:**
- `constraint_func`: Function returning positive value if constraint satisfied

**Example:**
```python
def budget_constraint(parameters: Dict[str, float]) -> float:
    """Ensure total cost doesn't exceed budget."""
    estimated_cost = calculate_total_compensation_cost(parameters)
    return 10000000.0 - estimated_cost  # $10M budget limit

optimizer.add_constraint(budget_constraint)
```

---

### 2. ObjectiveFunctions

**Module:** `orchestrator.optimization.objective_functions`

Provides standard objective functions for compensation optimization.

#### Constructor

```python
class ObjectiveFunctions:
    def __init__(
        self,
        duckdb_resource: DuckDBResource,
        scenario_id: str,
        use_synthetic: bool = False
    ) -> None
```

#### Methods

##### cost_objective()

Minimize total compensation costs.

```python
def cost_objective(self, parameters: Dict[str, float]) -> float
```

**Returns:** Cost score (lower is better)

##### equity_objective()

Minimize compensation variance across job levels.

```python
def equity_objective(self, parameters: Dict[str, float]) -> float
```

**Returns:** Equity score (lower variance is better)

##### growth_target_objective()

Minimize deviation from target growth rate.

```python
def growth_target_objective(
    self,
    parameters: Dict[str, float],
    target_growth: float = 0.025
) -> float
```

**Parameters:**
- `target_growth`: Desired annual growth rate (e.g., 0.025 for 2.5%)

**Returns:** Deviation score (lower is better)

##### combined_objective()

Calculate weighted combination of multiple objectives.

```python
def combined_objective(
    self,
    parameters: Dict[str, float],
    objectives: Dict[str, float]
) -> float
```

**Parameters:**
- `objectives`: Dictionary with keys "cost", "equity", "targets" and corresponding weights

**Example:**
```python
obj_funcs = ObjectiveFunctions(duckdb_resource, "scenario_123")

# Individual objectives
cost_score = obj_funcs.cost_objective(parameters)
equity_score = obj_funcs.equity_objective(parameters)
growth_score = obj_funcs.growth_target_objective(parameters, target_growth=0.03)

# Combined weighted objective
combined_score = obj_funcs.combined_objective(
    parameters,
    objectives={"cost": 0.5, "equity": 0.3, "targets": 0.2}
)
```

---

### 3. EvidenceGenerator

**Module:** `orchestrator.optimization.evidence_generator`

Generates comprehensive business impact reports.

#### Constructor

```python
class EvidenceGenerator:
    def __init__(self, optimization_result: OptimizationResult) -> None
```

#### Methods

##### generate_mdx_report()

Generate comprehensive Markdown evidence report.

```python
def generate_mdx_report(
    self,
    output_dir: Optional[str] = None
) -> str
```

**Parameters:**
- `output_dir`: Directory to save report (defaults to temp directory)

**Returns:** Path to generated report file

**Example:**
```python
from orchestrator.optimization.evidence_generator import EvidenceGenerator

# Generate evidence report
generator = EvidenceGenerator(optimization_result)
report_path = generator.generate_mdx_report(output_dir="/tmp/reports")

print(f"Evidence report generated: {report_path}")

# Report includes:
# - Executive summary
# - Optimization technical details
# - Parameter analysis and insights
# - Business impact assessment
# - Risk analysis and mitigation strategies
# - Implementation recommendations
```

---

### 4. ParameterSchema

**Module:** `streamlit_dashboard.optimization_schemas`

Provides parameter definitions, validation, and metadata.

#### Constructor

```python
class ParameterSchema:
    def __init__(self) -> None
```

#### Methods

##### get_parameter()

Get parameter definition by name.

```python
def get_parameter(self, parameter_name: str) -> ParameterDefinition
```

**Returns:** ParameterDefinition object with bounds, metadata, and validation

##### get_all_parameter_names()

Get list of all valid parameter names.

```python
def get_all_parameter_names(self) -> List[str]
```

##### validate_parameter_set()

Validate a complete set of parameters.

```python
def validate_parameter_set(
    self,
    parameters: Dict[str, float]
) -> Tuple[bool, List[str], Dict[str, str]]
```

**Returns:**
- `is_valid`: Whether all parameters are valid
- `messages`: List of warning/error messages
- `risk_levels`: Risk assessment per parameter

**Example:**
```python
from streamlit_dashboard.optimization_schemas import ParameterSchema

schema = ParameterSchema()

# Get parameter information
merit_param = schema.get_parameter("merit_rate_level_1")
print(f"Bounds: {merit_param.bounds.min_value} - {merit_param.bounds.max_value}")
print(f"Default: {merit_param.bounds.default_value}")
print(f"Description: {merit_param.description}")

# Validate parameter set
parameters = {
    "merit_rate_level_1": 0.045,
    "cola_rate": 0.025,
    "new_hire_salary_adjustment": 1.15
}

is_valid, messages, risk_levels = schema.validate_parameter_set(parameters)
if not is_valid:
    print(f"Validation errors: {messages}")
```

---

## Data Models

### OptimizationRequest

```python
class OptimizationRequest(BaseModel):
    scenario_id: str = Field(..., min_length=1, max_length=100)
    initial_parameters: Dict[str, float] = Field(..., min_items=1)
    objectives: Dict[str, float] = Field(..., min_items=1)
    algorithm: str = Field(default="SLSQP", pattern="^(SLSQP|DE|L-BFGS-B|TNC|COBYLA)$")
    max_evaluations: int = Field(default=100, ge=1, le=1000)
    timeout_minutes: int = Field(default=30, ge=1, le=480)
    random_seed: Optional[int] = Field(default=42, ge=1)
    use_synthetic: bool = Field(default=False)

    @validator('objectives')
    def objectives_must_sum_to_one(cls, v):
        if abs(sum(v.values()) - 1.0) > 1e-6:
            raise ValueError('Objective weights must sum to 1.0')
        return v
```

**Example:**
```python
request = OptimizationRequest(
    scenario_id="test_optimization_001",
    initial_parameters={
        "merit_rate_level_1": 0.045,
        "cola_rate": 0.025
    },
    objectives={
        "cost": 0.6,
        "equity": 0.4
    },
    algorithm="SLSQP",
    max_evaluations=50,
    timeout_minutes=15,
    random_seed=42,
    use_synthetic=True
)
```

### OptimizationResult

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
    solution_quality_score: float  # 0.0 - 1.0
    evidence_report_url: Optional[str]
    schema_version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.now)
```

**Example Usage:**
```python
if result.converged:
    print(f"✅ Optimization converged in {result.runtime_seconds:.1f}s")
    print(f"📊 Quality score: {result.solution_quality_score:.2f}/1.0")
    print(f"⚖️ Risk level: {result.risk_assessment}")

    # Access optimal parameters
    for param_name, value in result.optimal_parameters.items():
        print(f"  {param_name}: {value:.4f}")

    # Check business impact
    cost_impact = result.estimated_cost_impact
    print(f"💰 Cost impact: ${cost_impact['value']:,.0f} {cost_impact['unit']}")

    employee_impact = result.estimated_employee_impact
    print(f"👥 Employees affected: {employee_impact['count']:,}")
else:
    print("❌ Optimization failed to converge")
```

### OptimizationError

```python
class OptimizationError(BaseModel):
    scenario_id: str
    error_type: str  # "NUMERICAL", "TIMEOUT", "INFEASIBLE", "CONSTRAINT"
    error_message: str
    best_found_solution: Optional[Dict[str, float]]
    recommendations: List[str]
    timestamp: datetime = Field(default_factory=datetime.now)
    schema_version: str = "1.0.0"
```

**Example Error Handling:**
```python
if isinstance(result, OptimizationError):
    print(f"❌ Optimization failed: {result.error_type}")
    print(f"📝 Message: {result.error_message}")

    if result.best_found_solution:
        print("🔍 Best solution found:")
        for param, value in result.best_found_solution.items():
            print(f"  {param}: {value:.4f}")

    print("💡 Recommendations:")
    for rec in result.recommendations:
        print(f"  - {rec}")
```

### ParameterDefinition

```python
class ParameterDefinition:
    name: str
    display_name: str
    description: str
    category: ParameterCategory  # MERIT, COLA, PROMOTION, NEW_HIRE
    parameter_type: ParameterType  # FLOAT, PERCENTAGE, MULTIPLIER
    unit: ParameterUnit  # PERCENTAGE, MULTIPLIER, CURRENCY
    bounds: ParameterBounds
    job_levels: List[int]
    is_level_specific: bool
    validation_rules: Optional[Dict[str, Any]]
    business_impact: str
```

**Example:**
```python
# Access parameter metadata
param = schema.get_parameter("merit_rate_level_1")

print(f"Name: {param.display_name}")
print(f"Description: {param.description}")
print(f"Category: {param.category}")
print(f"Unit: {param.unit}")
print(f"Bounds: [{param.bounds.min_value}, {param.bounds.max_value}]")
print(f"Default: {param.bounds.default_value}")
print(f"Business Impact: {param.business_impact}")

# Validate parameter value
is_valid, warnings, risk_level = param.validate_value(0.055)
print(f"Valid: {is_valid}, Risk: {risk_level}")
if warnings:
    print(f"Warnings: {warnings}")
```

---

## Dagster Asset APIs

### advanced_optimization_engine

**Asset Name:** `advanced_optimization_engine`
**Group:** `optimization`

Primary Dagster asset for running optimization.

#### Configuration

Asset reads configuration from `/tmp/planwise_optimization_config.yaml`:

```yaml
optimization:
  scenario_id: "optimization_scenario_id"
  initial_parameters:
    merit_rate_level_1: 0.045
    # ... other parameters
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

#### Execution

```python
# Via Dagster CLI
dagster asset materialize --select advanced_optimization_engine -f definitions.py

# Via Python API
from definitions import defs

result = defs.get_asset_def("advanced_optimization_engine").execute_in_process()
optimization_data = result.output
```

#### Output Format

```python
{
    "scenario_id": "optimization_scenario_20250704_1445",
    "converged": True,
    "optimal_parameters": {
        "merit_rate_level_1": 0.0423,
        "merit_rate_level_2": 0.0389,
        # ... other parameters
    },
    "objective_value": 0.123456,
    "algorithm_used": "SLSQP",
    "iterations": 15,
    "function_evaluations": 67,
    "runtime_seconds": 45.7,
    "risk_assessment": "MEDIUM",
    "solution_quality_score": 0.87
}
```

### optimization_progress_tracker

**Asset Name:** `optimization_progress_tracker`
**Dependencies:** `advanced_optimization_engine`

Tracks optimization progress and performance metrics.

#### Output Format

```python
{
    "iterations": 15,
    "function_evaluations": 67,
    "runtime_seconds": 45.7,
    "converged": True,
    "objective_value": 0.123456,
    "cache_hit_rate": 0.23,
    "average_evaluation_time": 0.68
}
```

### evidence_report_generator

**Asset Name:** `evidence_report_generator`
**Dependencies:** `advanced_optimization_engine`

Generates business impact evidence reports.

#### Output Format

```python
{
    "report_path": "/tmp/optimization_evidence_scenario_20250704_1445.md",
    "report_url": "file:///tmp/optimization_evidence_scenario_20250704_1445.md",
    "sections_generated": [
        "executive_summary",
        "optimization_details",
        "parameter_analysis",
        "business_impact",
        "risk_assessment",
        "recommendations"
    ],
    "report_size_bytes": 15432
}
```

---

## Error Codes and Handling

### Error Types

| Error Type | Code | Description | Common Causes |
|-----------|------|-------------|---------------|
| NUMERICAL | E001 | Numerical optimization failure | Ill-conditioned problem, poor starting point |
| TIMEOUT | E002 | Optimization timeout exceeded | Complex problem, insufficient time limit |
| INFEASIBLE | E003 | No feasible solution exists | Conflicting constraints, unrealistic bounds |
| CONSTRAINT | E004 | Constraint violation | Invalid parameter bounds, business rule violations |
| VALIDATION | E005 | Input validation failure | Invalid parameters, malformed objectives |
| STORAGE | E006 | Data storage/retrieval error | Database connection, file system issues |

### Error Handling Examples

```python
try:
    result = optimizer.optimize(
        initial_parameters=parameters,
        objectives=objectives,
        method="SLSQP",
        max_evaluations=100
    )

    if isinstance(result, OptimizationError):
        if result.error_type == "TIMEOUT":
            # Retry with more time or fewer evaluations
            result = optimizer.optimize(
                initial_parameters=parameters,
                objectives=objectives,
                method="SLSQP",
                max_evaluations=50,
                timeout_minutes=120
            )
        elif result.error_type == "NUMERICAL":
            # Try different algorithm
            result = optimizer.optimize(
                initial_parameters=parameters,
                objectives=objectives,
                method="DE",  # More robust for difficult problems
                max_evaluations=100
            )
        elif result.error_type == "INFEASIBLE":
            # Relax constraints or adjust bounds
            print("Problem may be over-constrained")
            print(f"Recommendations: {result.recommendations}")

except Exception as e:
    logger.error(f"Unexpected optimization error: {e}")
    # Fallback to synthetic mode for debugging
    result = optimizer.optimize(
        initial_parameters=parameters,
        objectives=objectives,
        use_synthetic=True
    )
```

---

## Performance Considerations

### Function Evaluation Costs

| Mode | Time per Evaluation | Typical Iterations | Total Time |
|------|-------------------|------------------|------------|
| Synthetic | ~0.01s | 50-100 | 1-5 minutes |
| Real Simulation | ~30-60s | 50-100 | 30-100 minutes |

### Caching Strategy

The optimization engine includes intelligent caching:

```python
# Cache configuration
cache_config = {
    "cache_size": 10000,        # Maximum cached evaluations
    "cache_tolerance": 1e-6,    # Parameter similarity threshold
    "cache_enabled": True       # Enable/disable caching
}

# Access cache statistics
cache_stats = optimizer.cache.get_statistics()
print(f"Cache hit rate: {cache_stats['hit_rate']:.1%}")
print(f"Cache size: {cache_stats['size']}")
```

### Memory Usage

```python
# Monitor memory usage during optimization
import psutil
import os

def monitor_optimization_memory(optimizer):
    """Monitor memory usage during optimization."""
    process = psutil.Process(os.getpid())

    def memory_callback():
        memory_mb = process.memory_info().rss / 1024 / 1024
        print(f"Memory usage: {memory_mb:.1f} MB")

    # Add callback to optimizer
    optimizer.add_progress_callback(memory_callback)
```

---

## Rate Limits and Quotas

### Computational Limits

```python
# Built-in safety limits
MAX_EVALUATIONS = 1000      # Maximum function evaluations per optimization
MAX_TIMEOUT_MINUTES = 480   # Maximum timeout (8 hours)
MAX_CONCURRENT_OPTIMIZATIONS = 3  # Prevent resource exhaustion

# Recommended limits for different use cases
LIMITS_BY_USE_CASE = {
    "development": {"max_evaluations": 20, "timeout_minutes": 5},
    "testing": {"max_evaluations": 50, "timeout_minutes": 15},
    "production": {"max_evaluations": 200, "timeout_minutes": 120},
    "research": {"max_evaluations": 500, "timeout_minutes": 240}
}
```

### Database Connections

```python
# Connection pooling for concurrent optimizations
from orchestrator.resources.duckdb_resource import DuckDBResource

# Use connection pooling to prevent database locks
duckdb_resource = DuckDBResource(
    database_path="simulation.duckdb",
    max_connections=5,
    connection_timeout=30
)
```

---

## Version Compatibility

### API Version Matrix

| PlanWise Version | API Version | Schema Version | Compatible Algorithms |
|-----------------|-------------|----------------|---------------------|
| 1.0.0 | 1.0.0 | 1.0.0 | SLSQP, DE |
| 1.1.0 | 1.1.0 | 1.0.0 | SLSQP, DE, L-BFGS-B |
| 1.2.0 | 1.2.0 | 1.1.0 | SLSQP, DE, L-BFGS-B, TNC, COBYLA |

### Backward Compatibility

```python
# Check API version compatibility
from orchestrator.optimization import __version__ as opt_version

def check_compatibility(required_version: str) -> bool:
    """Check if current version is compatible with required version."""
    from packaging import version
    return version.parse(opt_version) >= version.parse(required_version)

if not check_compatibility("1.2.0"):
    raise ValueError("Optimization engine version 1.2.0+ required")
```

---

## Examples and Tutorials

### Basic Optimization Example

```python
"""Basic optimization example with error handling."""

from orchestrator.optimization.constraint_solver import CompensationOptimizer
from orchestrator.resources.duckdb_resource import DuckDBResource
from streamlit_dashboard.optimization_schemas import ParameterSchema

def run_basic_optimization():
    # Initialize components
    duckdb_resource = DuckDBResource(database_path="simulation.duckdb")
    optimizer = CompensationOptimizer(
        duckdb_resource=duckdb_resource,
        scenario_id="basic_example_001",
        use_synthetic=True  # Fast mode for example
    )

    # Define parameters
    schema = ParameterSchema()
    initial_parameters = {
        "merit_rate_level_1": 0.045,
        "merit_rate_level_2": 0.040,
        "cola_rate": 0.025,
        "new_hire_salary_adjustment": 1.15
    }

    # Validate parameters
    is_valid, messages, risk_levels = schema.validate_parameter_set(initial_parameters)
    if not is_valid:
        print(f"❌ Parameter validation failed: {messages}")
        return

    # Run optimization
    result = optimizer.optimize(
        initial_parameters=initial_parameters,
        objectives={"cost": 0.5, "equity": 0.3, "targets": 0.2},
        method="SLSQP",
        max_evaluations=50,
        timeout_minutes=10,
        random_seed=42
    )

    # Process results
    if isinstance(result, OptimizationResult) and result.converged:
        print("✅ Optimization successful!")
        print(f"📊 Quality score: {result.solution_quality_score:.2f}")
        print(f"⏱️ Runtime: {result.runtime_seconds:.1f}s")

        # Display optimal parameters
        print("\n🎯 Optimal parameters:")
        for param_name, value in result.optimal_parameters.items():
            print(f"  {param_name}: {value:.4f}")

        return result
    else:
        print(f"❌ Optimization failed: {result.error_message if hasattr(result, 'error_message') else 'Unknown error'}")
        return None

if __name__ == "__main__":
    result = run_basic_optimization()
```

### Advanced Multi-Objective Example

```python
"""Advanced optimization with custom objectives and constraints."""

def run_advanced_optimization():
    optimizer = CompensationOptimizer(
        duckdb_resource=duckdb_resource,
        scenario_id="advanced_example_001",
        use_synthetic=False  # Real simulation mode
    )

    # Add custom retention objective
    def retention_objective(parameters: Dict[str, float]) -> float:
        """Custom objective to optimize employee retention."""
        # Calculate retention score based on compensation competitiveness
        merit_avg = np.mean([parameters[f"merit_rate_level_{i}"] for i in range(1, 6)])
        cola_rate = parameters["cola_rate"]

        # Higher compensation = better retention (lower objective value)
        retention_score = 1.0 - (merit_avg + cola_rate) / 0.15
        return max(0.0, retention_score)

    optimizer.add_objective(retention_objective, weight=0.15)

    # Add budget constraint
    def budget_constraint(parameters: Dict[str, float]) -> float:
        """Ensure total compensation increase doesn't exceed 5%."""
        total_increase = sum(parameters[f"merit_rate_level_{i}"] for i in range(1, 6)) / 5
        total_increase += parameters["cola_rate"]
        return 0.05 - total_increase  # Positive if constraint satisfied

    optimizer.add_constraint(budget_constraint)

    # Run optimization with extended settings
    result = optimizer.optimize(
        initial_parameters=get_realistic_parameters(),
        objectives={"cost": 0.3, "equity": 0.3, "targets": 0.25, "retention": 0.15},
        method="L-BFGS-B",  # Good for constrained problems
        max_evaluations=200,
        timeout_minutes=120,
        random_seed=42
    )

    return result
```

### Batch Optimization Example

```python
"""Run multiple optimization scenarios for comparison."""

def run_batch_optimization():
    scenarios = [
        {"name": "conservative", "objectives": {"cost": 0.7, "equity": 0.2, "targets": 0.1}},
        {"name": "balanced", "objectives": {"cost": 0.4, "equity": 0.3, "targets": 0.3}},
        {"name": "growth_focused", "objectives": {"cost": 0.2, "equity": 0.2, "targets": 0.6}}
    ]

    results = {}

    for scenario in scenarios:
        print(f"\n🔄 Running {scenario['name']} optimization...")

        optimizer = CompensationOptimizer(
            duckdb_resource=duckdb_resource,
            scenario_id=f"batch_{scenario['name']}_001",
            use_synthetic=True  # Fast mode for comparison
        )

        result = optimizer.optimize(
            initial_parameters=get_realistic_parameters(),
            objectives=scenario["objectives"],
            method="SLSQP",
            max_evaluations=75,
            timeout_minutes=20,
            random_seed=42
        )

        results[scenario["name"]] = result

        if isinstance(result, OptimizationResult):
            print(f"✅ {scenario['name']}: Converged in {result.runtime_seconds:.1f}s")
            print(f"   Quality: {result.solution_quality_score:.2f}, Risk: {result.risk_assessment}")
        else:
            print(f"❌ {scenario['name']}: Failed - {result.error_message}")

    # Compare results
    print("\n📊 Scenario Comparison:")
    for name, result in results.items():
        if isinstance(result, OptimizationResult) and result.converged:
            print(f"{name:12}: Quality {result.solution_quality_score:.2f}, "
                  f"Risk {result.risk_assessment:6}, "
                  f"Objective {result.objective_value:.4f}")

    return results
```

---

## Support and Resources

### Getting Help

**Documentation:**
- [User Guide](auto_optimize_user_guide.md)
- [Technical Integration Guide](auto_optimize_technical_integration_guide.md)
- [Troubleshooting Guide](auto_optimize_troubleshooting.md)
- [Best Practices Guide](auto_optimize_best_practices.md)

**Community:**
- GitHub Issues: Report bugs and feature requests
- Developer Forums: Ask questions and share examples
- Stack Overflow: Use tag `planwise-navigator`

**Professional Support:**
- Technical Support: For production deployments
- Consulting Services: For custom integrations
- Training: API workshops and best practices

### Reference Links

- **SciPy Documentation**: https://docs.scipy.org/doc/scipy/reference/optimize.html
- **Dagster Assets**: https://docs.dagster.io/concepts/assets
- **Pydantic Models**: https://pydantic-docs.helpmanual.io/
- **DuckDB Python API**: https://duckdb.org/docs/api/python

---

*This API documentation is part of the Fidelity PlanAlign Engine E012 Compensation Tuning System documentation suite.*
