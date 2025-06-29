# S047: Optimization Engine

**Epic:** E012 - Analyst-Driven Compensation Tuning System
**Story Points:** 21 (Extra Large)
**Status:** Planned
**Assignee:** TBD
**Start Date:** TBD
**Target Date:** TBD

## Business Value

Analysts can automatically find optimal parameter combinations for complex multi-constraint scenarios, leveraging advanced optimization algorithms to solve problems that would be impossible to tune manually.

**User Story:**
As an analyst, I want the system to automatically find optimal compensation parameters that simultaneously meet multiple budget constraints and equity targets, so I can achieve complex business objectives that would be impossible to solve through manual trial and error.

## Technical Approach

Integrate SciPy optimization with existing hazard rate framework. Respect job level constraints (Staff: 3.5% merit → VP: 5.5% merit) while optimizing for multiple objectives. Use event sourcing for scenario rollback and comparison. Build on existing comprehensive testing framework with advanced mathematical optimization algorithms.

## Implementation Details

### Existing Components to Extend

**Dagster Integration:**
- `orchestrator/assets.py` → Add optimization engine assets
- `orchestrator/simulator_pipeline.py` → Extend with advanced optimization operations
- Existing tuning loop from S045 → Enhance with mathematical optimization

**Database Models:**
- `fct_yearly_events.sql` → Add optimization metadata tracking
- `dim_hazard_table.sql` → Optimization-aware parameter resolution
- New: `fct_optimization_history.sql` → Track optimization runs and results

### New Optimization Module Structure

```python
# orchestrator/optimization/
├── __init__.py
├── constraint_solver.py      # SciPy-based optimization engine
├── objective_functions.py    # Cost/target optimization functions
├── scenario_generator.py     # Multi-scenario comparison
├── sensitivity_analysis.py   # Parameter sensitivity analysis
└── optimization_validators.py # Constraint validation and feasibility
```

### Core Optimization Engine

**Constraint Solver:**
```python
# orchestrator/optimization/constraint_solver.py
from scipy.optimize import minimize, differential_evolution
from typing import Dict, List, Tuple, Callable
import numpy as np

class CompensationOptimizer:
    """
    Advanced compensation parameter optimization engine using SciPy.
    """

    def __init__(self, duckdb_resource: DuckDBResource, scenario_id: str):
        self.duckdb_resource = duckdb_resource
        self.scenario_id = scenario_id
        self.constraints = []
        self.objectives = []

    def add_constraint(self, constraint_func: Callable, constraint_type: str = 'ineq'):
        """Add optimization constraint (equality or inequality)."""
        self.constraints.append({
            'type': constraint_type,
            'fun': constraint_func
        })

    def add_objective(self, objective_func: Callable, weight: float = 1.0):
        """Add weighted objective function."""
        self.objectives.append({
            'function': objective_func,
            'weight': weight
        })

    def optimize(
        self,
        initial_parameters: Dict[str, float],
        method: str = 'SLSQP',
        max_evaluations: int = 1000
    ) -> Dict[str, Any]:
        """
        Run multi-objective optimization with constraints.
        """
        # Convert parameter dict to optimization vector
        param_names = list(initial_parameters.keys())
        x0 = np.array([initial_parameters[name] for name in param_names])

        # Define bounds based on job level constraints
        bounds = self._get_parameter_bounds(param_names)

        # Combined objective function
        def combined_objective(x):
            params = dict(zip(param_names, x))
            return sum(
                obj['weight'] * obj['function'](params)
                for obj in self.objectives
            )

        # Run optimization
        result = minimize(
            combined_objective,
            x0,
            method=method,
            bounds=bounds,
            constraints=self.constraints,
            options={'maxiter': max_evaluations}
        )

        # Convert result back to parameter dict
        optimal_params = dict(zip(param_names, result.x))

        return {
            'optimal_parameters': optimal_params,
            'objective_value': result.fun,
            'converged': result.success,
            'iterations': result.nit,
            'method': method
        }
```

**Objective Functions:**
```python
# orchestrator/optimization/objective_functions.py
class ObjectiveFunctions:
    """
    Collection of optimization objective functions.
    """

    def __init__(self, duckdb_resource: DuckDBResource, scenario_id: str):
        self.duckdb_resource = duckdb_resource
        self.scenario_id = scenario_id

    def total_cost_objective(self, parameters: Dict[str, float]) -> float:
        """
        Minimize total compensation cost.
        """
        # Update parameters in database
        self._update_scenario_parameters(parameters)

        # Run simulation
        self._run_simulation()

        # Calculate total cost
        with self.duckdb_resource.get_connection() as conn:
            result = conn.execute("""
                SELECT SUM(total_compensation_cost) as total_cost
                FROM fct_workforce_snapshot
                WHERE scenario_id = ?
            """, [self.scenario_id]).fetchone()

        return result[0] if result[0] else float('inf')

    def equity_objective(self, parameters: Dict[str, float]) -> float:
        """
        Minimize pay equity variance across job levels and demographics.
        """
        self._update_scenario_parameters(parameters)
        self._run_simulation()

        with self.duckdb_resource.get_connection() as conn:
            result = conn.execute("""
                SELECT STDDEV(median_salary) as salary_variance
                FROM fct_workforce_snapshot
                WHERE scenario_id = ?
                GROUP BY job_level
            """, [self.scenario_id]).fetchone()

        return result[0] if result[0] else 0.0

    def target_achievement_objective(self, parameters: Dict[str, float]) -> float:
        """
        Minimize distance from defined targets.
        """
        self._update_scenario_parameters(parameters)
        self._run_simulation()

        # Calculate weighted distance from all targets
        total_variance = 0.0

        with self.duckdb_resource.get_connection() as conn:
            targets = conn.execute("""
                SELECT metric_name, target_value, tolerance_pct, priority
                FROM comp_targets
                WHERE scenario_id = ?
            """, [self.scenario_id]).fetchall()

            for target in targets:
                actual_value = self._get_actual_value(target[0])  # metric_name
                variance = abs(actual_value - target[1]) / target[1]  # target_value
                weight = 2.0 if target[3] == 'high' else 1.0  # priority
                total_variance += weight * variance

        return total_variance
```

### Advanced Optimization Algorithms

**Multi-Objective Optimization:**
```python
def pareto_optimization(
    self,
    objectives: List[Callable],
    constraints: List[Dict],
    population_size: int = 50,
    generations: int = 100
) -> List[Dict[str, Any]]:
    """
    Find Pareto-optimal solutions for multi-objective optimization.
    """
    from scipy.optimize import differential_evolution

    def combined_fitness(x):
        """Multi-objective fitness function."""
        params = dict(zip(self.param_names, x))

        # Evaluate all objectives
        objective_values = [obj(params) for obj in objectives]

        # Return weighted sum for now (could use NSGA-II for true Pareto)
        return sum(objective_values)

    # Run differential evolution for global optimization
    result = differential_evolution(
        combined_fitness,
        self.bounds,
        constraints=constraints,
        popsize=population_size,
        maxiter=generations,
        seed=42  # For reproducibility
    )

    return {
        'pareto_solutions': [dict(zip(self.param_names, result.x))],
        'objective_values': result.fun,
        'converged': result.success
    }
```

**Sensitivity Analysis:**
```python
# orchestrator/optimization/sensitivity_analysis.py
class SensitivityAnalyzer:
    """
    Analyze parameter sensitivity and confidence intervals.
    """

    def parameter_sensitivity(
        self,
        base_parameters: Dict[str, float],
        perturbation: float = 0.01
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate first-order sensitivity for each parameter.
        """
        sensitivities = {}
        base_objectives = self._evaluate_objectives(base_parameters)

        for param_name in base_parameters:
            # Perturb parameter up and down
            params_up = base_parameters.copy()
            params_down = base_parameters.copy()

            params_up[param_name] *= (1 + perturbation)
            params_down[param_name] *= (1 - perturbation)

            obj_up = self._evaluate_objectives(params_up)
            obj_down = self._evaluate_objectives(params_down)

            # Calculate sensitivity (derivative approximation)
            sensitivity = {}
            for obj_name in base_objectives:
                derivative = (obj_up[obj_name] - obj_down[obj_name]) / (
                    2 * perturbation * base_parameters[param_name]
                )
                sensitivity[obj_name] = derivative

            sensitivities[param_name] = sensitivity

        return sensitivities

    def confidence_intervals(
        self,
        optimal_parameters: Dict[str, float],
        confidence_level: float = 0.95
    ) -> Dict[str, Tuple[float, float]]:
        """
        Calculate confidence intervals for optimal parameters.
        """
        # Use bootstrap resampling or Hessian-based confidence intervals
        intervals = {}

        for param_name, value in optimal_parameters.items():
            # Simplified confidence interval (would use proper statistical methods)
            std_error = self._estimate_parameter_std_error(param_name, value)
            margin = 1.96 * std_error  # 95% confidence interval

            intervals[param_name] = (
                max(0, value - margin),  # Lower bound (non-negative)
                value + margin           # Upper bound
            )

        return intervals
```

### Dagster Asset Integration

**Optimization Assets:**
```python
@asset(group_name="optimization_engine")
def advanced_optimization_engine(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    optimization_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Advanced multi-objective optimization with constraints.
    """
    scenario_id = context.partition_key or "optimization_run"

    # Initialize optimizer
    optimizer = CompensationOptimizer(duckdb_resource, scenario_id)

    # Add objectives
    obj_funcs = ObjectiveFunctions(duckdb_resource, scenario_id)
    optimizer.add_objective(obj_funcs.total_cost_objective, weight=0.4)
    optimizer.add_objective(obj_funcs.equity_objective, weight=0.3)
    optimizer.add_objective(obj_funcs.target_achievement_objective, weight=0.3)

    # Add constraints
    optimizer.add_constraint(lambda x: constraint_job_level_merit_rates(x))
    optimizer.add_constraint(lambda x: constraint_total_budget(x))

    # Run optimization
    result = optimizer.optimize(
        initial_parameters=optimization_config['initial_parameters'],
        method=optimization_config.get('method', 'SLSQP'),
        max_evaluations=optimization_config.get('max_evaluations', 1000)
    )

    context.log.info(f"Optimization converged: {result['converged']}")
    context.log.info(f"Iterations: {result['iterations']}")

    return result

@asset(group_name="optimization_engine")
def sensitivity_analysis_results(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    advanced_optimization_engine: Dict[str, Any]
) -> pd.DataFrame:
    """
    Sensitivity analysis for optimal parameters.
    """
    analyzer = SensitivityAnalyzer(duckdb_resource)

    sensitivities = analyzer.parameter_sensitivity(
        advanced_optimization_engine['optimal_parameters']
    )

    confidence_intervals = analyzer.confidence_intervals(
        advanced_optimization_engine['optimal_parameters']
    )

    # Convert to DataFrame for easier analysis
    results = []
    for param_name, sensitivity in sensitivities.items():
        for obj_name, value in sensitivity.items():
            ci_lower, ci_upper = confidence_intervals[param_name]
            results.append({
                'parameter': param_name,
                'objective': obj_name,
                'sensitivity': value,
                'confidence_lower': ci_lower,
                'confidence_upper': ci_upper,
                'optimal_value': advanced_optimization_engine['optimal_parameters'][param_name]
            })

    return pd.DataFrame(results)
```

## Acceptance Criteria

### Functional Requirements
- [ ] Multi-objective optimization (cost, equity, promotion rates) with configurable weights
- [ ] Constraint validation using existing job level structure (Staff: 3.5% → VP: 5.5% merit)
- [ ] Sensitivity analysis and confidence intervals for optimal parameters
- [ ] Auto-tuning finds solutions within 50 function evaluations for standard scenarios
- [ ] Pareto frontier analysis for trade-off visualization
- [ ] Integration with existing event sourcing for audit trail

### Technical Requirements
- [ ] Performance scaling for 10,000+ employee datasets
- [ ] Integration with S045 tuning loop infrastructure
- [ ] SciPy optimization library integration
- [ ] Comprehensive validation of optimization results
- [ ] Graceful handling of infeasible optimization problems

### Advanced Features
- [ ] Multiple optimization algorithms (SLSQP, differential evolution, genetic algorithms)
- [ ] Robust optimization under uncertainty
- [ ] Scenario generation for stress testing
- [ ] What-if analysis with parameter perturbation

## Dependencies

**Prerequisite Stories:**
- S045 (Dagster Enhancement) - Requires basic tuning loop infrastructure

**Dependent Stories:**
- S048 (Governance) - Will need approval workflows for auto-optimization

**External Dependencies:**
- SciPy optimization library
- NumPy for numerical computations
- Optional: DEAP for genetic algorithms
- Optional: Platypus for multi-objective optimization

## Testing Strategy

### Unit Tests
```python
def test_optimization_convergence():
    """Test optimization algorithms converge to known solutions"""

def test_constraint_validation():
    """Test constraint functions work correctly"""

def test_sensitivity_analysis():
    """Test sensitivity calculations are accurate"""

def test_objective_function_accuracy():
    """Test objective functions calculate correctly"""
```

### Integration Tests
- End-to-end optimization workflow
- Performance testing with large datasets
- Convergence testing with various starting points
- Constraint feasibility testing

### Mathematical Validation
- Verify optimization results against known analytical solutions
- Cross-validation with alternative optimization libraries
- Statistical validation of confidence intervals

## Implementation Steps

1. **Create optimization module structure** and base classes
2. **Implement objective functions** with database integration
3. **Add constraint functions** respecting job level structure
4. **Integrate SciPy optimization algorithms**
5. **Create sensitivity analysis framework**
6. **Add Dagster asset integration**
7. **Implement advanced algorithms** (multi-objective, robust optimization)
8. **Performance optimization** and scaling
9. **Comprehensive testing** and validation
10. **Documentation** and usage examples

## Performance Considerations

**Optimization Strategies:**
- **Function Evaluation Caching:** Cache expensive simulation runs
- **Parallel Optimization:** Run multiple optimization starts in parallel
- **Incremental Simulation:** Only recalculate affected employees
- **Surrogate Models:** Use machine learning to approximate expensive functions

**Performance Targets:**
- Single objective evaluation <10 seconds
- Full optimization convergence <30 minutes
- Memory usage <2GB during optimization
- 95% convergence rate for feasible problems

## Mathematical Formulation

**Multi-Objective Problem:**
```
minimize: F(x) = [f₁(x), f₂(x), f₃(x)]
where:
  f₁(x) = total_compensation_cost(x)
  f₂(x) = equity_variance(x)
  f₃(x) = target_deviation(x)

subject to:
  g₁(x): 0.035 ≤ merit_rate_level₁ ≤ 0.055
  g₂(x): 0.040 ≤ merit_rate_level₂ ≤ 0.060
  g₃(x): total_budget(x) ≤ budget_limit
  g₄(x): promotion_rates(x) ≥ equity_minimums
```

## Success Metrics

**Functional Success:**
- 95% convergence rate for feasible optimization problems
- Solutions within 5% of global optimum for test cases
- Constraint satisfaction rate 100%

**Performance Success:**
- <30 minutes for full multi-objective optimization
- <10 seconds per objective function evaluation
- <2GB memory usage during optimization

**Quality Success:**
- Sensitivity analysis accuracy within 1% of analytical derivatives
- Confidence intervals contain true optimum 95% of the time
- Zero optimization failures due to numerical instability

---

**Story Dependencies:** S045 (Dagster Enhancement)
**Blocked By:** S045
**Blocking:** None
**Related Stories:** S046 (Analyst Interface), S048 (Governance)
